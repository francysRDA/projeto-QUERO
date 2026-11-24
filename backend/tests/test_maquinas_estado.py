"""§7 / §14 item 25: toda transição fora das tabelas deve ser recusada (HTTP 409).

Os testes percorrem o produto cartesiano (estado × evento) de cada máquina e conferem que
apenas os pares documentados são aceitos.
"""

import itertools

import pytest

from app.core.errors import TransicaoInvalida
from app.domain.estados import (
    MAQUINA_AVALIACAO,
    MAQUINA_EDITAL,
    MAQUINA_INSCRICAO,
    MAQUINA_RECURSO,
    NOVO,
    EventoAvaliacao,
    EventoEdital,
    EventoInscricao,
    EventoRecurso,
    StatusAvaliacao,
    StatusEdital,
    StatusInscricao,
    StatusRecurso,
)

E, I, A, R = StatusEdital, StatusInscricao, StatusAvaliacao, StatusRecurso  # noqa: E741

# Especificação escrita à mão a partir do documento, independente da implementação.
ESPERADO_EDITAL = {
    (E.RASCUNHO, EventoEdital.PUBLICAR): E.ABERTO,
    (E.ABERTO, EventoEdital.ENCERRAR_INSCRICOES): E.INSCRICOES_ENCERRADAS,
    (E.INSCRICOES_ENCERRADAS, EventoEdital.INICIAR_AVALIACAO): E.EM_AVALIACAO,
    (E.EM_AVALIACAO, EventoEdital.PUBLICAR_PRELIMINAR): E.RESULTADO_PRELIMINAR,
    (E.RESULTADO_PRELIMINAR, EventoEdital.ABRIR_RECURSO): E.EM_RECURSO,
    (E.EM_RECURSO, EventoEdital.ENCERRAR_RECURSO): E.EM_HOMOLOGACAO_FINAL,
    (E.EM_HOMOLOGACAO_FINAL, EventoEdital.DEVOLVER_AJUSTES): E.EM_AVALIACAO,
    (E.EM_HOMOLOGACAO_FINAL, EventoEdital.HOMOLOGAR_FINAL): E.ENCERRADO,
    **{
        (s, EventoEdital.CANCELAR): E.CANCELADO
        for s in E
        if s not in (E.ENCERRADO, E.CANCELADO)
    },
}

ESPERADO_INSCRICAO = {
    (NOVO, EventoInscricao.SUBMETER_ELEGIVEL): I.HOMOLOGADA,
    (NOVO, EventoInscricao.SUBMETER_INELEGIVEL): I.INDEFERIDA,
    (NOVO, EventoInscricao.SUBMETER_ACADEMICO_INDISPONIVEL): I.PENDENTE_VALIDACAO_VINCULO,
    (I.PENDENTE_VALIDACAO_VINCULO, EventoInscricao.REPROCESSAR_ELEGIVEL): I.HOMOLOGADA,
    (I.PENDENTE_VALIDACAO_VINCULO, EventoInscricao.REPROCESSAR_INELEGIVEL): I.INDEFERIDA,
    (I.HOMOLOGADA, EventoInscricao.RETIFICAR_VALIDA): I.HOMOLOGADA,
    (I.HOMOLOGADA, EventoInscricao.RETIFICAR_INVALIDA): I.INDEFERIDA,
    (I.INDEFERIDA, EventoInscricao.RETIFICAR_VALIDA): I.HOMOLOGADA,
    (I.INDEFERIDA, EventoInscricao.RETIFICAR_INVALIDA): I.INDEFERIDA,
    (I.PENDENTE_VALIDACAO_VINCULO, EventoInscricao.RETIFICAR_PENDENTE): I.PENDENTE_VALIDACAO_VINCULO,
    (I.INDEFERIDA, EventoInscricao.REANALISAR_DEFERIR): I.HOMOLOGADA,
    (I.HOMOLOGADA, EventoInscricao.DESISTIR): I.DESISTENTE,
    (I.INDEFERIDA, EventoInscricao.DESISTIR): I.DESISTENTE,
    (I.PENDENTE_VALIDACAO_VINCULO, EventoInscricao.DESISTIR): I.DESISTENTE,
}

ESPERADO_AVALIACAO = {
    (NOVO, EventoAvaliacao.SALVAR_RASCUNHO): A.RASCUNHO,
    (A.RASCUNHO, EventoAvaliacao.SALVAR_RASCUNHO): A.RASCUNHO,
    (A.RASCUNHO, EventoAvaliacao.CONFIRMAR): A.CONFIRMADA,
    (A.CONFIRMADA, EventoAvaliacao.RETIFICAR): A.RETIFICADA,
    (A.RETIFICADA, EventoAvaliacao.RETIFICAR): A.RETIFICADA,
}

ESPERADO_RECURSO = {
    (NOVO, EventoRecurso.INTERPOR): R.ABERTO,
    (R.ABERTO, EventoRecurso.ASSUMIR): R.EM_ANALISE,
    (R.EM_ANALISE, EventoRecurso.DEFERIR): R.DEFERIDO,
    (R.EM_ANALISE, EventoRecurso.INDEFERIR): R.INDEFERIDO,
}

CASOS = [
    (MAQUINA_EDITAL, StatusEdital, EventoEdital, ESPERADO_EDITAL),
    (MAQUINA_INSCRICAO, StatusInscricao, EventoInscricao, ESPERADO_INSCRICAO),
    (MAQUINA_AVALIACAO, StatusAvaliacao, EventoAvaliacao, ESPERADO_AVALIACAO),
    (MAQUINA_RECURSO, StatusRecurso, EventoRecurso, ESPERADO_RECURSO),
]


def _todos_os_pares():
    for maquina, estados, eventos, esperado in CASOS:
        for estado, evento in itertools.product([NOVO, *estados], eventos):
            yield pytest.param(maquina, str(estado), str(evento), esperado, id=f"{maquina.nome}-{estado}-{evento}")


@pytest.mark.parametrize("maquina,estado,evento,esperado", list(_todos_os_pares()))
def test_transicao(maquina, estado, evento, esperado):
    chave = (estado, evento)
    esperado_str = {(str(a), str(b)): str(c) for (a, b), c in esperado.items()}
    if chave in esperado_str:
        assert maquina.proximo(estado, evento) == esperado_str[chave]
    else:
        with pytest.raises(TransicaoInvalida):
            maquina.proximo(estado, evento)


@pytest.mark.parametrize("maquina,_e,_v,esperado", CASOS, ids=lambda x: getattr(x, "nome", ""))
def test_tabela_identica_a_especificacao(maquina, _e, _v, esperado):
    """Nenhuma transição extra 'escondida' na implementação."""
    assert maquina.transicoes == {(str(a), str(b)): str(c) for (a, b), c in esperado.items()}


def test_estados_terminais_do_edital():
    for evento in EventoEdital:
        assert not MAQUINA_EDITAL.permitido(E.ENCERRADO, evento)
        assert not MAQUINA_EDITAL.permitido(E.CANCELADO, evento)


def test_desistente_e_terminal():
    for evento in EventoInscricao:
        assert not MAQUINA_INSCRICAO.permitido(I.DESISTENTE, evento)
