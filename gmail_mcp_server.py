import base64
import os
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from fastmcp import FastMCP

# Scopes necesarios para leer y enviar emails
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

mcp = FastMCP("GmailManager")


def get_gmail_service():
    """Maneja el flujo OAuth y devuelve el servicio de Gmail."""
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ─── TOOL: Listar emails ───────────────────────────────────────────────────────
@mcp.tool()
def list_emails(query: str = "in:inbox", max_results: int = 10) -> list[dict]:
    """Lista los emails más recientes de Gmail.
    
    Args:
        query: Filtro de búsqueda estilo Gmail (ej: 'in:inbox', 'is:unread')
        max_results: Número máximo de emails a devolver
    """
    service = get_gmail_service()

    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        detail = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()

        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": detail.get("snippet", ""),
        })

    return emails


# ─── TOOL: Enviar email ────────────────────────────────────────────────────────
@mcp.tool()
def send_email(to: str, subject: str, body: str) -> dict:
    """Envía un email desde la cuenta de Gmail autenticada.
    
    Args:
        to: Dirección de destino
        subject: Asunto del email
        body: Cuerpo del mensaje
    """
    service = get_gmail_service()

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject

    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(
        userId="me", body={"raw": encoded}
    ).execute()

    return {"status": "sent", "message_id": result["id"]}


# ─── RESOURCE: Perfil de usuario ──────────────────────────────────────────────
@mcp.resource("gmail://profile")
def get_profile() -> dict:
    """Devuelve la información del perfil de la cuenta de Gmail."""
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    return {
        "email": profile.get("emailAddress", ""),
        "total_messages": profile.get("messagesTotal", 0),
        "total_threads": profile.get("threadsTotal", 0),
    }


# ─── PROMPT: Plantilla para redactar email ────────────────────────────────────
@mcp.prompt()
def draft_email(recipient: str, topic: str) -> str:
    """Plantilla para pedir ayuda redactando un email profesional."""
    return f"""Por favor, ayúdame a redactar un email profesional con los siguientes detalles:

Destinatario: {recipient}
Tema: {topic}

El email debe ser claro, conciso y con tono profesional.
Incluye: saludo apropiado, cuerpo del mensaje y despedida."""


if __name__ == "__main__":
    mcp.run()