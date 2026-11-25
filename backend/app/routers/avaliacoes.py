"""Avaliação de mérito e classificação (UC-07: AVA-01, AVA-02)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.deps import DB, Avaliador, UsuarioAtual, exigir_perfis, ip_cliente
from app.core.errors import NaoEncontrado
from app.domain.perfis import Perfil
from app.models import Usuario
from app.schemas.avaliacao import (
    AvaliacaoEntrada,
    AvaliacaoSaida,
    ClassificacaoSaida,
    FilaSaida,
    ImpedimentoEntrada,
    Progresso,
)
from app.schemas.edital import EditalSaida
from app.services import avaliacoes as svc
from app.services import editais as svc_editais

router = APIRouter(tags=["avaliacao"])

ComissaoOuPR = Annotated[Usuario, Depends(exigir_perfis(Perfil.AVALIADOR, Perfil.PRO_REITOR))]


def _exigir_acesso_gestao(db, edital_id: int, usuario: Usuario):
    edital = svc_editais.carregar(db, edital_id)
    if usuario.perfil == Perfil.AVALIADOR and not svc_editais.eh_membro_comissao(db, edital_id, usuario.id):
        raise NaoEncontrado("Edital não encontrado entre as suas comissões.")
    return edital


@router.get("/editais/{edital_id}/avaliacoes", response_model=FilaSaida,
            summary="Fila de inscrições homologadas do edital designado — AVA-01, RN-06, RN-07")
def fila(edital_id: int, db: DB, usuario: Avaliador) -> FilaSaida:
    return svc.fila(db, edital_id, usuario)


@router.get("/editais/{edital_id}/avaliacoes/progresso", response_model=Progresso)
def progresso(edital_id: int, db: DB, usuario: ComissaoOuPR) -> Progresso:
    return svc.progresso(db, _exigir_acesso_gestao(db, edital_id, usuario))


@router.put("/inscricoes/{inscricao_id}/avaliacao", response_model=AvaliacaoSaida,
            summary="Salva rascunho, confirma ou retifica a avaliação — AVA-01, RN-07, RN-08, §7.3")
def salvar(inscricao_id: int, dados: AvaliacaoEntrada, request: Request, db: DB, usuario: Avaliador) -> AvaliacaoSaida:
    return AvaliacaoSaida.model_validate(svc.salvar(db, inscricao_id, dados, usuario, ip_cliente(request)))


@router.post("/inscricoes/{inscricao_id}/impedimento", status_code=status.HTTP_204_NO_CONTENT,
             summary="Declara impedimento/suspeição; a inscrição vai para outro membro — RN-07, UC-07 E1")
def impedimento(inscricao_id: int, dados: ImpedimentoEntrada, request: Request, db: DB, usuario: Avaliador) -> None:
    svc.declarar_impedimento(db, inscricao_id, dados.motivo, usuario, ip_cliente(request))


@router.post("/editais/{edital_id}/resultado-preliminar", response_model=EditalSaida,
             summary="Calcula a classificação, publica o preliminar e abre o recurso — AVA-02, RN-09, RN-10, RN-12")
def publicar_preliminar(edital_id: int, request: Request, db: DB, usuario: ComissaoOuPR) -> EditalSaida:
    svc.publicar_preliminar(db, edital_id, usuario, ip_cliente(request))
    return EditalSaida.model_validate(svc_editais.carregar(db, edital_id))


@router.get("/editais/{edital_id}/classificacao", response_model=ClassificacaoSaida,
            summary="Classificação publicada (todos) ou prévia (comissão e Pró-Reitoria)")
def classificacao(edital_id: int, db: DB, usuario: UsuarioAtual) -> ClassificacaoSaida:
    edital = svc_editais.carregar(db, edital_id)
    if edital.status in svc.STATUS_RESULTADO_PUBLICADO:
        fase, linhas = svc.classificacao_atual(db, edital)
        itens = svc.montar_itens(db, [(c.inscricao_id, c.posicao, c.nota, c.situacao) for c in linhas])
        return ClassificacaoSaida(edital_id=edital.id, fase=fase, publicada=True, vagas=edital.vagas, itens=itens)

    # Antes da publicação: só comissão designada e Pró-Reitoria veem a prévia (INS-06 para os demais).
    if usuario.perfil == Perfil.ESTUDANTE:
        raise NaoEncontrado("Resultado ainda não publicado.")
    _exigir_acesso_gestao(db, edital_id, usuario)
    posicoes = svc.calcular(db, edital)
    itens = svc.montar_itens(db, [(p.inscricao_id, p.posicao, p.nota, p.situacao) for p in posicoes])
    return ClassificacaoSaida(edital_id=edital.id, fase="PREVIA", publicada=False, vagas=edital.vagas, itens=itens)
