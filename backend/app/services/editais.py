"""Casos de uso de editais e comissão (UC-06: EDT-01…05, RN-07, RN-14)."""

from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.auditoria import registrar, snapshot
from app.core.errors import Conflito, NaoEncontrado, RegraViolada
from app.core.relogio import agora
from app.domain.estados import MAQUINA_EDITAL, EventoEdital, StatusEdital, StatusInscricao
from app.domain.perfis import Perfil
from app.models import (
    Avaliacao,
    ComissaoEdital,
    Edital,
    EditalCurso,
    EditalDocumentoExigido,
    Inscricao,
    Usuario,
)
from app.schemas.edital import ComissaoEntrada, EditalAtualizacao, EditalEntrada
from app.services.notificacoes import notificar

TERMINAIS = {StatusEdital.ENCERRADO, StatusEdital.CANCELADO}
CAMPOS_EDITAVEIS_APOS_PUBLICACAO = {"descricao"}


# --- Utilitários ---------------------------------------------------------------------------------
def foto(edital: Edital) -> dict:
    """Snapshot para auditoria, incluindo cursos e documentos."""
    dados = snapshot(edital)
    dados["cursos"] = [{"codigo_curso": c.codigo_curso, "nome_curso": c.nome_curso} for c in edital.cursos]
    dados["documentos"] = [
        {"nome": d.nome, "descricao": d.descricao, "obrigatorio": d.obrigatorio} for d in edital.documentos
    ]
    return dados


def carregar(db: Session, edital_id: int, *, bloquear: bool = False) -> Edital:
    stmt = (
        select(Edital)
        .where(Edital.id == edital_id)
        .options(selectinload(Edital.cursos), selectinload(Edital.documentos))
    )
    if bloquear:
        stmt = stmt.with_for_update(of=Edital)
    edital = db.scalar(stmt)
    if edital is None:
        raise NaoEncontrado("Edital não encontrado.")
    return edital


def transicionar(
    db: Session,
    edital: Edital,
    evento: EventoEdital,
    *,
    usuario_id: int | None,
    ip: str | None = None,
    extra_depois: dict | None = None,
) -> None:
    """Aplica um evento da máquina §7.1 e registra auditoria. usuario_id=None => sistema/worker."""
    antes = foto(edital)
    edital.status = MAQUINA_EDITAL.proximo(edital.status, evento)
    db.flush()
    depois = foto(edital) | (extra_depois or {})
    registrar(db, usuario_id=usuario_id, acao=f"EDITAL_{evento}", entidade="edital",
              entidade_id=edital.id, antes=antes, depois=depois, ip=ip)


def _substituir_listas(edital: Edital, cursos, documentos) -> None:
    if cursos is not None:
        codigos = [c.codigo_curso for c in cursos]
        if len(codigos) != len(set(codigos)):
            raise RegraViolada("Há cursos repetidos na lista.")
        edital.cursos = [EditalCurso(**c.model_dump()) for c in cursos]
    if documentos is not None:
        edital.documentos = [EditalDocumentoExigido(**d.model_dump()) for d in documentos]


# --- EDT-01 / EDT-02: cadastro e edição -------------------------------------------------------------
def criar(db: Session, dados: EditalEntrada, usuario: Usuario, ip: str | None) -> Edital:
    campos = dados.model_dump(exclude={"cursos", "documentos"})
    edital = Edital(**campos, criado_por=usuario.id, status=StatusEdital.RASCUNHO)
    _substituir_listas(edital, dados.cursos, dados.documentos)
    db.add(edital)
    db.flush()
    registrar(db, usuario_id=usuario.id, acao="EDITAL_CRIAR", entidade="edital",
              entidade_id=edital.id, depois=foto(edital), ip=ip)
    db.commit()
    return carregar(db, edital.id)


def atualizar(db: Session, edital_id: int, dados: EditalAtualizacao, usuario: Usuario, ip: str | None) -> Edital:
    edital = carregar(db, edital_id, bloquear=True)
    alteracoes = dados.model_dump(exclude_unset=True)
    if not alteracoes:
        raise RegraViolada("Nenhum campo informado para alteração.")

    if edital.status in TERMINAIS:
        raise Conflito(f"Edital {edital.status.lower()} não pode ser alterado.")
    if edital.status != StatusEdital.RASCUNHO:
        proibidos = sorted(set(alteracoes) - CAMPOS_EDITAVEIS_APOS_PUBLICACAO)
        if proibidos:
            raise Conflito(
                "Edital publicado só permite alterar o texto descritivo.",
                detalhes=[f"Campo não editável após publicação: {c}" for c in proibidos],
            )

    antes = foto(edital)
    cursos = alteracoes.pop("cursos", None)
    documentos = alteracoes.pop("documentos", None)
    for campo, valor in alteracoes.items():
        setattr(edital, campo, valor)
    _substituir_listas(
        edital,
        dados.cursos if cursos is not None else None,
        dados.documentos if documentos is not None else None,
    )
    db.flush()
    acao = "EDITAL_EDITAR" if edital.status == StatusEdital.RASCUNHO else "EDITAL_EDITAR_PUBLICADO"
    registrar(db, usuario_id=usuario.id, acao=acao, entidade="edital", entidade_id=edital.id,
              antes=antes, depois=foto(edital), ip=ip)
    db.commit()
    return carregar(db, edital.id)


# --- EDT-02 / EDT-03: publicação e ciclo de vida ----------------------------------------------------
def problemas_para_publicar(db: Session, edital: Edital) -> list[str]:
    """Regras de EDT-02 (+ L-08 do plano). Retorna todos os problemas de uma vez."""
    p: list[str] = []
    if edital.data_fim_inscricao <= edital.data_inicio_inscricao:
        p.append("O fim das inscrições deve ser posterior ao início.")
    if edital.data_inicio_avaliacao < edital.data_fim_inscricao:
        p.append("O início da avaliação não pode ser anterior ao fim das inscrições.")
    if edital.data_resultado_preliminar < edital.data_inicio_avaliacao:
        p.append("O resultado preliminar não pode ser anterior ao início da avaliação.")
    if edital.data_homologacao_final < edital.data_resultado_preliminar:
        p.append("A homologação final não pode ser anterior ao resultado preliminar.")
    if edital.data_fim_inscricao <= agora(db):
        p.append("O prazo de inscrição já terminou; ajuste o cronograma.")
    if not edital.cursos:
        p.append("Informe ao menos um curso autorizado.")
    if not edital.documentos:
        p.append("Informe ao menos um documento exigido.")
    elif not any(d.obrigatorio for d in edital.documentos):
        p.append("Informe ao menos um documento obrigatório.")
    return p


def publicar(db: Session, edital_id: int, usuario: Usuario, ip: str | None) -> Edital:
    edital = carregar(db, edital_id, bloquear=True)
    # Estado é checado antes do conteúdo: publicar duas vezes é 409, não 422.
    if not MAQUINA_EDITAL.permitido(edital.status, EventoEdital.PUBLICAR):
        MAQUINA_EDITAL.proximo(edital.status, EventoEdital.PUBLICAR)
    problemas = problemas_para_publicar(db, edital)
    if problemas:
        raise RegraViolada("O edital não pode ser publicado.", detalhes=problemas)
    transicionar(db, edital, EventoEdital.PUBLICAR, usuario_id=usuario.id, ip=ip)
    db.commit()
    return edital


def iniciar_avaliacao(db: Session, edital_id: int, usuario: Usuario | None, ip: str | None = None) -> Edital:
    """INSCRICOES_ENCERRADAS -> EM_AVALIACAO (antecipação manual pelo PR ou timer do worker)."""
    edital = carregar(db, edital_id, bloquear=True)
    transicionar(db, edital, EventoEdital.INICIAR_AVALIACAO, usuario_id=usuario.id if usuario else None, ip=ip)
    db.commit()
    return edital


def cancelar(db: Session, edital_id: int, justificativa: str, usuario: Usuario, ip: str | None) -> Edital:
    """EDT-05: cancela com justificativa e notifica todos os inscritos."""
    edital = carregar(db, edital_id, bloquear=True)
    if not MAQUINA_EDITAL.permitido(edital.status, EventoEdital.CANCELAR):
        MAQUINA_EDITAL.proximo(edital.status, EventoEdital.CANCELAR)
    edital.justificativa_cancelamento = justificativa
    transicionar(db, edital, EventoEdital.CANCELAR, usuario_id=usuario.id, ip=ip)

    inscritos = db.scalars(
        select(Inscricao.estudante_id).where(
            Inscricao.edital_id == edital.id, Inscricao.status != StatusInscricao.DESISTENTE
        )
    ).all()
    for estudante_id in inscritos:
        notificar(
            db,
            usuario_id=estudante_id,
            tipo="EDITAL_CANCELADO",
            titulo=f"Edital cancelado: {edital.titulo}",
            mensagem=f"O edital \"{edital.titulo}\" foi cancelado pela Pró-Reitoria.\n\nJustificativa: {justificativa}",
        )
    db.commit()
    return edital


# --- EDT-04: comissão avaliadora ------------------------------------------------------------------
def listar_comissao(db: Session, edital_id: int) -> list[tuple[ComissaoEdital, Usuario]]:
    carregar(db, edital_id)
    return db.execute(
        select(ComissaoEdital, Usuario)
        .join(Usuario, Usuario.id == ComissaoEdital.avaliador_id)
        .where(ComissaoEdital.edital_id == edital_id)
        .order_by(Usuario.nome)
    ).all()


def designar(db: Session, edital_id: int, dados: ComissaoEntrada, usuario: Usuario, ip: str | None) -> None:
    edital = carregar(db, edital_id, bloquear=True)
    if edital.status in TERMINAIS:
        raise Conflito("Não é possível alterar a comissão de um edital encerrado ou cancelado.")

    ids = sorted(set(dados.avaliador_ids))
    usuarios = {u.id: u for u in db.scalars(select(Usuario).where(Usuario.id.in_(ids)))}
    problemas = []
    for uid in ids:
        u = usuarios.get(uid)
        if u is None:
            problemas.append(f"Usuário {uid} não existe.")
        elif u.perfil != Perfil.AVALIADOR:
            problemas.append(f"{u.nome} não possui perfil de avaliador.")
        elif not u.ativo:
            problemas.append(f"{u.nome} está inativo.")
    if problemas:
        raise RegraViolada("Designação inválida.", detalhes=problemas)

    # RN-07: ninguém pode ser avaliador e candidato no mesmo edital.
    candidatos = db.scalars(
        select(Inscricao.estudante_id).where(Inscricao.edital_id == edital.id, Inscricao.estudante_id.in_(ids))
    ).all()
    if candidatos:
        nomes = [usuarios[c].nome for c in candidatos]
        raise Conflito("Usuário inscrito no edital não pode integrar a comissão (RN-07).", detalhes=nomes)

    ja = set(db.scalars(select(ComissaoEdital.avaliador_id).where(ComissaoEdital.edital_id == edital.id)))
    for uid in ids:
        if uid in ja:
            continue
        membro = ComissaoEdital(edital_id=edital.id, avaliador_id=uid, designado_por=usuario.id)
        db.add(membro)
        db.flush()
        registrar(db, usuario_id=usuario.id, acao="COMISSAO_DESIGNAR", entidade="edital",
                  entidade_id=edital.id, depois={"avaliador_id": uid, "nome": usuarios[uid].nome}, ip=ip)
        notificar(
            db,
            usuario_id=uid,
            tipo="COMISSAO_DESIGNADO",
            titulo=f"Você foi designado(a) para a comissão: {edital.titulo}",
            mensagem=f"Você integra a comissão avaliadora do edital \"{edital.titulo}\".",
        )
    db.commit()


def remover_da_comissao(db: Session, edital_id: int, avaliador_id: int, usuario: Usuario, ip: str | None) -> None:
    edital = carregar(db, edital_id, bloquear=True)
    if edital.status in TERMINAIS:
        raise Conflito("Não é possível alterar a comissão de um edital encerrado ou cancelado.")
    membro = db.scalar(
        select(ComissaoEdital).where(ComissaoEdital.edital_id == edital.id, ComissaoEdital.avaliador_id == avaliador_id)
    )
    if membro is None:
        raise NaoEncontrado("Avaliador não integra a comissão deste edital.")
    ja_avaliou = db.scalar(
        select(
            exists().where(
                Avaliacao.avaliador_id == avaliador_id,
                Avaliacao.inscricao_id == Inscricao.id,
                Inscricao.edital_id == edital.id,
            )
        )
    )
    if ja_avaliou:
        raise Conflito("Avaliador com avaliações registradas não pode ser removido da comissão.")
    db.delete(membro)
    registrar(db, usuario_id=usuario.id, acao="COMISSAO_REMOVER", entidade="edital",
              entidade_id=edital.id, antes={"avaliador_id": avaliador_id}, ip=ip)
    db.commit()


def eh_membro_comissao(db: Session, edital_id: int, usuario_id: int) -> bool:
    return bool(
        db.scalar(
            select(exists().where(ComissaoEdital.edital_id == edital_id, ComissaoEdital.avaliador_id == usuario_id))
        )
    )


def editais_designados(db: Session, avaliador: Usuario) -> list[Edital]:
    return list(
        db.scalars(
            select(Edital)
            .join(ComissaoEdital, ComissaoEdital.edital_id == Edital.id)
            .where(ComissaoEdital.avaliador_id == avaliador.id)
            .order_by(Edital.data_inicio_avaliacao.desc())
        )
    )


# --- Consulta (base de INS-01) --------------------------------------------------------------------
def listar(
    db: Session,
    usuario: Usuario | None,
    *,
    status: list[StatusEdital] | None,
    categoria: str | None,
    modalidade: str | None,
    curso: str | None,
    valor_min: Decimal | None,
    valor_max: Decimal | None,
    busca: str | None,
    limite: int,
    deslocamento: int,
) -> tuple[list[Edital], int]:
    eh_pr = usuario is not None and usuario.perfil == Perfil.PRO_REITOR
    stmt = select(Edital)

    if status:
        stmt = stmt.where(Edital.status.in_([str(s) for s in status]))
    else:
        stmt = stmt.where(Edital.status == StatusEdital.ABERTO)  # INS-01: abertos por padrão
    if not eh_pr:
        stmt = stmt.where(Edital.status != StatusEdital.RASCUNHO)  # rascunho é interno

    if categoria:
        stmt = stmt.where(Edital.categoria == categoria)
    if modalidade:
        stmt = stmt.where(Edital.modalidade.ilike(f"%{modalidade}%"))
    if curso:
        stmt = stmt.where(
            exists().where(
                EditalCurso.edital_id == Edital.id,
                (EditalCurso.codigo_curso == curso) | EditalCurso.nome_curso.ilike(f"%{curso}%"),
            )
        )
    if valor_min is not None:
        stmt = stmt.where(Edital.valor_bolsa >= valor_min)
    if valor_max is not None:
        stmt = stmt.where(Edital.valor_bolsa <= valor_max)
    if busca:
        stmt = stmt.where(Edital.titulo.ilike(f"%{busca}%") | Edital.descricao.ilike(f"%{busca}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    itens = db.scalars(
        stmt.order_by(Edital.data_fim_inscricao.asc(), Edital.id.desc()).limit(limite).offset(deslocamento)
    ).all()
    return list(itens), total or 0


def obter_visivel(db: Session, edital_id: int, usuario: Usuario | None) -> Edital:
    edital = carregar(db, edital_id)
    if edital.status == StatusEdital.RASCUNHO and (usuario is None or usuario.perfil != Perfil.PRO_REITOR):
        raise NaoEncontrado("Edital não encontrado.")  # não revela a existência de rascunhos
    return edital
