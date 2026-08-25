"""Deliver OTP mail through Resend, with SMTP as a fallback."""

from __future__ import annotations

import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

from config import (
    RESEND_API_KEY,
    RESEND_FROM,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

HOSTS_BY_DOMAIN = {
    "gmail.com": "smtp.gmail.com",
    "googlemail.com": "smtp.gmail.com",
    "outlook.com": "smtp.office365.com",
    "hotmail.com": "smtp.office365.com",
    "live.com": "smtp.office365.com",
    "yahoo.com": "smtp.mail.yahoo.com",
}


def smtp_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)


def resend_configured() -> bool:
    return bool(RESEND_API_KEY)


def email_configured() -> bool:
    return resend_configured() or smtp_configured()


def _host() -> str:
    if SMTP_HOST:
        return SMTP_HOST
    domain = SMTP_USER.split("@")[-1].lower() if "@" in SMTP_USER else ""
    return HOSTS_BY_DOMAIN.get(domain, "smtp.gmail.com")


def _from_header() -> str:
    display = "Staywise"
    if SMTP_FROM and "@" in SMTP_FROM and "localhost" not in SMTP_FROM and "hotelbudget.local" not in SMTP_FROM:
        return SMTP_FROM
    return formataddr((display, SMTP_USER))


def _password() -> str:
    return SMTP_PASSWORD.replace(" ", "")


def _otp_html(otp: str) -> str:
    return f"""
    <div style="font-family:Inter,'Segoe UI',sans-serif;max-width:480px;margin:0 auto;padding:24px;color:#1A1A2E">
      <div style="font-size:13px;font-weight:700;color:#173d34;margin-bottom:16px">staywise</div>
      <h2 style="color:#173d34;margin:0 0 8px">Verify your email</h2>
      <p style="color:#4B5563;margin:0 0 8px">Use this one-time code to finish setting up your account.</p>
      <div style="font-size:32px;letter-spacing:8px;font-weight:700;color:#173d34;background:#F4F6FB;
                  padding:16px 20px;border-radius:12px;text-align:center;margin:20px 0">{otp}</div>
      <p style="color:#6B7280;font-size:13px;margin:0">This code expires in 5 minutes. If you did not request it, ignore this email.</p>
    </div>
    """


def _send_via_resend(to_email: str, otp: str) -> bool:
    payload = json.dumps({
        "from": RESEND_FROM,
        "to": [to_email],
        "subject": "Your staywise verification code",
        "html": _otp_html(otp),
        "text": f"Your verification code is {otp}. It expires in 5 minutes.",
    }).encode()
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "staywise-hotel-budget/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if 200 <= response.status < 300:
                print(f"[OTP] Sent verification code to {to_email} via Resend")
                return True
            raise RuntimeError(f"Resend returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Resend could not send the email: {detail or exc}") from exc


def _send_via_smtp(to_email: str, otp: str) -> bool:
    message = MIMEMultipart("alternative")
    message["Subject"] = "Your staywise verification code"
    message["From"] = _from_header()
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="staywise.local")
    message.attach(MIMEText(f"Your verification code is {otp}. It expires in 5 minutes.", "plain"))
    message.attach(MIMEText(_otp_html(otp), "html"))

    host = _host()
    port = SMTP_PORT
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as server:
            server.login(SMTP_USER, _password())
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(SMTP_USER, _password())
            server.send_message(message)
    print(f"[OTP] Sent verification code to {to_email} via {host}:{port}")
    return True


def send_otp_email(to_email: str, otp: str) -> bool:
    """Deliver a 6-digit OTP. Returns True on success, False if no mail provider is configured."""
    if resend_configured():
        return _send_via_resend(to_email, otp)
    if smtp_configured():
        try:
            return _send_via_smtp(to_email, otp)
        except smtplib.SMTPAuthenticationError as exc:
            raise RuntimeError(
                "SMTP login failed. For Gmail, use a 16-character App Password, or set RESEND_API_KEY."
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"Could not reach SMTP host {_host()}:{SMTP_PORT}.") from exc
    print(f"[OTP] Email is not configured. Verification code for {to_email}: {otp}")
    return False
