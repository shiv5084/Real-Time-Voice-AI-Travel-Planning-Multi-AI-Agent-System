"""PDF report generator for travel itineraries.

Uses ReportLab Platypus for structured, branded layout.
Entry point: generate_itinerary_pdf(itinerary_data) -> bytes
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand colours ──────────────────────────────────────────────────────────

ACCENT       = colors.HexColor("#6c63ff")
DARK_BG      = colors.HexColor("#111117")
SURFACE      = colors.HexColor("#1a1a24")
TEXT_PRIMARY = colors.HexColor("#f0f0f8")
TEXT_MUTED   = colors.HexColor("#a0a0b8")
SUCCESS      = colors.HexColor("#22c55e")

# ── Styles ─────────────────────────────────────────────────────────────────

def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            fontName="Helvetica-Bold",
            fontSize=26,
            textColor=ACCENT,
            alignment=TA_CENTER,
            spaceAfter=4 * mm,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName="Helvetica",
            fontSize=13,
            textColor=TEXT_MUTED,
            alignment=TA_CENTER,
            spaceAfter=2 * mm,
        ),
        "section_header": ParagraphStyle(
            "section_header",
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=ACCENT,
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
        ),
        "day_header": ParagraphStyle(
            "day_header",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=colors.HexColor("#ffffff"),
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10,
            textColor=TEXT_PRIMARY,
            spaceAfter=2 * mm,
            leading=14,
        ),
        "muted": ParagraphStyle(
            "muted",
            fontName="Helvetica",
            fontSize=9,
            textColor=TEXT_MUTED,
            spaceAfter=1 * mm,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName="Helvetica",
            fontSize=8,
            textColor=TEXT_MUTED,
            alignment=TA_CENTER,
        ),
    }


# ── Table styles ───────────────────────────────────────────────────────────

def _activity_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  SURFACE),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  ACCENT),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#0f0f18"), colors.HexColor("#151520")]),
        ("TEXTCOLOR",   (0, 1), (-1, -1), TEXT_PRIMARY),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#2a2a3a")),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWHEIGHT",   (0, 0), (-1, -1), 18),
    ])


def _budget_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  SURFACE),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  ACCENT),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.HexColor("#0f0f18"), colors.HexColor("#151520")]),
        ("BACKGROUND",  (0, -1), (-1, -1), SURFACE),
        ("TEXTCOLOR",   (0, 1), (-1, -1), TEXT_PRIMARY),
        ("TEXTCOLOR",   (1, -1), (1, -1), SUCCESS),
        ("FONTNAME",    (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#2a2a3a")),
        ("ALIGN",       (1, 0), (1, -1), "RIGHT"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ])


# ── On-page header / footer ────────────────────────────────────────────────

def _make_on_page(destination: str, styles: dict[str, ParagraphStyle]):
    """Returns a function compatible with SimpleDocTemplate.build(onFirstPage/onLaterPages)."""

    page_w, page_h = A4

    def _draw(canvas, doc):  # type: ignore[no-untyped-def]
        canvas.saveState()

        # Top accent bar
        canvas.setFillColor(ACCENT)
        canvas.rect(0, page_h - 8 * mm, page_w, 8 * mm, fill=1, stroke=0)

        # Logo text in bar
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(15 * mm, page_h - 5.5 * mm, "✈  VoiceTravel AI")

        # Footer
        canvas.setFillColor(DARK_BG)
        canvas.rect(0, 0, page_w, 10 * mm, fill=1, stroke=0)
        canvas.setFillColor(TEXT_MUTED)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawCentredString(
            page_w / 2,
            3 * mm,
            f"{destination}  ·  Generated by VoiceTravel AI  ·  Page {doc.page}",
        )

        canvas.restoreState()

    return _draw


# ── Main generator ─────────────────────────────────────────────────────────

def generate_itinerary_pdf(itinerary_data: dict[str, Any]) -> bytes:
    """
    Generate a branded travel itinerary PDF.

    Parameters
    ----------
    itinerary_data : dict
        Expected keys (all optional except ``destination``):
        - destination: str
        - traveler_name: str
        - start_date: str
        - end_date: str
        - days: list[dict]  (each: day_number, date, activities, meals, transportation)
        - budget_breakdown: dict  (flights, hotels, activities, food, transport, total, currency)
        - summary: str

    Returns
    -------
    bytes
        Raw PDF bytes.
    """
    styles = _build_styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    destination    = itinerary_data.get("destination", "Your Trip")
    traveler_name  = itinerary_data.get("traveler_name", "")
    start_date     = itinerary_data.get("start_date", "")
    end_date       = itinerary_data.get("end_date", "")
    days           = itinerary_data.get("days") or []
    budget         = itinerary_data.get("budget_breakdown") or {}
    summary        = itinerary_data.get("summary", "")

    on_page = _make_on_page(destination, styles)
    story   = []

    # ── Title page ────────────────────────────────────────────────────────

    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(destination, styles["title"]))

    date_line = " — ".join(filter(None, [start_date, end_date]))
    if date_line:
        story.append(Paragraph(date_line, styles["subtitle"]))
    if traveler_name:
        story.append(Paragraph(f"Prepared for: {traveler_name}", styles["subtitle"]))

    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}",
        styles["muted"],
    ))
    story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=6 * mm))

    # ── Summary ───────────────────────────────────────────────────────────

    if summary:
        story.append(Paragraph("Trip Summary", styles["section_header"]))
        story.append(Paragraph(summary, styles["body"]))

    # ── Day-by-day schedule ───────────────────────────────────────────────

    if days:
        story.append(Paragraph("Day-by-Day Itinerary", styles["section_header"]))

        for day in days:
            day_num  = day.get("day_number", "?")
            day_date = day.get("date", "")
            day_label = f"Day {day_num}" + (f"  —  {day_date}" if day_date else "")
            story.append(Paragraph(day_label, styles["day_header"]))

            activities = day.get("activities") or []
            if activities:
                table_data = [["Time", "Activity", "Location", "Duration", "Cost"]]
                for act in activities:
                    currency = budget.get("currency", "$")
                    cost_val = act.get("cost")
                    cost_str = f"{currency}{cost_val:.0f}" if cost_val is not None else "—"
                    dur      = act.get("duration_minutes")
                    dur_str  = f"{dur}m" if dur else "—"
                    table_data.append([
                        act.get("time", "—"),
                        act.get("name", "—"),
                        act.get("location", "—"),
                        dur_str,
                        cost_str,
                    ])

                col_widths = [22 * mm, 65 * mm, 50 * mm, 22 * mm, 18 * mm]
                tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
                tbl.setStyle(_activity_table_style())
                story.append(tbl)
            else:
                story.append(Paragraph("No activities scheduled for this day.", styles["muted"]))

            # Meals row
            meals = day.get("meals") or {}
            if any(meals.values()):
                meal_parts = []
                for meal_type in ("breakfast", "lunch", "dinner"):
                    val = meals.get(meal_type)
                    if val:
                        meal_parts.append(f"<b>{meal_type.capitalize()}:</b> {val}")
                if meal_parts:
                    story.append(Paragraph("  ".join(meal_parts), styles["muted"]))

            # Transport note
            transport = day.get("transportation")
            if transport:
                story.append(Paragraph(f"🚗 {transport}", styles["muted"]))

            story.append(Spacer(1, 3 * mm))

    # ── Budget breakdown ──────────────────────────────────────────────────

    if budget:
        story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=4 * mm))
        story.append(Paragraph("Budget Breakdown", styles["section_header"]))

        currency = budget.get("currency", "$")
        categories = [
            ("Flights",       budget.get("flights")),
            ("Hotels",        budget.get("hotels")),
            ("Activities",    budget.get("activities")),
            ("Food",          budget.get("food")),
            ("Local Transport", budget.get("transport")),
        ]
        rows = [["Category", "Estimated Cost"]]
        for label, amount in categories:
            if amount is not None:
                rows.append([label, f"{currency}{amount:,.0f}"])

        total = budget.get("total")
        if total is not None:
            rows.append(["TOTAL", f"{currency}{total:,.0f}"])
        elif len(rows) > 1:
            computed = sum(
                v for _, v in categories if v is not None
            )
            rows.append(["TOTAL", f"{currency}{computed:,.0f}"])

        budget_tbl = Table(rows, colWidths=[80 * mm, 50 * mm])
        budget_tbl.setStyle(_budget_table_style())
        story.append(budget_tbl)

    # ── Build PDF ──────────────────────────────────────────────────────────

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
