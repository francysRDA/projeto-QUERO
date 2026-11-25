from datetime import datetime
from decimal import Decimal

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
