"""Notificações por painel e e-mail (TRV-01).

Cada evento grava uma linha em `notificacoes` (painel) e enfileira uma tarefa EMAIL para o worker,
que faz o envio SMTP com retentativas. Tudo na mesma transação da ação que originou o evento.
"""

from sqlalchemy.orm import Session

from app.models import Notificacao, Tarefa

TAREFA_EMAIL = "EMAIL"


def notificar(db: Session, *, usuario_id: int, tipo: str, titulo: str, mensagem: str) -> Notificacao:
    notif = Notificacao(usuario_id=usuario_id, tipo=tipo, titulo=titulo, mensagem=mensagem)
    db.add(notif)
    db.flush()
    db.add(Tarefa(tipo=TAREFA_EMAIL, payload={"notificacao_id": notif.id}))
    return notif
