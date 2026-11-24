"""Fatia 1 — TRV-02, RNF-06: autenticação, sessão e RBAC."""

from fastapi import APIRouter
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

import pytest

from app.core.deps import Avaliador, Estudante, ProReitor
from app.domain.perfis import Perfil
from app.main import app
from app.models import AuditoriaLog, Sessao, Usuario

from tests.conftest import SENHA

# Rotas auxiliares só para testar a matriz de RBAC.
_rbac = APIRouter(prefix="/api/v1/_teste_rbac")


@_rbac.get("/pro-reitor")
def _so_pr(u: ProReitor):
    return {"ok": u.id}


@_rbac.get("/estudante")
def _so_est(u: Estudante):
    return {"ok": u.id}


@_rbac.get("/avaliador")
def _so_av(u: Avaliador):
    return {"ok": u.id}


app.include_router(_rbac)


# --- Login -------------------------------------------------------------------------------------
def test_login_sucesso_retorna_token_e_cookie_httponly(client, criar_usuario):
    u = criar_usuario(Perfil.ESTUDANTE)
    r = client.post("/api/v1/auth/login", json={"email": u.email, "senha": SENHA})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    cookie = r.headers["set-cookie"]
    assert "quero_refresh=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/v1/auth" in cookie


def test_login_senha_errada_401_sem_revelar_existencia(client, criar_usuario):
    u = criar_usuario()
    r1 = client.post("/api/v1/auth/login", json={"email": u.email, "senha": "errada"})
    r2 = client.post("/api/v1/auth/login", json={"email": "naoexiste@teste.local", "senha": "x"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["mensagem"] == r2.json()["mensagem"]


def test_login_usuario_inativo_401(client, criar_usuario):
    u = criar_usuario(ativo=False)
    r = client.post("/api/v1/auth/login", json={"email": u.email, "senha": SENHA})
    assert r.status_code == 401


def test_senha_armazenada_com_argon2id(criar_usuario):
    u = criar_usuario()
    assert u.senha_hash.startswith("$argon2id$")
    assert SENHA not in u.senha_hash


def test_login_registra_auditoria(client, db, criar_usuario):
    u = criar_usuario()
    client.post("/api/v1/auth/login", json={"email": u.email, "senha": SENHA})
    log = db.scalar(select(AuditoriaLog).where(AuditoriaLog.usuario_id == u.id, AuditoriaLog.acao == "LOGIN"))
    assert log is not None


# --- /me ---------------------------------------------------------------------------------------
def test_me_sem_token_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_token_invalido_401(client):
    r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401


def test_me_retorna_perfil(client, criar_usuario, login):
    u = criar_usuario(Perfil.AVALIADOR)
    r = client.get("/api/v1/auth/me", headers=login(u))
    assert r.status_code == 200
    assert r.json()["perfil"] == "AVALIADOR"
    assert "senha_hash" not in r.json()


# --- Refresh e logout --------------------------------------------------------------------------
def test_refresh_rotaciona_token(client, criar_usuario, login):
    u = criar_usuario()
    login(u)
    antigo = client.cookies.get("quero_refresh")
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    novo = client.cookies.get("quero_refresh")
    assert novo and novo != antigo
    # O refresh antigo não serve mais.
    client.cookies.set("quero_refresh", antigo, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_sem_cookie_401(client):
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revoga_sessao_e_access_token(client, db, criar_usuario, login):
    u = criar_usuario()
    headers = login(u)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    assert client.post("/api/v1/auth/logout").status_code == 204

    sessao = db.scalar(select(Sessao).where(Sessao.usuario_id == u.id))
    assert sessao.revogada_em is not None
    # Access token ainda não expirado deixa de valer (RNF-06: revogação no logout).
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


# --- RBAC --------------------------------------------------------------------------------------
ROTAS = {
    Perfil.PRO_REITOR: "/api/v1/_teste_rbac/pro-reitor",
    Perfil.ESTUDANTE: "/api/v1/_teste_rbac/estudante",
    Perfil.AVALIADOR: "/api/v1/_teste_rbac/avaliador",
}


@pytest.mark.parametrize("perfil_usuario", list(Perfil))
@pytest.mark.parametrize("perfil_rota", list(Perfil))
def test_matriz_rbac(client, criar_usuario, login, perfil_usuario, perfil_rota):
    headers = login(criar_usuario(perfil_usuario))
    r = client.get(ROTAS[perfil_rota], headers=headers)
    assert r.status_code == (200 if perfil_usuario == perfil_rota else 403)


@pytest.mark.parametrize("perfil_rota", list(Perfil))
def test_rbac_sem_autenticacao_401(client, perfil_rota):
    assert client.get(ROTAS[perfil_rota]).status_code == 401


def test_usuario_desativado_perde_acesso_imediato(client, db, criar_usuario, login):
    u = criar_usuario()
    headers = login(u)
    u.ativo = False
    db.flush()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


# --- Auditoria imutável (L-09) -----------------------------------------------------------------
def test_auditoria_nao_aceita_update_nem_delete(client, db, criar_usuario):
    u = criar_usuario()
    client.post("/api/v1/auth/login", json={"email": u.email, "senha": SENHA})
    log_id = db.scalar(select(AuditoriaLog.id).where(AuditoriaLog.usuario_id == u.id))

    for sql in ("UPDATE auditoria_logs SET acao = 'X' WHERE id = :id", "DELETE FROM auditoria_logs WHERE id = :id"):
        sp = db.begin_nested()
        with pytest.raises(DBAPIError, match="imutável"):
            db.execute(text(sql), {"id": log_id})
        sp.rollback()


def test_perfil_invalido_recusado_pelo_banco(db):
    sp = db.begin_nested()
    with pytest.raises(DBAPIError):
        db.add(Usuario(nome="x", email="x@x.local", perfil="GESTOR"))
        db.flush()
    sp.rollback()
