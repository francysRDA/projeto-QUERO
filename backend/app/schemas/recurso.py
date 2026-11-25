"""Contratos de recursos (AVA-03, AVA-04; RN-10, RN-11)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.domain.estados import StatusRecurso
from app.schemas.inscricao import ArquivoSaida

TAMANHO_MAX_TEXTO = 5000
MIN_JUSTIFICATIVA_REFORCADA = 100  # RN-11: comissão de um único membro


class JulgamentoEntrada(BaseModel):
    decisao: Literal["DEFERIDO", "INDEFERIDO"]
    justificativa: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)]
    nova_nota: Annotated[Decimal, Field(ge=0, le=10, max_digits=4, decimal_places=2)] | None = None
    novo_parecer: Literal["DEFERIDO", "INDEFERIDO"] | None = None


class RecursoSaida(BaseModel):
    id: int
    inscricao_id: int
    texto: str
    anexo: ArquivoSaida | None
    status: StatusRecurso
    justificativa_decisao: str | None
    criado_em: datetime
    julgado_em: datetime | None


class RecursoGestao(RecursoSaida):
    protocolo: str
    estudante_nome: str
    nota_atual: Decimal | None
    parecer_atual: Literal["DEFERIDO", "INDEFERIDO"] | None
    autor_parecer_id: int | None
    autor_parecer_nome: str | None
    julgado_por_nome: str | None
    pode_julgar: bool
    motivo_bloqueio: str | None
    comissao_unica: bool  # RN-11: exige justificativa reforçada


class PainelRecursos(BaseModel):
    edital_id: int
    data_fim_recurso: datetime | None
    janela_aberta: bool
    recursos: list[RecursoGestao]
