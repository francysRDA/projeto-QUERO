"""Dados de demonstração (somente dev). Idempotente: pode rodar várias vezes.

Uso: python -m app.seed
Senha de todos os usuários de demonstração: quero123
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_senha
from app.domain.perfis import Perfil
from app.models import Usuario

SENHA_DEMO = "quero123"

USUARIOS_DEMO: list[dict] = [
    {"nome": "Profa. Helena Prado", "email": "prograd@quero.local", "perfil": Perfil.PRO_REITOR},
    {"nome": "Prof. Carlos Menezes", "email": "carlos.avaliador@quero.local", "perfil": Perfil.AVALIADOR},
    {"nome": "Profa. Beatriz Lima", "email": "beatriz.avaliadora@quero.local", "perfil": Perfil.AVALIADOR},
    {"nome": "Prof. Rafael Souza", "email": "rafael.avaliador@quero.local", "perfil": Perfil.AVALIADOR},
    {"nome": "Ana Costa", "email": "ana@aluno.quero.local", "perfil": Perfil.ESTUDANTE, "matricula": "2023001"},
    {"nome": "Bruno Alves", "email": "bruno@aluno.quero.local", "perfil": Perfil.ESTUDANTE, "matricula": "2023002"},
    {"nome": "Camila Rocha", "email": "camila@aluno.quero.local", "perfil": Perfil.ESTUDANTE, "matricula": "2023003"},
    {"nome": "Diego Martins", "email": "diego@aluno.quero.local", "perfil": Perfil.ESTUDANTE, "matricula": "2023004"},
    {"nome": "Elisa Ferreira", "email": "elisa@aluno.quero.local", "perfil": Perfil.ESTUDANTE, "matricula": "2023005"},
    {"nome": "Felipe Nunes", "email": "felipe@aluno.quero.local", "perfil": Perfil.ESTUDANTE, "matricula": "2023006"},
]


def semear(db: Session) -> int:
    criados = 0
    senha = hash_senha(SENHA_DEMO)
    for dados in USUARIOS_DEMO:
        if db.scalar(select(Usuario.id).where(Usuario.email == dados["email"])):
            continue
        db.add(Usuario(senha_hash=senha, **{**dados, "perfil": str(dados["perfil"])}))
        criados += 1
    db.commit()
    return criados


def main() -> None:
    if not get_settings().is_dev:
        raise SystemExit("Seed de demonstração só pode rodar com ENV=dev.")
    with SessionLocal() as db:
        n = semear(db)
    print(f"Seed concluído: {n} usuário(s) criado(s). Senha de demonstração: {SENHA_DEMO}")


if __name__ == "__main__":
    main()
