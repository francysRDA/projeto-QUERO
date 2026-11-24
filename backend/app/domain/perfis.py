from enum import StrEnum


class Perfil(StrEnum):
    """Papéis do RBAC (§2.2). DP-01: papel operacional separado ainda não existe."""

    ESTUDANTE = "ESTUDANTE"
    AVALIADOR = "AVALIADOR"
    PRO_REITOR = "PRO_REITOR"
