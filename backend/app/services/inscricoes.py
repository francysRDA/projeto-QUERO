"""Casos de uso da inscrição (UC-03: INS-02, INS-04, INS-05, INS-06, INS-07; RN-01…04, RN-15)."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.auditoria import registrar, snapshot
from app.core.errors import Conflito, NaoEncontrado, RegraViolada
from app.core.relogio import agora
from app.domain.estados import (
    MAQUINA_INSCRICAO,
    NOVO,
    EventoInscricao,
    StatusEdital,
    StatusInscricao,
)
from app.domain.perfis import Perfil
from app.models import Arquivo, Avaliacao, Classificacao, Edital, Inscricao, Usuario
from app.schemas.inscricao import ArquivoSaida, EditalDaInscricao, InscricaoSaida, ResultadoCandidato
from app.services import editais as svc_editais
from app.integrations.academico import ServicoAcademico
from app.services.homologacao import consultar_ramo_academico, decidir_submissao, todos_os_motivos
from app.services.notificacoes import notificar
from app.storage.base import ArmazenamentoArquivos
from app.storage.validacao import ArquivoInvalido, receber_pdf

# Ramo acadêmico do gateway AND (§7.5): roda em paralelo ao recebimento dos PDFs.
_ramo_academico = ThreadPoolExecutor(max_workers=16, thread_name_prefix="ramo-academico")

# INS-07: desistência só antes da publicação do resultado preliminar.
STATUS_EDITAL_PERMITE_DESISTIR = {
    StatusEdital.ABERTO,
    StatusEdital.INSCRICOES_ENCERRADAS,
    StatusEdital.EM_AVALIACAO,
}


@dataclass
class ArquivoEnviado:
    documento_exigido_id: int
    conteudo: BinaryIO
    nome: str | None
    content_type: str | None


# --- Regras de prazo e acesso --------------------------------------------------------------------
def _janela_aberta(db: Session, edital: Edital) -> tuple[bool, datetime]:
    momento = agora(db)
    aberta = (
        edital.status == StatusEdital.ABERTO
        and edital.data_inicio_inscricao <= momento < edital.data_fim_inscricao
    )
    return aberta, momento


def _exigir_janela(db: Session, edital: Edital, acao: str) -> datetime:
    """RN-03: só com edital ABERTO e dentro da janela, pelo relógio oficial do servidor."""
    aberta, momento = _janela_aberta(db, edital)
    if not aberta:
        if edital.status == StatusEdital.ABERTO and momento < edital.data_inicio_inscricao:
            raise Conflito(f"{acao}: o período de inscrição ainda não começou.")
        raise Conflito(f"{acao}: o período de inscrição deste edital está encerrado.")
    return momento


def _carregar_edital_compartilhado(db: Session, edital_id: int) -> Edital:
    """FOR SHARE: impede que o edital mude de estado (ex.: fechar inscrições) durante a submissão."""
    edital = db.scalar(
        select(Edital)
        .where(Edital.id == edital_id)
        .options(selectinload(Edital.documentos))
        .with_for_update(read=True, of=Edital)
    )
    if edital is None or edital.status == StatusEdital.RASCUNHO:
        raise NaoEncontrado("Edital não encontrado.")
    return edital


def carregar_visivel(db: Session, inscricao_id: int, usuario: Usuario, *, bloquear: bool = False) -> Inscricao:
    """RN-15 / anti-IDOR: titular, Pró-Reitor ou avaliador designado ao edital. Demais: 404."""
    stmt = select(Inscricao).where(Inscricao.id == inscricao_id)
    if bloquear:
        stmt = stmt.with_for_update()
    insc = db.scalar(stmt)
    if insc is None or not pode_ver(db, insc, usuario):
        raise NaoEncontrado("Inscrição não encontrada.")
    return insc


def pode_ver(db: Session, insc: Inscricao, usuario: Usuario) -> bool:
    if usuario.perfil == Perfil.PRO_REITOR or insc.estudante_id == usuario.id:
        return True
    if usuario.perfil == Perfil.AVALIADOR:
        return svc_editais.eh_membro_comissao(db, insc.edital_id, usuario.id)
    return False


def _carregar_do_titular(db: Session, inscricao_id: int, estudante: Usuario) -> Inscricao:
    insc = db.scalar(select(Inscricao).where(Inscricao.id == inscricao_id).with_for_update())
    if insc is None or insc.estudante_id != estudante.id:
        raise NaoEncontrado("Inscrição não encontrada.")
    return insc


# --- Gravação dos arquivos -------------------------------------------------------------------------
def _validar_documentos(edital: Edital, arquivos: list[ArquivoEnviado], *, exigir_todos: bool) -> None:
    ids_validos = {d.id for d in edital.documentos}
    problemas = [
        f"Documento {a.documento_exigido_id} não pertence a este edital."
        for a in arquivos
        if a.documento_exigido_id not in ids_validos
    ]
    repetidos = {a.documento_exigido_id for a in arquivos if [x.documento_exigido_id for x in arquivos].count(a.documento_exigido_id) > 1}
    problemas += [f"Documento {d} enviado mais de uma vez." for d in sorted(repetidos)]
    if exigir_todos:
        enviados = {a.documento_exigido_id for a in arquivos}
        problemas += [
            f"Documento obrigatório ausente: {d.nome}."
            for d in edital.documentos
            if d.obrigatorio and d.id not in enviados
        ]
    if not arquivos and not exigir_todos:
        problemas.append("Envie ao menos um documento para retificar.")
    if problemas:
        raise RegraViolada("Documentos inválidos ou incompletos.", detalhes=problemas)


def _gravar_arquivos(
    db: Session,
    insc: Inscricao,
    arquivos: list[ArquivoEnviado],
    armazenamento: ArmazenamentoArquivos,
) -> list[Arquivo]:
    """Valida e grava todos; se QUALQUER arquivo for inválido, apaga os já gravados e recusa tudo (422)."""
    gravados: list[Arquivo] = []
    erros: list[str] = []
    prefixo = f"editais/{insc.edital_id}/inscricoes/{insc.id}"
    try:
        for a in arquivos:
            try:
                r = receber_pdf(a.conteudo, nome_original=a.nome, content_type=a.content_type,
                                prefixo_chave=prefixo, armazenamento=armazenamento)
            except ArquivoInvalido as exc:
                erros.append(str(exc))
                continue
            versao_atual = db.scalar(
                select(func.max(Arquivo.versao)).where(
                    Arquivo.inscricao_id == insc.id, Arquivo.documento_exigido_id == a.documento_exigido_id
                )
            ) or 0
            gravados.append(
                Arquivo(
                    inscricao_id=insc.id,
                    documento_exigido_id=a.documento_exigido_id,
                    chave=r.chave,
                    nome_original=r.nome_original,
                    sha256=r.sha256,
                    tamanho_bytes=r.tamanho_bytes,
                    versao=versao_atual + 1,
                    status_varredura="VALIDADO",
                )
            )
        if erros:
            raise RegraViolada("Arquivos recusados.", detalhes=erros)
    except BaseException:
        for arq in gravados:
            armazenamento.delete(arq.chave)
        raise
    return gravados


# --- INS-02 / INS-03 / INS-04: submissão ------------------------------------------------------------
def submeter(
    db: Session,
    edital_id: int,
    estudante: Usuario,
    arquivos: list[ArquivoEnviado],
    armazenamento: ArmazenamentoArquivos,
    servico_academico: ServicoAcademico,
    ip: str | None,
) -> Inscricao:
    edital = _carregar_edital_compartilhado(db, edital_id)
    momento = _exigir_janela(db, edital, "Inscrição")

    if db.scalar(select(Inscricao.id).where(Inscricao.edital_id == edital.id, Inscricao.estudante_id == estudante.id)):
        raise Conflito("Você já possui inscrição neste edital (RN-01).")
    if svc_editais.eh_membro_comissao(db, edital.id, estudante.id):
        raise Conflito("Integrante da comissão avaliadora não pode se inscrever no edital (RN-07).")
    _validar_documentos(edital, arquivos, exigir_todos=True)

    # Gateway AND (§7.5), ramo 1: a consulta acadêmica (INT-01) começa agora, em outra thread...
    ramo_academico = _ramo_academico.submit(consultar_ramo_academico, servico_academico, estudante.matricula)

    insc = Inscricao(
        protocolo=f"TMP-{estudante.id}-{edital.id}",
        edital_id=edital.id,
        estudante_id=estudante.id,
        status=StatusInscricao.HOMOLOGADA,  # provisório; definido pela máquina abaixo
        data_submissao_original=momento,
    )
    db.add(insc)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise Conflito("Você já possui inscrição neste edital (RN-01).") from None
    insc.protocolo = f"QUERO-{momento.year}-{edital.id:04d}-{insc.id:06d}"

    novos: list[Arquivo] = []
    try:
        # ...ramo 2: recebimento e verificação estrutural dos PDFs (RN-04) nesta thread.
        novos = _gravar_arquivos(db, insc, arquivos, armazenamento)
        db.add_all(novos)
        db.flush()

        # Sincronização dos ramos e decisão da homologação formal (INS-03, RN-02, RN-05).
        evento = decidir_submissao(db, edital, insc, ramo_academico.result())
        insc.status = MAQUINA_INSCRICAO.proximo(NOVO, evento)
        db.flush()

        registrar(db, usuario_id=estudante.id, acao="INSCRICAO_SUBMETER", entidade="inscricao",
                  entidade_id=insc.id, depois=snapshot(insc) | {"arquivos": [snapshot(a) for a in novos]}, ip=ip)
        notificar(
            db,
            usuario_id=estudante.id,
            tipo="INSCRICAO_RECEBIDA",
            titulo=f"Inscrição recebida — protocolo {insc.protocolo}",
            mensagem=(
                f"Recebemos sua inscrição no edital \"{edital.titulo}\".\n"
                f"Protocolo: {insc.protocolo}\n"
                f"Data/hora: {momento.strftime('%d/%m/%Y %H:%M')} (horário de Brasília)\n"
                f"Situação: {insc.status}\n\n"
                + (
                    "O Sistema Acadêmico está temporariamente indisponível. Sua inscrição foi registrada e o "
                    "vínculo será validado automaticamente; você será avisado(a) do resultado.\n\n"
                    if insc.status == StatusInscricao.PENDENTE_VALIDACAO_VINCULO
                    else ""
                )
                + "O comprovante em PDF está disponível no painel \"Minhas inscrições\"."
            ),
        )
        db.commit()
    except BaseException:
        db.rollback()
        for arq in novos:
            armazenamento.delete(arq.chave)
        raise
    return insc


# --- INS-05: retificação ------------------------------------------------------------------------
def retificar(
    db: Session,
    inscricao_id: int,
    estudante: Usuario,
    arquivos: list[ArquivoEnviado],
    armazenamento: ArmazenamentoArquivos,
    ip: str | None,
) -> Inscricao:
    insc = _carregar_do_titular(db, inscricao_id, estudante)
    edital = _carregar_edital_compartilhado(db, insc.edital_id)
    if insc.status == StatusInscricao.DESISTENTE:
        raise Conflito("Inscrição desistente não pode ser retificada.")
    momento = _exigir_janela(db, edital, "Retificação")
    _validar_documentos(edital, arquivos, exigir_todos=False)

    antes = snapshot(insc) | {"arquivos_ativos": _ativos(db, insc.id)}
    novos: list[Arquivo] = []
    try:
        novos = _gravar_arquivos(db, insc, arquivos, armazenamento)
        # RN-04: prevalece a versão mais recente; o histórico é mantido (ativo = false).
        substituidos = db.scalars(
            select(Arquivo).where(
                Arquivo.inscricao_id == insc.id,
                Arquivo.ativo.is_(True),
                Arquivo.documento_exigido_id.in_([a.documento_exigido_id for a in arquivos]),
            )
        ).all()
        for velho in substituidos:
            velho.ativo = False
        db.add_all(novos)
        db.flush()

        # RN-02 / RN-09: protocolo, data original e dados acadêmicos congelados NÃO mudam;
        # só os arquivos são revalidados, reaplicando as regras sobre os dados congelados.
        if insc.status == StatusInscricao.PENDENTE_VALIDACAO_VINCULO:
            evento = EventoInscricao.RETIFICAR_PENDENTE
            motivos: list[str] = []
        else:
            motivos = todos_os_motivos(db, edital, insc)
            evento = EventoInscricao.RETIFICAR_INVALIDA if motivos else EventoInscricao.RETIFICAR_VALIDA
        insc.status = MAQUINA_INSCRICAO.proximo(insc.status, evento)
        if evento != EventoInscricao.RETIFICAR_PENDENTE:
            insc.motivos_indeferimento = motivos or None
        insc.data_ultima_retificacao = momento
        db.flush()

        registrar(db, usuario_id=estudante.id, acao="INSCRICAO_RETIFICAR", entidade="inscricao",
                  entidade_id=insc.id, antes=antes,
                  depois=snapshot(insc) | {"arquivos_ativos": _ativos(db, insc.id)}, ip=ip)
        notificar(
            db,
            usuario_id=estudante.id,
            tipo="INSCRICAO_RETIFICADA",
            titulo=f"Inscrição retificada — protocolo {insc.protocolo}",
            mensagem=f"Seus documentos do edital \"{edital.titulo}\" foram substituídos. Situação: {insc.status}.",
        )
        db.commit()
    except BaseException:
        db.rollback()
        for arq in novos:
            armazenamento.delete(arq.chave)
        raise
    return insc


def _ativos(db: Session, inscricao_id: int) -> list[dict]:
    return [
        {"id": a.id, "documento_exigido_id": a.documento_exigido_id, "versao": a.versao, "sha256": a.sha256}
        for a in db.scalars(
            select(Arquivo).where(Arquivo.inscricao_id == inscricao_id, Arquivo.ativo.is_(True)).order_by(Arquivo.id)
        )
    ]


# --- INS-07: desistência ----------------------------------------------------------------------------
def desistir(db: Session, inscricao_id: int, estudante: Usuario, ip: str | None) -> Inscricao:
    insc = _carregar_do_titular(db, inscricao_id, estudante)
    edital = db.get(Edital, insc.edital_id)
    if edital.status not in STATUS_EDITAL_PERMITE_DESISTIR:
        raise Conflito("A desistência só é permitida antes da publicação do resultado preliminar.")
    antes = snapshot(insc)
    insc.status = MAQUINA_INSCRICAO.proximo(insc.status, EventoInscricao.DESISTIR)
    db.flush()
    registrar(db, usuario_id=estudante.id, acao="INSCRICAO_DESISTIR", entidade="inscricao",
              entidade_id=insc.id, antes=antes, depois=snapshot(insc), ip=ip)
    db.commit()
    return insc


# --- INS-06: consulta -----------------------------------------------------------------------------
def montar_saida(db: Session, insc: Inscricao, usuario: Usuario) -> InscricaoSaida:
    edital = db.get(Edital, insc.edital_id)
    titular = insc.estudante_id == usuario.id
    # Avaliador vê só as versões vigentes; titular e PR veem o histórico (RN-04).
    stmt = select(Arquivo).where(Arquivo.inscricao_id == insc.id).order_by(Arquivo.documento_exigido_id, Arquivo.versao)
    if not titular and usuario.perfil != Perfil.PRO_REITOR:
        stmt = stmt.where(Arquivo.ativo.is_(True))
    janela, _ = _janela_aberta(db, edital)
    ativa = insc.status != StatusInscricao.DESISTENTE
    return InscricaoSaida(
        id=insc.id,
        protocolo=insc.protocolo,
        status=insc.status,
        motivos_indeferimento=insc.motivos_indeferimento,
        vinculo_ativo_congelado=insc.vinculo_ativo_congelado,
        curso_congelado=insc.curso_congelado,
        cr_congelado=insc.cr_congelado,
        data_submissao_original=insc.data_submissao_original,
        data_ultima_retificacao=insc.data_ultima_retificacao,
        edital=EditalDaInscricao(id=edital.id, titulo=edital.titulo, status=edital.status,
                                 data_fim_inscricao=edital.data_fim_inscricao),
        arquivos=[ArquivoSaida.model_validate(a) for a in db.scalars(stmt)],
        pode_retificar=titular and ativa and janela,
        pode_desistir=titular and ativa and edital.status in STATUS_EDITAL_PERMITE_DESISTIR,
        resultado=_resultado(db, edital, insc),
    )


def _resultado(db: Session, edital: Edital, insc: Inscricao) -> ResultadoCandidato | None:
    """INS-06: nota e classificação só aparecem após a publicação do resultado preliminar."""
    from app.services.avaliacoes import STATUS_RESULTADO_PUBLICADO

    if edital.status not in STATUS_RESULTADO_PUBLICADO:
        return None
    for fase in ("FINAL", "POS_RECURSO", "PRELIMINAR"):
        c = db.scalar(select(Classificacao).where(Classificacao.inscricao_id == insc.id, Classificacao.fase == fase))
        if c is not None:
            av = db.scalar(select(Avaliacao).where(Avaliacao.inscricao_id == insc.id))
            return ResultadoCandidato(
                fase=fase, nota=c.nota, parecer=av.parecer if av else None,
                justificativa=av.justificativa if av else None, posicao=c.posicao, situacao=c.situacao,
                total_vagas=edital.vagas,
            )
    return None


def minhas(db: Session, estudante: Usuario) -> list[Inscricao]:
    return list(
        db.scalars(
            select(Inscricao).where(Inscricao.estudante_id == estudante.id).order_by(Inscricao.data_submissao_original.desc())
        )
    )


# --- RN-15: download protegido -------------------------------------------------------------------------
def arquivo_para_download(db: Session, arquivo_id: int, usuario: Usuario, ip: str | None) -> Arquivo:
    arq = db.get(Arquivo, arquivo_id)
    if arq is None or arq.inscricao_id is None:
        raise NaoEncontrado("Arquivo não encontrado.")
    insc = db.get(Inscricao, arq.inscricao_id)
    if not pode_ver(db, insc, usuario):
        raise NaoEncontrado("Arquivo não encontrado.")
    # Avaliador só acessa a versão vigente (as substituídas não fazem parte da avaliação).
    if usuario.perfil == Perfil.AVALIADOR and not arq.ativo:
        raise NaoEncontrado("Arquivo não encontrado.")
    # §13.1 (c): auditoria de todo download de documento pessoal.
    registrar(db, usuario_id=usuario.id, acao="ARQUIVO_DOWNLOAD", entidade="arquivo", entidade_id=arq.id,
              depois={"inscricao_id": insc.id, "versao": arq.versao}, ip=ip)
    db.commit()
    return arq
