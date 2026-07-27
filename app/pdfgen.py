"""Task 5.5 — render variable cheque fields at template mm coordinates.

Only the variable text is drawn (no boxes/labels); the physical cheque
leaf already carries the bank's pre-printed layout. printer_offset_*_mm
from the template row is applied to every field.
"""
from io import BytesIO

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

MIN_FONT_SIZE = 6

_FONT_FAMILIES = ("Helvetica", "Times-Roman", "Courier")
_BOLD_NAME = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}

CROSSING_LABELS = {"ac_payee": "A/C PAYEE ONLY", "not_negotiable": "NOT NEGOTIABLE"}


def _resolve_font(spec: dict) -> str:
    """Per-field font family + bold, e.g. {"font_family": "Times-Roman", "bold": true}."""
    family = spec.get("font_family", "Helvetica")
    if family not in _FONT_FAMILIES:
        family = "Helvetica"
    return _BOLD_NAME[family] if spec.get("bold") else family


def _draw_crossing(c, page_h: float, crossing: str | None, crossing_text: str | None) -> None:
    """Standard cheque crossing: two parallel diagonal lines with a label
    between them in the top-left corner (A/C Payee Only / Not Negotiable /
    custom text)."""
    if not crossing or crossing == "none":
        return
    label = CROSSING_LABELS.get(crossing) or (crossing_text or "").strip()
    if not label:
        return
    x1, x2 = 4 * mm, 46 * mm
    y1, y2 = page_h - 22 * mm, page_h - 6 * mm
    offset = 3.2 * mm
    c.saveState()
    c.setLineWidth(0.8)
    c.line(x1, y1, x2, y2)
    c.line(x1, y1 + offset, x2, y2 + offset)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString((x1 + x2) / 2, (y1 + y2) / 2 + 1, label)
    c.restoreState()


def _draw_watermark(c, page_w: float, page_h: float, watermark_cancelled: bool) -> None:
    """Large diagonal 'CANCELLED' watermark across the whole leaf."""
    if not watermark_cancelled:
        return
    c.saveState()
    c.setFont("Helvetica-Bold", min(page_w, page_h) / mm)
    c.setFillColorRGB(0.82, 0.82, 0.82)
    c.translate(page_w / 2, page_h / 2)
    c.rotate(28)
    c.drawCentredString(0, 0, "CANCELLED")
    c.restoreState()


def generate_cheque_pdf(template: dict, data: dict, *, crossing: str | None = None,
                         crossing_text: str | None = None, watermark_cancelled: bool = False) -> bytes:
    """template: bank_templates row (fields JSONB per addendum 3.2).
    data: {payee_name, amount_figures, amount_words, date_day, date_month, date_year}
    Per-field style keys (all optional): font_family (Helvetica/Times-Roman/Courier),
    bold (bool), underline (bool).
    """
    page_w = float(template["page_width_mm"]) * mm
    page_h = float(template["page_height_mm"]) * mm
    off_x = float(template.get("printer_offset_x_mm", 0))
    off_y = float(template.get("printer_offset_y_mm", 0))

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    for field_name, spec in template["fields"].items():
        text = str(data.get(field_name, ""))
        if not text:
            continue
        x = (float(spec["x_mm"]) + off_x) * mm
        # PDF origin is bottom-left; template y_mm is measured from the top edge
        y = page_h - (float(spec["y_mm"]) + off_y) * mm
        font_size = float(spec.get("font_size", 10))
        font_name = _resolve_font(spec)

        max_width_mm = spec.get("max_width_mm")
        if max_width_mm:
            max_w = float(max_width_mm) * mm
            # Long payee names: shrink font until it fits (never below MIN_FONT_SIZE)
            while font_size > MIN_FONT_SIZE and c.stringWidth(text, font_name, font_size) > max_w:
                font_size -= 0.5

        c.setFont(font_name, font_size)
        c.drawString(x, y, text)
        if spec.get("underline"):
            width = c.stringWidth(text, font_name, font_size)
            underline_y = y - font_size * 0.12
            c.setLineWidth(max(0.4, font_size * 0.05))
            c.line(x, underline_y, x + width, underline_y)

    _draw_crossing(c, page_h, crossing, crossing_text)
    _draw_watermark(c, page_w, page_h, watermark_cancelled)

    c.save()
    return buf.getvalue()


def generate_alignment_grid_pdf(page_width_mm: float, page_height_mm: float, step_mm: float = 10) -> bytes:
    """Printer/leaf-size calibration aid: a plain 10mm ruled grid with mm
    labels, printed with NO offset applied. Print this on blank paper, hold
    it against (or under a light, against) the real cheque leaf, and read
    off how far the leaf's boxes sit from the ruled lines — that's the
    printer_offset_x/y_mm to enter on the Calibration page. This is a
    separate calibration concern from per-field x/y placement: this
    measures physical printer/tray drift, not where a field should go.
    """
    page_w = page_width_mm * mm
    page_h = page_height_mm * mm
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    c.setLineWidth(0.3)
    c.setStrokeColorRGB(0.55, 0.55, 0.55)
    c.setFont("Helvetica", 5.5)
    c.setFillColorRGB(0.3, 0.3, 0.3)

    x = 0.0
    while x <= page_width_mm + 1e-6:
        px = x * mm
        c.line(px, 0, px, page_h)
        if x > 0:
            c.drawString(px + 0.8, 2, str(int(x)))
        x += step_mm

    y = 0.0
    while y <= page_height_mm + 1e-6:
        # y is measured from the top edge, matching bank_templates field convention
        py = page_h - y * mm
        c.line(0, py, page_w, py)
        if y > 0:
            c.drawString(2, py + 0.8, str(int(y)))
        y += step_mm

    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.8)
    c.rect(0, 0, page_w, page_h)

    c.save()
    return buf.getvalue()
