"""Relógio oficial do sistema (RN-03): horário do servidor no fuso America/Sao_Paulo.

Em dev/test é possível deslocar o relógio para demonstrar prazos sem esperar (ver PLANO_PROTOTIPO §2.2).
O deslocamento fica no banco (tabela `relogio_dev`) para que API e worker enxerguem o mesmo tempo.
"""

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings


def agora(db: Session | None = None) -> datetime:
    settings = get_settings()
    atual = datetime.now(settings.tz)
    if db is not None and settings.is_dev:
        deslocamento = db.execute(text("SELECT segundos FROM relogio_dev WHERE id = 1")).scalar()
        if deslocamento:
            atual += timedelta(seconds=deslocamento)
    return atual
