"""Fatia 7 — HOM-01, HOM-02, RN-13, RN-14, TRV-01, TRV-03."""

import csv
import io
import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.domain.perfis import Perfil
from app.models import (
    Arquivo,
    AtaHomologacao,
    AuditoriaLog,
    Classificacao,
    Edital,
    Notificacao,
    Recurso,
)
from app.worker.jobs import transicoes_temporais
from tests.fabricas import URL as URL_EDITAIS
from tests.fabricas import URL_INSC, avancar_relogio


def iid(c, nome):
    return c["cands"][nome][2]["id"]


@pytest.fixture
def em_homologacao(client, db, cenario):
    """Preliminar: Caio 9,50 · Bia 8,00 (CR 9) · Ana 8,00 (CR 8). Ana recorre e a2 defere com 9,80.
    Fim da janela → EM_HOMOLOGACAO_FINAL. Resultado esperado: Ana 1º, Caio 2º (contemplados), Bia 3º (suplente)."""
    for nome, nota in {"ana": "8.00", "bia": "8.00", "caio": "9.50"}.items():
        client.put(f"{URL_INSC}/{iid(cenario, nome)}/avaliacao", headers=cenario["a1"][1],
                   json={"acao": "CONFIRMAR", "nota_merito": nota, "parecer": "DEFERIDO", "declaracao_sem_impedimento": True})
    client.post(f"{URL_EDITAIS}/{cenario['edital']['id']}/resultado-preliminar", headers=cenario["a1"][1])
    rid = client.post(f"{URL_INSC}/{iid(cenario, 'ana')}/recursos", headers=cenario["cands"]["ana"][1],
                      data={"texto": "Peço revisão da nota."}).json()["id"]
    client.post(f"/api/v1/recursos/{rid}/julgar", headers=cenario["a2"][1],
                json={"decisao": "DEFERIDO", "justificativa": "Experiência comprovada.", "nova_nota": "9.80"})
    avancar_relogio(db, 48.1)
    transicoes_temporais(db)
    assert db.get(Edital, cenario["edital"]["id"]).status == "EM_HOMOLOGACAO_FINAL"
    return cenario


def homologar(client, c, headers):
    return client.post(f"{URL_EDITAIS}/{c['edital']['id']}/homologar-final", headers=headers)


# === HOM-01 / HOM-02 ======================================================================================
def test_HOM01_HOM02_homologacao_gera_ata_listas_e_encerra(client, db, em_homologacao, pr, armazenamento):
    ed = em_homologacao["edital"]["id"]
    r = homologar(client, em_homologacao, pr[1])
    assert r.status_code == 200, r.text
    ata = r.json()
    assert ata["homologado_por"] == pr[0].nome

    edital = db.get(Edital, ed)
    assert edital.status == "ENCERRADO"
    final = {c.inscricao_id: (c.posicao, c.situacao) for c in db.scalars(
        select(Classificacao).where(Classificacao.edital_id == ed, Classificacao.fase == "FINAL"))}
    assert final == {
        iid(em_homologacao, "ana"): (1, "CONTEMPLADO"),
        iid(em_homologacao, "caio"): (2, "CONTEMPLADO"),
        iid(em_homologacao, "bia"): (3, "SUPLENTE"),
    }

    pdf, csv_arq = db.get(Arquivo, ata["arquivo_pdf_id"]), db.get(Arquivo, ata["arquivo_csv_id"])
    conteudo_pdf = b"".join(armazenamento.get(pdf.chave))
    assert conteudo_pdf.startswith(b"%PDF-")
    assert not os.access(armazenamento._caminho(pdf.chave), os.W_OK)  # somente leitura no disco
    assert csv_arq.content_type == "text/csv"

    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "EDITAL_HOMOLOGAR_FINAL"))
    assert log.usuario_id == pr[0].id
    assert log.dados_depois["ata_pdf_sha256"] == pdf.sha256
    assert len(log.dados_depois["resultado_final"]) == 4  # 3 classificados + 1 indeferida na homologação

    notificados = set(db.scalars(select(Notificacao.usuario_id).where(Notificacao.tipo == "RESULTADO_FINAL")))
    estudantes = {em_homologacao["cands"][n][0].id for n in ("ana", "bia", "caio", "dani")}
    avaliadores = {em_homologacao["a1"][0].id, em_homologacao["a2"][0].id}
    assert notificados == estudantes | avaliadores  # Edu (desistente) não


def test_HOM02_conteudo_do_csv(client, db, em_homologacao, pr, armazenamento):
    ata = homologar(client, em_homologacao, pr[1]).json()
    bruto = b"".join(armazenamento.get(db.get(Arquivo, ata["arquivo_csv_id"]).chave))
    assert bruto.startswith("﻿".encode())  # BOM para o Excel
    linhas = list(csv.DictReader(io.StringIO(bruto.decode("utf-8-sig")), delimiter=";"))
    resumo = [(linha["posicao"], linha["nome"], linha["nota"], linha["situacao"]) for linha in linhas]
    assert resumo == [
        ("1", "Ana", "9,80", "CONTEMPLADO"),
        ("2", "Caio", "9,50", "CONTEMPLADO"),
        ("3", "Bia", "8,00", "SUPLENTE"),
        ("", "Dani", "", "INDEFERIDA_HOMOLOGACAO"),
    ]


def test_HOM02_ata_publica_para_autenticados_com_auditoria(client, db, em_homologacao, pr):
    ed = em_homologacao["edital"]["id"]
    homologar(client, em_homologacao, pr[1])
    h_bia = em_homologacao["cands"]["bia"][1]
    atas = client.get(f"{URL_EDITAIS}/{ed}/atas", headers=h_bia).json()
    assert len(atas) == 1
    r = client.get(f"/api/v1/arquivos/{atas[0]['arquivo_pdf_id']}/download", headers=h_bia)
    assert r.status_code == 200 and r.content.startswith(b"%PDF-")
    r = client.get(f"/api/v1/arquivos/{atas[0]['arquivo_csv_id']}/download", headers=h_bia)
    assert r.headers["content-type"].startswith("text/csv")
    assert db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "ATA_DOWNLOAD"))
    assert client.get(f"/api/v1/arquivos/{atas[0]['arquivo_pdf_id']}/download").status_code == 401


def test_HOM02_resultado_final_visivel_ao_estudante(client, em_homologacao, pr):
    homologar(client, em_homologacao, pr[1])
    h = em_homologacao["cands"]["ana"][1]
    res = client.get(f"{URL_INSC}/me", headers=h).json()[0]["resultado"]
    assert (res["fase"], res["posicao"], res["situacao"]) == ("FINAL", 1, "CONTEMPLADO")
    lista = client.get(f"{URL_EDITAIS}/{em_homologacao['edital']['id']}/classificacao", headers=h).json()
    assert lista["fase"] == "FINAL"


def test_HOM01_so_homologa_em_homologacao_final_409(client, db, publicado, pr):
    assert homologar(client, publicado, pr[1]).status_code == 409  # ainda EM_RECURSO


def test_HOM01_homologar_duas_vezes_409(client, em_homologacao, pr):
    assert homologar(client, em_homologacao, pr[1]).status_code == 200
    assert homologar(client, em_homologacao, pr[1]).status_code == 409


def test_HOM01_bloqueia_com_recurso_pendente(client, db, em_homologacao, pr):
    # Estado defensivo: um recurso pendente não pode existir aqui, mas se existir a homologação é barrada.
    db.add(Recurso(inscricao_id=iid(em_homologacao, "bia"), texto="pendente", status="ABERTO"))
    db.flush()
    r = homologar(client, em_homologacao, pr[1])
    assert r.status_code == 409 and "pendente" in r.json()["mensagem"]


@pytest.mark.parametrize("quem", ["a1", "estudante"])
def test_HOM01_RN13_somente_pro_reitor_homologa(client, em_homologacao, quem):
    h = em_homologacao["a1"][1] if quem == "a1" else em_homologacao["cands"]["ana"][1]
    assert homologar(client, em_homologacao, h).status_code == 403


# === RN-13: imutabilidade =====================================================================================
def test_RN13_resultado_imutavel_apos_homologacao(client, db, em_homologacao, pr):
    ed = em_homologacao["edital"]["id"]
    ata = homologar(client, em_homologacao, pr[1]).json()

    # Pela API: nada mais muda.
    corpo = {"acao": "RETIFICAR", "nota_merito": "1.00", "parecer": "DEFERIDO", "declaracao_sem_impedimento": True,
             "justificativa_retificacao": "Tentativa após homologação."}
    assert client.put(f"{URL_INSC}/{iid(em_homologacao, 'bia')}/avaliacao", headers=em_homologacao["a1"][1],
                      json=corpo).status_code == 409
    assert client.put(f"{URL_EDITAIS}/{ed}", headers=pr[1], json={"descricao": "x"}).status_code == 409
    assert client.post(f"{URL_EDITAIS}/{ed}/cancelar", headers=pr[1],
                       json={"justificativa": "Tentativa após homologação."}).status_code == 409
    assert client.post(f"{URL_EDITAIS}/{ed}/devolver-ajustes", headers=pr[1],
                       json={"justificativa": "Tentativa após homologação."}).status_code == 409

    # No banco: triggers barram até alteração direta (defesa em profundidade).
    comandos = [
        ("UPDATE classificacoes SET posicao = 99 WHERE edital_id = :e AND fase = 'FINAL'", {"e": ed}),
        ("DELETE FROM classificacoes WHERE edital_id = :e AND fase = 'FINAL'", {"e": ed}),
        ("UPDATE atas_homologacao SET homologado_por = homologado_por WHERE id = :a", {"a": ata["id"]}),
        ("UPDATE arquivos SET nome_original = 'adulterado.pdf' WHERE id = :p", {"p": ata["arquivo_pdf_id"]}),
        ("DELETE FROM arquivos WHERE id = :p", {"p": ata["arquivo_csv_id"]}),
    ]
    for sql, params in comandos:
        sp = db.begin_nested()
        with pytest.raises(DBAPIError, match="imutável"):
            db.execute(text(sql), params)
        sp.rollback()


# === UC-09 A1: devolver para ajustes ===========================================================================
def test_devolver_para_ajustes_permite_retificar_e_republicar(client, db, em_homologacao, pr):
    ed = em_homologacao["edital"]["id"]
    r = client.post(f"{URL_EDITAIS}/{ed}/devolver-ajustes", headers=pr[1],
                    json={"justificativa": "Nota da Bia lançada com erro material."})
    assert r.status_code == 200 and r.json()["status"] == "EM_AVALIACAO"
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "EDITAL_DEVOLVER_AJUSTES"))
    assert log.dados_depois["justificativa_devolucao"].startswith("Nota da Bia")
    assert db.scalar(select(Notificacao).where(Notificacao.tipo == "EDITAL_DEVOLVIDO",
                                               Notificacao.usuario_id == em_homologacao["a1"][0].id))

    corpo = {"acao": "RETIFICAR", "nota_merito": "9.90", "parecer": "DEFERIDO", "declaracao_sem_impedimento": True,
             "justificativa_retificacao": "Correção solicitada pela Pró-Reitoria."}
    assert client.put(f"{URL_INSC}/{iid(em_homologacao, 'bia')}/avaliacao", headers=em_homologacao["a1"][1],
                      json=corpo).status_code == 200
    r = client.post(f"{URL_EDITAIS}/{ed}/resultado-preliminar", headers=pr[1])
    assert r.status_code == 200 and r.json()["status"] == "EM_RECURSO"
    pre = {c.inscricao_id: c.posicao for c in db.scalars(
        select(Classificacao).where(Classificacao.edital_id == ed, Classificacao.fase == "PRELIMINAR"))}
    assert pre[iid(em_homologacao, "bia")] == 1
    assert not db.scalars(select(Classificacao).where(Classificacao.edital_id == ed,
                                                      Classificacao.fase == "POS_RECURSO")).all()


def test_devolver_exige_justificativa_e_pro_reitor(client, em_homologacao, pr):
    url = f"{URL_EDITAIS}/{em_homologacao['edital']['id']}/devolver-ajustes"
    assert client.post(url, headers=pr[1], json={"justificativa": "curta"}).status_code == 422
    assert client.post(url, headers=em_homologacao["a1"][1],
                       json={"justificativa": "Avaliador não pode devolver."}).status_code == 403


def test_devolver_fora_da_homologacao_final_409(client, publicado, pr):
    url = f"{URL_EDITAIS}/{publicado['edital']['id']}/devolver-ajustes"
    assert client.post(url, headers=pr[1], json={"justificativa": "Ainda em recurso."}).status_code == 409


# === TRV-01: notificações do painel ============================================================================
def test_TRV01_notificacoes_do_proprio_usuario(client, db, publicado):
    h = publicado["cands"]["ana"][1]
    r = client.get("/api/v1/notificacoes", headers=h).json()
    tipos = [n["tipo"] for n in r["itens"]]
    assert "RESULTADO_PRELIMINAR" in tipos and "INSCRICAO_RECEBIDA" in tipos
    assert r["nao_lidas"] == len(r["itens"])
    usuario_ana = publicado["cands"]["ana"][0].id
    assert all(db.get(Notificacao, n["id"]).usuario_id == usuario_ana for n in r["itens"])

    primeira = r["itens"][0]["id"]
    assert client.post(f"/api/v1/notificacoes/{primeira}/lida", headers=h).status_code == 204
    assert client.get("/api/v1/notificacoes", headers=h).json()["nao_lidas"] == len(r["itens"]) - 1
    assert client.post("/api/v1/notificacoes/lidas", headers=h).status_code == 204
    assert client.get("/api/v1/notificacoes", headers=h).json()["nao_lidas"] == 0


def test_TRV01_nao_marca_notificacao_alheia(client, publicado):
    alheia = client.get("/api/v1/notificacoes", headers=publicado["cands"]["bia"][1]).json()["itens"][0]["id"]
    r = client.post(f"/api/v1/notificacoes/{alheia}/lida", headers=publicado["cands"]["ana"][1])
    assert r.status_code == 404


def test_TRV01_exige_autenticacao(client):
    assert client.get("/api/v1/notificacoes").status_code == 401


# === TRV-03: auditoria =====================================================================================
def test_TRV03_auditoria_por_edital(client, db, em_homologacao, pr, criar_edital):
    outro = criar_edital()  # registros de outro edital não podem aparecer
    ed = em_homologacao["edital"]["id"]
    r = client.get("/api/v1/auditoria", params={"edital_id": ed, "limite": 200}, headers=pr[1])
    assert r.status_code == 200
    acoes = {i["acao"] for i in r.json()["itens"]}
    assert {"EDITAL_CRIAR", "EDITAL_PUBLICAR", "INSCRICAO_SUBMETER", "AVALIACAO_CONFIRMAR", "RECURSO_INTERPOR",
            "RECURSO_JULGAR", "AVALIACAO_RETIFICAR_RECURSO", "EDITAL_ENCERRAR_RECURSO"} <= acoes
    assert not any(i["entidade"] == "edital" and i["entidade_id"] == outro["id"] for i in r.json()["itens"])
    sistema = next(i for i in r.json()["itens"] if i["acao"] == "EDITAL_ENCERRAR_RECURSO")
    assert sistema["usuario_nome"] == "Sistema"


def test_TRV03_auditoria_por_inscricao_e_filtros(client, em_homologacao, pr):
    alvo = iid(em_homologacao, "ana")
    r = client.get("/api/v1/auditoria", params={"inscricao_id": alvo, "limite": 200}, headers=pr[1]).json()
    acoes = {i["acao"] for i in r["itens"]}
    assert {"INSCRICAO_SUBMETER", "AVALIACAO_CONFIRMAR", "RECURSO_INTERPOR", "RECURSO_JULGAR"} <= acoes
    assert "EDITAL_CRIAR" not in acoes
    filtrado = client.get("/api/v1/auditoria", params={"inscricao_id": alvo, "acao": "RECURSO"}, headers=pr[1]).json()
    # Busca por trecho: inclui a retificação da avaliação decorrente do recurso.
    assert {i["acao"] for i in filtrado["itens"]} == {"RECURSO_INTERPOR", "RECURSO_JULGAR", "AVALIACAO_RETIFICAR_RECURSO"}


@pytest.mark.parametrize("perfil", [Perfil.ESTUDANTE, Perfil.AVALIADOR])
def test_TRV03_somente_pro_reitor_consulta(client, criar_usuario, login, perfil):
    assert client.get("/api/v1/auditoria", headers=login(criar_usuario(perfil))).status_code == 403


def test_TRV03_nao_existe_edicao_nem_exclusao(client, db, pr, em_homologacao):
    log_id = db.scalar(select(AuditoriaLog.id).limit(1))
    for metodo in ("put", "patch", "delete"):
        r = getattr(client, metodo)(f"/api/v1/auditoria/{log_id}", headers=pr[1])
        assert r.status_code in (404, 405)
    assert client.post("/api/v1/auditoria", headers=pr[1], json={}).status_code == 405


def test_ata_e_unica_e_registrada(client, db, em_homologacao, pr):
    homologar(client, em_homologacao, pr[1])
    assert len(db.scalars(select(AtaHomologacao).where(
        AtaHomologacao.edital_id == em_homologacao["edital"]["id"])).all()) == 1
