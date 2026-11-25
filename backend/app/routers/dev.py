"""Ferramentas de demonstração — registradas SOMENTE com ENV=dev/test.

Permitem avançar o relógio oficial para atravessar as fases de um edital sem esperar dias.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.deps import DB, ProReitor
from app.core.relogio import agora
from app.worker.jobs import executar_ciclo

router = APIRouter(prefix="/dev", tags=["dev"])


class RelogioSaida(BaseModel):
    agora: datetime
    deslocamento_segundos: int


class AvancarEntrada(BaseModel):
    horas: Annotated[float, Field(gt=0, le=24 * 365)]


def _estado(db) -> RelogioSaida:
    seg = db.execute(text("SELECT segundos FROM relogio_dev WHERE id = 1")).scalar() or 0
    return RelogioSaida(agora=agora(db), deslocamento_segundos=seg)


@router.get("/relogio", response_model=RelogioSaida)
def ver(db: DB, _: ProReitor) -> RelogioSaida:
    return _estado(db)


@router.post("/relogio/avancar", response_model=RelogioSaida,
             summary="Avança o relógio e já executa as transições temporais")
def avancar(dados: AvancarEntrada, db: DB, _: ProReitor) -> RelogioSaida:
    db.execute(text("UPDATE relogio_dev SET segundos = segundos + :s WHERE id = 1"), {"s": int(dados.horas * 3600)})
    db.commit()
    executar_ciclo(db, enviar_emails=False)
    return _estado(db)


@router.post("/relogio/zerar", response_model=RelogioSaida)
def zerar(db: DB, _: ProReitor) -> RelogioSaida:
    db.execute(text("UPDATE relogio_dev SET segundos = 0 WHERE id = 1"))
    db.commit()
    return _estado(db)
