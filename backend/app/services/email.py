import html
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_welcome_email(to_email: str) -> None:
    subject = "Bienvenido a ARI"
    html_body = _auth_email_template(
        eyebrow="ARI Solara",
        title="Tu luz ya esta encendida",
        body=(
            "Bienvenido a ARI. Tu espacio privado esta listo para ordenar ideas, "
            "guardar memoria y convertir conversaciones en accion."
        ),
        cta_label="Entrar en ARI",
        cta_url=settings.PUBLIC_APP_URL,
        footer="Si no creaste esta cuenta, puedes ignorar este mensaje.",
    )
    text_body = (
        "Bienvenido a ARI.\n\n"
        "Tu espacio privado esta listo para ordenar ideas, guardar memoria y convertir conversaciones en accion.\n\n"
        f"Entrar en ARI: {settings.PUBLIC_APP_URL}"
    )
    send_email(to_email, subject, html_body, text_body)


def send_password_reset_email(to_email: str, reset_url: str, expires_minutes: int) -> None:
    subject = "Recupera tu contrasena de ARI"
    html_body = _auth_email_template(
        eyebrow="Recuperacion segura",
        title="Restablece tu acceso",
        body=(
            f"Recibimos una solicitud para cambiar tu contrasena. "
            f"Este enlace vence en {expires_minutes} minutos."
        ),
        cta_label="Crear nueva contrasena",
        cta_url=reset_url,
        footer="Si no fuiste tu, no necesitas hacer nada. Tu contrasena actual sigue activa.",
    )
    text_body = (
        "Recupera tu contrasena de ARI.\n\n"
        f"Este enlace vence en {expires_minutes} minutos:\n{reset_url}\n\n"
        "Si no fuiste tu, no necesitas hacer nada."
    )
    send_email(to_email, subject, html_body, text_body)


def send_email(to_email: str, subject: str, html_body: str, text_body: str) -> None:
    if not settings.SMTP_HOST:
        logger.info("Email not sent because SMTP_HOST is empty: to=%s subject=%s", to_email, subject)
        logger.debug("Email body preview: %s", text_body)
        return

    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=12) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USERNAME:
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def _auth_email_template(eyebrow: str, title: str, body: str, cta_label: str, cta_url: str, footer: str) -> str:
    safe_eyebrow = html.escape(eyebrow)
    safe_title = html.escape(title)
    safe_body = html.escape(body)
    safe_cta_label = html.escape(cta_label)
    safe_cta_url = html.escape(cta_url, quote=True)
    safe_footer = html.escape(footer)

    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
  </head>
  <body style="margin:0;background:#1A1208;color:#F7F2EC;font-family:Jost,Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#1A1208;padding:36px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;border:1px solid rgba(201,169,110,.26);background:#160d05;">
            <tr>
              <td style="height:2px;background:linear-gradient(90deg,transparent,#C4836A,#C9A96E,transparent);"></td>
            </tr>
            <tr>
              <td style="padding:42px 36px 34px;text-align:center;">
                <div style="font-size:10px;letter-spacing:4px;text-transform:uppercase;color:rgba(201,169,110,.58);">{safe_eyebrow}</div>
                <div style="margin-top:18px;font-family:Georgia,serif;font-size:46px;font-style:italic;font-weight:300;letter-spacing:7px;color:#F7F2EC;"><span style="color:#C9A96E;">A</span>ri</div>
                <div style="margin-top:6px;font-size:9px;letter-spacing:4px;text-transform:uppercase;color:rgba(201,169,110,.44);">Solara · Quantum Intelligent</div>
                <h1 style="margin:34px 0 12px;font-family:Georgia,serif;font-size:28px;font-style:italic;font-weight:300;color:#F7F2EC;">{safe_title}</h1>
                <p style="margin:0 auto;max-width:420px;color:rgba(255,248,240,.76);font-size:16px;line-height:1.65;">{safe_body}</p>
                <a href="{safe_cta_url}" style="display:inline-block;margin-top:30px;padding:14px 24px;border:1px solid rgba(201,169,110,.42);color:#F7F2EC;text-decoration:none;font-family:Georgia,serif;font-size:17px;font-style:italic;letter-spacing:2px;">{safe_cta_label}</a>
                <p style="margin:28px auto 0;max-width:420px;color:rgba(201,169,110,.46);font-size:12px;line-height:1.6;">{safe_footer}</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
