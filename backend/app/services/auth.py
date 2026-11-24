"""Autenticação local (dev/contingência — DP-02) e ciclo de vida de sessões.

Quando o SSO institucional for confirmado, um ProvedorIdentidade OIDC/SAML produzirá o `Usuario`
e reutilizará `abrir_sessao` — o restante do sistema não muda.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auditoria import registrar
from app.core.config import get_settings
from app.core.errors import NaoAutenticado
from app.core.security import criar_access_token, hash_refresh, novo_refresh_token, verificar_senha
from app.models import Sessao, Usuario


def autenticar_local(db: Session, email: str, senha: str) -> Usuario:
    usuario = db.scalar(select(Usuario).where(Usuario.email == email.lower()))
    # Mensagem única para não revelar se o e-mail existe.
    if usuario is None or not usuario.ativo or not verificar_senha(senha, usuario.senha_hash):
        raise NaoAutenticado("E-mail ou senha inválidos.")
    return usuario


def abrir_sessao(db: Session, usuario: Usuario, ip: str | None) -> tuple[str, str]:
    """Cria sessão e devolve (access_token, refresh_token)."""
    s = get_settings()
    refresh, refresh_h = novo_refresh_token()
    sessao = Sessao(
        usuario_id=usuario.id,
        refresh_hash=refresh_h,
        expira_em=datetime.now(timezone.utc) + timedelta(days=s.refresh_token_dias),
        ip_origem=ip,
    )
    db.add(sessao)
    db.flush()
    registrar(db, usuario_id=usuario.id, acao="LOGIN", entidade="usuario", entidade_id=usuario.id, ip=ip)
    db.commit()
    return criar_access_token(usuario.id, usuario.perfil, sessao.id), refresh


def renovar_sessao(db: Session, refresh: str | None) -> tuple[str, str]:
    """Rotaciona o refresh token: o anterior é revogado e um novo é emitido."""
    if not refresh:
        raise NaoAutenticado("Sessão ausente.")
    sessao = db.scalar(select(Sessao).where(Sessao.refresh_hash == hash_refresh(refresh)))
    agora = datetime.now(timezone.utc)
    if sessao is None or sessao.revogada_em is not None or sessao.expira_em <= agora:
        raise NaoAutenticado("Sessão expirada ou revogada.")
    usuario = db.get(Usuario, sessao.usuario_id)
    if usuario is None or not usuario.ativo:
        raise NaoAutenticado("Usuário inativo.")

    novo, novo_h = novo_refresh_token()
    sessao.refresh_hash = novo_h
    sessao.expira_em = agora + timedelta(days=get_settings().refresh_token_dias)
    db.commit()
    return criar_access_token(usuario.id, usuario.perfil, sessao.id), novo


def encerrar_sessao(db: Session, refresh: str | None, ip: str | None) -> None:
    if not refresh:
        return
    sessao = db.scalar(select(Sessao).where(Sessao.refresh_hash == hash_refresh(refresh)))
    if sessao is None or sessao.revogada_em is not None:
        return
    sessao.revogada_em = datetime.now(timezone.utc)
    registrar(db, usuario_id=sessao.usuario_id, acao="LOGOUT", entidade="usuario",
              entidade_id=sessao.usuario_id, ip=ip)
    db.commit()
