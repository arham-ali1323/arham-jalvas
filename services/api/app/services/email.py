"""Minimal email sender for password-reset links.

Backends:
  console — prints the message to the log. Development only.
  smtp    — sends real mail via the configured SMTP server.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import get_settings


def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    backend = (settings.email_backend or "console").lower()

    if backend == "console":
        # Development: the reset link is written to the service log so it can be
        # followed locally. Never enable this in production.
        if settings.is_production:
            raise RuntimeError(
                "EMAIL_BACKEND=console must not be used in production."
            )
        print(f"[email:console] to={to} subject={subject!r}\n{body}\n")
        return

    if backend == "smtp":
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        return

    raise RuntimeError(f"Unsupported EMAIL_BACKEND: {settings.email_backend}")
