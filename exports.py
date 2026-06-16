"""
Export helpers — turn an AJ reply into a downloadable file.

Markdown export is dependency-free. PDF export uses reportlab if available.
"""

from __future__ import annotations

import io
from typing import Optional, Tuple


def to_pdf(text: str, title: str = "AJ — Purvi Technologies") -> Tuple[Optional[bytes], Optional[str]]:
    """Render plain text to a simple PDF. Returns (pdf_bytes, error)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        return None, "PDF export needs reportlab: pip install reportlab"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for block in text.split("\n\n"):
        block = block.strip().replace("\n", "<br/>")
        if block:
            # Escape stray angle brackets that aren't our <br/>.
            safe = block.replace("&", "&amp;").replace("<br/>", "\x00").replace("<", "&lt;").replace(">", "&gt;").replace("\x00", "<br/>")
            story.append(Paragraph(safe, styles["BodyText"]))
            story.append(Spacer(1, 8))
    try:
        doc.build(story)
    except Exception as exc:
        return None, f"PDF build failed: {exc}"
    return buf.getvalue(), None
