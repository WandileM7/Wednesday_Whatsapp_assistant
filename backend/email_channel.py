"""Email channel: poll IMAP for mail from allowlisted senders, route it
through the agent, reply in-thread via SMTP.

Stdlib imaplib/smtplib in worker threads — no new dependencies. Off unless
EMAIL_ADDRESS and EMAIL_PASSWORD (an app password) are set. The first
allowlisted sender shares the owner's identity (default_user); other
allowlisted senders get their own history threads.
"""
from __future__ import annotations
import asyncio, email, imaplib, logging, smtplib
from email.message import EmailMessage
from email.utils import parseaddr

from . import agent, markers
from .config import settings

log = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(settings.email_address and settings.email_password)


def _allowed_senders() -> list[str]:
    return [a.strip().lower() for a in settings.email_allowed_senders.split(",") if a.strip()]


def user_key_for(sender: str) -> str | None:
    """None = not allowed to talk to Wednesday."""
    allowed = _allowed_senders()
    sender = sender.lower()
    if not allowed or sender not in allowed: return None
    return settings.default_user if sender == allowed[0] else f"mail:{sender}"


def extract_text(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload: return payload.decode(part.get_content_charset() or "utf-8",
                                                  errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace") \
        if payload else ""


def _fetch_unseen() -> list[email.message.Message]:
    with imaplib.IMAP4_SSL(settings.email_imap_host) as imap:
        imap.login(settings.email_address, settings.email_password)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        out = []
        for num in (data[0].split() if data and data[0] else []):
            _, raw = imap.fetch(num, "(RFC822)")
            if raw and raw[0]:
                out.append(email.message_from_bytes(raw[0][1]))
            imap.store(num, "+FLAGS", "\\Seen")
        return out


def _send_reply(to_addr: str, subject: str, body: str, in_reply_to: str | None) -> None:
    reply = EmailMessage()
    reply["From"] = settings.email_address
    reply["To"] = to_addr
    reply["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to:
        reply["In-Reply-To"] = in_reply_to
        reply["References"] = in_reply_to
    reply.set_content(body)
    with smtplib.SMTP_SSL(settings.email_smtp_host) as smtp:
        smtp.login(settings.email_address, settings.email_password)
        smtp.send_message(reply)


async def _handle(msg: email.message.Message) -> None:
    sender = parseaddr(msg.get("From", ""))[1]
    user = user_key_for(sender)
    if user is None:
        log.info("ignoring email from non-allowlisted %s", sender)
        return
    subject = msg.get("Subject", "") or "(no subject)"
    body = extract_text(msg).strip()
    if not body: return
    text = f"[Email from {sender}] Subject: {subject}\n\n{body[:4000]}"
    reply_text = markers.strip(await agent.reply(user, text, surface="email")).strip()
    if reply_text:
        await asyncio.to_thread(_send_reply, sender, subject, reply_text,
                                msg.get("Message-ID"))


async def run() -> None:
    if not enabled():
        return
    if not _allowed_senders():
        log.warning("email channel: EMAIL_ALLOWED_SENDERS is empty — answering nobody")
    log.info("email channel polling %s every %ds",
             settings.email_imap_host, settings.email_poll_seconds)
    while True:
        try:
            for msg in await asyncio.to_thread(_fetch_unseen):
                await _handle(msg)
        except Exception:
            log.exception("email poll failed")
        await asyncio.sleep(settings.email_poll_seconds)
