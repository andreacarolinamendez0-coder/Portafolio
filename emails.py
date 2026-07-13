"""
mailer.py — Envío de correos vía Gmail API.

Funciona en Railway (Free/Hobby) porque usa HTTPS, no SMTP.

Variables de entorno requeridas:
    GMAIL_CLIENT_ID
    GMAIL_CLIENT_SECRET
    GMAIL_REFRESH_TOKEN
    GMAIL_SENDER      -> tucorreo@gmail.com

Dependencias:
    google-api-python-client
    google-auth
"""
from dotenv import load_dotenv
load_dotenv()  
import base64
import html as html_lib
import logging
import os
import re
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
TOKEN_URI = "https://oauth2.googleapis.com/token"

_creds = None  # se cachean: google-auth refresca el access token solo


def _get_credentials() -> Credentials:
    global _creds
    if _creds is None:
        try:
            _creds = Credentials(
                token=None,
                refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
                client_id=os.environ["GMAIL_CLIENT_ID"],
                client_secret=os.environ["GMAIL_CLIENT_SECRET"],
                token_uri=TOKEN_URI,
                scopes=SCOPES,
            )
        except KeyError as e:
            raise RuntimeError(f"Falta la variable de entorno {e}") from e
    return _creds


def _html_to_text(html: str) -> str:
    """Fallback en texto plano para clientes que no renderizan HTML."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</(p|div|h\d|tr)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def send_email(to: str, subject: str, html: str, text: str | None = None) -> bool:
    """Envía un correo. Devuelve True/False; nunca lanza excepción hacia arriba."""
    sender = os.getenv("GMAIL_SENDER")
    app_name = os.getenv("APP_NAME", "Portafolio")

    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = f"{app_name} <{sender}>"
    msg["Subject"] = subject
    msg["Reply-To"] = sender
    msg.set_content(text or _html_to_text(html))
    msg.add_alternative(html, subtype="html")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        # El service se construye por llamada: el objeto HTTP de googleapiclient
        # no es thread-safe y Flask puede atender peticiones en paralelo.
        service = build(
            "gmail", "v1", credentials=_get_credentials(), cache_discovery=False
        )
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        logger.info("Correo enviado a %s (id=%s)", to, result.get("id"))
        return True
    except HttpError as e:
        logger.error("Gmail API rechazó el envío a %s: %s", to, e)
        return False
    except Exception as e:  # refresh token revocado, red caída, etc.
        logger.exception("Error inesperado enviando a %s: %s", to, e)
        return False


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------

def _layout(titulo: str, cuerpo: str, cta_texto: str = "", cta_url: str = "") -> str:
    app_name = os.getenv("APP_NAME", "Portafolio")
    cta = ""
    if cta_texto and cta_url:
        cta = f"""
        <p style="margin:28px 0;">
          <a href="{cta_url}"
             style="background:#1a73e8;color:#fff;text-decoration:none;
                    padding:12px 22px;border-radius:6px;display:inline-block;
                    font-weight:600;">{cta_texto}</a>
        </p>"""

    return f"""\
<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:24px;background:#f5f6f8;
             font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:10px;
              padding:32px;color:#202124;line-height:1.6;">
    <h1 style="margin:0 0 20px;font-size:20px;">{titulo}</h1>
    {cuerpo}
    {cta}
    <hr style="border:0;border-top:1px solid #e8eaed;margin:28px 0 16px;">
    <p style="font-size:12px;color:#5f6368;margin:0;">
      {app_name} · Este es un correo automático.
    </p>
  </div>
</body>
</html>"""


def enviar_bienvenida(to: str, nombre: str) -> bool:
    app_name = os.getenv("APP_NAME", "Portafolio")
    app_url = os.getenv("APP_URL", "")
    cuerpo = f"""
    <p>Hola {nombre}, ¡bienvenido/a a {app_name}!</p>
    <p>Tu cuenta ya está activa. Puedes empezar a construir tu portafolio,
       configurar alertas de precio y recibir tu reporte mensual.</p>"""
    return send_email(
        to,
        f"Bienvenido/a a {app_name}",
        _layout(f"Bienvenido/a a {app_name}", cuerpo, "Ir a la app", app_url),
    )


def enviar_reset_password(to: str, reset_url: str, minutos: int = 60) -> bool:
    cuerpo = f"""
    <p>Recibimos una solicitud para restablecer tu contraseña.</p>
    <p>El enlace vence en <strong>{minutos} minutos</strong> y solo puede usarse una vez.</p>
    <p style="font-size:13px;color:#5f6368;">
      Si no fuiste tú, ignora este correo: tu contraseña no cambiará.</p>"""
    return send_email(
        to,
        "Restablece tu contraseña",
        _layout("Restablece tu contraseña", cuerpo, "Crear nueva contraseña", reset_url),
    )


def enviar_reporte_mensual(to: str, nombre: str, periodo: str, metricas: dict) -> bool:
    """metricas: {'Valor del portafolio': '$12.400', 'Rendimiento': '+3,2%', ...}"""
    filas = "".join(
        f"""<tr>
              <td style="padding:10px 0;color:#5f6368;">{k}</td>
              <td style="padding:10px 0;text-align:right;font-weight:600;">{v}</td>
            </tr>"""
        for k, v in metricas.items()
    )
    cuerpo = f"""
    <p>Hola {nombre}, este es el resumen de tu portafolio en {periodo}.</p>
    <table style="width:100%;border-collapse:collapse;margin-top:8px;">{filas}</table>"""
    return send_email(
        to,
        f"Tu reporte de {periodo}",
        _layout(
            f"Reporte de {periodo}",
            cuerpo,
            "Ver detalle",
            os.getenv("APP_URL", ""),
        ),
    )