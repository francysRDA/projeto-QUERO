"""Interface de armazenamento de arquivos (§9.2 item 19).

A aplicação só conhece CHAVES lógicas (ex.: editais/1/inscricoes/7/<uuid>.pdf), nunca caminhos.
Trocar o disco local por MinIO/Garage/S3 = implementar outro adapter (§9.2 item 21).
"""

from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Protocol

TAMANHO_BLOCO = 64 * 1024  # §9.2 item 20: streaming em blocos de 64 KB


class ArmazenamentoArquivos(Protocol):
    def put(self, chave: str, blocos: Iterable[bytes], *, somente_leitura: bool = False) -> int:
        """Grava o conteúdo de forma atômica e devolve o total de bytes gravados.
        `somente_leitura`: documentos oficiais (ata) não podem ser sobrescritos (HOM-02)."""

    def get(self, chave: str) -> Iterator[bytes]:
        """Lê o conteúdo em blocos."""

    def delete(self, chave: str) -> None:
        """Remove a chave (sem erro se não existir)."""

    def listar(self) -> Iterator[tuple[str, datetime]]:
        """Todas as chaves e a data de modificação (usado na limpeza de órfãos)."""
