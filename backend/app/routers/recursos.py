"""Recursos (UC-08: AVA-03, AVA-04)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.deps import DB, Avaliador, Estudante, exigir_perfis, ip_cliente
from app.core.errors import RegraViolada
from app.domain.perfis import Perfil
from app.models import Usuario
from app.schemas.recurso import JulgamentoEntrada, PainelRecursos, RecursoSaida
from app.services import recursos as svc
from app.storage import get_armazenamento
from app.storage.base import ArmazenamentoArquivos

router = APIRouter(tags=["recursos"])

ComissaoOuPR = Annotated[Usuario, Depends(exigir_perfis(Perfil.AVALIADOR, Perfil.PRO_REITOR))]


@router.post("/inscricoes/{inscricao_id}/recursos", response_model=RecursoSaida, status_code=status.HTTP_201_CREATED,
             summary="Interpõe recurso único na janela do edital — AVA-03, RN-10",
             description="multipart/form-data: `texto` (até 5.000 caracteres) e `anexo` opcional (PDF até 10 MB).")
async def interpor(inscricao_id: int, request: Request, db: DB, usuario: Estudante,
                   armaz: Annotated[ArmazenamentoArquivos, Depends(get_armazenamento)]) -> RecursoSaida:
    try:
        form = await request.form(max_files=1, max_fields=2)
    except Exception as exc:
        raise RegraViolada("Envie o recurso como multipart/form-data.") from exc
    texto = form.get("texto")
    if not isinstance(texto, str):
        raise RegraViolada("Campo obrigatório: texto.")
    anexo = form.get("anexo")
    dados_anexo = None
    if isinstance(anexo, UploadFile) and anexo.filename:
        dados_anexo = (anexo.file, anexo.filename, anexo.content_type)
    recurso = await run_in_threadpool(svc.interpor, db, inscricao_id, usuario, texto, dados_anexo, armaz,
                                      ip_cliente(request))
    return svc.recurso_da_inscricao(db, recurso.inscricao_id)


@router.post("/recursos/{recurso_id}/julgar", response_model=RecursoSaida,
             summary="Julga recurso (autor do parecer bloqueado se comissão ≥ 2) — AVA-04, RN-11")
def julgar(recurso_id: int, dados: JulgamentoEntrada, request: Request, db: DB, usuario: Avaliador) -> RecursoSaida:
    recurso = svc.julgar(db, recurso_id, dados, usuario, ip_cliente(request))
    return svc.recurso_da_inscricao(db, recurso.inscricao_id)


@router.get("/editais/{edital_id}/recursos", response_model=PainelRecursos,
            summary="Recursos do edital para a comissão designada e a Pró-Reitoria")
def painel(edital_id: int, db: DB, usuario: ComissaoOuPR) -> PainelRecursos:
    return svc.painel(db, edital_id, usuario)
