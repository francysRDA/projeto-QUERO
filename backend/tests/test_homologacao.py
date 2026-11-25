"""Fatia 4 — INS-03, INT-01, RN-02, RN-05: homologação formal, Sistema Acadêmico e reanálise."""

import time
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domain.elegibilidade import motivos_academicos
from app.domain.perfis import Perfil
from app.integrations.academico import (
    AcademicoIndisponivel,
    DadosAcademicos,
    ServicoAcademicoSimulado,
    consultar_com_retentativa,
)
from app.models import AuditoriaLog, Edital, Inscricao, Notificacao
from app.services.homologacao import MOTIVO_EXPIRADO, reprocessar_pendentes
from tests.fabricas import URL as URL_EDITAIS
from tests.test_inscricoes import arquivos_form, avancar_relogio, docs_ids, inscrever, pdf

D = Decimal


# === Regra pura (RN-02) ===============================================================================
def _motivos(**kw):
    base = dict(vinculo_ativo=True, codigo_curso="MAT", nome_curso="Matemática", cr=D("8.00"),
                cursos_autorizados={"MAT", "FIS"}, cr_minimo=D("7.00"))
    return motivos_academicos(**(base | kw))


def test_RN02_elegivel_sem_motivos():
    assert _motivos() == []


def test_RN02_cr_igual_ao_minimo_e_elegivel():
    assert _motivos(cr=D("7.00")) == []


@pytest.mark.parametrize(
    "ajuste,trecho",
    [
        ({"vinculo_ativo": False}, "Vínculo acadêmico inativo"),
        ({"codigo_curso": "DIR", "nome_curso": "Direito"}, "Curso não autorizado neste edital: Direito"),
        ({"cr": D("6.99")}, "CR 6.99 inferior ao mínimo exigido (7.00)"),
        ({"vinculo_ativo": None}, "não localizados"),
    ],
)
def test_RN02_cada_motivo(ajuste, trecho):
    motivos = _motivos(**ajuste)
    assert len(motivos) == 1 and trecho in motivos[0]


def test_RN05_todos_os_motivos_de_uma_vez():
    assert len(_motivos(vinculo_ativo=False, codigo_curso="DIR", cr=D("5"))) == 3


# === INT-01: retentativa e timeout ======================================================================
class _Instavel:
    def __init__(self, falhas: int, atraso: float = 0):
        self.falhas, self.atraso, self.chamadas = falhas, atraso, 0

    def consultar(self, matricula):
        self.chamadas += 1
        if self.atraso:
            time.sleep(self.atraso)
        if self.chamadas <= self.falhas:
            raise AcademicoIndisponivel("instável")
        return DadosAcademicos(matricula, True, "MAT", "Matemática", D("8"))


def test_INT01_recupera_na_terceira_tentativa():
    s = _Instavel(falhas=2)
    assert consultar_com_retentativa(s, "1", espera_s=0).cr == D("8")
    assert s.chamadas == 3


def test_INT01_desiste_apos_tres_tentativas():
    s = _Instavel(falhas=99)
    with pytest.raises(AcademicoIndisponivel):
        consultar_com_retentativa(s, "1", espera_s=0)
    assert s.chamadas == 3


def test_INT01_timeout_conta_como_falha():
    s = _Instavel(falhas=0, atraso=0.3)
    inicio = time.monotonic()
    with pytest.raises(AcademicoIndisponivel, match="Timeout"):
        consultar_com_retentativa(s, "1", tentativas=2, timeout_s=0.05, espera_s=0)
    assert time.monotonic() - inicio < 0.3 * 2  # não esperou cada chamada lenta terminar


# === Adapter simulado (CSV) =============================================================================
def test_simulado_le_csv_recarrega_e_simula_queda(tmp_path):
    csv = tmp_path / "academico.csv"
    csv.write_text("matricula;vinculo_ativo;codigo_curso;nome_curso;cr\n1;sim;MAT;Matemática;8,5\nlixo\n",
                   encoding="utf-8")
    s = ServicoAcademicoSimulado(csv, tmp_path / "flag")
    assert s.consultar("1") == DadosAcademicos("1", True, "MAT", "Matemática", D("8.5"))
    assert s.consultar("2") is None

    import os
    csv.write_text("matricula;vinculo_ativo;codigo_curso;nome_curso;cr\n1;nao;MAT;Matemática;8.5\n", encoding="utf-8")
    os.utime(csv, (time.time() + 5, time.time() + 5))  # garante mtime diferente
    assert s.consultar("1").vinculo_ativo is False

    s.definir_fora_do_ar(True)
    with pytest.raises(AcademicoIndisponivel):
        s.consultar("1")
    s.definir_fora_do_ar(False)
    assert s.consultar("1") is not None


def test_simulado_csv_inexistente_e_indisponibilidade(tmp_path):
    with pytest.raises(AcademicoIndisponivel):
        ServicoAcademicoSimulado(tmp_path / "nao-existe.csv", tmp_path / "flag").consultar("1")


def test_csv_de_demonstracao_e_valido():
    s = ServicoAcademicoSimulado("seed/academico.csv", "/caminho/inexistente/flag")
    assert s.consultar("2023001").nome_curso == "Matemática"
    assert s.consultar("2023006").vinculo_ativo is False


# === INS-03: homologação formal na submissão =================================================================
def test_INS03_elegivel_homologada_com_dados_congelados(client, edital, estudante):
    r = inscrever(client, edital, estudante[1])
    assert r.status_code == 201
    i = r.json()
    assert i["status"] == "HOMOLOGADA"
    assert (i["vinculo_ativo_congelado"], i["curso_congelado"], i["cr_congelado"]) == (True, "Matemática", "8.00")
    assert i["motivos_indeferimento"] is None


def test_INS03_inelegivel_indeferida_com_todos_os_motivos(client, criar_usuario, login, academico, edital):
    u = criar_usuario(Perfil.ESTUDANTE, matricula="X1")
    academico.cadastrar("X1", curso="DIR", nome_curso="Direito", cr="5.00", ativo=False)
    i = inscrever(client, edital, login(u)).json()
    assert i["status"] == "INDEFERIDA"
    assert len(i["motivos_indeferimento"]) == 3
    assert i["cr_congelado"] == "5.00"  # congelado mesmo quando indeferida (base para reanálise)


def test_INS03_matricula_nao_localizada(client, criar_usuario, login, edital):
    u = criar_usuario(Perfil.ESTUDANTE, matricula="NAO-EXISTE")
    i = inscrever(client, edital, login(u)).json()
    assert i["status"] == "INDEFERIDA"
    assert "não localizados" in i["motivos_indeferimento"][0]


def test_INS03_usuario_sem_matricula(client, criar_usuario, login, academico, edital):
    i = inscrever(client, edital, login(criar_usuario(Perfil.ESTUDANTE))).json()
    assert i["status"] == "INDEFERIDA"
    assert "não possui matrícula" in i["motivos_indeferimento"][0]
    assert academico.chamadas == 0


def test_INS03_INT01_academico_fora_do_ar_fica_pendente(client, db, academico, edital, estudante):
    academico.fora_do_ar = True
    r = inscrever(client, edital, estudante[1])
    assert r.status_code == 201  # a inscrição NÃO é perdida
    i = r.json()
    assert i["status"] == "PENDENTE_VALIDACAO_VINCULO"
    assert i["cr_congelado"] is None
    assert academico.chamadas == 3  # INT-01: 3 tentativas
    notif = db.scalar(select(Notificacao).where(Notificacao.usuario_id == estudante[0].id))
    assert "indisponível" in notif.mensagem


# === RN-02: dados congelados na retificação ====================================================================
def test_RN02_retificacao_nao_reconsulta_nem_muda_cr(client, academico, edital, estudante):
    h = docs_ids(edital)[0]
    i = inscrever(client, edital, estudante[1]).json()
    chamadas = academico.chamadas
    academico.cadastrar(estudante[0].matricula, cr="3.00")  # CR mudou no Sistema Acadêmico depois

    r = client.put(f"/api/v1/inscricoes/{i['id']}/retificar", headers=estudante[1],
                   files=arquivos_form((h, pdf(), "novo.pdf")))
    assert r.status_code == 200
    assert r.json()["status"] == "HOMOLOGADA"
    assert r.json()["cr_congelado"] == "8.00"
    assert academico.chamadas == chamadas


def test_RN02_indeferida_por_cr_continua_indeferida_apos_retificar(client, criar_usuario, login, academico, edital):
    u = criar_usuario(Perfil.ESTUDANTE, matricula="BAIXO")
    academico.cadastrar("BAIXO", cr="6.00")
    h = login(u)
    i = inscrever(client, edital, h).json()
    assert i["status"] == "INDEFERIDA"
    academico.cadastrar("BAIXO", cr="9.00")  # mesmo que o CR suba, vale o congelado
    r = client.put(f"/api/v1/inscricoes/{i['id']}/retificar", headers=h,
                   files=arquivos_form((docs_ids(edital)[0], pdf(), "n.pdf")))
    assert r.json()["status"] == "INDEFERIDA"
    assert any("CR 6.00" in m for m in r.json()["motivos_indeferimento"])


def test_retificacao_de_pendente_continua_pendente(client, academico, edital, estudante):
    academico.fora_do_ar = True
    i = inscrever(client, edital, estudante[1]).json()
    r = client.put(f"/api/v1/inscricoes/{i['id']}/retificar", headers=estudante[1],
                   files=arquivos_form((docs_ids(edital)[0], pdf(), "n.pdf")))
    assert r.status_code == 200
    assert r.json()["status"] == "PENDENTE_VALIDACAO_VINCULO"


# === INT-01: reprocessamento pelo worker =========================================================================
def _pendente(client, academico, edital, estudante) -> int:
    academico.fora_do_ar = True
    return inscrever(client, edital, estudante[1]).json()["id"]


def test_INT01_worker_homologa_quando_sistema_volta(client, db, academico, edital, estudante):
    iid = _pendente(client, academico, edital, estudante)
    academico.fora_do_ar = False
    assert reprocessar_pendentes(db, academico)["homologadas"] == 1
    insc = db.get(Inscricao, iid)
    assert insc.status == "HOMOLOGADA" and insc.cr_congelado == D("8.00")
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "INSCRICAO_REPROCESSAR_VINCULO"))
    assert log.usuario_id is None and log.dados_antes["status"] == "PENDENTE_VALIDACAO_VINCULO"
    assert db.scalar(select(Notificacao).where(Notificacao.tipo == "INSCRICAO_STATUS",
                                               Notificacao.usuario_id == estudante[0].id))


def test_INT01_worker_mantem_pendente_enquanto_fora_do_ar(client, db, academico, edital, estudante):
    iid = _pendente(client, academico, edital, estudante)
    assert reprocessar_pendentes(db, academico)["aguardando"] == 1
    assert db.get(Inscricao, iid).status == "PENDENTE_VALIDACAO_VINCULO"


def test_INT01_worker_indefere_inelegivel(client, db, academico, edital, estudante):
    iid = _pendente(client, academico, edital, estudante)
    academico.fora_do_ar = False
    academico.cadastrar(estudante[0].matricula, ativo=False)
    reprocessar_pendentes(db, academico)
    assert db.get(Inscricao, iid).status == "INDEFERIDA"
    assert db.get(Inscricao, iid).motivos_indeferimento == ["Vínculo acadêmico inativo."]


def test_INT01_pendente_expira_no_inicio_da_avaliacao(client, db, academico, edital, estudante):
    iid = _pendente(client, academico, edital, estudante)
    avancar_relogio(db, 24 * 8 + 1)  # passou de data_inicio_avaliacao, sistema ainda fora do ar
    reprocessar_pendentes(db, academico)
    insc = db.get(Inscricao, iid)
    assert insc.status == "INDEFERIDA"
    assert insc.motivos_indeferimento == [MOTIVO_EXPIRADO]


def test_INT01_pendente_de_edital_cancelado_e_ignorada(client, db, academico, edital, estudante, pr):
    iid = _pendente(client, academico, edital, estudante)
    client.post(f"{URL_EDITAIS}/{edital['id']}/cancelar", headers=pr[1], json={"justificativa": "Cancelado no teste."})
    academico.fora_do_ar = False
    reprocessar_pendentes(db, academico)
    assert db.get(Inscricao, iid).status == "PENDENTE_VALIDACAO_VINCULO"


def test_INT01_dev_religar_sistema_reprocessa(client, db, academico, edital, estudante, pr):
    iid = _pendente(client, academico, edital, estudante)
    r = client.put("/api/v1/dev/academico", headers=pr[1], json={"fora_do_ar": False})
    assert r.status_code == 200 and r.json() == {"fora_do_ar": False}
    assert db.get(Inscricao, iid).status == "HOMOLOGADA"


def test_INT01_dev_avancar_relogio_expira_pendentes(client, db, academico, edital, estudante, pr):
    iid = _pendente(client, academico, edital, estudante)
    client.post("/api/v1/dev/relogio/avancar", headers=pr[1], json={"horas": 24 * 9})
    assert db.get(Inscricao, iid).status == "INDEFERIDA"
    assert db.get(Edital, edital["id"]).status == "EM_AVALIACAO"


# === RN-05: reanálise pelo Pró-Reitor ==================================================================
@pytest.fixture
def indeferida(client, criar_usuario, login, academico, edital):
    u = criar_usuario(Perfil.ESTUDANTE, matricula="IND")
    academico.cadastrar("IND", cr="6.50")
    return inscrever(client, edital, login(u)).json()


def test_RN05_reanalise_homologa_com_auditoria(client, db, pr, indeferida):
    r = client.post(f"/api/v1/inscricoes/{indeferida['id']}/reanalisar", headers=pr[1],
                    json={"justificativa": "Histórico comprova CR 7,10 após revisão de nota."})
    assert r.status_code == 200
    assert r.json()["status"] == "HOMOLOGADA"
    insc = db.get(Inscricao, indeferida["id"])
    assert insc.reanalisada_por == pr[0].id
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "INSCRICAO_REANALISAR"))
    assert log.dados_antes["motivos_indeferimento"]  # motivos originais preservados na auditoria
    assert log.dados_depois["justificativa_reanalise"].startswith("Histórico")


def test_RN05_justificativa_obrigatoria(client, pr, indeferida):
    r = client.post(f"/api/v1/inscricoes/{indeferida['id']}/reanalisar", headers=pr[1], json={"justificativa": "ok"})
    assert r.status_code == 422


def test_RN05_reanalise_de_homologada_409(client, pr, edital, estudante):
    i = inscrever(client, edital, estudante[1]).json()
    r = client.post(f"/api/v1/inscricoes/{i['id']}/reanalisar", headers=pr[1],
                    json={"justificativa": "Tentativa sobre homologada."})
    assert r.status_code == 409


def test_RN05_prazo_termina_no_inicio_da_avaliacao_do_cronograma(client, db, pr, indeferida):
    avancar_relogio(db, 24 * 8 + 1)  # passou de data_inicio_avaliacao, edital ainda não mudou de estado
    r = client.post(f"/api/v1/inscricoes/{indeferida['id']}/reanalisar", headers=pr[1],
                    json={"justificativa": "Fora do prazo de reanálise."})
    assert r.status_code == 409


def test_RN05_prazo_termina_quando_edital_entra_em_avaliacao(client, db, pr, edital, indeferida):
    db.get(Edital, edital["id"]).status = "EM_AVALIACAO"  # antecipado pelo PR, antes da data
    db.flush()
    r = client.post(f"/api/v1/inscricoes/{indeferida['id']}/reanalisar", headers=pr[1],
                    json={"justificativa": "Edital já em avaliação."})
    assert r.status_code == 409


@pytest.mark.parametrize("perfil", [Perfil.ESTUDANTE, Perfil.AVALIADOR])
def test_RN05_somente_pro_reitor_reanalisa(client, criar_usuario, login, indeferida, perfil):
    r = client.post(f"/api/v1/inscricoes/{indeferida['id']}/reanalisar", headers=login(criar_usuario(perfil)),
                    json={"justificativa": "Sem permissão para reanalisar."})
    assert r.status_code == 403


# === UC-04: conferência pela Pró-Reitoria ==================================================================
def test_UC04_pro_reitor_lista_inscricoes_com_flag_de_reanalise(client, pr, edital, estudante, indeferida):
    inscrever(client, edital, estudante[1])
    r = client.get(f"{URL_EDITAIS}/{edital['id']}/inscricoes", headers=pr[1])
    assert r.status_code == 200
    por_status = {i["status"]: i for i in r.json()}
    assert por_status["INDEFERIDA"]["pode_reanalisar"] is True
    assert por_status["HOMOLOGADA"]["pode_reanalisar"] is False
    assert por_status["INDEFERIDA"]["estudante_matricula"] == "IND"

    filtrado = client.get(f"{URL_EDITAIS}/{edital['id']}/inscricoes", params={"status": "INDEFERIDA"}, headers=pr[1])
    assert [i["id"] for i in filtrado.json()] == [indeferida["id"]]


def test_UC04_lista_de_inscricoes_so_pro_reitor(client, edital, estudante):
    assert client.get(f"{URL_EDITAIS}/{edital['id']}/inscricoes", headers=estudante[1]).status_code == 403


# === UC-03 passo 7: estudante consulta os próprios dados acadêmicos =========================================
def test_academico_me(client, estudante):
    r = client.get("/api/v1/academico/me", headers=estudante[1])
    assert r.status_code == 200
    assert r.json()["nome_curso"] == "Matemática" and r.json()["cr"] == "8.00"


def test_academico_me_fora_do_ar_503(client, academico, estudante):
    academico.fora_do_ar = True
    r = client.get("/api/v1/academico/me", headers=estudante[1])
    assert r.status_code == 503
    assert r.json()["codigo"] == "SERVICO_INDISPONIVEL"


def test_academico_me_matricula_desconhecida_404(client, criar_usuario, login):
    u = criar_usuario(Perfil.ESTUDANTE, matricula="DESCONHECIDA")
    assert client.get("/api/v1/academico/me", headers=login(u)).status_code == 404


def test_academico_me_so_estudante(client, pr):
    assert client.get("/api/v1/academico/me", headers=pr[1]).status_code == 403
