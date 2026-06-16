"""
Document & image handling for AJ.

- Text-based files (PDF, txt, md, csv) are extracted to text and injected as context.
- Images are converted to OpenAI-style image parts so a multimodal model (Gemini)
  can actually see them.
"""

from __future__ import annotations

import base64
import io
import os
from typing import Optional, Tuple

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".py", ".log"}


def is_image(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTS


def extract_text(filename: str, data: bytes, max_chars: int = 12000) -> Tuple[str, Optional[str]]:
    """Extract text from a document. Returns (text, error)."""
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return "", "PDF support needs pypdf: pip install pypdf"
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages).strip()
        except Exception as exc:
            return "", f"Couldn't read the PDF: {exc}"
    elif ext in TEXT_EXTS:
        try:
            text = data.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            return "", f"Couldn't read the file: {exc}"
    else:
        return "", f"Unsupported file type: {ext or 'unknown'}"

    if not text:
        return "", "No readable text found in the file."
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...truncated...]"
    return text, None


def image_part(filename: str, data: bytes) -> dict:
    """Build an OpenAI-style image content part (base64 data URL)."""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    mime = "jpeg" if ext == "jpg" else ext
    b64 = base64.b64encode(data).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}}
