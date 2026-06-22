"""
WhatsApp sending via Twilio (outbound).

AJ uses this to send WhatsApp messages on the founder's behalf. Credentials come from
the environment (never hard-coded), so the feature stays dormant until they're set:

    TWILIO_ACCOUNT_SID    -> from console.twilio.com (starts with "AC...")
    TWILIO_AUTH_TOKEN     -> from console.twilio.com
    TWILIO_WHATSAPP_FROM  -> the sender, e.g. "whatsapp:+14155238886" (sandbox default)

In the Twilio sandbox a recipient must have joined the sandbox first (send the join code
from their phone), so outbound works to your own number and anyone who has opted in.
"""

from __future__ import annotations

import os

# Twilio's shared WhatsApp sandbox sender — overridden once you have your own number.
_SANDBOX_FROM = "whatsapp:+14155238886"


def from_number() -> str:
    return os.environ.get("TWILIO_WHATSAPP_FROM", _SANDBOX_FROM).strip()


def configured() -> bool:
    """True once Twilio credentials are present in the environment."""
    return bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN"))


def _normalize(to: str) -> str:
    """Turn a phone number into Twilio's `whatsapp:+<E.164>` form."""
    to = (to or "").strip()
    if to.startswith("whatsapp:"):
        return to
    digits = to.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not digits.startswith("+"):
        digits = "+" + digits
    return "whatsapp:" + digits


def send_whatsapp(to: str, body: str) -> str:
    """Send a WhatsApp message. Returns a short human-readable status string."""
    if not configured():
        return ("WhatsApp isn't set up yet — Twilio credentials are missing. "
                "Ask the founder to add them in settings.")
    body = (body or "").strip()
    if not body:
        return "Nothing to send — the message was empty."
    if not (to or "").strip():
        return "I need a phone number (with country code) to send the WhatsApp message to."
    try:
        from twilio.rest import Client  # lazy import so the app runs without the SDK installed
        client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
        msg = client.messages.create(from_=from_number(), to=_normalize(to), body=body[:1500])
        return f"✅ WhatsApp message sent to {to} (Twilio id {msg.sid})."
    except Exception as exc:  # noqa: BLE001 — surface the reason to the agent/user
        return (f"⚠️ Couldn't send the WhatsApp message: {exc}. "
                "If using the sandbox, make sure the recipient has joined it first.")
