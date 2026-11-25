"""Classificação (RN-09, RN-12) — FUNÇÃO PURA. ⚠ Revisão humana obrigatória (§14 item 28c).

Regras implementadas, na ordem:
  1. Só candidatos com parecer de mérito DEFERIDO são classificados (RN-09).
     Os INDEFERIDOS ficam como NAO_CLASSIFICADO, sem posição.
  2. Ordenação por nota DECRESCENTE.
  3. Empates resolvidos pelos critérios configurados no edital, na ordem da lista (RN-09):
       - "CR_DESC":       maior CR congelado primeiro (CR ausente vai para o fim);
       - "SUBMISSAO_ASC": menor data/hora da SUBMISSÃO ORIGINAL primeiro (retificações não penalizam).
     Padrão do edital: ["CR_DESC", "SUBMISSAO_ASC"].
  4. Se ainda houver empate depois de todos os critérios, desempata pelo id da inscrição (ordem de
     chegada no banco) apenas para o resultado ser DETERMINÍSTICO. Na prática, SUBMISSAO_ASC com precisão
     de microssegundos torna esse caso praticamente impossível.
  5. Os N primeiros (N = vagas) são CONTEMPLADOS; os demais deferidos, SUPLENTES na ordem (RN-12).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

CRITERIOS_VALIDOS = {"CR_DESC", "SUBMISSAO_ASC"}


class Situacao(StrEnum):
    CONTEMPLADO = "CONTEMPLADO"
    SUPLENTE = "SUPLENTE"
    NAO_CLASSIFICADO = "NAO_CLASSIFICADO"


@dataclass(frozen=True)
class Candidato:
    inscricao_id: int
    nota: Decimal
    deferido: bool
    cr: Decimal | None
    submissao_original: datetime


@dataclass(frozen=True)
class Posicao:
    inscricao_id: int
    posicao: int | None
    nota: Decimal
    situacao: Situacao


def _chave(c: Candidato, criterios: Sequence[str]) -> tuple:
    chave: list = [-c.nota]
    for criterio in criterios:
        if criterio == "CR_DESC":
            # (False, -cr) vem antes de (True, 0): CR ausente sempre por último.
            chave.append((c.cr is None, -(c.cr or Decimal(0))))
        elif criterio == "SUBMISSAO_ASC":
            chave.append(c.submissao_original)
    chave.append(c.inscricao_id)
    return tuple(chave)


def classificar(candidatos: Iterable[Candidato], vagas: int, criterios_desempate: Sequence[str]) -> list[Posicao]:
    if vagas < 1:
        raise ValueError("O edital deve ter ao menos uma vaga.")
    invalidos = set(criterios_desempate) - CRITERIOS_VALIDOS
    if invalidos:
        raise ValueError(f"Critério(s) de desempate desconhecido(s): {sorted(invalidos)}")

    candidatos = list(candidatos)
    deferidos = sorted((c for c in candidatos if c.deferido), key=lambda c: _chave(c, criterios_desempate))
    indeferidos = sorted((c for c in candidatos if not c.deferido), key=lambda c: (-c.nota, c.inscricao_id))

    resultado = [
        Posicao(c.inscricao_id, i, c.nota, Situacao.CONTEMPLADO if i <= vagas else Situacao.SUPLENTE)
        for i, c in enumerate(deferidos, start=1)
    ]
    resultado += [Posicao(c.inscricao_id, None, c.nota, Situacao.NAO_CLASSIFICADO) for c in indeferidos]
    return resultado
