"""Infra de testes: PostgreSQL real (DoD §4.7 — sem banco em memória).

- Cria o banco `quero_test` (se não existir) no mesmo servidor do DATABASE_URL e aplica as migrations.
- Cada teste roda dentro de uma transação que é desfeita no final (isolamento + velocidade).
"""

import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("ACADEMICO_ESPERA_S", "0")  # sem espera entre retentativas nos testes

from collections.abc import Iterator  # noqa: E402
from decimal import Decimal  # noqa: E402

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
from app.integrations.academico import (  # noqa: E402
    AcademicoIndisponivel,
    DadosAcademicos,
    get_servico_academico,
)
from app.models import Usuario  # noqa: E402
from app.storage import get_armazenamento  # noqa: E402
from app.storage.disco import ArmazenamentoDisco  # noqa: E402
from tests.fabricas import URL as URL_EDITAIS  # noqa: E402
from tests.fabricas import payload  # noqa: E402

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


class AcademicoFalso:
    """Sistema Acadêmico programável para testes (mesmo contrato de ServicoAcademico)."""

    def __init__(self):
        self.dados: dict[str, DadosAcademicos] = {}
        self.fora_do_ar = False
        self.chamadas = 0

    def cadastrar(self, matricula: str, *, curso: str = "MAT", nome_curso: str = "Matemática",
                  cr: str = "8.00", ativo: bool = True) -> None:
        self.dados[matricula] = DadosAcademicos(matricula, ativo, curso, nome_curso, Decimal(cr))

    def definir_fora_do_ar(self, valor: bool) -> None:
        self.fora_do_ar = valor

    def consultar(self, matricula: str) -> DadosAcademicos | None:
        self.chamadas += 1
        if self.fora_do_ar:
            raise AcademicoIndisponivel("fora do ar (teste)")
        return self.dados.get(matricula)


@pytest.fixture
def academico() -> AcademicoFalso:
    return AcademicoFalso()


@pytest.fixture
def client(db: Session, armazenamento, academico) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_armazenamento] = lambda: armazenamento
    app.dependency_overrides[get_servico_academico] = lambda: academico
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


# --- Fixtures de domínio compartilhadas (editais / inscrições) ----------------------------------------
@pytest.fixture
def pr(criar_usuario, login):
    """Pró-Reitor autenticado: (usuario, headers)."""
    u = criar_usuario(Perfil.PRO_REITOR)
    return u, login(u)


@pytest.fixture
def edital(client, pr):
    """Edital ABERTO com 2 documentos obrigatórios e 1 opcional."""
    docs = [
        {"nome": "Histórico escolar", "obrigatorio": True},
        {"nome": "Carta de motivação", "obrigatorio": True},
        {"nome": "Currículo Lattes", "obrigatorio": False},
    ]
    r = client.post(URL_EDITAIS, json=payload(documentos=docs), headers=pr[1])
    ed = r.json()
    assert client.post(f"{URL_EDITAIS}/{ed['id']}/publicar", headers=pr[1]).status_code == 200
    return ed


@pytest.fixture
def estudante(criar_usuario, login, academico):
    """Estudante elegível: vínculo ativo, curso MAT (autorizado no edital padrão), CR 8,00."""
    u = criar_usuario(Perfil.ESTUDANTE, matricula=f"M{os.urandom(3).hex()}")
    academico.cadastrar(u.matricula)
    return u, login(u)


