"""Autenticação (TRV-02, RNF-06).

Access token curto no corpo da resposta (guardado em memória pelo SPA) e refresh token em cookie
HttpOnly + SameSite=Lax restrito ao caminho /api/v1/auth.
"""

from fastapi import APIRouter, Cookie, Request, Response, status

from app.core.config import get_settings
from app.core.deps import DB, UsuarioAtual, ip_cliente
from app.schemas.auth import LoginEntrada, TokenSaida, UsuarioSaida
from app.services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_REFRESH = "quero_refresh"


def _gravar_cookie(resp: Response, refresh: str) -> None:
    s = get_settings()
    resp.set_cookie(
        COOKIE_REFRESH,
        refresh,
        max_age=s.refresh_token_dias * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def _token(access: str) -> TokenSaida:
    return TokenSaida(access_token=access, expira_em_segundos=get_settings().access_token_minutos * 60)


@router.post("/login", response_model=TokenSaida, summary="Login local (dev/contingência sem SSO)")
def login(dados: LoginEntrada, request: Request, response: Response, db: DB) -> TokenSaida:
    usuario = svc.autenticar_local(db, dados.email, dados.senha)
    access, refresh = svc.abrir_sessao(db, usuario, ip_cliente(request))
    _gravar_cookie(response, refresh)
    return _token(access)


@router.post("/refresh", response_model=TokenSaida, summary="Renova o access token (rotaciona o refresh)")
def refresh(response: Response, db: DB, quero_refresh: str | None = Cookie(default=None)) -> TokenSaida:
    access, novo = svc.renovar_sessao(db, quero_refresh)
    _gravar_cookie(response, novo)
    return _token(access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoga a sessão atual")
def logout(request: Request, response: Response, db: DB, quero_refresh: str | None = Cookie(default=None)):
    svc.encerrar_sessao(db, quero_refresh, ip_cliente(request))
    response.delete_cookie(COOKIE_REFRESH, path="/api/v1/auth")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UsuarioSaida)
def me(usuario: UsuarioAtual) -> UsuarioSaida:
    return UsuarioSaida.model_validate(usuario)
