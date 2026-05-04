import base64
import os
import jwt
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from fastmcp import FastMCP

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# JWT Config
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

mcp = FastMCP("GmailManager")


# ─── JWT UTILITIES ─────────────────────────────────────────────────────────────
def generate_token(user_id: str) -> str:
    """Genera un token JWT válido por 24 horas."""
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verifica y decodifica un token JWT."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {"valid": True, "user_id": payload["sub"]}
    except jwt.ExpiredSignatureError:
        return {"valid": False, "error": "Token expirado"}
    except jwt.InvalidTokenError:
        return {"valid": False, "error": "Token inválido"}


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


# ─── TOOL: Generar token JWT ───────────────────────────────────────────────────
@mcp.tool()
def get_jwt_token(user_id: str) -> dict:
    """Genera un token JWT para autenticación remota.
    
    Args:
        user_id: Identificador del usuario (ej: tu email)
    """
    token = generate_token(user_id)
    return {
        "token": token,
        "expires_in": f"{JWT_EXPIRY_HOURS} horas",
        "algorithm": JWT_ALGORITHM,
    }


# ─── TOOL: Verificar token JWT ─────────────────────────────────────────────────
@mcp.tool()
def check_jwt_token(token: str) -> dict:
    """Verifica si un token JWT es válido.
    
    Args:
        token: El token JWT a verificar
    """
    return verify_token(token)


# ─── TOOL: Listar emails ───────────────────────────────────────────────────────
@mcp.tool()
def list_emails(query: str = "in:inbox", max_results: int = 10, token: str = "") -> list[dict]:
    """Lista los emails más recientes de Gmail.
    
    Args:
        query: Filtro de búsqueda estilo Gmail
        max_results: Número máximo de emails a devolver
        token: JWT token para autenticación remota (opcional en local)
    """
    if token:
        result = verify_token(token)
        if not result["valid"]:
            return [{"error": result["error"]}]

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
def send_email(to: str, subject: str, body: str, token: str = "") -> dict:
    """Envía un email desde la cuenta de Gmail autenticada.
    
    Args:
        to: Dirección de destino
        subject: Asunto del email
        body: Cuerpo del mensaje
        token: JWT token para autenticación remota (opcional en local)
    """
    if token:
        result = verify_token(token)
        if not result["valid"]:
            return {"error": result["error"]}

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