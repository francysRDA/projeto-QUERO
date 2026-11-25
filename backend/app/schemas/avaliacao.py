"""Contratos da avaliação de mérito e da classificação (AVA-01, AVA-02)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.estados import StatusAvaliacao, StatusEdital
from app.schemas.inscricao import ArquivoSaida

Nota = Annotated[Decimal, Field(ge=0, le=10, max_digits=4, decimal_places=2)]
Parecer = Literal["DEFERIDO", "INDEFERIDO"]


class AvaliacaoEntrada(BaseModel):
    """`acao`: RASCUNHO (salva parcial), CONFIRMAR (exige tudo + declaração) ou RETIFICAR (exige motivo)."""

    acao: Literal["RASCUNHO", "CONFIRMAR", "RETIFICAR"]
    nota_merito: Nota | None = None
    parecer: Parecer | None = None
    justificativa: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None
    declaracao_sem_impedimento: bool = False
    justificativa_retificacao: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None


class ImpedimentoEntrada(BaseModel):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)]


class AvaliacaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inscricao_id: int
    avaliador_id: int
    declaracao_sem_impedimento: bool
    nota_merito: Decimal | None
    parecer: Parecer | None
    justificativa: str | None
    status: StatusAvaliacao
    justificativa_retificacao: str | None
    atualizado_em: datetime


class ItemFila(BaseModel):
    inscricao_id: int
    protocolo: str
    estudante_nome: str
    curso_congelado: str | None
    cr_congelado: Decimal | None
    data_submissao_original: datetime
    arquivos: list[ArquivoSaida]
    avaliacao: AvaliacaoSaida | None


class Progresso(BaseModel):
    homologadas: int
    confirmadas: int
    em_rascunho: int
    nao_iniciadas: int
    sem_avaliador_disponivel: list[str]  # protocolos em que todos os membros declararam impedimento
    pode_publicar: bool


class FilaSaida(BaseModel):
    edital_id: int
    edital_titulo: str
    edital_status: StatusEdital
    pode_avaliar: bool
    itens: list[ItemFila]
    progresso: Progresso


class ItemClassificacao(BaseModel):
    posicao: int | None
    inscricao_id: int
    protocolo: str
    estudante_nome: str
    nota: Decimal | None
    parecer: Parecer | None
    cr_congelado: Decimal | None
    data_submissao_original: datetime
    situacao: Literal["CONTEMPLADO", "SUPLENTE", "NAO_CLASSIFICADO"]


class ClassificacaoSaida(BaseModel):
    edital_id: int
    fase: Literal["PREVIA", "PRELIMINAR", "POS_RECURSO", "FINAL"]
    publicada: bool
    vagas: int
    itens: list[ItemClassificacao]
