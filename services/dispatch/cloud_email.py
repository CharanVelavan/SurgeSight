"""Email senders for Cloud Run (SendGrid and SMTP) that do not need interactive login."""

import os
from typing import Any
import requests
import smtplib
from email.message import EmailMessage

def send_email(recipients: list[str], subject: str, body: str, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    provider = os.getenv("EMAIL_PROVIDER", "smtp").lower()
    
    # Cap recipients per send
    recipients = recipients[:50]
    
    if provider == "sendgrid":
        return _send_sendgrid(recipients, subject, body, attachments)
    elif provider == "smtp":
        return _send_smtp(recipients, subject, body, attachments)
    else:
        raise ValueError(f"Unknown EMAIL_PROVIDER '{provider}'")

def _send_sendgrid(recipients: list[str], subject: str, body: str, attachments: list[dict[str, Any]] | None) -> dict[str, Any]:
    api_key = os.getenv("SENDGRID_API_KEY")
    sender = os.getenv("EMAIL_SENDER_ADDRESS", "noreply@surgesight.org")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY is not set")
    
    url = "https://api.sendgrid.com/v3/mail/send"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    payload: dict[str, Any] = {
        "personalizations": [{"to": [{"email": r} for r in recipients]}],
        "from": {"email": sender},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}]
    }
    
    if attachments:
        import base64
        atts = []
        for a in attachments:
            atts.append({
                "content": base64.b64encode(a["text"].encode("utf-8")).decode("utf-8"),
                "filename": a["name"],
                "type": a.get("mime", "text/plain"),
                "disposition": "attachment"
            })
        payload["attachments"] = atts

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return {"status": "sent", "provider": "sendgrid"}

def _send_smtp(recipients: list[str], subject: str, body: str, attachments: list[dict[str, Any]] | None) -> dict[str, Any]:
    server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if not user or not password:
        raise RuntimeError("SMTP_USER or SMTP_PASSWORD is not set")
        
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = user
    msg['To'] = ", ".join(recipients)
    msg.set_content(body)
    
    for att in (attachments or []):
        maintype, _, subtype = att.get("mime", "text/plain").partition("/")
        msg.add_attachment(att["text"].encode("utf-8"), maintype=maintype, subtype=subtype or "plain", filename=att["name"])
        
    with smtplib.SMTP(server, port, timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
        
    return {"status": "sent", "provider": "smtp"}
