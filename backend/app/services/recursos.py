"""Recursos (UC-08: AVA-03, AVA-04; RN-10, RN-11, §7.4).

Decisões de protótipo (ver PLANO_PROTOTIPO L-16):
  - Só recorre quem participou da avaliação de mérito (tem classificação PRELIMINAR). Indeferimentos da
    homologação formal são tratados pela reanálise do Pró-Reitor (RN-05).
  - `julgar` assume o recurso (ABERTO → EM_ANALISE) e decide no mesmo ato; o avaliador que assumiu é o único
    que pode decidir.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auditoria import registrar, snapshot
from app.core.errors import Conflito, NaoEncontrado, Proibido, RegraViolada
from app.core.relogio import agora
from app.domain.estados import (
    MAQUINA_AVALIACAO,
    MAQUINA_RECURSO,
    NOVO,
    EventoAvaliacao,
    EventoEdital,
    EventoRecurso,
    StatusEdital,
    StatusRecurso,
)
from app.domain.perfis import Perfil
from app.models import (
    Arquivo,
    Avaliacao,
    Classificacao,
    ComissaoEdital,
    Edital,
    Inscricao,
    Recurso,
    Usuario,
)
from app.schemas.inscricao import ArquivoSaida
from app.schemas.recurso import (
    MIN_JUSTIFICATIVA_REFORCADA,
    TAMANHO_MAX_TEXTO,
    JulgamentoEntrada,
    PainelRecursos,
    RecursoGestao,
    RecursoSaida,
)
from app.services import avaliacoes as svc_avaliacoes
from app.services import editais as svc_editais
from app.services.notificacoes import notificar
from app.storage.base import ArmazenamentoArquivos
from app.storage.validacao import ArquivoInvalido, receber_pdf

PENDENTES = (StatusRecurso.ABERTO, StatusRecurso.EM_ANALISE)


# --- Consultas auxiliares --------------------------------------------------------------------------
def janela_aberta(db: Session, edital: Edital, momento: datetime | None = None) -> bool:
    """RN-10: janela aberta na publicação do preliminar, com a duração definida no edital."""
    momento = momento or agora(db)
    return (
        edital.status == StatusEdital.EM_RECURSO
        and edital.data_fim_recurso is not None
        and momento < edital.data_fim_recurso
    )


def _participou_do_merito(db: Session, insc: Inscricao) -> bool:
    return bool(db.scalar(select(Classificacao.id).where(Classificacao.inscricao_id == insc.id,
                                                         Classificacao.fase == "PRELIMINAR")))


def pode_recorrer(db: Session, edital: Edital, insc: Inscricao) -> bool:
    return (
        janela_aberta(db, edital)
        and _participou_do_merito(db, insc)
        and db.scalar(select(Recurso.id).where(Recurso.inscricao_id == insc.id)) is None
    )


def recurso_da_inscricao(db: Session, inscricao_id: int) -> RecursoSaida | None:
    r = db.scalar(select(Recurso).where(Recurso.inscricao_id == inscricao_id))
    return _saida(db, r) if r else None


def _saida(db: Session, r: Recurso) -> RecursoSaida:
    anexo = db.get(Arquivo, r.arquivo_anexo_id) if r.arquivo_anexo_id else None
    return RecursoSaida(
        id=r.id, inscricao_id=r.inscricao_id, texto=r.texto,
        anexo=ArquivoSaida.model_validate(anexo) if anexo else None, status=r.status,
        justificativa_decisao=r.justificativa_decisao, criado_em=r.criado_em, julgado_em=r.julgado_em,
    )


# --- AVA-03: interposição --------------------------------------------------------------------------
def interpor(
    db: Session,
    inscricao_id: int,
    estudante: Usuario,
    texto: str,
    anexo: tuple | None,  # (conteudo, nome, content_type)
    armazenamento: ArmazenamentoArquivos,
    ip: str | None,
) -> Recurso:
    insc = db.scalar(select(Inscricao).where(Inscricao.id == inscricao_id).with_for_update())
    if insc is None or insc.estudante_id != estudante.id:
        raise NaoEncontrado("Inscrição não encontrada.")
    edital = db.scalar(select(Edital).where(Edital.id == insc.edital_id).with_for_update(read=True))

    if not janela_aberta(db, edital):
        raise Conflito("Fora da janela de recurso deste edital (RN-10).")
    if not _participou_do_merito(db, insc):
        raise Conflito("Apenas candidatos avaliados no mérito podem interpor recurso.")
    if db.scalar(select(Recurso.id).where(Recurso.inscricao_id == insc.id)):
        raise Conflito("Você já interpôs recurso neste edital — é permitido apenas um (RN-10).")
    texto = (texto or "").strip()
    if not texto:
        raise RegraViolada("Escreva a fundamentação do recurso.")
    if len(texto) > TAMANHO_MAX_TEXTO:
        raise RegraViolada(f"O texto do recurso deve ter no máximo {TAMANHO_MAX_TEXTO} caracteres (RN-10).")

    arq: Arquivo | None = None
    if anexo is not None:
        conteudo, nome, content_type = anexo
        try:
            r = receber_pdf(conteudo, nome_original=nome, content_type=content_type,
                            prefixo_chave=f"editais/{edital.id}/inscricoes/{insc.id}/recurso",
                            armazenamento=armazenamento)
        except ArquivoInvalido as exc:
            raise RegraViolada("Anexo recusado.", detalhes=[str(exc)]) from None
        arq = Arquivo(inscricao_id=insc.id, documento_exigido_id=None, chave=r.chave, nome_original=r.nome_original,
                      sha256=r.sha256, tamanho_bytes=r.tamanho_bytes)
    try:
        if arq is not None:
            db.add(arq)
            db.flush()
        recurso = Recurso(inscricao_id=insc.id, texto=texto, arquivo_anexo_id=arq.id if arq else None,
                          status=MAQUINA_RECURSO.proximo(NOVO, EventoRecurso.INTERPOR), criado_em=agora(db))
        db.add(recurso)
        db.flush()
        registrar(db, usuario_id=estudante.id, acao="RECURSO_INTERPOR", entidade="recurso", entidade_id=recurso.id,
                  depois=snapshot(recurso), ip=ip)
        notificar(db, usuario_id=estudante.id, tipo="RECURSO_RECEBIDO",
                  titulo=f"Recurso recebido — {insc.protocolo}",
                  mensagem=f"Seu recurso no edital \"{edital.titulo}\" foi registrado e será julgado pela comissão.")
        db.commit()
    except BaseException:
        db.rollback()
        if arq is not None:
            armazenamento.delete(arq.chave)
        raise
    return recurso


# --- AVA-04: julgamento ----------------------------------------------------------------------------------
def _contexto(db: Session, recurso: Recurso) -> tuple[Inscricao, Edital, Avaliacao | None, int]:
    insc = db.get(Inscricao, recurso.inscricao_id)
    edital = db.get(Edital, insc.edital_id)
    avaliacao = db.scalar(select(Avaliacao).where(Avaliacao.inscricao_id == insc.id))
    tamanho = db.scalar(select(func.count()).select_from(ComissaoEdital).where(ComissaoEdital.edital_id == edital.id))
    return insc, edital, avaliacao, tamanho or 0


def bloqueio_rn11(recurso: Recurso, avaliacao: Avaliacao | None, tamanho_comissao: int, avaliador_id: int) -> str | None:
    """RN-11: com 2+ membros, o autor do parecer original não julga o recurso."""
    if tamanho_comissao >= 2 and avaliacao is not None and avaliacao.avaliador_id == avaliador_id:
        return "Você é o autor do parecer original; o recurso deve ser julgado por outro membro (RN-11)."
    if recurso.status == StatusRecurso.EM_ANALISE and recurso.julgado_por not in (None, avaliador_id):
        return "Recurso em análise por outro membro da comissão."
    return None


def julgar(db: Session, recurso_id: int, dados: JulgamentoEntrada, avaliador: Usuario, ip: str | None) -> Recurso:
    recurso = db.scalar(select(Recurso).where(Recurso.id == recurso_id).with_for_update())
    if recurso is None:
        raise NaoEncontrado("Recurso não encontrado.")
    insc, edital, avaliacao, tamanho = _contexto(db, recurso)
    if not svc_editais.eh_membro_comissao(db, edital.id, avaliador.id):
        raise NaoEncontrado("Recurso não encontrado.")
    if edital.status != StatusEdital.EM_RECURSO:
        raise Conflito("O edital não está em fase de recurso.")

    bloqueio = bloqueio_rn11(recurso, avaliacao, tamanho, avaliador.id)
    if bloqueio:
        raise Proibido(bloqueio)
    comissao_unica = tamanho < 2
    if comissao_unica and len(dados.justificativa) < MIN_JUSTIFICATIVA_REFORCADA:
        raise RegraViolada(
            f"Comissão de um único membro: a decisão exige justificativa reforçada, com ao menos "
            f"{MIN_JUSTIFICATIVA_REFORCADA} caracteres (RN-11)."
        )
    if dados.decisao == "DEFERIDO" and dados.nova_nota is None:
        raise RegraViolada("Ao deferir o recurso, informe a nova nota de mérito (AVA-04).")

    antes = snapshot(recurso)
    estado = recurso.status
    if estado == StatusRecurso.ABERTO:
        estado = MAQUINA_RECURSO.proximo(estado, EventoRecurso.ASSUMIR)
    estado = MAQUINA_RECURSO.proximo(
        estado, EventoRecurso.DEFERIR if dados.decisao == "DEFERIDO" else EventoRecurso.INDEFERIR
    )  # recurso já julgado -> 409
    momento = agora(db)
    recurso.status = estado
    recurso.julgado_por = avaliador.id
    recurso.justificativa_decisao = dados.justificativa
    recurso.julgado_em = momento
    db.flush()
    registrar(db, usuario_id=avaliador.id, acao="RECURSO_JULGAR", entidade="recurso", entidade_id=recurso.id,
              antes=antes, depois=snapshot(recurso) | {"comissao_unica": comissao_unica}, ip=ip,
              destaque=comissao_unica)  # RN-11: destaque na auditoria

    if dados.decisao == "DEFERIDO":
        _reavaliar(db, avaliacao, dados, avaliador, momento, ip)

    # AVA-04: toda decisão recalcula a classificação pós-recurso.
    svc_avaliacoes.gravar_classificacao(db, edital, "POS_RECURSO")
    notificar(
        db, usuario_id=insc.estudante_id, tipo="RECURSO_JULGADO",
        titulo=f"Recurso julgado: {dados.decisao.lower()} — {insc.protocolo}",
        mensagem=(
            f"Seu recurso no edital \"{edital.titulo}\" foi {dados.decisao}.\n\nFundamentação: {dados.justificativa}"
            + (f"\n\nNova nota de mérito: {dados.nova_nota:.2f}." if dados.decisao == "DEFERIDO" else "")
        ),
    )
    encerrar_se_concluido(db, edital, ip=ip)
    db.commit()
    return recurso


def _reavaliar(db: Session, avaliacao: Avaliacao, dados: JulgamentoEntrada, avaliador: Usuario, momento, ip) -> None:
    """Recurso deferido: a avaliação original é RETIFICADA (§7.3: 'via recurso')."""
    antes = snapshot(avaliacao)
    avaliacao.status = MAQUINA_AVALIACAO.proximo(avaliacao.status, EventoAvaliacao.RETIFICAR)
    avaliacao.nota_merito = dados.nova_nota
    avaliacao.parecer = dados.novo_parecer or "DEFERIDO"
    avaliacao.justificativa_retificacao = f"Recurso deferido: {dados.justificativa}"
    avaliacao.atualizado_em = momento
    db.flush()
    registrar(db, usuario_id=avaliador.id, acao="AVALIACAO_RETIFICAR_RECURSO", entidade="avaliacao",
              entidade_id=avaliacao.id, antes=antes, depois=snapshot(avaliacao), ip=ip)


# --- Encerramento da fase de recurso (§7.1: EM_RECURSO -> EM_HOMOLOGACAO_FINAL) ------------------------------
def encerrar_se_concluido(db: Session, edital: Edital, *, ip: str | None = None) -> bool:
    """Fim da janela + todos os recursos julgados. Chamado pelo worker e após cada julgamento."""
    if edital.status != StatusEdital.EM_RECURSO or janela_aberta(db, edital):
        return False
    pendentes = db.scalar(
        select(func.count()).select_from(Recurso).join(Inscricao, Inscricao.id == Recurso.inscricao_id)
        .where(Inscricao.edital_id == edital.id, Recurso.status.in_([str(s) for s in PENDENTES]))
    )
    if pendentes:
        return False
    svc_avaliacoes.gravar_classificacao(db, edital, "POS_RECURSO")  # consolida (também quando não houve recurso)
    svc_editais.transicionar(db, edital, EventoEdital.ENCERRAR_RECURSO, usuario_id=None, ip=ip)
    for pr_id in db.scalars(select(Usuario.id).where(Usuario.perfil == Perfil.PRO_REITOR, Usuario.ativo.is_(True))):
        notificar(db, usuario_id=pr_id, tipo="EDITAL_AGUARDA_HOMOLOGACAO",
                  titulo=f"Edital pronto para homologação final: {edital.titulo}",
                  mensagem="A fase de recursos foi concluída. Revise o resultado e homologue (HOM-01).")
    return True


# --- Painel da comissão / Pró-Reitoria ----------------------------------------------------------------------
def painel(db: Session, edital_id: int, usuario: Usuario) -> PainelRecursos:
    edital = svc_editais.carregar(db, edital_id)
    if usuario.perfil == Perfil.AVALIADOR and not svc_editais.eh_membro_comissao(db, edital_id, usuario.id):
        raise NaoEncontrado("Edital não encontrado entre as suas comissões.")
    tamanho = db.scalar(select(func.count()).select_from(ComissaoEdital).where(ComissaoEdital.edital_id == edital.id)) or 0
    linhas = db.execute(
        select(Recurso, Inscricao).join(Inscricao, Inscricao.id == Recurso.inscricao_id)
        .where(Inscricao.edital_id == edital.id).order_by(Recurso.criado_em)
    ).all()
    nomes = dict(db.execute(select(Usuario.id, Usuario.nome)).all())
    itens = []
    for recurso, insc in linhas:
        av = db.scalar(select(Avaliacao).where(Avaliacao.inscricao_id == insc.id))
        bloqueio = None
        if usuario.perfil == Perfil.AVALIADOR:
            bloqueio = bloqueio_rn11(recurso, av, tamanho, usuario.id)
            if recurso.status not in PENDENTES:
                bloqueio = "Recurso já julgado."
            elif edital.status != StatusEdital.EM_RECURSO:
                bloqueio = "O edital não está em fase de recurso."
        base = _saida(db, recurso)
        itens.append(RecursoGestao(
            **base.model_dump(), protocolo=insc.protocolo, estudante_nome=nomes.get(insc.estudante_id, "?"),
            nota_atual=av.nota_merito if av else None, parecer_atual=av.parecer if av else None,
            autor_parecer_id=av.avaliador_id if av else None,
            autor_parecer_nome=nomes.get(av.avaliador_id) if av else None,
            julgado_por_nome=nomes.get(recurso.julgado_por) if recurso.julgado_por else None,
            pode_julgar=usuario.perfil == Perfil.AVALIADOR and bloqueio is None,
            motivo_bloqueio=bloqueio, comissao_unica=tamanho < 2,
        ))
    return PainelRecursos(edital_id=edital.id, data_fim_recurso=edital.data_fim_recurso,
                          janela_aberta=janela_aberta(db, edital), recursos=itens)
