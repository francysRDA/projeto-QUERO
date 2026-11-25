"""Envio de e-mail por SMTP (em dev, o Mailpit captura tudo em http://localhost:8025)."""

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


def enviar_email(destinatario: str, assunto: str, corpo: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_remetente
    msg["To"] = destinatario
    msg["Subject"] = f"[QUERO] {assunto}"
    msg.set_content(corpo)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        smtp.send_message(msg)
