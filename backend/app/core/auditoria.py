"""Trilha de auditoria imutável (RN-14).

Deve ser chamada DENTRO da mesma transação da ação auditada: se a ação falhar, o log também
não é gravado; se o log falhar, a ação é desfeita.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import AuditoriaLog


def _json(valor: Any) -> Any:
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: _json(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json(v) for v in valor]
    return valor


CAMPOS_SENSIVEIS = {"senha_hash", "refresh_hash"}


def snapshot(obj: Any) -> dict[str, Any]:
    """Foto das colunas de uma entidade ORM, para dados_antes / dados_depois."""
    return {
        c.key: _json(getattr(obj, c.key))
        for c in inspect(obj).mapper.column_attrs
        if c.key not in CAMPOS_SENSIVEIS
    }


def registrar(
    db: Session,
    *,
    usuario_id: int | None,
    acao: str,
    entidade: str,
    entidade_id: int,
    antes: dict | None = None,
    depois: dict | None = None,
    ip: str | None = None,
    destaque: bool = False,
) -> AuditoriaLog:
    log = AuditoriaLog(
        usuario_id=usuario_id,
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        dados_antes=_json(antes) if antes is not None else None,
        dados_depois=_json(depois) if depois is not None else None,
        ip_origem=ip,
        destaque=destaque,
    )
    db.add(log)
    return log
