from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://quero:quero@localhost:5433/quero"

    jwt_secret: str = "troque-este-segredo-em-producao"
    jwt_algoritmo: str = "HS256"
    access_token_minutos: int = 15
    refresh_token_dias: int = 7
    cookie_secure: bool = False  # True em produção (HTTPS)

    storage_dir: str = "./data/arquivos"
    tamanho_max_arquivo: int = 10 * 1024 * 1024

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_remetente: str = "nao-responda@quero.local"

    fuso: str = "America/Sao_Paulo"

    # Sistema Acadêmico (INT-01). Simulado por CSV enquanto a TI não confirma a API (DP-03).
    academico_csv: str = "./seed/academico.csv"
    academico_flag_fora_do_ar: str = "./data/academico_fora_do_ar"
    academico_tentativas: int = 3
    academico_timeout_s: float = 5.0
    academico_espera_s: float = 0.5
    reprocessamento_intervalo_s: int = 60

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.fuso)

    @property
    def is_dev(self) -> bool:
        return self.env in ("dev", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
