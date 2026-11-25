"""Homologação e divulgação do resultado final (UC-09: HOM-01, HOM-02; RN-13, RN-14)."""

import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflito
from app.core.relogio import agora
from app.domain.estados import MAQUINA_EDITAL, EventoEdital, StatusInscricao, StatusRecurso
from app.models import (
    Arquivo,
    AtaHomologacao,
    ComissaoEdital,
    Edital,
    Inscricao,
    Recurso,
    Usuario,
)
from app.reports.ata import DadosAta, LinhaResultado, gerar_csv, gerar_pdf
from app.services import avaliacoes as svc_avaliacoes
from app.services import editais as svc_editais
from app.services.notificacoes import notificar
from app.storage.base import ArmazenamentoArquivos

ORDEM_SITUACAO = {"CONTEMPLADO": 0, "SUPLENTE": 1, "NAO_CLASSIFICADO": 2, "INDEFERIDA_HOMOLOGACAO": 3}


def _exigir_estado(edital: Edital, evento: EventoEdital) -> None:
    if not MAQUINA_EDITAL.permitido(edital.status, evento):
        MAQUINA_EDITAL.proximo(edital.status, evento)  # 409 padronizado


def _recursos(db: Session, edital_id: int) -> dict[str, int]:
    linhas = db.execute(
        select(Recurso.status, func.count()).join(Inscricao, Inscricao.id == Recurso.inscricao_id)
        .where(Inscricao.edital_id == edital_id).group_by(Recurso.status)
    ).all()
    return {status: n for status, n in linhas}


def _linhas_resultado(db: Session, edital: Edital, posicoes) -> list[LinhaResultado]:
    inscricoes = {i.id: i for i in db.scalars(select(Inscricao).where(Inscricao.edital_id == edital.id))}
    usuarios = {u.id: u for u in db.scalars(select(Usuario).where(
        Usuario.id.in_([i.estudante_id for i in inscricoes.values()])))}
    linhas = []
    for p in posicoes:
        i = inscricoes[p.inscricao_id]
        u = usuarios[i.estudante_id]
        linhas.append(LinhaResultado(p.posicao, i.protocolo, u.nome, u.matricula, p.nota, i.cr_congelado, str(p.situacao)))
    for i in inscricoes.values():
        if i.status == StatusInscricao.INDEFERIDA:
            u = usuarios[i.estudante_id]
            linhas.append(LinhaResultado(None, i.protocolo, u.nome, u.matricula, None, i.cr_congelado,
                                         "INDEFERIDA_HOMOLOGACAO"))
    return sorted(linhas, key=lambda x: (ORDEM_SITUACAO[x.situacao], x.posicao or 0, x.nome))


def _gravar_documento(db: Session, armazenamento: ArmazenamentoArquivos, edital_id: int, conteudo: bytes,
                      nome: str, content_type: str) -> Arquivo:
    chave = f"editais/{edital_id}/atas/{uuid.uuid4().hex}-{nome}"
    armazenamento.put(chave, [conteudo], somente_leitura=True)
    arq = Arquivo(inscricao_id=None, documento_exigido_id=None, chave=chave, nome_original=nome,
                  sha256=hashlib.sha256(conteudo).hexdigest(), tamanho_bytes=len(conteudo), content_type=content_type)
    db.add(arq)
    db.flush()
    return arq


# --- HOM-01 / HOM-02: homologar ----------------------------------------------------------------------
def homologar(db: Session, edital_id: int, pro_reitor: Usuario, armazenamento: ArmazenamentoArquivos,
              ip: str | None) -> AtaHomologacao:
    edital = svc_editais.carregar(db, edital_id, bloquear=True)
    _exigir_estado(edital, EventoEdital.HOMOLOGAR_FINAL)

    contagem = _recursos(db, edital.id)
    pendentes = contagem.get(StatusRecurso.ABERTO, 0) + contagem.get(StatusRecurso.EM_ANALISE, 0)
    if pendentes:
        raise Conflito(f"Há {pendentes} recurso(s) pendente(s) de julgamento (HOM-01).")

    momento = agora(db)
    # Classificação FINAL: recalculada a partir das avaliações vigentes (já refletem os recursos deferidos).
    # O trigger do banco torna essas linhas imutáveis (RN-13).
    posicoes = svc_avaliacoes.gravar_classificacao(db, edital, "FINAL")

    dados = DadosAta(
        edital_id=edital.id, titulo=edital.titulo, categoria=edital.categoria, vagas=edital.vagas,
        valor_bolsa=edital.valor_bolsa, homologado_por=pro_reitor.nome,
        homologado_em=momento.astimezone(agora(db).tzinfo), linhas=_linhas_resultado(db, edital, posicoes),
        recursos_deferidos=contagem.get(StatusRecurso.DEFERIDO, 0),
        recursos_indeferidos=contagem.get(StatusRecurso.INDEFERIDO, 0),
    )
    arquivos_gravados: list[str] = []
    try:
        pdf = _gravar_documento(db, armazenamento, edital.id, gerar_pdf(dados),
                                f"ata-edital-{edital.id}.pdf", "application/pdf")
        arquivos_gravados.append(pdf.chave)
        csv = _gravar_documento(db, armazenamento, edital.id, gerar_csv(dados),
                                f"resultado-final-edital-{edital.id}.csv", "text/csv")
        arquivos_gravados.append(csv.chave)

        ata = AtaHomologacao(edital_id=edital.id, homologado_por=pro_reitor.id, arquivo_pdf_id=pdf.id,
                             arquivo_csv_id=csv.id, homologado_em=momento)
        db.add(ata)
        db.flush()
        svc_editais.transicionar(
            db, edital, EventoEdital.HOMOLOGAR_FINAL, usuario_id=pro_reitor.id, ip=ip,
            extra_depois={
                "ata_id": ata.id,
                "ata_pdf_sha256": pdf.sha256,
                "lista_csv_sha256": csv.sha256,
                "resultado_final": [
                    {"protocolo": linha.protocolo, "posicao": linha.posicao, "situacao": linha.situacao}
                    for linha in dados.linhas
                ],
            },
        )
        _notificar_resultado_final(db, edital, dados)
        db.commit()
    except BaseException:
        db.rollback()
        for chave in arquivos_gravados:
            _remover_somente_leitura(armazenamento, chave)
        raise
    return ata


def _remover_somente_leitura(armazenamento: ArmazenamentoArquivos, chave: str) -> None:
    """Só usado para desfazer uma homologação que falhou antes do commit."""
    caminho = getattr(armazenamento, "_caminho", None)
    if caminho is not None:
        import os

        try:
            os.chmod(caminho(chave), 0o644)
        except FileNotFoundError:
            return
    armazenamento.delete(chave)


def _notificar_resultado_final(db: Session, edital: Edital, dados: DadosAta) -> None:
    por_protocolo = {linha.protocolo: linha for linha in dados.linhas}
    textos = {
        "CONTEMPLADO": "Parabéns! Você foi CONTEMPLADO(A) — {pos}º lugar.",
        "SUPLENTE": "Você ficou como SUPLENTE — {pos}º lugar. Você poderá ser convocado(a) em caso de vacância.",
        "NAO_CLASSIFICADO": "Você não foi classificado(a) na avaliação de mérito.",
        "INDEFERIDA_HOMOLOGACAO": "Sua inscrição foi indeferida na homologação e não participou da classificação.",
    }
    for insc in db.scalars(select(Inscricao).where(Inscricao.edital_id == edital.id,
                                                   Inscricao.status != StatusInscricao.DESISTENTE)):
        linha = por_protocolo.get(insc.protocolo)
        if linha is None:
            continue
        notificar(
            db, usuario_id=insc.estudante_id, tipo="RESULTADO_FINAL",
            titulo=f"Resultado final homologado: {edital.titulo}",
            mensagem=textos[linha.situacao].format(pos=linha.posicao) + "\n\nA ata está disponível no portal.",
        )
    for membro in db.scalars(select(ComissaoEdital.avaliador_id).where(ComissaoEdital.edital_id == edital.id)):
        notificar(db, usuario_id=membro, tipo="RESULTADO_FINAL", titulo=f"Resultado final homologado: {edital.titulo}",
                  mensagem="O resultado do edital em que você integrou a comissão foi homologado.")


# --- UC-09 A1: devolver para ajustes ---------------------------------------------------------------------
def devolver_ajustes(db: Session, edital_id: int, justificativa: str, pro_reitor: Usuario, ip: str | None) -> Edital:
    edital = svc_editais.carregar(db, edital_id, bloquear=True)
    _exigir_estado(edital, EventoEdital.DEVOLVER_AJUSTES)
    svc_editais.transicionar(db, edital, EventoEdital.DEVOLVER_AJUSTES, usuario_id=pro_reitor.id, ip=ip,
                             extra_depois={"justificativa_devolucao": justificativa})
    for membro in db.scalars(select(ComissaoEdital.avaliador_id).where(ComissaoEdital.edital_id == edital.id)):
        notificar(
            db, usuario_id=membro, tipo="EDITAL_DEVOLVIDO",
            titulo=f"Edital devolvido para ajustes: {edital.titulo}",
            mensagem=(f"A Pró-Reitoria devolveu o processo para a fase de avaliação.\n\nJustificativa: {justificativa}\n\n"
                      "Retifique as avaliações necessárias e publique novamente o resultado preliminar."),
        )
    db.commit()
    return edital


# --- Consulta da ata -----------------------------------------------------------------------------------
def atas_do_edital(db: Session, edital_id: int) -> list[AtaHomologacao]:
    svc_editais.carregar(db, edital_id)
    return list(db.scalars(select(AtaHomologacao).where(AtaHomologacao.edital_id == edital_id)
                           .order_by(AtaHomologacao.homologado_em)))


def eh_documento_de_ata(db: Session, arquivo_id: int) -> bool:
    return db.scalar(select(AtaHomologacao.id).where(
        (AtaHomologacao.arquivo_pdf_id == arquivo_id) | (AtaHomologacao.arquivo_csv_id == arquivo_id))) is not None
