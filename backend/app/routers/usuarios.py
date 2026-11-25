from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import DB, ProReitor
from app.domain.perfis import Perfil
from app.models import Usuario
from app.schemas.edital import UsuarioResumo

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("/avaliadores", response_model=list[UsuarioResumo], summary="Avaliadores ativos (para designar comissão)")
def avaliadores(db: DB, _: ProReitor) -> list[UsuarioResumo]:
    return [
        UsuarioResumo.model_validate(u)
        for u in db.scalars(
            select(Usuario).where(Usuario.perfil == Perfil.AVALIADOR, Usuario.ativo.is_(True)).order_by(Usuario.nome)
        )
    ]
