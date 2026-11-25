"""Adapter de disco local (§9.2 item 20). O diretório raiz fica FORA da raiz pública do Nginx."""

import os
import uuid
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path

from app.storage.base import TAMANHO_BLOCO


class ChaveInvalida(ValueError):
    pass


class ArmazenamentoDisco:
    def __init__(self, raiz: str | os.PathLike):
        self.raiz = Path(raiz).resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def _caminho(self, chave: str) -> Path:
        partes = chave.split("/")  # segmentos crus: não normaliza "a//b" nem "a/./b"
        if not chave or "\\" in chave or any(p in ("..", ".", "") for p in partes):
            raise ChaveInvalida(f"Chave inválida: {chave!r}")
        caminho = (self.raiz / Path(*partes)).resolve()
        if self.raiz not in caminho.parents:  # defesa extra contra path traversal
            raise ChaveInvalida(f"Chave fora do armazenamento: {chave!r}")
        return caminho

    def put(self, chave: str, blocos: Iterable[bytes], *, somente_leitura: bool = False) -> int:
        destino = self._caminho(chave)
        if somente_leitura and destino.exists():
            raise FileExistsError(f"Documento somente leitura já existe: {chave}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.parcial")
        total = 0
        try:
            with open(temporario, "wb") as f:
                for bloco in blocos:
                    f.write(bloco)
                    total += len(bloco)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporario, destino)  # rename atômico: nunca existe arquivo pela metade na chave
            if somente_leitura:
                os.chmod(destino, 0o444)
        except BaseException:
            temporario.unlink(missing_ok=True)
            raise
        return total

    def get(self, chave: str) -> Iterator[bytes]:
        caminho = self._caminho(chave)
        if not caminho.is_file():
            raise FileNotFoundError(chave)

        def _ler() -> Iterator[bytes]:
            with open(caminho, "rb") as f:
                while bloco := f.read(TAMANHO_BLOCO):
                    yield bloco

        return _ler()

    def delete(self, chave: str) -> None:
        self._caminho(chave).unlink(missing_ok=True)

    def listar(self) -> Iterator[tuple[str, datetime]]:
        for caminho in self.raiz.rglob("*"):
            if caminho.is_file():
                chave = caminho.relative_to(self.raiz).as_posix()
                modificado = datetime.fromtimestamp(caminho.stat().st_mtime, tz=timezone.utc)
                yield chave, modificado
