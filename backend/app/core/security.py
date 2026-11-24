"""Hash de senha (Argon2id) e tokens JWT (RNF-06)."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()  # argon2id por padrão


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def verificar_senha(senha: str, hash_: str | None) -> bool:
    if not hash_:
        return False
    try:
        return _hasher.verify(hash_, senha)
    except (VerifyMismatchError, InvalidHashError):
        return False


def criar_access_token(usuario_id: int, perfil: str, sessao_id: int) -> str:
    s = get_settings()
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "perfil": perfil,
        "sid": sessao_id,
        "iat": agora,
        "exp": agora + timedelta(minutes=s.access_token_minutos),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algoritmo)


def decodificar_access_token(token: str) -> dict:
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algoritmo])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("tipo de token inválido")
    return payload


def novo_refresh_token() -> tuple[str, str]:
    """Retorna (token em claro para o cookie, hash SHA-256 para o banco)."""
    token = secrets.token_urlsafe(48)
    return token, hash_refresh(token)


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
