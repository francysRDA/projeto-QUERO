"""Homologação final, notificações e auditoria (UC-09, UC-10: HOM-01, HOM-02, TRV-01, TRV-03)."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update

from app.core.deps import DB, ProReitor, UsuarioAtual, ip_cliente
from app.core.errors import NaoEncontrado
from app.models import Arquivo, Notificacao, Usuario
from app.schemas.edital import EditalSaida, JustificativaEntrada
from app.services import auditoria_consulta
from app.services import editais as svc_editais
from app.services import homologacao_final as svc
from app.storage import get_armazenamento
from app.storage.base import ArmazenamentoArquivos

router = APIRouter()


# --- HOM-01 / HOM-02 ---------------------------------------------------------------------------------
class AtaSaida(BaseModel):
    id: int
    edital_id: int
    homologado_por: str
    homologado_em: datetime
    eh_retificacao: bool
    arquivo_pdf_id: int
    arquivo_csv_id: int
    pdf_sha256: str
    csv_sha256: str


def _ata_saida(db, ata) -> AtaSaida:
    pdf, csv = db.get(Arquivo, ata.arquivo_pdf_id), db.get(Arquivo, ata.arquivo_csv_id)
    return AtaSaida(
        id=ata.id, edital_id=ata.edital_id, homologado_por=db.get(Usuario, ata.homologado_por).nome,
        homologado_em=ata.homologado_em, eh_retificacao=ata.eh_retificacao, arquivo_pdf_id=pdf.id,
        arquivo_csv_id=csv.id, pdf_sha256=pdf.sha256, csv_sha256=csv.sha256,
    )


@router.post("/editais/{edital_id}/homologar-final", response_model=AtaSaida, tags=["homologacao"],
             summary="Homologa o resultado final, gera ata PDF e listas CSV — HOM-01, HOM-02, RN-13")
def homologar(edital_id: int, request: Request, db: DB, usuario: ProReitor,
              armaz: Annotated[ArmazenamentoArquivos, Depends(get_armazenamento)]) -> AtaSaida:
    return _ata_saida(db, svc.homologar(db, edital_id, usuario, armaz, ip_cliente(request)))


@router.post("/editais/{edital_id}/devolver-ajustes", response_model=EditalSaida, tags=["homologacao"],
             summary="Devolve o processo para EM_AVALIACAO com justificativa — HOM-01, RN-14")
def devolver(edital_id: int, dados: JustificativaEntrada, request: Request, db: DB, usuario: ProReitor) -> EditalSaida:
    svc.devolver_ajustes(db, edital_id, dados.justificativa, usuario, ip_cliente(request))
    return EditalSaida.model_validate(svc_editais.carregar(db, edital_id))


@router.get("/editais/{edital_id}/atas", response_model=list[AtaSaida], tags=["homologacao"],
            summary="Atas de homologação do edital (resultado final é público aos usuários autenticados)")
def atas(edital_id: int, db: DB, _: UsuarioAtual) -> list[AtaSaida]:
    return [_ata_saida(db, a) for a in svc.atas_do_edital(db, edital_id)]


# --- TRV-01: notificações do painel ----------------------------------------------------------------------
class NotificacaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tipo: str
    titulo: str
    mensagem: str
    lida: bool
    email_status: str
    criado_em: datetime


class PaginaNotificacoes(BaseModel):
    itens: list[NotificacaoSaida]
    nao_lidas: int


@router.get("/notificacoes", response_model=PaginaNotificacoes, tags=["notificacoes"],
            summary="Notificações internas do usuário — TRV-01")
def notificacoes(db: DB, usuario: UsuarioAtual, limite: Annotated[int, Query(ge=1, le=100)] = 30,
                 somente_nao_lidas: bool = False) -> PaginaNotificacoes:
    stmt = select(Notificacao).where(Notificacao.usuario_id == usuario.id)
    if somente_nao_lidas:
        stmt = stmt.where(Notificacao.lida.is_(False))
    itens = db.scalars(stmt.order_by(Notificacao.id.desc()).limit(limite)).all()
    nao_lidas = db.scalar(select(func.count()).select_from(Notificacao).where(
        Notificacao.usuario_id == usuario.id, Notificacao.lida.is_(False))) or 0
    return PaginaNotificacoes(itens=[NotificacaoSaida.model_validate(n) for n in itens], nao_lidas=nao_lidas)


@router.post("/notificacoes/{notificacao_id}/lida", status_code=status.HTTP_204_NO_CONTENT, tags=["notificacoes"])
def marcar_lida(notificacao_id: int, db: DB, usuario: UsuarioAtual) -> None:
    n = db.get(Notificacao, notificacao_id)
    if n is None or n.usuario_id != usuario.id:  # anti-IDOR
        raise NaoEncontrado("Notificação não encontrada.")
    n.lida = True
    db.commit()


@router.post("/notificacoes/lidas", status_code=status.HTTP_204_NO_CONTENT, tags=["notificacoes"])
def marcar_todas(db: DB, usuario: UsuarioAtual) -> None:
    db.execute(update(Notificacao).where(Notificacao.usuario_id == usuario.id, Notificacao.lida.is_(False))
               .values(lida=True))
    db.commit()


# --- TRV-03: trilha de auditoria (somente leitura) ---------------------------------------------------------
class RegistroAuditoria(BaseModel):
    id: int
    usuario_id: int | None
    usuario_nome: str | None
    acao: str
    entidade: str
    entidade_id: int
    dados_antes: dict[str, Any] | None
    dados_depois: dict[str, Any] | None
    ip_origem: str | None
    destaque: bool
    criado_em: datetime


class PaginaAuditoria(BaseModel):
    itens: list[RegistroAuditoria]
    total: int


@router.get("/auditoria", response_model=PaginaAuditoria, tags=["auditoria"],
            summary="Consulta a trilha de auditoria por edital ou inscrição — TRV-03, RN-14")
def auditoria(
    db: DB, _: ProReitor,
    edital_id: int | None = None,
    inscricao_id: int | None = None,
    acao: Annotated[str | None, Query(max_length=60)] = None,
    somente_destaques: bool = False,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaAuditoria:
    linhas, total = auditoria_consulta.consultar(
        db, edital_id=edital_id, inscricao_id=inscricao_id, acao=acao, somente_destaques=somente_destaques,
        limite=limite, deslocamento=deslocamento,
    )
    return PaginaAuditoria(
        itens=[
            RegistroAuditoria(
                id=log.id, usuario_id=log.usuario_id, usuario_nome=nome or ("Sistema" if log.usuario_id is None else None),
                acao=log.acao, entidade=log.entidade, entidade_id=log.entidade_id, dados_antes=log.dados_antes,
                dados_depois=log.dados_depois, ip_origem=log.ip_origem, destaque=log.destaque, criado_em=log.criado_em,
            )
            for log, nome in linhas
        ],
        total=total,
    )
