"""Consulta da trilha de auditoria (TRV-03). Somente leitura — não existe operação de edição ou exclusão."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Arquivo, AuditoriaLog, Avaliacao, Inscricao, Recurso, Usuario


def _filtro_inscricoes(inscricoes_ids):
    """Tudo que pertence a um conjunto de inscrições: a própria inscrição, avaliação, recurso e arquivos."""
    return or_(
        and_(AuditoriaLog.entidade == "inscricao", AuditoriaLog.entidade_id.in_(inscricoes_ids)),
        and_(AuditoriaLog.entidade == "avaliacao",
             AuditoriaLog.entidade_id.in_(select(Avaliacao.id).where(Avaliacao.inscricao_id.in_(inscricoes_ids)))),
        and_(AuditoriaLog.entidade == "recurso",
             AuditoriaLog.entidade_id.in_(select(Recurso.id).where(Recurso.inscricao_id.in_(inscricoes_ids)))),
        and_(AuditoriaLog.entidade == "arquivo",
             AuditoriaLog.entidade_id.in_(select(Arquivo.id).where(Arquivo.inscricao_id.in_(inscricoes_ids)))),
    )


def consultar(
    db: Session,
    *,
    edital_id: int | None,
    inscricao_id: int | None,
    acao: str | None,
    somente_destaques: bool,
    limite: int,
    deslocamento: int,
) -> tuple[list[tuple[AuditoriaLog, str | None]], int]:
    stmt = select(AuditoriaLog, Usuario.nome).outerjoin(Usuario, Usuario.id == AuditoriaLog.usuario_id)
    if inscricao_id is not None:
        stmt = stmt.where(_filtro_inscricoes(select(Inscricao.id).where(Inscricao.id == inscricao_id)))
    elif edital_id is not None:
        do_edital = select(Inscricao.id).where(Inscricao.edital_id == edital_id)
        stmt = stmt.where(or_(
            and_(AuditoriaLog.entidade == "edital", AuditoriaLog.entidade_id == edital_id),
            _filtro_inscricoes(do_edital),
        ))
    if acao:
        stmt = stmt.where(AuditoriaLog.acao.ilike(f"%{acao}%"))
    if somente_destaques:
        stmt = stmt.where(AuditoriaLog.destaque.is_(True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    linhas = db.execute(stmt.order_by(AuditoriaLog.id.desc()).limit(limite).offset(deslocamento)).all()
    return [(log, nome) for log, nome in linhas], total
