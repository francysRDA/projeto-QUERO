from datetime import datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.estados import StatusEdital, StatusInscricao


class ArquivoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    documento_exigido_id: int | None
    nome_original: str
    sha256: str
    tamanho_bytes: int
    versao: int
    ativo: bool
    enviado_em: datetime


class EditalDaInscricao(BaseModel):
    id: int
    titulo: str
    status: StatusEdital
    data_fim_inscricao: datetime


class ResultadoCandidato(BaseModel):
    """O que o estudante vê da própria avaliação — só após a publicação (INS-06)."""

    fase: Literal["PRELIMINAR", "POS_RECURSO", "FINAL"]
    nota: Decimal | None
    parecer: Literal["DEFERIDO", "INDEFERIDO"] | None
    justificativa: str | None
    posicao: int | None
    situacao: Literal["CONTEMPLADO", "SUPLENTE", "NAO_CLASSIFICADO"]
    total_vagas: int


class InscricaoSaida(BaseModel):
    id: int
    protocolo: str
    status: StatusInscricao
    motivos_indeferimento: list[str] | None
    vinculo_ativo_congelado: bool | None
    curso_congelado: str | None
    cr_congelado: Decimal | None
    data_submissao_original: datetime
    data_ultima_retificacao: datetime | None
    edital: EditalDaInscricao
    arquivos: list[ArquivoSaida]
    pode_retificar: bool
    pode_desistir: bool
    resultado: ResultadoCandidato | None = None  # INS-06: só após a publicação do resultado preliminar
    recurso: "RecursoResumo | None" = None
    pode_recorrer: bool = False  # AVA-03: o botão só aparece dentro da janela


class RecursoResumo(BaseModel):
    id: int
    texto: str
    status: str
    justificativa_decisao: str | None
    criado_em: datetime
    julgado_em: datetime | None
    anexo_id: int | None


InscricaoSaida.model_rebuild()


class InscricaoGestao(BaseModel):
    """Linha da conferência de inscrições pela Pró-Reitoria (UC-04)."""

    id: int
    protocolo: str
    status: StatusInscricao
    estudante_nome: str
    estudante_matricula: str | None
    curso_congelado: str | None
    cr_congelado: Decimal | None
    vinculo_ativo_congelado: bool | None
    motivos_indeferimento: list[str] | None
    data_submissao_original: datetime
    reanalisada: bool
    justificativa_reanalise: str | None
    pode_reanalisar: bool


class DadosAcademicosSaida(BaseModel):
    matricula: str
    vinculo_ativo: bool
    codigo_curso: str
    nome_curso: str
    cr: Decimal
