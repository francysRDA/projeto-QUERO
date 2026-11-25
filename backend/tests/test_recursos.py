"""Fatia 6 — AVA-03, AVA-04, RN-10, RN-11, §7.4 e encerramento da fase de recurso (§7.1)."""

import io

import pytest
from sqlalchemy import select

from app.domain.perfis import Perfil
from app.models import Arquivo, AuditoriaLog, Avaliacao, Classificacao, Edital, Notificacao, Recurso
from app.worker.jobs import transicoes_temporais
from tests.fabricas import URL as URL_EDITAIS
from tests.fabricas import URL_INSC, avancar_relogio, pdf


def iid(c, nome):
    return c["cands"][nome][2]["id"]


def recorrer(client, c, nome, texto="A nota não considerou meu relatório de monitoria anterior.", anexo=None,
             headers=None):
    files = {"anexo": anexo} if anexo else None
    return client.post(f"{URL_INSC}/{iid(c, nome)}/recursos", headers=headers or c["cands"][nome][1],
                       data={"texto": texto}, files=files)


def julgar(client, c, recurso_id, avaliador="a2", **kw):
    corpo = {"decisao": "DEFERIDO", "justificativa": "Relatório anterior comprova experiência.",
             "nova_nota": "9.80"} | kw
    return client.post(f"/api/v1/recursos/{recurso_id}/julgar", headers=c[avaliador][1], json=corpo)


def posicoes(db, edital_id, fase):
    return {c.inscricao_id: (c.posicao, c.situacao) for c in db.scalars(
        select(Classificacao).where(Classificacao.edital_id == edital_id, Classificacao.fase == fase))}


# === AVA-03 / RN-10: interposição =======================================================================
def test_AVA03_interpoe_recurso_na_janela(client, db, publicado):
    me = client.get(f"{URL_INSC}/me", headers=publicado["cands"]["ana"][1]).json()[0]
    assert me["pode_recorrer"] is True and me["recurso"] is None

    r = recorrer(client, publicado, "ana")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "ABERTO"
    assert db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "RECURSO_INTERPOR"))
    assert db.scalar(select(Notificacao).where(Notificacao.tipo == "RECURSO_RECEBIDO"))

    me = client.get(f"{URL_INSC}/me", headers=publicado["cands"]["ana"][1]).json()[0]
    assert me["pode_recorrer"] is False and me["recurso"]["status"] == "ABERTO"


def test_AVA03_recurso_com_anexo_pdf_acessivel_a_comissao(client, db, publicado, armazenamento):
    r = recorrer(client, publicado, "ana", anexo=("relatorio.pdf", io.BytesIO(pdf(marca=b"relatorio")), "application/pdf"))
    assert r.status_code == 201
    anexo = r.json()["anexo"]
    assert anexo["nome_original"] == "relatorio.pdf"
    assert db.get(Arquivo, anexo["id"]).chave.endswith(".pdf")
    assert client.get(f"/api/v1/arquivos/{anexo['id']}/download", headers=publicado["a2"][1]).status_code == 200


def test_AVA03_anexo_invalido_nao_cria_recurso(client, db, publicado, armazenamento):
    r = recorrer(client, publicado, "ana", anexo=("x.pdf", io.BytesIO(b"MZ nao sou pdf"), "application/pdf"))
    assert r.status_code == 422
    assert db.scalar(select(Recurso).where(Recurso.inscricao_id == iid(publicado, "ana"))) is None


def test_AVA03_RN10_apenas_um_recurso(client, publicado):
    assert recorrer(client, publicado, "ana").status_code == 201
    assert recorrer(client, publicado, "ana").status_code == 409


@pytest.mark.parametrize("texto", ["", "   ", "x" * 5001])
def test_AVA03_RN10_texto_invalido_422(client, publicado, texto):
    assert recorrer(client, publicado, "ana", texto=texto).status_code == 422


def test_AVA03_texto_de_5000_caracteres_aceito(client, publicado):
    assert recorrer(client, publicado, "ana", texto="a" * 5000).status_code == 201


def test_AVA03_fora_da_janela_409_e_botao_oculto(client, db, publicado):
    avancar_relogio(db, 48.1)
    assert recorrer(client, publicado, "ana").status_code == 409
    me = client.get(f"{URL_INSC}/me", headers=publicado["cands"]["ana"][1]).json()[0]
    assert me["pode_recorrer"] is False


def test_AVA03_antes_da_publicacao_409(client, cenario):
    assert recorrer(client, cenario, "ana").status_code == 409


def test_AVA03_indeferido_na_homologacao_nao_recorre(client, publicado):
    """L-16: quem não participou do mérito usa a reanálise (RN-05), não o recurso."""
    assert recorrer(client, publicado, "dani").status_code == 409


def test_AVA03_recurso_por_terceiro(client, criar_usuario, login, publicado, pr):
    outro = login(criar_usuario(Perfil.ESTUDANTE))
    assert recorrer(client, publicado, "ana", headers=outro).status_code == 404
    assert recorrer(client, publicado, "ana", headers=pr[1]).status_code == 403


# === AVA-04 / RN-11: julgamento ============================================================================
def test_AVA04_RN11_autor_do_parecer_nao_julga_403(client, publicado):
    rid = recorrer(client, publicado, "ana").json()["id"]
    r = julgar(client, publicado, rid, avaliador="a1")
    assert r.status_code == 403
    assert "RN-11" in r.json()["mensagem"]


def test_AVA04_deferido_retifica_nota_e_recalcula_classificacao(client, db, publicado):
    ed = publicado["edital"]["id"]
    assert posicoes(db, ed, "PRELIMINAR")[iid(publicado, "ana")] == (3, "SUPLENTE")
    rid = recorrer(client, publicado, "ana").json()["id"]

    r = julgar(client, publicado, rid, nova_nota="9.80")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "DEFERIDO"

    av = db.scalar(select(Avaliacao).where(Avaliacao.inscricao_id == iid(publicado, "ana")))
    assert (av.status, str(av.nota_merito)) == ("RETIFICADA", "9.80")
    assert av.justificativa_retificacao.startswith("Recurso deferido")

    pos = posicoes(db, ed, "POS_RECURSO")
    assert pos[iid(publicado, "ana")] == (1, "CONTEMPLADO")
    assert pos[iid(publicado, "caio")] == (2, "CONTEMPLADO")
    assert pos[iid(publicado, "bia")] == (3, "SUPLENTE")
    # A preliminar não é alterada: o histórico fica preservado.
    assert posicoes(db, ed, "PRELIMINAR")[iid(publicado, "ana")] == (3, "SUPLENTE")

    acoes = set(db.scalars(select(AuditoriaLog.acao)))
    assert {"RECURSO_JULGAR", "AVALIACAO_RETIFICAR_RECURSO"} <= acoes
    assert db.scalar(select(Notificacao).where(Notificacao.tipo == "RECURSO_JULGADO"))

    res = client.get(f"{URL_INSC}/me", headers=publicado["cands"]["ana"][1]).json()[0]["resultado"]
    assert (res["fase"], res["posicao"], res["situacao"]) == ("POS_RECURSO", 1, "CONTEMPLADO")


def test_AVA04_indeferido_mantem_nota(client, db, publicado):
    rid = recorrer(client, publicado, "ana").json()["id"]
    r = julgar(client, publicado, rid, decisao="INDEFERIDO", nova_nota=None,
               justificativa="A nota atribuída está de acordo com o barema.")
    assert r.status_code == 200 and r.json()["status"] == "INDEFERIDO"
    av = db.scalar(select(Avaliacao).where(Avaliacao.inscricao_id == iid(publicado, "ana")))
    assert (av.status, str(av.nota_merito)) == ("CONFIRMADA", "8.00")
    assert posicoes(db, publicado["edital"]["id"], "POS_RECURSO")[iid(publicado, "ana")] == (3, "SUPLENTE")


def test_AVA04_recurso_contra_parecer_indeferido_pode_classificar(client, db, cenario):
    for nome, (nota, parecer) in {"ana": ("6.00", "INDEFERIDO"), "bia": ("8.00", "DEFERIDO"),
                                  "caio": ("7.00", "DEFERIDO")}.items():
        client.put(f"{URL_INSC}/{iid(cenario, nome)}/avaliacao", headers=cenario["a1"][1],
                   json={"acao": "CONFIRMAR", "nota_merito": nota, "parecer": parecer, "declaracao_sem_impedimento": True,
                         "justificativa": "Plano de trabalho fraco."})
    client.post(f"{URL_EDITAIS}/{cenario['edital']['id']}/resultado-preliminar", headers=cenario["a1"][1])
    rid = recorrer(client, cenario, "ana").json()["id"]
    julgar(client, cenario, rid, nova_nota="7.50", novo_parecer="DEFERIDO")
    assert posicoes(db, cenario["edital"]["id"], "POS_RECURSO")[iid(cenario, "ana")] == (2, "CONTEMPLADO")


@pytest.mark.parametrize("ajuste", [{"nova_nota": None}, {"justificativa": "curta"}, {"nova_nota": "11"}])
def test_AVA04_julgamento_invalido_422(client, publicado, ajuste):
    rid = recorrer(client, publicado, "ana").json()["id"]
    assert julgar(client, publicado, rid, **ajuste).status_code == 422


def test_AVA04_julgar_duas_vezes_409(client, publicado):
    rid = recorrer(client, publicado, "ana").json()["id"]
    assert julgar(client, publicado, rid).status_code == 200
    assert julgar(client, publicado, rid, decisao="INDEFERIDO").status_code == 409


def test_AVA04_permissoes(client, criar_usuario, login, publicado):
    rid = recorrer(client, publicado, "ana").json()["id"]
    intruso = login(criar_usuario(Perfil.AVALIADOR))
    corpo = {"decisao": "INDEFERIDO", "justificativa": "Sem permissão para julgar."}
    assert client.post(f"/api/v1/recursos/{rid}/julgar", headers=intruso, json=corpo).status_code == 404
    assert client.post(f"/api/v1/recursos/{rid}/julgar", headers=publicado["cands"]["bia"][1], json=corpo).status_code == 403


def test_AVA04_RN11_comissao_unica_exige_justificativa_reforcada_e_destaque(client, db, publicado, pr):
    ed = publicado["edital"]["id"]
    assert client.delete(f"{URL_EDITAIS}/{ed}/comissao/{publicado['a2'][0].id}", headers=pr[1]).status_code == 204
    rid = recorrer(client, publicado, "ana").json()["id"]

    assert julgar(client, publicado, rid, avaliador="a1").status_code == 422  # justificativa comum não basta
    reforcada = ("Após reanálise integral do relatório anexado ao recurso, verifica-se que a experiência prévia "
                 "em monitoria não foi pontuada conforme o item 4.2 do barema do edital.")
    r = julgar(client, publicado, rid, avaliador="a1", justificativa=reforcada)
    assert r.status_code == 200
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "RECURSO_JULGAR"))
    assert log.destaque is True and log.dados_depois["comissao_unica"] is True


def test_painel_de_recursos_indica_quem_pode_julgar(client, publicado, pr):
    recorrer(client, publicado, "ana")
    url = f"{URL_EDITAIS}/{publicado['edital']['id']}/recursos"
    autor = client.get(url, headers=publicado["a1"][1]).json()["recursos"][0]
    outro = client.get(url, headers=publicado["a2"][1]).json()["recursos"][0]
    assert (autor["pode_julgar"], outro["pode_julgar"]) == (False, True)
    assert "RN-11" in autor["motivo_bloqueio"]
    assert outro["autor_parecer_nome"] == "Avaliador Um"
    painel_pr = client.get(url, headers=pr[1]).json()
    assert painel_pr["janela_aberta"] is True and painel_pr["recursos"][0]["pode_julgar"] is False


def test_painel_de_recursos_permissoes(client, criar_usuario, login, publicado):
    url = f"{URL_EDITAIS}/{publicado['edital']['id']}/recursos"
    assert client.get(url, headers=login(criar_usuario(Perfil.AVALIADOR))).status_code == 404
    assert client.get(url, headers=publicado["cands"]["ana"][1]).status_code == 403


# === §7.1: EM_RECURSO -> EM_HOMOLOGACAO_FINAL ==============================================================
def test_sem_recursos_edital_avanca_ao_fim_da_janela(client, db, publicado, pr):
    ed = publicado["edital"]["id"]
    transicoes_temporais(db)
    assert db.get(Edital, ed).status == "EM_RECURSO"  # janela ainda aberta
    avancar_relogio(db, 48.1)
    transicoes_temporais(db)
    assert db.get(Edital, ed).status == "EM_HOMOLOGACAO_FINAL"
    assert posicoes(db, ed, "POS_RECURSO") == posicoes(db, ed, "PRELIMINAR")
    assert db.scalar(select(Notificacao).where(Notificacao.usuario_id == pr[0].id,
                                               Notificacao.tipo == "EDITAL_AGUARDA_HOMOLOGACAO"))


def test_recurso_pendente_segura_o_edital_ate_o_julgamento(client, db, publicado):
    ed = publicado["edital"]["id"]
    rid = recorrer(client, publicado, "ana").json()["id"]
    avancar_relogio(db, 48.1)
    transicoes_temporais(db)
    assert db.get(Edital, ed).status == "EM_RECURSO"  # aguarda julgamento
    julgar(client, publicado, rid)
    assert db.get(Edital, ed).status == "EM_HOMOLOGACAO_FINAL"  # avança no último julgamento


def test_julgamento_com_janela_aberta_nao_encerra_a_fase(client, db, publicado):
    rid = recorrer(client, publicado, "ana").json()["id"]
    julgar(client, publicado, rid)
    assert db.get(Edital, publicado["edital"]["id"]).status == "EM_RECURSO"
