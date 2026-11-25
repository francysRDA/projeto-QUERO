from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import ArmazenamentoArquivos
from app.storage.disco import ArmazenamentoDisco


@lru_cache
def get_armazenamento() -> ArmazenamentoArquivos:
    """Ponto único de troca de adapter (disco hoje; S3/MinIO no futuro)."""
    return ArmazenamentoDisco(get_settings().storage_dir)
