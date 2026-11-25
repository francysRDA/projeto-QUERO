"""Processo do worker: python -m app.worker"""

import logging
import signal
import time

from app.core.db import SessionLocal
from app.worker.jobs import executar_ciclo

INTERVALO_SEGUNDOS = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("quero.worker")

_rodando = True


def _parar(*_):
    global _rodando
    _rodando = False


def main() -> None:
    signal.signal(signal.SIGINT, _parar)
    signal.signal(signal.SIGTERM, _parar)
    log.info("Worker iniciado (ciclo de %ss).", INTERVALO_SEGUNDOS)
    while _rodando:
        try:
            with SessionLocal() as db:
                executar_ciclo(db)
        except Exception:
            log.exception("Erro no ciclo do worker")
        time.sleep(INTERVALO_SEGUNDOS)
    log.info("Worker encerrado.")


if __name__ == "__main__":
    main()
