"""Máquinas de estado do domínio (Documento de Projeto §7).

Cada máquina é uma tabela {(estado_atual, evento): proximo_estado}. Qualquer par fora da tabela
lança TransicaoInvalida (HTTP 409). Não há lógica escondida: as tabelas abaixo SÃO a especificação.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import TransicaoInvalida


@dataclass(frozen=True)
class MaquinaEstados:
    nome: str
    transicoes: dict[tuple[str, str], str]

    def proximo(self, estado: str, evento: str) -> str:
        try:
            return self.transicoes[(estado, evento)]
        except KeyError:
            raise TransicaoInvalida(
                f"{self.nome}: evento '{evento}' não é permitido no estado '{estado}'."
            ) from None

    def permitido(self, estado: str, evento: str) -> bool:
        return (estado, evento) in self.transicoes

    def eventos(self) -> set[str]:
        return {e for (_, e) in self.transicoes}

    def estados(self) -> set[str]:
        return {s for (s, _) in self.transicoes} | set(self.transicoes.values())


# Pseudo-estado para entidades ainda não persistidas ("(Nova)" nas tabelas do documento).
NOVO = "NOVO"


# ---------------------------------------------------------------------------------------------
# §7.1 Edital
# ---------------------------------------------------------------------------------------------
class StatusEdital(StrEnum):
    RASCUNHO = "RASCUNHO"
    ABERTO = "ABERTO"
    INSCRICOES_ENCERRADAS = "INSCRICOES_ENCERRADAS"
    EM_AVALIACAO = "EM_AVALIACAO"
    RESULTADO_PRELIMINAR = "RESULTADO_PRELIMINAR"
    EM_RECURSO = "EM_RECURSO"
    EM_HOMOLOGACAO_FINAL = "EM_HOMOLOGACAO_FINAL"
    ENCERRADO = "ENCERRADO"
    CANCELADO = "CANCELADO"


class EventoEdital(StrEnum):
    PUBLICAR = "PUBLICAR"
    ENCERRAR_INSCRICOES = "ENCERRAR_INSCRICOES"
    INICIAR_AVALIACAO = "INICIAR_AVALIACAO"
    PUBLICAR_PRELIMINAR = "PUBLICAR_PRELIMINAR"
    ABRIR_RECURSO = "ABRIR_RECURSO"
    ENCERRAR_RECURSO = "ENCERRAR_RECURSO"
    DEVOLVER_AJUSTES = "DEVOLVER_AJUSTES"
    HOMOLOGAR_FINAL = "HOMOLOGAR_FINAL"
    CANCELAR = "CANCELAR"


_E = StatusEdital
_EV = EventoEdital
_transicoes_edital = {
    (_E.RASCUNHO, _EV.PUBLICAR): _E.ABERTO,
    (_E.ABERTO, _EV.ENCERRAR_INSCRICOES): _E.INSCRICOES_ENCERRADAS,
    (_E.INSCRICOES_ENCERRADAS, _EV.INICIAR_AVALIACAO): _E.EM_AVALIACAO,
    (_E.EM_AVALIACAO, _EV.PUBLICAR_PRELIMINAR): _E.RESULTADO_PRELIMINAR,
    (_E.RESULTADO_PRELIMINAR, _EV.ABRIR_RECURSO): _E.EM_RECURSO,
    (_E.EM_RECURSO, _EV.ENCERRAR_RECURSO): _E.EM_HOMOLOGACAO_FINAL,
    (_E.EM_HOMOLOGACAO_FINAL, _EV.DEVOLVER_AJUSTES): _E.EM_AVALIACAO,
    (_E.EM_HOMOLOGACAO_FINAL, _EV.HOMOLOGAR_FINAL): _E.ENCERRADO,
}
# "Qualquer estado ≠ ENCERRADO -> CANCELADO" (EDT-05). CANCELADO -> CANCELADO não faz sentido.
for _s in _E:
    if _s not in (_E.ENCERRADO, _E.CANCELADO):
        _transicoes_edital[(_s, _EV.CANCELAR)] = _E.CANCELADO

MAQUINA_EDITAL = MaquinaEstados("Edital", {(str(a), str(b)): str(c) for (a, b), c in _transicoes_edital.items()})


# ---------------------------------------------------------------------------------------------
# §7.2 Inscrição
# ---------------------------------------------------------------------------------------------
class StatusInscricao(StrEnum):
    PENDENTE_VALIDACAO_VINCULO = "PENDENTE_VALIDACAO_VINCULO"
    HOMOLOGADA = "HOMOLOGADA"
    INDEFERIDA = "INDEFERIDA"
    DESISTENTE = "DESISTENTE"


class EventoInscricao(StrEnum):
    SUBMETER_ELEGIVEL = "SUBMETER_ELEGIVEL"
    SUBMETER_INELEGIVEL = "SUBMETER_INELEGIVEL"
    SUBMETER_ACADEMICO_INDISPONIVEL = "SUBMETER_ACADEMICO_INDISPONIVEL"
    REPROCESSAR_ELEGIVEL = "REPROCESSAR_ELEGIVEL"
    REPROCESSAR_INELEGIVEL = "REPROCESSAR_INELEGIVEL"  # também usado na expiração (início da avaliação)
    RETIFICAR_VALIDA = "RETIFICAR_VALIDA"
    RETIFICAR_INVALIDA = "RETIFICAR_INVALIDA"
    RETIFICAR_PENDENTE = "RETIFICAR_PENDENTE"  # L-06: retificação enquanto aguarda o Sistema Acadêmico
    REANALISAR_DEFERIR = "REANALISAR_DEFERIR"
    DESISTIR = "DESISTIR"


_I = StatusInscricao
_IV = EventoInscricao
_transicoes_inscricao = {
    (NOVO, _IV.SUBMETER_ELEGIVEL): _I.HOMOLOGADA,
    (NOVO, _IV.SUBMETER_INELEGIVEL): _I.INDEFERIDA,
    (NOVO, _IV.SUBMETER_ACADEMICO_INDISPONIVEL): _I.PENDENTE_VALIDACAO_VINCULO,
    (_I.PENDENTE_VALIDACAO_VINCULO, _IV.REPROCESSAR_ELEGIVEL): _I.HOMOLOGADA,
    (_I.PENDENTE_VALIDACAO_VINCULO, _IV.REPROCESSAR_INELEGIVEL): _I.INDEFERIDA,
    (_I.HOMOLOGADA, _IV.RETIFICAR_VALIDA): _I.HOMOLOGADA,
    (_I.HOMOLOGADA, _IV.RETIFICAR_INVALIDA): _I.INDEFERIDA,
    (_I.INDEFERIDA, _IV.RETIFICAR_VALIDA): _I.HOMOLOGADA,
    (_I.INDEFERIDA, _IV.RETIFICAR_INVALIDA): _I.INDEFERIDA,
    (_I.PENDENTE_VALIDACAO_VINCULO, _IV.RETIFICAR_PENDENTE): _I.PENDENTE_VALIDACAO_VINCULO,
    (_I.INDEFERIDA, _IV.REANALISAR_DEFERIR): _I.HOMOLOGADA,
    (_I.HOMOLOGADA, _IV.DESISTIR): _I.DESISTENTE,
    (_I.INDEFERIDA, _IV.DESISTIR): _I.DESISTENTE,
    (_I.PENDENTE_VALIDACAO_VINCULO, _IV.DESISTIR): _I.DESISTENTE,
}
MAQUINA_INSCRICAO = MaquinaEstados(
    "Inscrição", {(str(a), str(b)): str(c) for (a, b), c in _transicoes_inscricao.items()}
)


# ---------------------------------------------------------------------------------------------
# §7.3 Avaliação de mérito
# ---------------------------------------------------------------------------------------------
class StatusAvaliacao(StrEnum):
    RASCUNHO = "RASCUNHO"
    CONFIRMADA = "CONFIRMADA"
    RETIFICADA = "RETIFICADA"


class EventoAvaliacao(StrEnum):
    SALVAR_RASCUNHO = "SALVAR_RASCUNHO"
    CONFIRMAR = "CONFIRMAR"
    RETIFICAR = "RETIFICAR"


_A = StatusAvaliacao
_AV = EventoAvaliacao
_transicoes_avaliacao = {
    (NOVO, _AV.SALVAR_RASCUNHO): _A.RASCUNHO,
    (_A.RASCUNHO, _AV.SALVAR_RASCUNHO): _A.RASCUNHO,  # editar rascunho
    (_A.RASCUNHO, _AV.CONFIRMAR): _A.CONFIRMADA,
    (_A.CONFIRMADA, _AV.RETIFICAR): _A.RETIFICADA,
    (_A.RETIFICADA, _AV.RETIFICAR): _A.RETIFICADA,  # nova retificação (ex.: via recurso)
}
MAQUINA_AVALIACAO = MaquinaEstados(
    "Avaliação", {(str(a), str(b)): str(c) for (a, b), c in _transicoes_avaliacao.items()}
)


# ---------------------------------------------------------------------------------------------
# §7.4 Recurso
# ---------------------------------------------------------------------------------------------
class StatusRecurso(StrEnum):
    ABERTO = "ABERTO"
    EM_ANALISE = "EM_ANALISE"
    DEFERIDO = "DEFERIDO"
    INDEFERIDO = "INDEFERIDO"


class EventoRecurso(StrEnum):
    INTERPOR = "INTERPOR"
    ASSUMIR = "ASSUMIR"
    DEFERIR = "DEFERIR"
    INDEFERIR = "INDEFERIR"


_R = StatusRecurso
_RV = EventoRecurso
_transicoes_recurso = {
    (NOVO, _RV.INTERPOR): _R.ABERTO,
    (_R.ABERTO, _RV.ASSUMIR): _R.EM_ANALISE,
    (_R.EM_ANALISE, _RV.DEFERIR): _R.DEFERIDO,
    (_R.EM_ANALISE, _RV.INDEFERIR): _R.INDEFERIDO,
}
MAQUINA_RECURSO = MaquinaEstados(
    "Recurso", {(str(a), str(b)): str(c) for (a, b), c in _transicoes_recurso.items()}
)
