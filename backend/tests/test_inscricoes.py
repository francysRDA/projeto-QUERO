"""Fatia 3 — INS-02, INS-04, INS-05, INS-06, INS-07, RN-01, RN-03, RN-04, RN-15 e armazenamento (§9.2)."""

import hashlib
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.domain.perfis import Perfil
from app.models import Arquivo, AuditoriaLog, ComissaoEdital, Edital, Inscricao, Notificacao, Tarefa
from app.storage.disco import ChaveInvalida
from app.worker.jobs import limpar_orfaos
from tests.fabricas import (
    MB,
    URL as URL_EDITAIS,
    arquivos_form,
    arquivos_no_disco,
    avancar_relogio,
    docs_ids,
    inscrever,
    payload,
    pdf,
)

# === INS-02 / INS-03 / RN-04: submissão ==================================================================
def test_INS02_inscricao_completa(client, db, edital, estudante, armazenamento):
    conteudo = pdf(marca=b"hist")
    h, c, _ = docs_ids(edital)
    r = inscrever(client, edital, estudante[1], (h, conteudo, "Histórico 2026.pdf"), (c, pdf(), "carta.pdf"))
    assert r.status_code == 201, r.text
    insc = r.json()
    assert insc["status"] == "HOMOLOGADA"
    assert insc["protocolo"].startswith("QUERO-") and insc["protocolo"].endswith(f"-{insc['id']:06d}")
    assert {a["documento_exigido_id"] for a in insc["arquivos"]} == {h, c}

    hist = next(a for a in insc["arquivos"] if a["documento_exigido_id"] == h)
    assert hist["sha256"] == hashlib.sha256(conteudo).hexdigest()
    assert hist["tamanho_bytes"] == len(conteudo)
    assert hist["nome_original"] == "Histórico 2026.pdf"
    assert hist["versao"] == 1

    # Arquivos realmente gravados no disco, com o conteúdo enviado.
    arq = db.get(Arquivo, hist["id"])
    assert b"".join(armazenamento.get(arq.chave)) == conteudo
    assert arq.chave.startswith(f"editais/{edital['id']}/inscricoes/{insc['id']}/")

    # Auditoria + notificação + e-mail enfileirado (INS-04).
    assert db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "INSCRICAO_SUBMETER",
                                                AuditoriaLog.entidade_id == insc["id"]))
    notif = db.scalar(select(Notificacao).where(Notificacao.usuario_id == estudante[0].id))
    assert insc["protocolo"] in notif.titulo
    assert db.scalar(select(Tarefa).where(Tarefa.payload["notificacao_id"].as_integer() == notif.id))


def test_INS02_documento_opcional_pode_ser_enviado(client, edital, estudante):
    h, c, o = docs_ids(edital)
    r = inscrever(client, edital, estudante[1], (h, pdf(), "a.pdf"), (c, pdf(), "b.pdf"), (o, pdf(), "c.pdf"))
    assert r.status_code == 201
    assert len(r.json()["arquivos"]) == 3


@pytest.mark.parametrize(
    "conteudo,nome,content_type,trecho",
    [
        (b"MZ\x90\x00executavel" * 50, "virus.pdf", "application/pdf", "não é um PDF"),
        (pdf(), "documento.docx", "application/pdf", "apenas arquivos .pdf"),
        (pdf(), "doc.pdf", "image/png", "tipo de arquivo"),
        (b"", "vazio.pdf", "application/pdf", "vazio"),
        (pdf(10 * MB + 1), "grande.pdf", "application/pdf", "10 MB"),
    ],
    ids=["magic-bytes", "extensao", "mime", "vazio", "acima-10MB"],
)
def test_INS02_RN04_arquivo_invalido_recusa_tudo(client, db, edital, estudante, armazenamento,
                                                  conteudo, nome, content_type, trecho):
    h, c, _ = docs_ids(edital)
    r = inscrever(client, edital, estudante[1], (h, pdf(), "ok.pdf"), (c, conteudo, nome, content_type))
    assert r.status_code == 422
    assert any(trecho in d for d in r.json()["detalhes"]), r.json()
    # Nada persiste: nem inscrição, nem arquivos (inclusive o válido) no disco.
    assert db.scalar(select(Inscricao).where(Inscricao.estudante_id == estudante[0].id)) is None
    assert arquivos_no_disco(armazenamento) == []


def test_INS02_arquivo_de_exatamente_10MB_e_aceito(client, edital, estudante):
    h, c, _ = docs_ids(edital)
    r = inscrever(client, edital, estudante[1], (h, pdf(10 * MB), "a.pdf"), (c, pdf(), "b.pdf"))
    assert r.status_code == 201


def test_INS02_documento_obrigatorio_ausente_422(client, edital, estudante):
    h, _, o = docs_ids(edital)
    r = inscrever(client, edital, estudante[1], (h, pdf(), "a.pdf"), (o, pdf(), "c.pdf"))
    assert r.status_code == 422
    assert any("Carta de motivação" in d for d in r.json()["detalhes"])


def test_INS02_sem_arquivos_422(client, edital, estudante):
    r = client.post(f"{URL_EDITAIS}/{edital['id']}/inscricoes", headers=estudante[1], data={"x": "1"})
    assert r.status_code == 422


def test_INS02_documento_de_outro_edital_422(client, edital, estudante, pr):
    outro = client.post(URL_EDITAIS, json=payload(), headers=pr[1]).json()
    h, c, _ = docs_ids(edital)
    r = inscrever(client, edital, estudante[1], (h, pdf(), "a.pdf"), (c, pdf(), "b.pdf"),
                  (outro["documentos"][0]["id"], pdf(), "x.pdf"))
    assert r.status_code == 422


def test_INS02_mesmo_documento_duas_vezes_422(client, edital, estudante):
    h, c, _ = docs_ids(edital)
    r = inscrever(client, edital, estudante[1], (h, pdf(), "a.pdf"), (h, pdf(), "a2.pdf"), (c, pdf(), "b.pdf"))
    assert r.status_code == 422


def test_INS02_RN01_segunda_inscricao_409(client, edital, estudante):
    assert inscrever(client, edital, estudante[1]).status_code == 201
    assert inscrever(client, edital, estudante[1]).status_code == 409


def test_INS02_RN01_desistente_nao_se_reinscreve(client, edital, estudante):
    """L-04 do plano: desistência é definitiva."""
    insc = inscrever(client, edital, estudante[1]).json()
    client.post(f"/api/v1/inscricoes/{insc['id']}/desistir", headers=estudante[1])
    assert inscrever(client, edital, estudante[1]).status_code == 409


def test_INS02_RN03_apos_fim_das_inscricoes_409(client, db, edital, estudante):
    avancar_relogio(db, 24 * 7 + 1)  # edital ainda ABERTO no banco (worker não rodou), mas o prazo passou
    assert db.get(Edital, edital["id"]).status == "ABERTO"
    r = inscrever(client, edital, estudante[1])
    assert r.status_code == 409
    assert "encerrado" in r.json()["mensagem"]


def test_INS02_RN03_antes_do_inicio_409(client, pr, estudante):
    inicio = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    ed = client.post(URL_EDITAIS, json=payload(data_inicio_inscricao=inicio), headers=pr[1]).json()
    client.post(f"{URL_EDITAIS}/{ed['id']}/publicar", headers=pr[1])
    r = inscrever(client, ed, estudante[1])
    assert r.status_code == 409
    assert "não começou" in r.json()["mensagem"]


def test_INS02_RN03_edital_cancelado_409(client, edital, estudante, pr):
    client.post(f"{URL_EDITAIS}/{edital['id']}/cancelar", headers=pr[1], json={"justificativa": "Cancelado para teste."})
    assert inscrever(client, edital, estudante[1]).status_code == 409


def test_INS02_edital_em_rascunho_404(client, pr, estudante):
    ed = client.post(URL_EDITAIS, json=payload(), headers=pr[1]).json()
    assert inscrever(client, ed, estudante[1]).status_code == 404


def test_INS02_RN07_membro_da_comissao_nao_se_inscreve(client, db, edital, estudante, pr):
    # Cenário L-05: inserido direto no banco porque a API só designa perfis AVALIADOR.
    db.add(ComissaoEdital(edital_id=edital["id"], avaliador_id=estudante[0].id, designado_por=pr[0].id))
    db.flush()
    assert inscrever(client, edital, estudante[1]).status_code == 409


@pytest.mark.parametrize("perfil", [Perfil.AVALIADOR, Perfil.PRO_REITOR])
def test_INS02_somente_estudante_se_inscreve(client, criar_usuario, login, edital, perfil):
    assert inscrever(client, edital, login(criar_usuario(perfil))).status_code == 403


def test_INS02_anonimo_401(client, edital):
    assert inscrever(client, edital, {}).status_code == 401


# === INS-04: comprovante ===================================================================================
def test_INS04_comprovante_pdf(client, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    r = client.get(f"/api/v1/inscricoes/{insc['id']}/comprovante", headers=estudante[1])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert insc["protocolo"] in r.headers["content-disposition"]
    assert "no-store" in r.headers["cache-control"]


def test_INS04_comprovante_de_outro_estudante_404(client, criar_usuario, login, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    outro = login(criar_usuario(Perfil.ESTUDANTE))
    assert client.get(f"/api/v1/inscricoes/{insc['id']}/comprovante", headers=outro).status_code == 404


# === INS-05: retificação ==================================================================================
def test_INS05_retificacao_versiona_e_preserva_protocolo(client, db, edital, estudante, armazenamento):
    h, c, _ = docs_ids(edital)
    insc = inscrever(client, edital, estudante[1]).json()
    original_hist = next(a for a in insc["arquivos"] if a["documento_exigido_id"] == h)
    avancar_relogio(db, 24)

    novo = pdf(marca=b"historico-corrigido")
    r = client.put(f"/api/v1/inscricoes/{insc['id']}/retificar", headers=estudante[1],
                   files=arquivos_form((h, novo, "historico-v2.pdf")))
    assert r.status_code == 200, r.text
    ret = r.json()

    assert ret["protocolo"] == insc["protocolo"]
    assert ret["data_submissao_original"] == insc["data_submissao_original"]  # RN-09
    assert ret["data_ultima_retificacao"] is not None
    hist = sorted((a for a in ret["arquivos"] if a["documento_exigido_id"] == h), key=lambda a: a["versao"])
    assert [(a["versao"], a["ativo"]) for a in hist] == [(1, False), (2, True)]
    assert hist[1]["sha256"] == hashlib.sha256(novo).hexdigest()
    # Histórico mantido: a versão 1 continua no disco (RN-04).
    assert b"".join(armazenamento.get(db.get(Arquivo, original_hist["id"]).chave)).startswith(b"%PDF-")

    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "INSCRICAO_RETIFICAR"))
    assert log.dados_antes["arquivos_ativos"] != log.dados_depois["arquivos_ativos"]


def test_INS05_retificacao_com_arquivo_invalido_mantem_versao_anterior(client, db, edital, estudante):
    h, _, _ = docs_ids(edital)
    insc = inscrever(client, edital, estudante[1]).json()
    r = client.put(f"/api/v1/inscricoes/{insc['id']}/retificar", headers=estudante[1],
                   files=arquivos_form((h, b"nao sou pdf", "x.pdf")))
    assert r.status_code == 422
    ativos = db.scalars(select(Arquivo).where(Arquivo.inscricao_id == insc["id"], Arquivo.ativo.is_(True))).all()
    assert len(ativos) == 2 and all(a.versao == 1 for a in ativos)


def test_INS05_retificacao_fora_do_prazo_409(client, db, edital, estudante):
    h, _, _ = docs_ids(edital)
    insc = inscrever(client, edital, estudante[1]).json()
    avancar_relogio(db, 24 * 7 + 1)
    r = client.put(f"/api/v1/inscricoes/{insc['id']}/retificar", headers=estudante[1],
                   files=arquivos_form((h, pdf(), "x.pdf")))
    assert r.status_code == 409


def test_INS05_retificacao_de_outro_estudante_404(client, criar_usuario, login, edital, estudante):
    h, _, _ = docs_ids(edital)
    insc = inscrever(client, edital, estudante[1]).json()
    outro = login(criar_usuario(Perfil.ESTUDANTE))
    r = client.put(f"/api/v1/inscricoes/{insc['id']}/retificar", headers=outro, files=arquivos_form((h, pdf(), "x.pdf")))
    assert r.status_code == 404


def test_INS05_retificacao_de_desistente_409(client, edital, estudante):
    h, _, _ = docs_ids(edital)
    insc = inscrever(client, edital, estudante[1]).json()
    client.post(f"/api/v1/inscricoes/{insc['id']}/desistir", headers=estudante[1])
    r = client.put(f"/api/v1/inscricoes/{insc['id']}/retificar", headers=estudante[1],
                   files=arquivos_form((h, pdf(), "x.pdf")))
    assert r.status_code == 409


def test_INS05_retificacao_sem_arquivos_422(client, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    r = client.put(f"/api/v1/inscricoes/{insc['id']}/retificar", headers=estudante[1], data={"x": "1"})
    assert r.status_code == 422


# === INS-06: acompanhamento e visibilidade ==================================================================
def test_INS06_estudante_ve_apenas_as_proprias(client, criar_usuario, login, edital, estudante):
    minha = inscrever(client, edital, estudante[1]).json()
    outro = login(criar_usuario(Perfil.ESTUDANTE))
    inscrever(client, edital, outro)
    r = client.get("/api/v1/inscricoes/me", headers=estudante[1])
    assert [i["id"] for i in r.json()] == [minha["id"]]
    assert r.json()[0]["pode_retificar"] is True
    assert r.json()[0]["pode_desistir"] is True


def test_INS06_detalhe_de_outro_estudante_404(client, criar_usuario, login, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    outro = login(criar_usuario(Perfil.ESTUDANTE))
    assert client.get(f"/api/v1/inscricoes/{insc['id']}", headers=outro).status_code == 404


def test_INS06_pro_reitor_e_avaliador_designado_veem_detalhe(client, criar_usuario, login, edital, estudante, pr):
    insc = inscrever(client, edital, estudante[1]).json()
    assert client.get(f"/api/v1/inscricoes/{insc['id']}", headers=pr[1]).status_code == 200

    designado, intruso = criar_usuario(Perfil.AVALIADOR), criar_usuario(Perfil.AVALIADOR)
    client.post(f"{URL_EDITAIS}/{edital['id']}/comissao", headers=pr[1], json={"avaliador_ids": [designado.id]})
    assert client.get(f"/api/v1/inscricoes/{insc['id']}", headers=login(designado)).status_code == 200
    assert client.get(f"/api/v1/inscricoes/{insc['id']}", headers=login(intruso)).status_code == 404


def test_INS06_minhas_exige_perfil_estudante(client, pr):
    assert client.get("/api/v1/inscricoes/me", headers=pr[1]).status_code == 403


# === INS-07: desistência ==================================================================================
def test_INS07_desistencia_auditada(client, db, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    r = client.post(f"/api/v1/inscricoes/{insc['id']}/desistir", headers=estudante[1])
    assert r.status_code == 200
    assert r.json()["status"] == "DESISTENTE"
    assert r.json()["pode_desistir"] is False and r.json()["pode_retificar"] is False
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "INSCRICAO_DESISTIR"))
    assert (log.dados_antes["status"], log.dados_depois["status"]) == ("HOMOLOGADA", "DESISTENTE")


def test_INS07_desistir_duas_vezes_409(client, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    client.post(f"/api/v1/inscricoes/{insc['id']}/desistir", headers=estudante[1])
    assert client.post(f"/api/v1/inscricoes/{insc['id']}/desistir", headers=estudante[1]).status_code == 409


@pytest.mark.parametrize("status_edital", ["RESULTADO_PRELIMINAR", "EM_RECURSO", "ENCERRADO", "CANCELADO"])
def test_INS07_desistencia_apos_resultado_preliminar_409(client, db, edital, estudante, status_edital):
    insc = inscrever(client, edital, estudante[1]).json()
    db.get(Edital, edital["id"]).status = status_edital
    db.flush()
    assert client.post(f"/api/v1/inscricoes/{insc['id']}/desistir", headers=estudante[1]).status_code == 409


def test_INS07_desistir_inscricao_alheia_404(client, criar_usuario, login, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    outro = login(criar_usuario(Perfil.ESTUDANTE))
    assert client.post(f"/api/v1/inscricoes/{insc['id']}/desistir", headers=outro).status_code == 404


# === RN-15: download protegido (IDOR) ===================================================================
def _primeiro_arquivo(insc):
    return insc["arquivos"][0]["id"]


def test_RN15_titular_baixa_em_streaming_e_download_e_auditado(client, db, edital, estudante):
    h, c, _ = docs_ids(edital)
    conteudo = pdf(300 * 1024, marca=b"meu historico")
    insc = inscrever(client, edital, estudante[1], (h, conteudo, "hist.pdf"), (c, pdf(), "c.pdf")).json()
    arq_id = next(a["id"] for a in insc["arquivos"] if a["documento_exigido_id"] == h)
    r = client.get(f"/api/v1/arquivos/{arq_id}/download", headers=estudante[1])
    assert r.status_code == 200
    assert r.content == conteudo
    assert r.headers["x-content-type-options"] == "nosniff"
    assert db.scalar(select(AuditoriaLog).where(AuditoriaLog.acao == "ARQUIVO_DOWNLOAD", AuditoriaLog.entidade_id == arq_id))


def test_RN15_IDOR_outro_estudante_nao_baixa(client, criar_usuario, login, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    outro = login(criar_usuario(Perfil.ESTUDANTE))
    assert client.get(f"/api/v1/arquivos/{_primeiro_arquivo(insc)}/download", headers=outro).status_code == 404


def test_RN15_anonimo_nao_baixa(client, edital, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    assert client.get(f"/api/v1/arquivos/{_primeiro_arquivo(insc)}/download").status_code == 401


def test_RN15_avaliador_so_baixa_se_designado(client, criar_usuario, login, edital, estudante, pr):
    insc = inscrever(client, edital, estudante[1]).json()
    designado, intruso = criar_usuario(Perfil.AVALIADOR), criar_usuario(Perfil.AVALIADOR)
    client.post(f"{URL_EDITAIS}/{edital['id']}/comissao", headers=pr[1], json={"avaliador_ids": [designado.id]})
    url = f"/api/v1/arquivos/{_primeiro_arquivo(insc)}/download"
    assert client.get(url, headers=login(designado)).status_code == 200
    assert client.get(url, headers=login(intruso)).status_code == 404
    assert client.get(url, headers=pr[1]).status_code == 200


def test_RN15_versao_substituida_so_para_titular_e_pr(client, criar_usuario, login, edital, estudante, pr):
    h, _, _ = docs_ids(edital)
    insc = inscrever(client, edital, estudante[1]).json()
    v1 = next(a["id"] for a in insc["arquivos"] if a["documento_exigido_id"] == h)
    client.put(f"/api/v1/inscricoes/{insc['id']}/retificar", headers=estudante[1], files=arquivos_form((h, pdf(), "v2.pdf")))
    av = criar_usuario(Perfil.AVALIADOR)
    client.post(f"{URL_EDITAIS}/{edital['id']}/comissao", headers=pr[1], json={"avaliador_ids": [av.id]})
    url = f"/api/v1/arquivos/{v1}/download"
    assert client.get(url, headers=estudante[1]).status_code == 200
    assert client.get(url, headers=pr[1]).status_code == 200
    assert client.get(url, headers=login(av)).status_code == 404


def test_RN15_arquivo_inexistente_404(client, estudante):
    assert client.get("/api/v1/arquivos/999999/download", headers=estudante[1]).status_code == 404


# === Armazenamento (§9.2) ==============================================================================
@pytest.mark.parametrize("chave", ["../fora.pdf", "/abs.pdf", "a/../../b.pdf", "a\\..\\b.pdf", "", "a//b.pdf"])
def test_storage_rejeita_path_traversal(armazenamento, chave):
    with pytest.raises(ChaveInvalida):
        armazenamento.put(chave, [b"%PDF-"])


def test_storage_gravacao_atomica(armazenamento):
    def blocos():
        yield b"%PDF-parcial"
        raise RuntimeError("conexão caiu")

    with pytest.raises(RuntimeError):
        armazenamento.put("x/arquivo.pdf", blocos())
    assert arquivos_no_disco(armazenamento) == []


def test_limpeza_de_orfaos(db, armazenamento, edital, client, estudante):
    insc = inscrever(client, edital, estudante[1]).json()
    registrada = db.get(Arquivo, _primeiro_arquivo(insc)).chave
    armazenamento.put("editais/1/inscricoes/999/orfao-velho.pdf", [b"%PDF-"])
    armazenamento.put("editais/1/inscricoes/999/orfao-novo.pdf", [b"%PDF-"])

    velho = (datetime.now() - timedelta(hours=25)).timestamp()
    for chave in (registrada, "editais/1/inscricoes/999/orfao-velho.pdf"):
        os.utime(armazenamento._caminho(chave), (velho, velho))

    assert limpar_orfaos(db, armazenamento) == 1
    restantes = arquivos_no_disco(armazenamento)
    assert registrada in restantes  # registrado no banco: mantém, mesmo antigo
    assert "editais/1/inscricoes/999/orfao-novo.pdf" in restantes  # recente: pode ser upload em andamento
    assert "editais/1/inscricoes/999/orfao-velho.pdf" not in restantes
