"""Email delivery service for itinerary sending.

Uses GmailMCPClient to send formatted HTML emails with optional PDF attachment.
Entry point: send_itinerary_email(to_email, itinerary, pdf_bytes) -> bool
"""

from __future__ import annotations

import base64
from typing import Any

from app.mcp_clients.gmail import GmailMCPClient
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _build_html(itinerary: dict[str, Any]) -> str:
    """Render the itinerary as a simple HTML email body."""
    destination  = itinerary.get("destination", "Your Trip")
    start_date   = itinerary.get("start_date", "")
    end_date     = itinerary.get("end_date", "")
    summary      = itinerary.get("summary", "")
    days: list   = itinerary.get("days") or []
    budget: dict = itinerary.get("budget_breakdown") or {}
    currency     = budget.get("currency", "$")

    date_range = " — ".join(filter(None, [start_date, end_date]))

    # ── CSS ──────────────────────────────────────────────────────────────
    css = """
    <style>
      body { font-family: Arial, sans-serif; background: #0a0a0f; color: #f0f0f8; margin: 0; padding: 0; }
      .wrapper { max-width: 620px; margin: 0 auto; padding: 24px 16px; }
      .header  { background: #6c63ff; border-radius: 12px 12px 0 0; padding: 28px 24px; text-align: center; }
      .header h1 { color: #fff; margin: 0; font-size: 24px; }
      .header p  { color: rgba(255,255,255,0.75); margin: 6px 0 0; font-size: 14px; }
      .body    { background: #111117; border: 1px solid rgba(255,255,255,0.08); padding: 24px; border-radius: 0 0 12px 12px; }
      .section-title { font-size: 13px; font-weight: 700; color: #6c63ff; text-transform: uppercase;
                       letter-spacing: 0.08em; margin: 20px 0 10px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 6px; }
      .day-card { background: #1a1a24; border-radius: 8px; padding: 14px 16px; margin-bottom: 10px; }
      .day-title { font-size: 13px; font-weight: 700; color: #fff; margin: 0 0 8px; }
      table  { width: 100%; border-collapse: collapse; font-size: 13px; }
      th     { background: #1a1a24; color: #6c63ff; text-align: left; padding: 6px 8px; }
      td     { padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.06); color: #a0a0b8; vertical-align: top; }
      .total-row td { font-weight: 700; color: #22c55e; border-top: 1px solid rgba(255,255,255,0.12); }
      .footer { text-align: center; color: #5c5c7a; font-size: 11px; margin-top: 24px; }
    </style>
    """

    # ── Day plans ─────────────────────────────────────────────────────────
    days_html = ""
    for day in days[:10]:  # cap at 10 days to keep email size reasonable
        day_num   = day.get("day_number", "?")
        day_date  = day.get("date", "")
        day_label = f"Day {day_num}" + (f" — {day_date}" if day_date else "")
        activities = day.get("activities") or []

        acts_html = ""
        for act in activities:
            acts_html += (
                f"<tr><td>{act.get('time','')}</td>"
                f"<td>{act.get('name','')}</td>"
                f"<td>{act.get('location','')}</td></tr>"
            )

        days_html += f"""
        <div class="day-card">
          <div class="day-title">{day_label}</div>
          {"<table><tr><th>Time</th><th>Activity</th><th>Location</th></tr>" + acts_html + "</table>" if activities else "<p style='color:#5c5c7a;font-size:12px;margin:0'>No activities planned.</p>"}
        </div>
        """

    # ── Budget ────────────────────────────────────────────────────────────
    budget_rows = ""
    cat_map = [
        ("Flights",         budget.get("flights")),
        ("Hotels",          budget.get("hotels")),
        ("Activities",      budget.get("activities")),
        ("Food",            budget.get("food")),
        ("Local Transport", budget.get("transport")),
    ]
    total_computed = 0.0
    for label, amount in cat_map:
        if amount is not None:
            total_computed += amount
            budget_rows += f"<tr><td>{label}</td><td style='text-align:right'>{currency}{amount:,.0f}</td></tr>"

    total = budget.get("total") or total_computed
    budget_section = ""
    if budget_rows:
        budget_section = f"""
        <div class="section-title">Budget Breakdown</div>
        <table>
          <tr><th>Category</th><th style="text-align:right">Est. Cost</th></tr>
          {budget_rows}
          <tr class="total-row"><td>TOTAL</td><td style="text-align:right">{currency}{total:,.0f}</td></tr>
        </table>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Your Itinerary — {destination}</title>{css}</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>✈ {destination}</h1>
    {"<p>" + date_range + "</p>" if date_range else ""}
  </div>
  <div class="body">
    {"<p style='color:#a0a0b8;line-height:1.6'>" + summary + "</p>" if summary else ""}
    {"<div class='section-title'>Day-by-Day Plan</div>" + days_html if days_html else ""}
    {budget_section}
  </div>
  <div class="footer">
    Generated by VoiceTravel AI &nbsp;·&nbsp; AI-powered travel planning
  </div>
</div>
</body>
</html>"""


async def send_itinerary_email(
    to_email: str,
    itinerary: dict[str, Any],
    pdf_bytes: bytes | None = None,
) -> bool:
    """
    Send the itinerary as a formatted HTML email via GmailMCPClient.

    Parameters
    ----------
    to_email    : Recipient email address.
    itinerary   : Itinerary dict (destination, days, budget_breakdown, …).
    pdf_bytes   : Optional PDF attachment bytes.

    Returns
    -------
    bool — True on success, False on error.
    """
    destination  = itinerary.get("destination", "Your Trip")
    traveler     = itinerary.get("traveler_name", "Traveller")
    subject      = f"Your {destination} Itinerary — VoiceTravel AI"

    html_body   = _build_html(itinerary)
    pdf_base64  = base64.b64encode(pdf_bytes).decode() if pdf_bytes else None

    client = GmailMCPClient()
    try:
        await client.send_itinerary_email(
            to=to_email,
            traveler_name=traveler,
            itinerary_html=html_body,
            trip_title=subject,
            pdf_base64=pdf_base64,
        )
        logger.info(
            "Itinerary email sent",
            extra={"event": {"to": to_email, "destination": destination}},
        )
        return True

    except Exception as exc:
        logger.error(
            "Failed to send itinerary email",
            extra={"event": {"to": to_email, "error": str(exc)}},
            exc_info=True,
        )
        return False
