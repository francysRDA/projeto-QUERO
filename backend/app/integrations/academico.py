"""Integração com o Sistema Acadêmico (INT-01, DP-03).

`ServicoAcademico` é a interface. Hoje existe apenas o adapter SIMULADO (CSV), que também serve de
plano de contingência do RSK-02 (importação periódica via CSV). Quando a TI confirmar a API real,
basta implementar `ServicoAcademicoApi` com o mesmo contrato.
"""

import csv
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoTimeout
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

log = logging.getLogger("quero.academico")


@dataclass(frozen=True)
class DadosAcademicos:
    matricula: str
    vinculo_ativo: bool
    codigo_curso: str
    nome_curso: str
    cr: Decimal


class AcademicoIndisponivel(Exception):
    """O Sistema Acadêmico não respondeu (timeout, erro de rede, manutenção)."""


class ServicoAcademico(Protocol):
    def consultar(self, matricula: str) -> DadosAcademicos | None:
        """Dados da matrícula, None se não existir. Lança AcademicoIndisponivel se fora do ar."""
        ...


class ServicoAcademicoSimulado:
    """Lê `matricula;vinculo_ativo;codigo_curso;nome_curso;cr` de um CSV.

    A presença do arquivo-sinal `flag_fora_do_ar` simula indisponibilidade (usado em demonstrações e
    testes). Por ser um arquivo, API e worker enxergam o mesmo estado.
    """

    def __init__(self, caminho_csv: str | Path, flag_fora_do_ar: str | Path):
        self.caminho_csv = Path(caminho_csv)
        self.flag_fora_do_ar = Path(flag_fora_do_ar)
        self._cache: dict[str, DadosAcademicos] = {}
        self._mtime: float | None = None

    # Simulação de indisponibilidade -------------------------------------------------------------
    @property
    def fora_do_ar(self) -> bool:
        return self.flag_fora_do_ar.exists()

    def definir_fora_do_ar(self, valor: bool) -> None:
        if valor:
            self.flag_fora_do_ar.parent.mkdir(parents=True, exist_ok=True)
            self.flag_fora_do_ar.touch()
        else:
            self.flag_fora_do_ar.unlink(missing_ok=True)

    # Consulta ---------------------------------------------------------------------------------------
    def _carregar(self) -> dict[str, DadosAcademicos]:
        mtime = self.caminho_csv.stat().st_mtime
        if mtime != self._mtime:  # recarrega quando a secretaria publica um CSV novo
            dados: dict[str, DadosAcademicos] = {}
            with open(self.caminho_csv, encoding="utf-8", newline="") as f:
                for n, linha in enumerate(csv.DictReader(f, delimiter=";"), start=2):
                    try:
                        dados[linha["matricula"].strip()] = DadosAcademicos(
                            matricula=linha["matricula"].strip(),
                            vinculo_ativo=linha["vinculo_ativo"].strip().lower() in ("1", "true", "sim", "s"),
                            codigo_curso=linha["codigo_curso"].strip(),
                            nome_curso=linha["nome_curso"].strip(),
                            cr=Decimal(linha["cr"].strip().replace(",", ".")),
                        )
                    except (KeyError, InvalidOperation, AttributeError):
                        log.warning("Linha %s inválida no CSV acadêmico; ignorada.", n)
            self._cache, self._mtime = dados, mtime
        return self._cache

    def consultar(self, matricula: str) -> DadosAcademicos | None:
        if self.fora_do_ar:
            raise AcademicoIndisponivel("Sistema Acadêmico indisponível (simulação).")
        try:
            return self._carregar().get(matricula.strip())
        except OSError as exc:
            raise AcademicoIndisponivel(f"Base acadêmica inacessível: {exc}") from exc


# INT-01: timeout de 5 s com até 3 tentativas ---------------------------------------------------------
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="academico")


def consultar_com_retentativa(
    servico: ServicoAcademico,
    matricula: str,
    *,
    tentativas: int = 3,
    timeout_s: float = 5.0,
    espera_s: float = 0.5,
) -> DadosAcademicos | None:
    ultimo: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        futuro = _executor.submit(servico.consultar, matricula)
        try:
            return futuro.result(timeout=timeout_s)
        except FuturoTimeout:
            ultimo = AcademicoIndisponivel(f"Timeout de {timeout_s}s")
        except AcademicoIndisponivel as exc:
            ultimo = exc
        log.warning("Sistema Acadêmico: tentativa %s/%s falhou (%s)", tentativa, tentativas, ultimo)
        if tentativa < tentativas and espera_s > 0:
            time.sleep(espera_s * tentativa)
    raise AcademicoIndisponivel(str(ultimo))


# Injeção de dependência ------------------------------------------------------------------------------
_servico_padrao: ServicoAcademicoSimulado | None = None


def get_servico_academico() -> ServicoAcademico:
    """Ponto único de troca do adapter (simulado hoje; API real quando DP-03 for resolvida)."""
    global _servico_padrao
    if _servico_padrao is None:
        from app.core.config import get_settings

        s = get_settings()
        _servico_padrao = ServicoAcademicoSimulado(s.academico_csv, s.academico_flag_fora_do_ar)
    return _servico_padrao


def consultar(servico: ServicoAcademico, matricula: str) -> DadosAcademicos | None:
    """Consulta com a política de INT-01 lida das configurações."""
    from app.core.config import get_settings

    s = get_settings()
    return consultar_com_retentativa(
        servico, matricula, tentativas=s.academico_tentativas, timeout_s=s.academico_timeout_s,
        espera_s=s.academico_espera_s,
    )
