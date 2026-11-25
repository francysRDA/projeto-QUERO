"""Validação estrutural síncrona de PDFs (RN-04, RNF-03, RNF-04).

Lê o upload em blocos de 64 KB e, ao mesmo tempo:
  - confere a assinatura mágica %PDF- nos primeiros bytes;
  - corta o envio assim que passar de 10 MB (não lê o resto);
  - calcula o SHA-256;
  - grava em streaming no armazenamento.
Nenhum arquivo é carregado inteiro na memória.
"""

import hashlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO

from app.core.config import get_settings
from app.storage.base import TAMANHO_BLOCO, ArmazenamentoArquivos

MAGICO_PDF = b"%PDF-"
TIPOS_ACEITOS = {"application/pdf", "application/x-pdf", "application/octet-stream", ""}


class ArquivoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class ArquivoRecebido:
    chave: str
    nome_original: str
    sha256: str
    tamanho_bytes: int


def nome_seguro(nome: str | None) -> str:
    nome = (nome or "documento.pdf").replace("\\", "/").split("/")[-1].strip()
    nome = "".join(c for c in nome if c.isprintable() and c not in '<>:"|?*')
    return (nome or "documento.pdf")[:255]


def validar_cabecalho(nome: str, content_type: str | None) -> None:
    if not nome.lower().endswith(".pdf"):
        raise ArquivoInvalido(f"\"{nome}\": apenas arquivos .pdf são aceitos.")
    if (content_type or "").split(";")[0].strip().lower() not in TIPOS_ACEITOS:
        raise ArquivoInvalido(f"\"{nome}\": tipo de arquivo não permitido ({content_type}).")


def receber_pdf(
    origem: BinaryIO,
    *,
    nome_original: str | None,
    content_type: str | None,
    prefixo_chave: str,
    armazenamento: ArmazenamentoArquivos,
) -> ArquivoRecebido:
    limite = get_settings().tamanho_max_arquivo
    nome = nome_seguro(nome_original)
    validar_cabecalho(nome, content_type)

    sha = hashlib.sha256()
    estado = {"total": 0}

    def blocos() -> Iterator[bytes]:
        primeiro = True
        while bloco := origem.read(TAMANHO_BLOCO):
            if primeiro:
                if not bloco.startswith(MAGICO_PDF):
                    raise ArquivoInvalido(f"\"{nome}\": o conteúdo não é um PDF válido.")
                primeiro = False
            estado["total"] += len(bloco)
            if estado["total"] > limite:
                raise ArquivoInvalido(f"\"{nome}\": excede o limite de {limite // (1024 * 1024)} MB.")
            sha.update(bloco)
            yield bloco
        if primeiro:
            raise ArquivoInvalido(f"\"{nome}\": arquivo vazio.")

    chave = f"{prefixo_chave.rstrip('/')}/{uuid.uuid4().hex}.pdf"
    armazenamento.put(chave, blocos())  # put() apaga o temporário se blocos() lançar erro
    return ArquivoRecebido(chave=chave, nome_original=nome, sha256=sha.hexdigest(), tamanho_bytes=estado["total"])
