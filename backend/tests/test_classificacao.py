"""RN-09 / RN-12 — classificação (função pura). Casos escritos como tabela para facilitar a REVISÃO HUMANA
exigida pelo §14 item 28(c) do documento de projeto."""

import random
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.classificacao import Candidato, Situacao, classificar

T0 = datetime(2027, 3, 1, 10, 0, 0)
PADRAO = ["CR_DESC", "SUBMISSAO_ASC"]
C, S, N = Situacao.CONTEMPLADO, Situacao.SUPLENTE, Situacao.NAO_CLASSIFICADO


def cand(iid: int, nota: str, cr: str | None = "7.00", minutos: int = 0, deferido: bool = True) -> Candidato:
    return Candidato(iid, Decimal(nota), deferido, Decimal(cr) if cr is not None else None, T0 + timedelta(minutes=minutos))


def ordem(resultado) -> list[tuple[int, int | None, Situacao]]:
    return [(p.inscricao_id, p.posicao, p.situacao) for p in resultado]


# Cada caso: (descrição, candidatos, vagas, critérios, esperado [(inscricao_id, posição, situação)])
CASOS = [
    (
        "ordena por nota decrescente",
        [cand(1, "7.50"), cand(2, "9.00"), cand(3, "8.25")],
        3, PADRAO,
        [(2, 1, C), (3, 2, C), (1, 3, C)],
    ),
    (
        "empate de nota: maior CR congelado vence (1º critério)",
        [cand(1, "8.00", cr="7.10"), cand(2, "8.00", cr="9.30"), cand(3, "8.00", cr="8.00")],
        3, PADRAO,
        [(2, 1, C), (3, 2, C), (1, 3, C)],
    ),
    (
        "empate de nota e CR: submissão ORIGINAL mais antiga vence (2º critério)",
        [cand(1, "8.00", cr="8.00", minutos=30), cand(2, "8.00", cr="8.00", minutos=5)],
        2, PADRAO,
        [(2, 1, C), (1, 2, C)],
    ),
    (
        "nota vale mais que CR e data",
        [cand(1, "7.99", cr="10.00", minutos=0), cand(2, "8.00", cr="6.00", minutos=999)],
        2, PADRAO,
        [(2, 1, C), (1, 2, C)],
    ),
    (
        "N primeiros contemplados, demais suplentes na ordem (RN-12)",
        [cand(1, "9.00"), cand(2, "8.00"), cand(3, "7.00"), cand(4, "6.00")],
        2, PADRAO,
        [(1, 1, C), (2, 2, C), (3, 3, S), (4, 4, S)],
    ),
    (
        "menos candidatos que vagas: todos contemplados",
        [cand(1, "5.00"), cand(2, "6.00")],
        5, PADRAO,
        [(2, 1, C), (1, 2, C)],
    ),
    (
        "parecer INDEFERIDO não é classificado, mesmo com nota maior (RN-09)",
        [cand(1, "9.50", deferido=False), cand(2, "6.00"), cand(3, "7.00")],
        1, PADRAO,
        [(3, 1, C), (2, 2, S), (1, None, N)],
    ),
    (
        "critérios na ordem inversa: data antes do CR",
        [cand(1, "8.00", cr="9.00", minutos=10), cand(2, "8.00", cr="7.00", minutos=1)],
        2, ["SUBMISSAO_ASC", "CR_DESC"],
        [(2, 1, C), (1, 2, C)],
    ),
    (
        "CR ausente fica atrás no desempate por CR",
        [cand(1, "8.00", cr=None, minutos=0), cand(2, "8.00", cr="0.00", minutos=50)],
        2, PADRAO,
        [(2, 1, C), (1, 2, C)],
    ),
    (
        "sem critérios configurados: empate resolvido pelo id (determinístico)",
        [cand(5, "8.00"), cand(3, "8.00")],
        2, [],
        [(3, 1, C), (5, 2, C)],
    ),
    (
        "notas com duas casas decimais (RN-08)",
        [cand(1, "8.09"), cand(2, "8.10"), cand(3, "8.01")],
        3, PADRAO,
        [(2, 1, C), (1, 2, C), (3, 3, C)],
    ),
    (
        "nenhum candidato deferido",
        [cand(1, "4.00", deferido=False)],
        2, PADRAO,
        [(1, None, N)],
    ),
]


@pytest.mark.parametrize("descricao,candidatos,vagas,criterios,esperado", CASOS, ids=[c[0] for c in CASOS])
def test_RN09_RN12_tabela(descricao, candidatos, vagas, criterios, esperado):
    assert ordem(classificar(candidatos, vagas, criterios)) == esperado


def test_resultado_nao_depende_da_ordem_de_entrada():
    candidatos = [cand(i, f"{random.Random(i).randint(50, 100) / 10:.2f}", cr=f"{7 + i % 3}.00", minutos=i % 4)
                  for i in range(1, 41)]
    esperado = ordem(classificar(candidatos, 10, PADRAO))
    for semente in range(20):
        embaralhado = candidatos[:]
        random.Random(semente).shuffle(embaralhado)
        assert ordem(classificar(embaralhado, 10, PADRAO)) == esperado


def test_posicoes_contiguas_e_vagas_respeitadas():
    candidatos = [cand(i, "8.00", cr=f"{i % 10}.00", minutos=i) for i in range(1, 26)] + [cand(99, "9", deferido=False)]
    res = classificar(candidatos, 7, PADRAO)
    posicoes = [p.posicao for p in res if p.posicao is not None]
    assert posicoes == list(range(1, 26))
    assert sum(p.situacao == C for p in res) == 7
    assert sum(p.situacao == S for p in res) == 18


@pytest.mark.parametrize("vagas,criterios", [(0, PADRAO), (1, ["IDADE_DESC"])])
def test_entradas_invalidas(vagas, criterios):
    with pytest.raises(ValueError):
        classificar([cand(1, "8")], vagas, criterios)
