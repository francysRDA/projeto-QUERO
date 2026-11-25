"""Dependências FastAPI: usuário autenticado e controle de acesso por papel (TRV-02)."""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import NaoAutenticado, Proibido
from app.core.security import decodificar_access_token
from app.domain.perfis import Perfil
from app.models import Sessao, Usuario

_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def usuario_atual(
    db: DB,
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    if cred is None:
        raise NaoAutenticado("Autenticação necessária.")
    try:
        payload = decodificar_access_token(cred.credentials)
    except jwt.PyJWTError:
        raise NaoAutenticado("Token inválido ou expirado.") from None

    # Sessão revogada no logout invalida também o access token ainda não expirado.
    sessao = db.scalar(select(Sessao).where(Sessao.id == payload["sid"]))
    if sessao is None or sessao.revogada_em is not None:
        raise NaoAutenticado("Sessão encerrada.")

    usuario = db.get(Usuario, int(payload["sub"]))
    if usuario is None or not usuario.ativo:
        raise NaoAutenticado("Usuário inativo.")
    return usuario


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]


def usuario_opcional(
    db: DB,
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario | None:
    """Para rotas públicas que mostram mais conteúdo a usuários autenticados (ex.: GET /editais).
    Token presente mas inválido continua sendo erro 401 — não degrada silenciosamente para anônimo."""
    if cred is None:
        return None
    return usuario_atual(db, cred)


UsuarioOpcional = Annotated[Usuario | None, Depends(usuario_opcional)]


def exigir_perfis(*perfis: Perfil) -> Callable[[Usuario], Usuario]:
    """Uso: `usuario: Annotated[Usuario, Depends(exigir_perfis(Perfil.PRO_REITOR))]`."""

    permitidos = {str(p) for p in perfis}

    def _dep(usuario: UsuarioAtual) -> Usuario:
        if usuario.perfil not in permitidos:
            raise Proibido("Seu perfil não tem permissão para esta operação.")
        return usuario

    return _dep


ProReitor = Annotated[Usuario, Depends(exigir_perfis(Perfil.PRO_REITOR))]
Estudante = Annotated[Usuario, Depends(exigir_perfis(Perfil.ESTUDANTE))]
Avaliador = Annotated[Usuario, Depends(exigir_perfis(Perfil.AVALIADOR))]


def ip_cliente(request: Request) -> str | None:
    encaminhado = request.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else None
