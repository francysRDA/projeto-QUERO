"""Contratos da API de editais (EDT-01…05)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from app.domain.estados import StatusEdital

Categoria = Literal["ESTAGIO", "MONITORIA", "BOLSA"]
CriterioDesempate = Literal["CR_DESC", "SUBMISSAO_ASC"]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CursoEntrada(BaseModel):
    codigo_curso: Annotated[Texto, StringConstraints(max_length=40)]
    nome_curso: Annotated[Texto, StringConstraints(max_length=120)]


class DocumentoEntrada(BaseModel):
    nome: Annotated[Texto, StringConstraints(max_length=120)]
    descricao: str | None = None
    obrigatorio: bool = True


class _CamposEdital(BaseModel):
    titulo: Annotated[Texto, StringConstraints(max_length=200)]
    descricao: Texto
    categoria: Categoria
    modalidade: Annotated[Texto, StringConstraints(max_length=50)]
    valor_bolsa: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
    carga_horaria_semanal: Annotated[int, Field(gt=0, le=44)]
    vagas: Annotated[int, Field(gt=0)]
    cr_minimo: Annotated[Decimal, Field(ge=0, le=10, max_digits=4, decimal_places=2)]
    prazo_recurso_horas: Annotated[int, Field(gt=0)] = 48
    criterios_pontuacao: dict[str, Any] = Field(default_factory=dict)
    criterios_desempate: list[CriterioDesempate] = Field(default_factory=lambda: ["CR_DESC", "SUBMISSAO_ASC"])
    data_inicio_inscricao: AwareDatetime
    data_fim_inscricao: AwareDatetime
    data_inicio_avaliacao: AwareDatetime
    data_resultado_preliminar: AwareDatetime
    data_homologacao_final: AwareDatetime


class EditalEntrada(_CamposEdital):
    """Criação em RASCUNHO. Cursos/documentos podem ficar vazios até a publicação (EDT-02)."""

    cursos: list[CursoEntrada] = Field(default_factory=list)
    documentos: list[DocumentoEntrada] = Field(default_factory=list)


class EditalAtualizacao(BaseModel):
    """Atualização parcial. Após a publicação, apenas `descricao` pode mudar (EDT-01)."""

    titulo: Annotated[Texto, StringConstraints(max_length=200)] | None = None
    descricao: Texto | None = None
    categoria: Categoria | None = None
    modalidade: Annotated[Texto, StringConstraints(max_length=50)] | None = None
    valor_bolsa: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)] | None = None
    carga_horaria_semanal: Annotated[int, Field(gt=0, le=44)] | None = None
    vagas: Annotated[int, Field(gt=0)] | None = None
    cr_minimo: Annotated[Decimal, Field(ge=0, le=10, max_digits=4, decimal_places=2)] | None = None
    prazo_recurso_horas: Annotated[int, Field(gt=0)] | None = None
    criterios_pontuacao: dict[str, Any] | None = None
    criterios_desempate: list[CriterioDesempate] | None = None
    data_inicio_inscricao: AwareDatetime | None = None
    data_fim_inscricao: AwareDatetime | None = None
    data_inicio_avaliacao: AwareDatetime | None = None
    data_resultado_preliminar: AwareDatetime | None = None
    data_homologacao_final: AwareDatetime | None = None
    cursos: list[CursoEntrada] | None = None
    documentos: list[DocumentoEntrada] | None = None


class JustificativaEntrada(BaseModel):
    justificativa: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)]


class ComissaoEntrada(BaseModel):
    avaliador_ids: Annotated[list[int], Field(min_length=1)]


# --- Saídas -------------------------------------------------------------------------------------
class CursoSaida(CursoEntrada):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DocumentoSaida(DocumentoEntrada):
    model_config = ConfigDict(from_attributes=True)
    id: int


class EditalResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    categoria: Categoria
    modalidade: str
    valor_bolsa: Decimal
    carga_horaria_semanal: int
    vagas: int
    cr_minimo: Decimal
    status: StatusEdital
    data_inicio_inscricao: datetime
    data_fim_inscricao: datetime


class EditalSaida(EditalResumo):
    descricao: str
    prazo_recurso_horas: int
    criterios_pontuacao: dict[str, Any]
    criterios_desempate: list[str]
    data_inicio_avaliacao: datetime
    data_resultado_preliminar: datetime
    data_homologacao_final: datetime
    data_fim_recurso: datetime | None
    justificativa_cancelamento: str | None
    criado_em: datetime
    cursos: list[CursoSaida]
    documentos: list[DocumentoSaida]


class PaginaEditais(BaseModel):
    itens: list[EditalResumo]
    total: int


class MembroComissao(BaseModel):
    avaliador_id: int
    nome: str
    email: str
    designado_em: datetime


class UsuarioResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    email: str
