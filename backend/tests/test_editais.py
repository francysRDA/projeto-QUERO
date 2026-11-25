"""Fatia 2 — EDT-01…05, RN-07, RN-14 e transições temporais do worker (§7.5)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.domain.perfis import Perfil
from app.models import AuditoriaLog, ComissaoEdital, Edital, Inscricao, Notificacao, Tarefa
from app.worker import jobs
from tests.fabricas import SP, URL, payload



@pytest.fixture
def criar_edital(client, pr):
    def _criar(publicar: bool = False, **kw) -> dict:
        r = client.post(URL, json=payload(**kw), headers=pr[1])
        assert r.status_code == 201, r.text
        ed = r.json()
        if publicar:
            r = client.post(f"{URL}/{ed['id']}/publicar", headers=pr[1])
            assert r.status_code == 200, r.text
            ed = r.json()
        return ed

    return _criar


def avancar_relogio(db, horas: float) -> None:
    db.execute(text("UPDATE relogio_dev SET segundos = segundos + :s WHERE id = 1"), {"s": int(horas * 3600)})


def inscrever_direto(db, edital_id: int, estudante_id: int, status: str = "HOMOLOGADA") -> Inscricao:
    """Atalho de teste: a inscrição via API chega na Fatia 3."""
    i = Inscricao(protocolo=f"T-{edital_id}-{estudante_id}", edital_id=edital_id, estudante_id=estudante_id,
                  status=status)
    db.add(i)
    db.flush()
    return i


def acoes_auditadas(db, edital_id: int) -> list[str]:
    return list(db.scalars(
        select(AuditoriaLog.acao).where(AuditoriaLog.entidade == "edital", AuditoriaLog.entidade_id == edital_id)
        .order_by(AuditoriaLog.id)
    ))


# === EDT-01 ======================================================================================
def test_EDT01_cria_em_rascunho_com_auditoria(client, db, pr):
    r = client.post(URL, json=payload(), headers=pr[1])
    assert r.status_code == 201
    ed = r.json()
    assert ed["status"] == "RASCUNHO"
    assert [c["codigo_curso"] for c in ed["cursos"]] == ["ENG-CIV", "MAT"]
    assert len(ed["documentos"]) == 2
    assert acoes_auditadas(db, ed["id"]) == ["EDITAL_CRIAR"]


@pytest.mark.parametrize("perfil", [Perfil.ESTUDANTE, Perfil.AVALIADOR])
def test_EDT01_somente_pro_reitor_cria(client, criar_usuario, login, perfil):
    r = client.post(URL, json=payload(), headers=login(criar_usuario(perfil)))
    assert r.status_code == 403


def test_EDT01_anonimo_nao_cria(client):
    assert client.post(URL, json=payload()).status_code == 401


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("vagas", 0),
        ("cr_minimo", "10.50"),
        ("valor_bolsa", "-1"),
        ("carga_horaria_semanal", 0),
        ("categoria", "ESTAGIO_REMOTO"),
        ("titulo", "   "),
        ("data_fim_inscricao", "2027-01-10T10:00:00"),  # sem fuso horário
        ("criterios_desempate", ["IDADE_DESC"]),
    ],
)
def test_EDT01_entrada_invalida_422(client, pr, campo, valor):
    r = client.post(URL, json=payload(**{campo: valor}), headers=pr[1])
    assert r.status_code == 422


def test_EDT01_cursos_repetidos_422(client, pr):
    cursos = [{"codigo_curso": "MAT", "nome_curso": "Matemática"}] * 2
    assert client.post(URL, json=payload(cursos=cursos), headers=pr[1]).status_code == 422


def test_EDT01_rascunho_edita_livremente(client, db, pr, criar_edital):
    ed = criar_edital()
    r = client.put(f"{URL}/{ed['id']}", headers=pr[1],
                   json={"vagas": 5, "cursos": [{"codigo_curso": "FIS", "nome_curso": "Física"}]})
    assert r.status_code == 200
    assert r.json()["vagas"] == 5
    assert [c["codigo_curso"] for c in r.json()["cursos"]] == ["FIS"]
    assert acoes_auditadas(db, ed["id"])[-1] == "EDITAL_EDITAR"


def test_EDT01_publicado_so_edita_descricao_com_auditoria(client, db, pr, criar_edital):
    ed = criar_edital(publicar=True)
    r = client.put(f"{URL}/{ed['id']}", headers=pr[1], json={"descricao": "Texto revisado."})
    assert r.status_code == 200
    assert r.json()["descricao"] == "Texto revisado."

    log = db.scalars(select(AuditoriaLog).where(AuditoriaLog.acao == "EDITAL_EDITAR_PUBLICADO")).one()
    assert log.dados_antes["descricao"] != log.dados_depois["descricao"] == "Texto revisado."


@pytest.mark.parametrize("alteracao", [{"vagas": 10}, {"cr_minimo": "5.00"}, {"descricao": "x", "valor_bolsa": "1"}])
def test_EDT01_publicado_recusa_outros_campos_409(client, pr, criar_edital, alteracao):
    ed = criar_edital(publicar=True)
    r = client.put(f"{URL}/{ed['id']}", headers=pr[1], json=alteracao)
    assert r.status_code == 409


def test_EDT01_cancelado_nao_edita(client, pr, criar_edital):
    ed = criar_edital()
    client.post(f"{URL}/{ed['id']}/cancelar", headers=pr[1], json={"justificativa": "Erro de cadastro do edital."})
    assert client.put(f"{URL}/{ed['id']}", headers=pr[1], json={"descricao": "y"}).status_code == 409


def test_EDT01_edital_inexistente_404(client, pr):
    assert client.put(f"{URL}/999999", headers=pr[1], json={"vagas": 1}).status_code == 404


# === EDT-02 / EDT-03: publicação ====================================================================
def test_EDT02_publica_edital_valido(client, db, pr, criar_edital):
    ed = criar_edital(publicar=True)
    assert ed["status"] == "ABERTO"
    assert acoes_auditadas(db, ed["id"]) == ["EDITAL_CRIAR", "EDITAL_PUBLICAR"]


def _datas(**deltas_dias):
    base = datetime.now(SP)
    return {k: (base + timedelta(days=v)).isoformat() for k, v in deltas_dias.items()}


@pytest.mark.parametrize(
    "ajuste,trecho",
    [
        (_datas(data_inicio_inscricao=5, data_fim_inscricao=5), "fim das inscrições"),
        (_datas(data_inicio_inscricao=5, data_fim_inscricao=3), "fim das inscrições"),
        (_datas(data_fim_inscricao=7, data_inicio_avaliacao=6), "início da avaliação"),
        (_datas(data_inicio_avaliacao=8, data_resultado_preliminar=7), "resultado preliminar"),
        (_datas(data_resultado_preliminar=12, data_homologacao_final=11), "homologação final"),
        (_datas(data_inicio_inscricao=-5, data_fim_inscricao=-1), "já terminou"),
        ({"cursos": []}, "curso"),
        ({"documentos": []}, "documento"),
        ({"documentos": [{"nome": "Opcional", "obrigatorio": False}]}, "obrigatório"),
    ],
)
def test_EDT02_publicacao_recusada_422(client, pr, criar_edital, ajuste, trecho):
    ed = criar_edital(**ajuste)
    r = client.post(f"{URL}/{ed['id']}/publicar", headers=pr[1])
    assert r.status_code == 422
    assert any(trecho in d for d in r.json()["detalhes"]), r.json()


def test_EDT02_publicacao_lista_todos_os_problemas(client, pr, criar_edital):
    ed = criar_edital(cursos=[], documentos=[], **_datas(data_fim_inscricao=7, data_inicio_avaliacao=6))
    r = client.post(f"{URL}/{ed['id']}/publicar", headers=pr[1])
    assert len(r.json()["detalhes"]) == 3


def test_EDT03_publicar_duas_vezes_409(client, pr, criar_edital):
    ed = criar_edital(publicar=True)
    assert client.post(f"{URL}/{ed['id']}/publicar", headers=pr[1]).status_code == 409


def test_EDT03_iniciar_avaliacao_com_edital_aberto_409(client, pr, criar_edital):
    ed = criar_edital(publicar=True)
    assert client.post(f"{URL}/{ed['id']}/iniciar-avaliacao", headers=pr[1]).status_code == 409


def test_EDT03_worker_encerra_inscricoes_e_inicia_avaliacao(client, db, pr, criar_edital):
    ed = criar_edital(publicar=True)
    jobs.transicoes_temporais(db)
    assert db.get(Edital, ed["id"]).status == "ABERTO"  # ainda no prazo

    avancar_relogio(db, 24 * 7 + 1)  # passou do fim das inscrições, antes do início da avaliação
    jobs.transicoes_temporais(db)
    assert db.get(Edital, ed["id"]).status == "INSCRICOES_ENCERRADAS"

    avancar_relogio(db, 24)
    jobs.transicoes_temporais(db)
    edital = db.get(Edital, ed["id"])
    assert edital.status == "EM_AVALIACAO"
    logs = db.scalars(select(AuditoriaLog).where(AuditoriaLog.entidade_id == ed["id"],
                                                 AuditoriaLog.acao.like("EDITAL_%"))).all()
    automaticos = [lg.acao for lg in logs if lg.usuario_id is None]
    assert automaticos == ["EDITAL_ENCERRAR_INSCRICOES", "EDITAL_INICIAR_AVALIACAO"]


def test_EDT03_worker_atravessa_duas_etapas_no_mesmo_ciclo(client, db, pr, criar_edital):
    ed = criar_edital(publicar=True)
    avancar_relogio(db, 24 * 30)
    jobs.transicoes_temporais(db)
    assert db.get(Edital, ed["id"]).status == "EM_AVALIACAO"


def test_EDT03_pro_reitor_antecipa_inicio_da_avaliacao(client, db, pr, criar_edital):
    ed = criar_edital(publicar=True)
    avancar_relogio(db, 24 * 7 + 1)
    jobs.transicoes_temporais(db)
    r = client.post(f"{URL}/{ed['id']}/iniciar-avaliacao", headers=pr[1])
    assert r.status_code == 200
    assert r.json()["status"] == "EM_AVALIACAO"


def test_EDT03_rascunho_nao_e_afetado_pelo_worker(client, db, pr, criar_edital):
    ed = criar_edital()
    avancar_relogio(db, 24 * 30)
    jobs.transicoes_temporais(db)
    assert db.get(Edital, ed["id"]).status == "RASCUNHO"


# === Listagem e visibilidade (base de INS-01) =========================================================
def test_listagem_publica_mostra_apenas_abertos(client, criar_edital):
    aberto = criar_edital(publicar=True, titulo="Aberto A")
    criar_edital(titulo="Rascunho B")
    r = client.get(URL)
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()["itens"]]
    assert aberto["id"] in ids
    assert all(e["status"] == "ABERTO" for e in r.json()["itens"])


def test_rascunho_invisivel_para_nao_pro_reitor(client, criar_usuario, login, criar_edital):
    ed = criar_edital()
    assert client.get(f"{URL}/{ed['id']}").status_code == 404
    est = login(criar_usuario(Perfil.ESTUDANTE))
    assert client.get(f"{URL}/{ed['id']}", headers=est).status_code == 404
    r = client.get(URL, params={"status": "RASCUNHO"}, headers=est)
    assert r.json()["total"] == 0


def test_pro_reitor_lista_rascunhos(client, pr, criar_edital):
    ed = criar_edital()
    r = client.get(URL, params={"status": "RASCUNHO"}, headers=pr[1])
    assert ed["id"] in [e["id"] for e in r.json()["itens"]]


def test_filtros_da_listagem(client, criar_edital):
    criar_edital(publicar=True, titulo="Estágio TI", categoria="ESTAGIO", valor_bolsa="1500.00",
                 cursos=[{"codigo_curso": "CC", "nome_curso": "Ciência da Computação"}])
    criar_edital(publicar=True, titulo="Monitoria Física", categoria="MONITORIA", valor_bolsa="500.00",
                 cursos=[{"codigo_curso": "FIS", "nome_curso": "Física"}])

    def titulos(**params):
        return {e["titulo"] for e in client.get(URL, params=params).json()["itens"]}

    assert "Estágio TI" in titulos(categoria="ESTAGIO")
    assert "Monitoria Física" not in titulos(categoria="ESTAGIO")
    assert titulos(curso="FIS") >= {"Monitoria Física"} and "Estágio TI" not in titulos(curso="FIS")
    assert "Estágio TI" in titulos(curso="computação")
    assert "Monitoria Física" not in titulos(valor_min=1000)
    assert "Estágio TI" not in titulos(valor_max=1000)
    assert titulos(busca="Física") >= {"Monitoria Física"}


def test_token_invalido_na_listagem_publica_401(client):
    assert client.get(URL, headers={"Authorization": "Bearer lixo"}).status_code == 401


# === EDT-04: comissão =================================================================================
def test_EDT04_designa_comissao_notifica_e_audita(client, db, pr, criar_usuario, criar_edital):
    ed = criar_edital(publicar=True)
    a1, a2 = criar_usuario(Perfil.AVALIADOR), criar_usuario(Perfil.AVALIADOR)
    r = client.post(f"{URL}/{ed['id']}/comissao", headers=pr[1], json={"avaliador_ids": [a1.id, a2.id, a1.id]})
    assert r.status_code == 200
    assert {m["avaliador_id"] for m in r.json()} == {a1.id, a2.id}
    assert acoes_auditadas(db, ed["id"]).count("COMISSAO_DESIGNAR") == 2
    assert db.scalar(select(Notificacao).where(Notificacao.usuario_id == a1.id)).tipo == "COMISSAO_DESIGNADO"


def test_EDT04_designacao_idempotente(client, db, pr, criar_usuario, criar_edital):
    ed = criar_edital()
    a = criar_usuario(Perfil.AVALIADOR)
    for _ in range(2):
        assert client.post(f"{URL}/{ed['id']}/comissao", headers=pr[1], json={"avaliador_ids": [a.id]}).status_code == 200
    assert len(db.scalars(select(ComissaoEdital).where(ComissaoEdital.edital_id == ed["id"])).all()) == 1


@pytest.mark.parametrize("perfil", [Perfil.ESTUDANTE, Perfil.PRO_REITOR])
def test_EDT04_so_avaliadores_podem_ser_designados_422(client, pr, criar_usuario, criar_edital, perfil):
    ed = criar_edital()
    u = criar_usuario(perfil)
    r = client.post(f"{URL}/{ed['id']}/comissao", headers=pr[1], json={"avaliador_ids": [u.id]})
    assert r.status_code == 422


def test_EDT04_usuario_inexistente_422(client, pr, criar_edital):
    ed = criar_edital()
    assert client.post(f"{URL}/{ed['id']}/comissao", headers=pr[1], json={"avaliador_ids": [999999]}).status_code == 422


def test_EDT04_RN07_candidato_do_edital_nao_integra_comissao_409(client, db, pr, criar_usuario, criar_edital):
    ed = criar_edital(publicar=True)
    # Cenário de L-05: usuário com perfil de avaliador que também está inscrito (ex.: pós-graduando).
    a = criar_usuario(Perfil.AVALIADOR)
    inscrever_direto(db, ed["id"], a.id)
    r = client.post(f"{URL}/{ed['id']}/comissao", headers=pr[1], json={"avaliador_ids": [a.id]})
    assert r.status_code == 409


def test_EDT04_RN07_avaliador_ve_apenas_editais_designados(client, pr, criar_usuario, login, criar_edital):
    ed1, ed2 = criar_edital(publicar=True), criar_edital(publicar=True)
    a = criar_usuario(Perfil.AVALIADOR)
    client.post(f"{URL}/{ed1['id']}/comissao", headers=pr[1], json={"avaliador_ids": [a.id]})
    r = client.get(f"{URL}/designados", headers=login(a))
    assert [e["id"] for e in r.json()] == [ed1["id"]]
    assert ed2["id"] not in [e["id"] for e in r.json()]


@pytest.mark.parametrize("perfil", [Perfil.ESTUDANTE, Perfil.AVALIADOR])
def test_EDT04_comissao_so_pro_reitor_gerencia(client, criar_usuario, login, criar_edital, perfil):
    ed = criar_edital()
    h = login(criar_usuario(perfil))
    assert client.get(f"{URL}/{ed['id']}/comissao", headers=h).status_code == 403
    assert client.post(f"{URL}/{ed['id']}/comissao", headers=h, json={"avaliador_ids": [1]}).status_code == 403


def test_EDT04_designados_exige_perfil_avaliador(client, criar_usuario, login):
    assert client.get(f"{URL}/designados", headers=login(criar_usuario(Perfil.ESTUDANTE))).status_code == 403


def test_EDT04_remove_membro_sem_avaliacoes(client, db, pr, criar_usuario, criar_edital):
    ed = criar_edital()
    a = criar_usuario(Perfil.AVALIADOR)
    client.post(f"{URL}/{ed['id']}/comissao", headers=pr[1], json={"avaliador_ids": [a.id]})
    assert client.delete(f"{URL}/{ed['id']}/comissao/{a.id}", headers=pr[1]).status_code == 204
    assert client.get(f"{URL}/{ed['id']}/comissao", headers=pr[1]).json() == []
    assert "COMISSAO_REMOVER" in acoes_auditadas(db, ed["id"])


def test_EDT04_nao_remove_membro_que_ja_avaliou_409(client, db, pr, criar_usuario, criar_edital):
    from app.models import Avaliacao

    ed = criar_edital(publicar=True)
    a, est = criar_usuario(Perfil.AVALIADOR), criar_usuario(Perfil.ESTUDANTE)
    client.post(f"{URL}/{ed['id']}/comissao", headers=pr[1], json={"avaliador_ids": [a.id]})
    insc = inscrever_direto(db, ed["id"], est.id)
    db.add(Avaliacao(inscricao_id=insc.id, avaliador_id=a.id))
    db.flush()
    assert client.delete(f"{URL}/{ed['id']}/comissao/{a.id}", headers=pr[1]).status_code == 409


def test_EDT04_comissao_de_edital_cancelado_409(client, pr, criar_usuario, criar_edital):
    ed = criar_edital()
    client.post(f"{URL}/{ed['id']}/cancelar", headers=pr[1], json={"justificativa": "Cancelado para teste."})
    a = criar_usuario(Perfil.AVALIADOR)
    assert client.post(f"{URL}/{ed['id']}/comissao", headers=pr[1], json={"avaliador_ids": [a.id]}).status_code == 409


# === EDT-05: cancelamento =============================================================================
def test_EDT05_cancela_notifica_inscritos_e_audita(client, db, pr, criar_usuario, criar_edital):
    ed = criar_edital(publicar=True)
    e1, e2, e3 = (criar_usuario(Perfil.ESTUDANTE) for _ in range(3))
    inscrever_direto(db, ed["id"], e1.id)
    inscrever_direto(db, ed["id"], e2.id, status="INDEFERIDA")
    inscrever_direto(db, ed["id"], e3.id, status="DESISTENTE")

    r = client.post(f"{URL}/{ed['id']}/cancelar", headers=pr[1],
                    json={"justificativa": "Corte orçamentário da Pró-Reitoria."})
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELADO"
    assert r.json()["justificativa_cancelamento"] == "Corte orçamentário da Pró-Reitoria."

    notificados = set(db.scalars(select(Notificacao.usuario_id).where(Notificacao.tipo == "EDITAL_CANCELADO")))
    assert notificados == {e1.id, e2.id}  # desistente não é notificado
    emails = db.scalars(select(Tarefa).where(Tarefa.tipo == "EMAIL")).all()
    assert len(emails) == 2
    assert "EDITAL_CANCELAR" in acoes_auditadas(db, ed["id"])


@pytest.mark.parametrize("justificativa", ["", "curta"])
def test_EDT05_justificativa_obrigatoria_422(client, pr, criar_edital, justificativa):
    ed = criar_edital(publicar=True)
    r = client.post(f"{URL}/{ed['id']}/cancelar", headers=pr[1], json={"justificativa": justificativa})
    assert r.status_code == 422


@pytest.mark.parametrize("status_final", ["ENCERRADO", "CANCELADO"])
def test_EDT05_nao_cancela_estado_terminal_409(client, db, pr, criar_edital, status_final):
    ed = criar_edital()
    db.get(Edital, ed["id"]).status = status_final
    db.flush()
    r = client.post(f"{URL}/{ed['id']}/cancelar", headers=pr[1], json={"justificativa": "Tentativa inválida."})
    assert r.status_code == 409


def test_EDT05_cancelamento_so_pro_reitor(client, criar_usuario, login, criar_edital):
    ed = criar_edital(publicar=True)
    h = login(criar_usuario(Perfil.AVALIADOR))
    assert client.post(f"{URL}/{ed['id']}/cancelar", headers=h,
                       json={"justificativa": "Sem permissão para isso."}).status_code == 403


# === TRV-01 (parcial): worker de e-mail ==================================================================
def _notificacao_pendente(db, usuario_id: int) -> Notificacao:
    from app.services.notificacoes import notificar

    n = notificar(db, usuario_id=usuario_id, tipo="TESTE", titulo="Olá", mensagem="Corpo")
    db.flush()
    return n


def test_TRV01_worker_envia_email(db, criar_usuario, monkeypatch):
    enviados = []
    monkeypatch.setattr(jobs, "enviar_email", lambda para, assunto, corpo: enviados.append((para, assunto)))
    u = criar_usuario()
    n = _notificacao_pendente(db, u.id)
    assert jobs.processar_emails(db) == 1
    assert enviados == [(u.email, "Olá")]
    assert n.email_status == "ENVIADO"


def test_TRV01_falha_smtp_e_reenviada_ate_o_limite(db, criar_usuario, monkeypatch):
    def falhar(*_):
        raise ConnectionRefusedError("SMTP fora do ar")

    monkeypatch.setattr(jobs, "enviar_email", falhar)
    u = criar_usuario()
    n = _notificacao_pendente(db, u.id)
    tarefa = db.scalar(select(Tarefa).where(Tarefa.payload["notificacao_id"].as_integer() == n.id))

    for tentativa in range(1, jobs.MAX_TENTATIVAS_EMAIL + 1):
        tarefa.executar_em = datetime.now(SP) - timedelta(seconds=1)  # simula o tempo de espera
        db.flush()
        jobs.processar_emails(db)
        assert tarefa.tentativas == tentativa
    assert tarefa.status == "FALHA"
    assert n.email_status == "FALHA"
    assert "SMTP fora do ar" in tarefa.ultimo_erro


# === Relógio de demonstração ============================================================================
def test_dev_avancar_relogio_dispara_transicoes(client, db, pr, criar_edital):
    ed = criar_edital(publicar=True)
    r = client.post("/api/v1/dev/relogio/avancar", headers=pr[1], json={"horas": 24 * 30})
    assert r.status_code == 200
    assert r.json()["deslocamento_segundos"] == 24 * 30 * 3600
    assert db.get(Edital, ed["id"]).status == "EM_AVALIACAO"


def test_dev_relogio_exige_pro_reitor(client, criar_usuario, login):
    h = login(criar_usuario(Perfil.ESTUDANTE))
    assert client.post("/api/v1/dev/relogio/avancar", headers=h, json={"horas": 1}).status_code == 403
