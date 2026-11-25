"""Infra de testes: PostgreSQL real (DoD §4.7 — sem banco em memória).

- Cria o banco `quero_test` (se não existir) no mesmo servidor do DATABASE_URL e aplica as migrations.
- Cada teste roda dentro de uma transação que é desfeita no final (isolamento + velocidade).
"""

import os

os.environ.setdefault("ENV", "test")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.domain.perfis import Perfil  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Usuario  # noqa: E402
from app.storage import get_armazenamento  # noqa: E402
from app.storage.disco import ArmazenamentoDisco  # noqa: E402

SENHA = "senha-de-teste"
_HASH = hash_senha(SENHA)  # Argon2 é lento de propósito: calcula uma vez só.


@pytest.fixture(scope="session")
def engine():
    url = make_url(get_settings().database_url)
    url_teste = url.set(database="quero_test")

    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("DROP DATABASE IF EXISTS quero_test WITH (FORCE)"))
        c.execute(text("CREATE DATABASE quero_test"))
    admin.dispose()

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={url_teste.render_as_string(hide_password=False)}"]})()
    command.upgrade(cfg, "head")

    eng = create_engine(url_teste)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    conn = engine.connect()
    trans = conn.begin()
    sessao = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield sessao
    finally:
        sessao.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def armazenamento(tmp_path) -> ArmazenamentoDisco:
    """Cada teste grava PDFs num diretório temporário próprio."""
    return ArmazenamentoDisco(tmp_path / "arquivos")


@pytest.fixture
def client(db: Session, armazenamento) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_armazenamento] = lambda: armazenamento
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def criar_usuario(db: Session):
    contador = {"n": 0}

    def _criar(perfil: Perfil = Perfil.ESTUDANTE, **extra) -> Usuario:
        contador["n"] += 1
        n = contador["n"]
        u = Usuario(
            nome=extra.pop("nome", f"Usuário {n}"),
            email=extra.pop("email", f"u{n}-{perfil.lower()}@teste.local"),
            perfil=str(perfil),
            senha_hash=_HASH,
            **extra,
        )
        db.add(u)
        db.flush()
        return u

    return _criar


@pytest.fixture
def login(client: TestClient):
    """Faz login e devolve headers Authorization prontos para uso."""

    def _login(usuario: Usuario) -> dict[str, str]:
        r = client.post("/api/v1/auth/login", json={"email": usuario.email, "senha": SENHA})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
