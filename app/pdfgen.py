"""Task 5.5 — render variable cheque fields at template mm coordinates.

Only the variable text is drawn (no boxes/labels); the physical cheque
leaf already carries the bank's pre-printed layout. printer_offset_*_mm
from the template row is applied to every field.
"""
from io import BytesIO

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

MIN_FONT_SIZE = 6


def generate_cheque_pdf(template: dict, data: dict) -> bytes:
    """template: bank_templates row (fields JSONB per addendum 3.2).
    data: {payee_name, amount_figures, amount_words, date_day, date_month, date_year}
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

        max_width_mm = spec.get("max_width_mm")
        if max_width_mm:
            max_w = float(max_width_mm) * mm
            # Long payee names: shrink font until it fits (never below MIN_FONT_SIZE)
            while font_size > MIN_FONT_SIZE and c.stringWidth(text, "Helvetica", font_size) > max_w:
                font_size -= 0.5

        c.setFont("Helvetica", font_size)
        c.drawString(x, y, text)

    c.save()
    return buf.getvalue()
