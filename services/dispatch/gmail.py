"""Gmail API sender with the OAuth desktop flow (WP5.3).

The OAuth client file and the saved token live outside the repository (default ``~/.config/surgesight/``);
in the cloud they belong in Secret Manager. Only ``gmail.send`` is requested.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage
import os
from pathlib import Path
from typing import Any

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CONFIG_DIR = Path(os.getenv("SURGESIGHT_CONFIG_DIR", str(Path.home() / ".config" / "surgesight")))


def client_secret_file() -> Path:
    return Path(os.getenv("GMAIL_CLIENT_SECRET_FILE", str(CONFIG_DIR / "gmail_client_secret.json")))


def token_file() -> Path:
    return Path(os.getenv("GMAIL_TOKEN_FILE", str(CONFIG_DIR / "gmail_token.json")))


def is_configured() -> bool:
    return token_file().exists() or client_secret_file().exists()


def build_message(sender: str | None, recipients: list[str], subject: str, body: str, attachments: list[dict[str, Any]] | None = None) -> EmailMessage:
    message = EmailMessage()
    message["To"], message["Subject"] = ", ".join(recipients), subject
    if sender:  # with the gmail.send scope only, Gmail sets From to the signed-in account
        message["From"] = sender
    message.set_content(body)
    for item in attachments or []:
        maintype, _, subtype = item.get("mime", "text/plain").partition("/")
        message.add_attachment(item["text"].encode("utf-8"), maintype=maintype, subtype=subtype or "plain", filename=item["name"])
    return message


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = Credentials.from_authorized_user_file(str(token_file()), SCOPES) if token_file().exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not client_secret_file().exists():
            raise RuntimeError(f"Gmail OAuth client file not found at {client_secret_file()}")
        creds = InstalledAppFlow.from_client_secrets_file(str(client_secret_file()), SCOPES).run_local_server(port=0)
    token_file().parent.mkdir(parents=True, exist_ok=True)
    token_file().write_text(creds.to_json(), encoding="utf-8")
    token_file().chmod(0o600)
    return creds


def send_email(recipients: list[str], subject: str, body: str, attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from googleapiclient.discovery import build

    service = build("gmail", "v1", credentials=_credentials(), cache_discovery=False)
    message = build_message(None, recipients, subject, body, attachments)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"message_id": sent.get("id")}
