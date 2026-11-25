"""Exceções de domínio e seu mapeamento para HTTP.

Regra do documento (§7): transição de estado inválida -> 409; violação de regra de entrada -> 422;
falta de permissão -> 403; não autenticado -> 401.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ErroDominio(Exception):
    status_code = 400
    codigo = "ERRO"

    def __init__(self, mensagem: str, detalhes: list[str] | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or []


class TransicaoInvalida(ErroDominio):
    status_code = 409
    codigo = "TRANSICAO_INVALIDA"


class Conflito(ErroDominio):
    status_code = 409
    codigo = "CONFLITO"


class RegraViolada(ErroDominio):
    status_code = 422
    codigo = "REGRA_VIOLADA"


class NaoAutenticado(ErroDominio):
    status_code = 401
    codigo = "NAO_AUTENTICADO"


class Proibido(ErroDominio):
    status_code = 403
    codigo = "PROIBIDO"


class NaoEncontrado(ErroDominio):
    status_code = 404
    codigo = "NAO_ENCONTRADO"


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ErroDominio)
    async def _handler(_: Request, exc: ErroDominio) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content={"codigo": exc.codigo, "mensagem": exc.mensagem, "detalhes": exc.detalhes},
            headers=headers,
        )


class ServicoIndisponivel(ErroDominio):
    status_code = 503
    codigo = "SERVICO_INDISPONIVEL"
