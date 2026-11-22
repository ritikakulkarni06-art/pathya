"""Outgoing mail. With SMTP_HOST set, messages go through that server; otherwise each message is
written to <PATHYA_DATA_DIR>/outbox/ so an operator (or a test) can read and pass it on."""

import smtplib
from email.message import EmailMessage
from uuid import uuid4

from app.clock import now_utc
from app.config import Settings


def send(settings: Settings, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if settings.smtp_host:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            server.send_message(message)
        return
    outbox = settings.pathya_data_dir / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    stamp = now_utc().replace(":", "").replace("-", "")
    (outbox / f"{stamp}-{uuid4().hex[:8]}.eml").write_bytes(bytes(message))
