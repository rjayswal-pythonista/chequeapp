"""Task 5.7 — dot matrix output: raw ESC/P text stream, grid-positioned.

Dot matrix printers are character-grid devices: positioning is rows and
columns at a fixed pitch (10 CPI, 6 LPI here), not free-form millimeters.
The mm coordinates in bank_templates are converted to the nearest grid
cell — this is a genuinely separate rendering path from the PDF pipeline,
per the main spec Section 3.5.2, and must be physically calibrated against
the client's actual printer model before production use.
"""
CPI = 10   # characters per inch (standard draft pitch)
LPI = 6    # lines per inch
MM_PER_INCH = 25.4

ESC_INIT = b"\x1b@"   # ESC @ — reset printer
FORM_FEED = b"\x0c"   # advance to next cheque in the continuous booklet

CROSSING_LABELS = {"ac_payee": "A/C PAYEE ONLY", "not_negotiable": "NOT NEGOTIABLE"}


def _mm_to_col(x_mm: float) -> int:
    return max(0, round(x_mm / MM_PER_INCH * CPI))


def _mm_to_row(y_mm: float) -> int:
    return max(0, round(y_mm / MM_PER_INCH * LPI))


def generate_cheque_escp(template: dict, data: dict, *, crossing: str | None = None,
                          crossing_text: str | None = None, watermark_cancelled: bool = False) -> bytes:
    off_x = float(template.get("printer_offset_x_mm", 0))
    off_y = float(template.get("printer_offset_y_mm", 0))

    rows: dict[int, list[tuple[int, str]]] = {}
    for field_name, spec in template["fields"].items():
        text = str(data.get(field_name, "") or "")
        if not text:
            continue
        r = _mm_to_row(float(spec["y_mm"]) + off_y)
        c = _mm_to_col(float(spec["x_mm"]) + off_x)
        rows.setdefault(r, []).append((c, text))

    # Character-grid printers can't draw diagonal lines or a rotated
    # watermark; render crossing/cancellation as a plain banner line instead.
    banner_parts = []
    if crossing and crossing != "none":
        label = CROSSING_LABELS.get(crossing) or (crossing_text or "").strip()
        if label:
            banner_parts.append(f"[{label}]")
    if watermark_cancelled:
        banner_parts.append("*** CANCELLED ***")
    if banner_parts:
        rows.setdefault(0, []).insert(0, (0, "  ".join(banner_parts)))

    out = bytearray(ESC_INIT)
    current_row = 0
    for r in sorted(rows):
        out += b"\n" * (r - current_row)
        current_row = r
        line = ""
        for col, text in sorted(rows[r]):
            if col > len(line):
                line += " " * (col - len(line))
            elif col < len(line):
                line += " "  # collision: separate rather than overwrite
            line += text
        out += line.encode("ascii", "replace")
        out += b"\r"
    out += FORM_FEED
    return bytes(out)
