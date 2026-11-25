"""Inscrições (UC-03, UC-05) e download protegido de arquivos (RN-15)."""

import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from starlette.datastructures import UploadFile

from app.core.deps import DB, Estudante, ProReitor, UsuarioAtual, ip_cliente
from app.core.errors import NaoEncontrado, RegraViolada
from app.core.relogio import agora
from app.integrations.academico import ServicoAcademico, get_servico_academico
from app.domain.estados import StatusInscricao
from app.models import Arquivo, Edital, EditalDocumentoExigido, Inscricao, Usuario
from app.reports.comprovante import gerar_comprovante
from app.schemas.edital import JustificativaEntrada
from app.schemas.inscricao import InscricaoGestao, InscricaoSaida
from app.services import editais as svc_editais
from app.services import homologacao as svc_homologacao
from app.services import inscricoes as svc
from app.storage import get_armazenamento
from app.storage.base import ArmazenamentoArquivos

router = APIRouter(tags=["inscricoes"])

Armazenamento = Annotated[ArmazenamentoArquivos, Depends(get_armazenamento)]
Academico = Annotated[ServicoAcademico, Depends(get_servico_academico)]
CAMPO_DOC = re.compile(r"^doc_(\d+)$")
MAX_ARQUIVOS = 20

DESCRICAO_UPLOAD = (
    "multipart/form-data com um arquivo PDF por documento exigido, no campo `doc_<documento_exigido_id>`. "
    "Cada arquivo: PDF válido (%PDF-), até 10 MB."
)


async def _ler_arquivos(request: Request) -> list[svc.ArquivoEnviado]:
    """O parser do Starlette despeja cada arquivo em disco temporário acima de 1 MB (não fica em RAM)."""
    try:
        form = await request.form(max_files=MAX_ARQUIVOS, max_fields=MAX_ARQUIVOS)
    except Exception as exc:  # corpo que não é multipart válido
        raise RegraViolada("Envie os documentos como multipart/form-data.") from exc
    arquivos, problemas = [], []
    for campo, valor in form.multi_items():
        m = CAMPO_DOC.match(campo)
        if not m:
            problemas.append(f"Campo não reconhecido: {campo}.")
        elif not isinstance(valor, UploadFile):
            problemas.append(f"O campo {campo} deve conter um arquivo.")
        else:
            arquivos.append(svc.ArquivoEnviado(int(m.group(1)), valor.file, valor.filename, valor.content_type))
    if problemas:
        raise RegraViolada("Formulário inválido.", detalhes=problemas)
    return arquivos


@router.post("/editais/{edital_id}/inscricoes", response_model=InscricaoSaida, status_code=status.HTTP_201_CREATED,
             summary="Submete inscrição com upload em streaming dos PDFs — INS-02, INS-03, INS-04",
             description=DESCRICAO_UPLOAD)
async def submeter(edital_id: int, request: Request, db: DB, usuario: Estudante, armaz: Armazenamento,
                   academico: Academico):
    arquivos = await _ler_arquivos(request)
    insc = await run_in_threadpool(
        svc.submeter, db, edital_id, usuario, arquivos, armaz, academico, ip_cliente(request)
    )
    return await run_in_threadpool(svc.montar_saida, db, insc, usuario)


@router.put("/inscricoes/{inscricao_id}/retificar", response_model=InscricaoSaida,
            summary="Substitui PDFs no prazo (mantém protocolo, data original e CR) — INS-05",
            description=DESCRICAO_UPLOAD + " Envie apenas os documentos que deseja substituir.")
async def retificar(inscricao_id: int, request: Request, db: DB, usuario: Estudante, armaz: Armazenamento):
    arquivos = await _ler_arquivos(request)
    insc = await run_in_threadpool(svc.retificar, db, inscricao_id, usuario, arquivos, armaz, ip_cliente(request))
    return await run_in_threadpool(svc.montar_saida, db, insc, usuario)


@router.post("/inscricoes/{inscricao_id}/desistir", response_model=InscricaoSaida, summary="Desiste — INS-07")
def desistir(inscricao_id: int, request: Request, db: DB, usuario: Estudante) -> InscricaoSaida:
    insc = svc.desistir(db, inscricao_id, usuario, ip_cliente(request))
    return svc.montar_saida(db, insc, usuario)


@router.get("/inscricoes/me", response_model=list[InscricaoSaida], summary="Minhas inscrições — INS-06")
def minhas(db: DB, usuario: Estudante) -> list[InscricaoSaida]:
    return [svc.montar_saida(db, i, usuario) for i in svc.minhas(db, usuario)]


@router.get("/inscricoes/{inscricao_id}", response_model=InscricaoSaida)
def obter(inscricao_id: int, db: DB, usuario: UsuarioAtual) -> InscricaoSaida:
    return svc.montar_saida(db, svc.carregar_visivel(db, inscricao_id, usuario), usuario)


@router.get("/inscricoes/{inscricao_id}/comprovante", summary="Comprovante em PDF com protocolo — INS-04",
            response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def comprovante(inscricao_id: int, db: DB, usuario: Estudante) -> Response:
    insc = svc.carregar_visivel(db, inscricao_id, usuario)
    if insc.estudante_id != usuario.id:
        raise NaoEncontrado("Inscrição não encontrada.")
    edital = db.get(Edital, insc.edital_id)
    ativos = list(db.scalars(
        select(Arquivo).where(Arquivo.inscricao_id == insc.id, Arquivo.ativo.is_(True)).order_by(Arquivo.documento_exigido_id)
    ))
    docs = {d.id: d for d in db.scalars(select(EditalDocumentoExigido).where(EditalDocumentoExigido.edital_id == edital.id))}
    pdf = gerar_comprovante(insc, edital, db.get(Usuario, insc.estudante_id), ativos, docs, agora(db))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="comprovante-{insc.protocolo}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/arquivos/{arquivo_id}/download", summary="Download protegido em streaming — RN-15, RNF-07",
            response_class=StreamingResponse, responses={200: {"content": {"application/pdf": {}}}})
def download(arquivo_id: int, request: Request, db: DB, usuario: UsuarioAtual, armaz: Armazenamento):
    arq = svc.arquivo_para_download(db, arquivo_id, usuario, ip_cliente(request))
    return StreamingResponse(
        armaz.get(arq.chave),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(arq.nome_original)}",
            "Content-Length": str(arq.tamanho_bytes),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --- UC-04: homologação formal (visão da Pró-Reitoria) ----------------------------------------------
@router.get("/editais/{edital_id}/inscricoes", response_model=list[InscricaoGestao],
            summary="Inscrições do edital para conferência e reanálise — UC-04")
def inscricoes_do_edital(
    edital_id: int, db: DB, _: ProReitor, status_: Annotated[StatusInscricao | None, Query(alias="status")] = None
) -> list[InscricaoGestao]:
    edital = svc_editais.carregar(db, edital_id)
    stmt = (
        select(Inscricao, Usuario)
        .join(Usuario, Usuario.id == Inscricao.estudante_id)
        .where(Inscricao.edital_id == edital_id)
        .order_by(Inscricao.data_submissao_original)
    )
    if status_:
        stmt = stmt.where(Inscricao.status == status_)
    return [
        InscricaoGestao(
            id=i.id, protocolo=i.protocolo, status=i.status, estudante_nome=u.nome, estudante_matricula=u.matricula,
            curso_congelado=i.curso_congelado, cr_congelado=i.cr_congelado,
            vinculo_ativo_congelado=i.vinculo_ativo_congelado, motivos_indeferimento=i.motivos_indeferimento,
            data_submissao_original=i.data_submissao_original, reanalisada=i.reanalisada_por is not None,
            justificativa_reanalise=i.justificativa_reanalise,
            pode_reanalisar=svc_homologacao.pode_reanalisar(db, edital, i),
        )
        for i, u in db.execute(stmt)
    ]


@router.post("/inscricoes/{inscricao_id}/reanalisar", response_model=InscricaoSaida,
             summary="Reanálise manual de indeferimento até o início da avaliação — RN-05, RN-14")
def reanalisar(inscricao_id: int, dados: JustificativaEntrada, request: Request, db: DB, usuario: ProReitor):
    insc = svc_homologacao.reanalisar(db, inscricao_id, dados.justificativa, usuario, ip_cliente(request))
    return svc.montar_saida(db, insc, usuario)
