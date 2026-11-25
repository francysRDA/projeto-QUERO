"""Jobs do worker assíncrono (§8.2). Todos idempotentes e seguros com vários workers
(SELECT ... FOR UPDATE SKIP LOCKED)."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.relogio import agora
from app.domain.estados import EventoEdital, StatusEdital
from app.integrations.email import enviar_email
from app.models import Edital, Notificacao, Tarefa, Usuario
from app.services import editais as svc_editais
from app.services.notificacoes import TAREFA_EMAIL

log = logging.getLogger("quero.worker")

MAX_TENTATIVAS_EMAIL = 5


def transicoes_temporais(db: Session) -> int:
    """§7.5 timers (1) fechamento das inscrições e (2) início da avaliação."""
    momento = agora(db)
    regras = [
        (StatusEdital.ABERTO, Edital.data_fim_inscricao, EventoEdital.ENCERRAR_INSCRICOES),
        (StatusEdital.INSCRICOES_ENCERRADAS, Edital.data_inicio_avaliacao, EventoEdital.INICIAR_AVALIACAO),
    ]
    total = 0
    # Ordem importa: um edital cujo prazo e início de avaliação já passaram atravessa as duas etapas.
    for status, coluna, evento in regras:
        editais = db.scalars(
            select(Edital)
            .where(Edital.status == status, coluna <= momento)
            .with_for_update(skip_locked=True)
        ).all()
        for edital in editais:
            svc_editais.transicionar(db, edital, evento, usuario_id=None)
            log.info("Edital %s: %s -> %s", edital.id, status, edital.status)
            total += 1
        db.commit()
    return total


def processar_emails(db: Session, limite: int = 20) -> int:
    agora_real = datetime.now(timezone.utc)
    tarefas = db.scalars(
        select(Tarefa)
        .where(Tarefa.tipo == TAREFA_EMAIL, Tarefa.status == "PENDENTE", Tarefa.executar_em <= agora_real)
        .order_by(Tarefa.id)
        .limit(limite)
        .with_for_update(skip_locked=True)
    ).all()
    enviados = 0
    for tarefa in tarefas:
        notif = db.get(Notificacao, tarefa.payload.get("notificacao_id"))
        if notif is None:
            tarefa.status = "FALHA"
            tarefa.ultimo_erro = "Notificação inexistente"
            continue
        usuario = db.get(Usuario, notif.usuario_id)
        tarefa.tentativas += 1
        notif.tentativas_email = tarefa.tentativas
        try:
            enviar_email(usuario.email, notif.titulo, notif.mensagem)
        except Exception as exc:  # noqa: BLE001 — qualquer falha SMTP vira retentativa
            tarefa.ultimo_erro = str(exc)[:1000]
            if tarefa.tentativas >= MAX_TENTATIVAS_EMAIL:
                tarefa.status = "FALHA"
                notif.email_status = "FALHA"
            else:
                tarefa.executar_em = agora_real + timedelta(minutes=2 ** tarefa.tentativas)
            log.warning("Falha ao enviar e-mail (tarefa %s, tentativa %s): %s", tarefa.id, tarefa.tentativas, exc)
        else:
            tarefa.status = "CONCLUIDA"
            notif.email_status = "ENVIADO"
            enviados += 1
    db.commit()
    return enviados


def executar_ciclo(db: Session, *, enviar_emails: bool = True) -> None:
    transicoes_temporais(db)
    if enviar_emails:
        processar_emails(db)
