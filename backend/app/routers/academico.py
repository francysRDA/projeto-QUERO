"""Consulta dos próprios dados acadêmicos antes da inscrição (UC-03 passo 7, INT-01)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import Estudante
from app.core.errors import NaoEncontrado, ServicoIndisponivel
from app.integrations import academico
from app.integrations.academico import AcademicoIndisponivel, ServicoAcademico, get_servico_academico
from app.schemas.inscricao import DadosAcademicosSaida

router = APIRouter(prefix="/academico", tags=["academico"])


@router.get("/me", response_model=DadosAcademicosSaida, summary="Meus dados no Sistema Acadêmico")
def meus_dados(
    usuario: Estudante, servico: Annotated[ServicoAcademico, Depends(get_servico_academico)]
) -> DadosAcademicosSaida:
    if not usuario.matricula:
        raise NaoEncontrado("Seu cadastro não possui matrícula.")
    try:
        dados = academico.consultar(servico, usuario.matricula)
    except AcademicoIndisponivel:
        raise ServicoIndisponivel(
            "O Sistema Acadêmico está indisponível no momento. Você ainda pode se inscrever: "
            "o vínculo será validado automaticamente depois."
        ) from None
    if dados is None:
        raise NaoEncontrado("Matrícula não localizada no Sistema Acadêmico.")
    return DadosAcademicosSaida(**dados.__dict__)
