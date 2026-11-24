from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.perfis import Perfil


class LoginEntrada(BaseModel):
    # Sem validação de formato: o login só compara com o cadastro (e .local é usado em dev).
    email: str = Field(min_length=3, max_length=120)
    senha: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _normalizar(cls, v: str) -> str:
        return v.strip().lower()


class TokenSaida(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em_segundos: int


class UsuarioSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str
    matricula: str | None
    perfil: Perfil
