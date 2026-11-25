"""Ferramentas de demonstração — registradas SOMENTE com ENV=dev/test.

Permitem avançar o relógio oficial para atravessar as fases de um edital sem esperar dias.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.deps import DB, ProReitor
from app.core.errors import Conflito
from app.integrations.academico import ServicoAcademico, get_servico_academico
from app.core.relogio import agora
from app.services.homologacao import reprocessar_pendentes
from app.worker.jobs import executar_ciclo

router = APIRouter(prefix="/dev", tags=["dev"])

Academico = Annotated[ServicoAcademico, Depends(get_servico_academico)]


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
def avancar(dados: AvancarEntrada, db: DB, servico: Academico, _: ProReitor) -> RelogioSaida:
    db.execute(text("UPDATE relogio_dev SET segundos = segundos + :s WHERE id = 1"), {"s": int(dados.horas * 3600)})
    db.commit()
    executar_ciclo(db, enviar_emails=False, servico_academico=servico)
    return _estado(db)


@router.post("/relogio/zerar", response_model=RelogioSaida)
def zerar(db: DB, _: ProReitor) -> RelogioSaida:
    db.execute(text("UPDATE relogio_dev SET segundos = 0 WHERE id = 1"))
    db.commit()
    return _estado(db)


# --- Simulação do Sistema Acadêmico (INT-01) ----------------------------------------------------------
class AcademicoEstado(BaseModel):
    fora_do_ar: bool


def _simulavel(servico: ServicoAcademico):
    if not hasattr(servico, "definir_fora_do_ar"):
        raise Conflito("O Sistema Acadêmico configurado não permite simulação.")
    return servico


@router.get("/academico", response_model=AcademicoEstado)
def academico_estado(servico: Academico, _: ProReitor) -> AcademicoEstado:
    return AcademicoEstado(fora_do_ar=_simulavel(servico).fora_do_ar)


@router.put("/academico", response_model=AcademicoEstado, summary="Simula o Sistema Acadêmico fora do ar / de volta")
def academico_definir(dados: AcademicoEstado, db: DB, servico: Academico, _: ProReitor) -> AcademicoEstado:
    _simulavel(servico).definir_fora_do_ar(dados.fora_do_ar)
    if not dados.fora_do_ar:
        reprocessar_pendentes(db, servico)  # serviço voltou: reprocessa já, sem esperar o worker
    return AcademicoEstado(fora_do_ar=servico.fora_do_ar)
