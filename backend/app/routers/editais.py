"""Editais e comissão avaliadora (UC-06 — EDT-01…05)."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.core.deps import DB, Avaliador, ProReitor, UsuarioOpcional, ip_cliente
from app.domain.estados import StatusEdital
from app.schemas.edital import (
    Categoria,
    ComissaoEntrada,
    EditalAtualizacao,
    EditalEntrada,
    EditalResumo,
    EditalSaida,
    JustificativaEntrada,
    MembroComissao,
    PaginaEditais,
)
from app.services import editais as svc

router = APIRouter(prefix="/editais", tags=["editais"])


@router.get("", response_model=PaginaEditais, summary="Lista e filtra editais (Abertos por padrão) — INS-01")
def listar(
    db: DB,
    usuario: UsuarioOpcional,
    status_: Annotated[list[StatusEdital] | None, Query(alias="status")] = None,
    categoria: Categoria | None = None,
    modalidade: str | None = None,
    curso: str | None = None,
    valor_min: Annotated[Decimal | None, Query(ge=0)] = None,
    valor_max: Annotated[Decimal | None, Query(ge=0)] = None,
    busca: Annotated[str | None, Query(max_length=100)] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    deslocamento: Annotated[int, Query(ge=0)] = 0,
) -> PaginaEditais:
    itens, total = svc.listar(
        db, usuario, status=status_, categoria=categoria, modalidade=modalidade, curso=curso,
        valor_min=valor_min, valor_max=valor_max, busca=busca, limite=limite, deslocamento=deslocamento,
    )
    return PaginaEditais(itens=[EditalResumo.model_validate(e) for e in itens], total=total)


@router.get("/designados", response_model=list[EditalResumo], summary="Editais em que sou avaliador (RN-07)")
def designados(db: DB, usuario: Avaliador) -> list[EditalResumo]:
    return [EditalResumo.model_validate(e) for e in svc.editais_designados(db, usuario)]


@router.get("/{edital_id}", response_model=EditalSaida)
def obter(edital_id: int, db: DB, usuario: UsuarioOpcional) -> EditalSaida:
    return EditalSaida.model_validate(svc.obter_visivel(db, edital_id, usuario))


@router.post("", response_model=EditalSaida, status_code=status.HTTP_201_CREATED,
             summary="Cria edital em Rascunho — EDT-01, EDT-02")
def criar(dados: EditalEntrada, request: Request, db: DB, usuario: ProReitor) -> EditalSaida:
    return EditalSaida.model_validate(svc.criar(db, dados, usuario, ip_cliente(request)))


@router.put("/{edital_id}", response_model=EditalSaida,
            summary="Edita edital (após publicar, só a descrição) — EDT-01, RN-14")
def atualizar(edital_id: int, dados: EditalAtualizacao, request: Request, db: DB, usuario: ProReitor) -> EditalSaida:
    return EditalSaida.model_validate(svc.atualizar(db, edital_id, dados, usuario, ip_cliente(request)))


@router.post("/{edital_id}/publicar", response_model=EditalSaida, summary="Valida e publica — EDT-02, EDT-03")
def publicar(edital_id: int, request: Request, db: DB, usuario: ProReitor) -> EditalSaida:
    svc.publicar(db, edital_id, usuario, ip_cliente(request))
    return EditalSaida.model_validate(svc.carregar(db, edital_id))


@router.post("/{edital_id}/iniciar-avaliacao", response_model=EditalSaida,
             summary="Antecipa o início da avaliação após o fim das inscrições — §7.1")
def iniciar_avaliacao(edital_id: int, request: Request, db: DB, usuario: ProReitor) -> EditalSaida:
    svc.iniciar_avaliacao(db, edital_id, usuario, ip_cliente(request))
    return EditalSaida.model_validate(svc.carregar(db, edital_id))


@router.post("/{edital_id}/cancelar", response_model=EditalSaida,
             summary="Cancela com justificativa e notifica inscritos — EDT-05")
def cancelar(edital_id: int, dados: JustificativaEntrada, request: Request, db: DB, usuario: ProReitor) -> EditalSaida:
    svc.cancelar(db, edital_id, dados.justificativa, usuario, ip_cliente(request))
    return EditalSaida.model_validate(svc.carregar(db, edital_id))


@router.get("/{edital_id}/comissao", response_model=list[MembroComissao])
def listar_comissao(edital_id: int, db: DB, _: ProReitor) -> list[MembroComissao]:
    return [
        MembroComissao(avaliador_id=u.id, nome=u.nome, email=u.email, designado_em=m.designado_em)
        for m, u in svc.listar_comissao(db, edital_id)
    ]


@router.post("/{edital_id}/comissao", response_model=list[MembroComissao],
             summary="Designa avaliadores (bloqueia candidatos do edital) — EDT-04, RN-07")
def designar(edital_id: int, dados: ComissaoEntrada, request: Request, db: DB, usuario: ProReitor):
    svc.designar(db, edital_id, dados, usuario, ip_cliente(request))
    return listar_comissao(edital_id, db, usuario)


@router.delete("/{edital_id}/comissao/{avaliador_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(edital_id: int, avaliador_id: int, request: Request, db: DB, usuario: ProReitor) -> None:
    svc.remover_da_comissao(db, edital_id, avaliador_id, usuario, ip_cliente(request))
