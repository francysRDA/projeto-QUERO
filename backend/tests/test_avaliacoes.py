"""Fatia 5 — AVA-01, AVA-02, RN-06…09, RN-12, INS-06 (visibilidade do resultado)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.relogio import agora
from app.domain.perfis import Perfil
from app.models import AuditoriaLog, Classificacao, Edital, Inscricao, Notificacao
from tests.fabricas import URL as URL_EDITAIS

from tests.fabricas import URL_INSC


def iid(cenario, nome):
    return cenario["cands"][nome][2]["id"]


def avaliar(client, cenario, avaliador: str, nome: str, acao="CONFIRMAR", **kw):
    corpo = {"acao": acao, "nota_merito": "8.00", "parecer": "DEFERIDO", "declaracao_sem_impedimento": True} | kw
    return client.put(f"{URL_INSC}/{iid(cenario, nome)}/avaliacao", headers=cenario[avaliador][1], json=corpo)


def fila(client, cenario, avaliador="a1"):
    return client.get(f"{URL_EDITAIS}/{cenario['edital']['id']}/avaliacoes", headers=cenario[avaliador][1])


# === AVA-01 / RN-06 / RN-07: fila ======================================================================
def test_AVA01_RN06_fila_so_com_homologadas(client, cenario):
    r = fila(client, cenario)
    assert r.status_code == 200
    assert {i["estudante_nome"] for i in r.json()["itens"]} == {"Ana", "Bia", "Caio"}  # sem Dani e Edu
    assert r.json()["pode_avaliar"] is True
    assert r.json()["progresso"]["homologadas"] == 3
    assert all(i["arquivos"] for i in r.json()["itens"])  # documentos vigentes para análise


def test_AVA01_RN07_avaliador_nao_designado_nao_ve_nem_avalia(client, criar_usuario, login, cenario):
    intruso = login(criar_usuario(Perfil.AVALIADOR))
    assert client.get(f"{URL_EDITAIS}/{cenario['edital']['id']}/avaliacoes", headers=intruso).status_code == 404
    corpo = {"acao": "RASCUNHO", "nota_merito": "5"}
    assert client.put(f"{URL_INSC}/{iid(cenario, 'ana')}/avaliacao", headers=intruso, json=corpo).status_code == 404


@pytest.mark.parametrize("perfil", [Perfil.ESTUDANTE, Perfil.PRO_REITOR])
def test_AVA01_somente_avaliador_lanca_nota(client, criar_usuario, login, cenario, perfil):
    h = login(criar_usuario(perfil))
    r = client.put(f"{URL_INSC}/{iid(cenario, 'ana')}/avaliacao", headers=h, json={"acao": "RASCUNHO"})
    assert r.status_code == 403


def test_AVA01_RN06_inscricao_nao_homologada_409(client, cenario):
    assert avaliar(client, cenario, "a1", "dani").status_code == 409


def test_AVA01_fora_da_fase_de_avaliacao_409(client, db, cenario):
    db.get(Edital, cenario["edital"]["id"]).status = "INSCRICOES_ENCERRADAS"
    db.flush()
    assert avaliar(client, cenario, "a1", "ana").status_code == 409


# === AVA-01 / §7.3: rascunho, confirmação, retificação ============================================================
def test_AVA01_rascunho_parcial_e_auditado(client, db, cenario):
    r = avaliar(client, cenario, "a1", "ana", acao="RASCUNHO", nota_merito="6.5", parecer=None,
                declaracao_sem_impedimento=False)
    assert r.status_code == 200
    assert r.json()["status"] == "RASCUNHO"
    assert db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "AVALIACAO_RASCUNHO"))
    item = next(i for i in fila(client, cenario).json()["itens"] if i["estudante_nome"] == "Ana")
    assert item["avaliacao"]["nota_merito"] == "6.50"


def test_AVA01_confirmacao_direta(client, cenario):
    r = avaliar(client, cenario, "a1", "ana")
    assert r.status_code == 200
    assert r.json()["status"] == "CONFIRMADA"


@pytest.mark.parametrize(
    "ajuste,trecho",
    [
        ({"declaracao_sem_impedimento": False}, "impedimento"),
        ({"parecer": "INDEFERIDO", "justificativa": None}, "justificativa"),
        ({"nota_merito": None}, "nota"),
        ({"parecer": None}, "parecer"),
    ],
)
def test_AVA01_RN07_RN08_confirmacao_incompleta_422(client, cenario, ajuste, trecho):
    r = avaliar(client, cenario, "a1", "ana", **ajuste)
    assert r.status_code == 422
    assert any(trecho in d.lower() for d in r.json()["detalhes"]), r.json()


@pytest.mark.parametrize("nota", ["10.01", "-0.5", "7.125"])
def test_AVA01_RN08_nota_fora_da_escala_422(client, cenario, nota):
    assert avaliar(client, cenario, "a1", "ana", nota_merito=nota).status_code == 422


def test_AVA01_RN08_indeferido_com_justificativa(client, cenario):
    r = avaliar(client, cenario, "a1", "ana", parecer="INDEFERIDO", nota_merito="3.00",
                justificativa="Plano de trabalho não atende aos objetivos do edital.")
    assert r.status_code == 200


def test_AVA01_rascunho_depois_de_confirmada_409(client, cenario):
    avaliar(client, cenario, "a1", "ana")
    assert avaliar(client, cenario, "a1", "ana", acao="RASCUNHO").status_code == 409


def test_AVA01_retificacao_exige_motivo_e_e_auditada(client, db, cenario):
    avaliar(client, cenario, "a1", "ana", nota_merito="7.00")
    assert avaliar(client, cenario, "a1", "ana", acao="RETIFICAR", nota_merito="7.50").status_code == 422
    r = avaliar(client, cenario, "a1", "ana", acao="RETIFICAR", nota_merito="7.50",
                justificativa_retificacao="Erro de digitação na soma dos critérios.")
    assert r.status_code == 200
    assert r.json()["status"] == "RETIFICADA"
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "AVALIACAO_RETIFICAR"))
    assert (log.dados_antes["nota_merito"], log.dados_depois["nota_merito"]) == ("7.00", "7.50")


def test_AVA01_retificar_sem_confirmar_antes_409(client, cenario):
    avaliar(client, cenario, "a1", "ana", acao="RASCUNHO")
    r = avaliar(client, cenario, "a1", "ana", acao="RETIFICAR", justificativa_retificacao="Motivo suficiente.")
    assert r.status_code == 409


def test_AVA01_inscricao_assumida_some_da_fila_do_outro(client, cenario):
    avaliar(client, cenario, "a1", "ana", acao="RASCUNHO")
    assert "Ana" not in {i["estudante_nome"] for i in fila(client, cenario, "a2").json()["itens"]}
    assert avaliar(client, cenario, "a2", "ana").status_code == 409


# === RN-07 / UC-07 E1: impedimento ===============================================================================
def impedir(client, cenario, avaliador, nome):
    return client.post(f"{URL_INSC}/{iid(cenario, nome)}/impedimento", headers=cenario[avaliador][1],
                       json={"motivo": "Sou orientador(a) do candidato."})


def test_RN07_impedimento_redireciona_para_outro_membro(client, db, cenario):
    avaliar(client, cenario, "a1", "ana", acao="RASCUNHO")
    assert impedir(client, cenario, "a1", "ana").status_code == 204
    assert "Ana" not in {i["estudante_nome"] for i in fila(client, cenario, "a1").json()["itens"]}
    assert "Ana" in {i["estudante_nome"] for i in fila(client, cenario, "a2").json()["itens"]}
    assert avaliar(client, cenario, "a1", "ana").status_code == 409  # impedido não avalia
    assert avaliar(client, cenario, "a2", "ana").status_code == 200  # rascunho de a1 foi descartado
    assert db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "AVALIACAO_IMPEDIMENTO"))


def test_RN07_impedimento_apos_confirmar_409(client, cenario):
    avaliar(client, cenario, "a1", "ana")
    assert impedir(client, cenario, "a1", "ana").status_code == 409


def test_RN07_todos_impedidos_alerta_pro_reitor(client, db, cenario, pr):
    impedir(client, cenario, "a1", "ana")
    impedir(client, cenario, "a2", "ana")
    prog = client.get(f"{URL_EDITAIS}/{cenario['edital']['id']}/avaliacoes/progresso", headers=pr[1]).json()
    assert prog["sem_avaliador_disponivel"] == [cenario["cands"]["ana"][2]["protocolo"]]
    assert db.scalar(select(Notificacao).where(Notificacao.usuario_id == pr[0].id,
                                               Notificacao.tipo == "COMISSAO_SEM_AVALIADOR"))


def test_impedimento_motivo_obrigatorio_422(client, cenario):
    r = client.post(f"{URL_INSC}/{iid(cenario, 'ana')}/impedimento", headers=cenario["a1"][1], json={"motivo": "x"})
    assert r.status_code == 422


# === AVA-02: classificação e resultado preliminar =====================================================================
def avaliar_todos(client, cenario, notas: dict[str, str]):
    for nome, nota in notas.items():
        assert avaliar(client, cenario, "a1", nome, nota_merito=nota).status_code == 200


def publicar(client, cenario, headers):
    return client.post(f"{URL_EDITAIS}/{cenario['edital']['id']}/resultado-preliminar", headers=headers)


def test_AVA02_nao_publica_com_avaliacao_pendente(client, cenario):
    avaliar_todos(client, cenario, {"ana": "8.00", "bia": "7.00"})
    avaliar(client, cenario, "a1", "caio", acao="RASCUNHO")
    r = publicar(client, cenario, cenario["a1"][1])
    assert r.status_code == 409
    assert r.json()["detalhes"] == [f"Pendente: {cenario['cands']['caio'][2]['protocolo']}"]


def test_AVA02_publica_classifica_abre_recurso_e_notifica(client, db, cenario):
    # Ana e Bia empatam em 8,00: Bia tem CR 9,00 > Ana 8,00 (RN-09). Vagas = 2 (RN-12).
    avaliar_todos(client, cenario, {"ana": "8.00", "bia": "8.00", "caio": "9.50"})
    r = publicar(client, cenario, cenario["a2"][1])
    assert r.status_code == 200, r.text
    ed = r.json()
    assert ed["status"] == "EM_RECURSO"  # RESULTADO_PRELIMINAR -> EM_RECURSO automaticamente (RN-10)

    edital = db.get(Edital, ed["id"])
    assert abs(edital.data_fim_recurso - (agora(db) + timedelta(hours=48))) < timedelta(minutes=1)

    linhas = {c.inscricao_id: (c.posicao, c.situacao) for c in db.scalars(
        select(Classificacao).where(Classificacao.edital_id == ed["id"], Classificacao.fase == "PRELIMINAR"))}
    assert linhas == {
        iid(cenario, "caio"): (1, "CONTEMPLADO"),
        iid(cenario, "bia"): (2, "CONTEMPLADO"),
        iid(cenario, "ana"): (3, "SUPLENTE"),
    }
    acoes = list(db.scalars(select(AuditoriaLog.acao).where(AuditoriaLog.entidade == "edital",
                                                            AuditoriaLog.entidade_id == ed["id"])))
    assert acoes[-2:] == ["EDITAL_PUBLICAR_PRELIMINAR", "EDITAL_ABRIR_RECURSO"]
    notificados = set(db.scalars(select(Notificacao.usuario_id).where(Notificacao.tipo == "RESULTADO_PRELIMINAR")))
    esperados = {cenario["cands"][n][0].id for n in ("ana", "bia", "caio", "dani")}  # desistente não
    assert notificados == esperados


def test_AVA02_indeferido_no_merito_nao_e_classificado(client, db, cenario):
    avaliar_todos(client, cenario, {"ana": "8.00", "bia": "7.00"})
    avaliar(client, cenario, "a1", "caio", parecer="INDEFERIDO", nota_merito="9.90",
            justificativa="Documentação de mérito insuficiente.")
    publicar(client, cenario, cenario["a1"][1])
    c = db.scalar(select(Classificacao).where(Classificacao.inscricao_id == iid(cenario, "caio")))
    assert (c.posicao, c.situacao) == (None, "NAO_CLASSIFICADO")


def test_AVA02_publicar_duas_vezes_409(client, cenario, pr):
    avaliar_todos(client, cenario, {"ana": "8", "bia": "7", "caio": "6"})
    assert publicar(client, cenario, pr[1]).status_code == 200
    assert publicar(client, cenario, pr[1]).status_code == 409


def test_AVA02_permissoes_de_publicacao(client, criar_usuario, login, cenario):
    avaliar_todos(client, cenario, {"ana": "8", "bia": "7", "caio": "6"})
    assert publicar(client, cenario, login(criar_usuario(Perfil.AVALIADOR))).status_code == 404
    assert publicar(client, cenario, cenario["cands"]["ana"][1]).status_code == 403


def test_AVA02_desistencia_durante_a_avaliacao_sai_da_classificacao(client, db, cenario):
    avaliar_todos(client, cenario, {"ana": "8", "bia": "7"})
    client.post(f"{URL_INSC}/{iid(cenario, 'caio')}/desistir", headers=cenario["cands"]["caio"][1])
    assert publicar(client, cenario, cenario["a1"][1]).status_code == 200
    assert db.scalar(select(Classificacao).where(Classificacao.inscricao_id == iid(cenario, "caio"))) is None


# === INS-06: visibilidade do resultado ============================================================================
def test_INS06_resultado_invisivel_antes_da_publicacao(client, cenario):
    avaliar_todos(client, cenario, {"ana": "8", "bia": "7", "caio": "6"})
    h = cenario["cands"]["ana"][1]
    assert client.get(f"{URL_INSC}/me", headers=h).json()[0]["resultado"] is None
    r = client.get(f"{URL_EDITAIS}/{cenario['edital']['id']}/classificacao", headers=h)
    assert r.status_code == 404


def test_INS06_previa_para_comissao_e_pro_reitor(client, cenario, pr):
    avaliar_todos(client, cenario, {"ana": "8", "bia": "9"})
    for h in (pr[1], cenario["a2"][1]):
        r = client.get(f"{URL_EDITAIS}/{cenario['edital']['id']}/classificacao", headers=h)
        assert r.status_code == 200
        assert r.json()["fase"] == "PREVIA" and r.json()["publicada"] is False
        assert [i["estudante_nome"] for i in r.json()["itens"]] == ["Bia", "Ana"]  # Caio ainda sem avaliação


def test_INS06_resultado_visivel_apos_publicacao(client, cenario):
    avaliar_todos(client, cenario, {"ana": "8.00", "bia": "8.00", "caio": "9.50"})
    publicar(client, cenario, cenario["a1"][1])
    h = cenario["cands"]["ana"][1]
    res = client.get(f"{URL_INSC}/me", headers=h).json()[0]["resultado"]
    assert res == {"fase": "PRELIMINAR", "nota": "8.00", "parecer": "DEFERIDO", "justificativa": None,
                   "posicao": 3, "situacao": "SUPLENTE", "total_vagas": 2}
    lista = client.get(f"{URL_EDITAIS}/{cenario['edital']['id']}/classificacao", headers=h).json()
    assert lista["fase"] == "PRELIMINAR" and lista["publicada"] is True
    assert [(i["posicao"], i["estudante_nome"]) for i in lista["itens"]] == [(1, "Caio"), (2, "Bia"), (3, "Ana")]


def test_INS06_indeferida_na_homologacao_nao_tem_resultado_de_merito(client, cenario):
    avaliar_todos(client, cenario, {"ana": "8", "bia": "7", "caio": "6"})
    publicar(client, cenario, cenario["a1"][1])
    assert client.get(f"{URL_INSC}/me", headers=cenario["cands"]["dani"][1]).json()[0]["resultado"] is None


def test_cenario_sanidade(db, cenario):
    """Garante que o cenário montado é o esperado pelos demais testes."""
    status = {n: db.get(Inscricao, iid(cenario, n)).status for n in cenario["cands"]}
    assert status == {"ana": "HOMOLOGADA", "bia": "HOMOLOGADA", "caio": "HOMOLOGADA",
                      "dani": "INDEFERIDA", "edu": "DESISTENTE"}
