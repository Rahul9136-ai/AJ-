"""
AJ on WhatsApp — inbound webhook (Twilio).

A tiny FastAPI service that lets the founder chat with AJ straight from WhatsApp.
Twilio POSTs every incoming WhatsApp message to `/whatsapp`; we run it through the
same coordinator the dashboard uses and reply with TwiML.

Run locally:   uvicorn whatsapp_bot:app --host 0.0.0.0 --port 8000
On Azure:      gunicorn -k uvicorn.workers.UvicornWorker whatsapp_bot:app

Point your Twilio WhatsApp sandbox "When a message comes in" webhook at:
    https://<this-app>/whatsapp     (HTTP POST)

It shares the agents, memory and to-do list with the dashboard (same code), so what
you tell AJ on WhatsApp is remembered in the dashboard too.
"""

from __future__ import annotations

import html
from typing import Dict, List

from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from orchestrator import coordinate

app = FastAPI(title="AJ WhatsApp webhook")

# Short rolling history per WhatsApp sender (in-memory; resets on restart).
_HISTORY: Dict[str, List[dict]] = {}
_MAX_TURNS = 10          # keep the last few exchanges for context
_MAX_REPLY = 1500        # Twilio caps a WhatsApp message around 1600 chars


@app.get("/")
def health() -> JSONResponse:
    return JSONResponse({"status": "AJ WhatsApp webhook is running"})


def _twiml(message: str) -> Response:
    body = html.escape(message[:_MAX_REPLY] or "…")
    xml = f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{body}</Message></Response>"
    return Response(content=xml, media_type="application/xml")


@app.post("/whatsapp")
async def incoming(Body: str = Form(default=""), From: str = Form(default="")) -> Response:
    text = (Body or "").strip()
    sender = (From or "anon").strip()

    if not text:
        return _twiml("Hi! I'm AJ from Purvi Technologies. Send me a message and I'll help. 🙂")

    history = _HISTORY.get(sender, [])
    try:
        reply = coordinate(text, history=list(history))
    except Exception:  # noqa: BLE001 — never 500 back to Twilio; reply gracefully
        return _twiml("Sorry, I hit a snag just now. Please try again in a moment.")

    history = (history + [
        {"role": "user", "content": text},
        {"role": "assistant", "content": reply},
    ])[-(_MAX_TURNS * 2):]
    _HISTORY[sender] = history

    return _twiml(reply)


@app.get("/whatsapp")
def whatsapp_get() -> PlainTextResponse:
    # Friendly response if someone opens the webhook URL in a browser.
    return PlainTextResponse("AJ WhatsApp webhook is live. Twilio should POST here.")
