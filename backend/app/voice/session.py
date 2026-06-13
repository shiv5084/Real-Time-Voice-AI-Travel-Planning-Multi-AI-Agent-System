"""Voice session management backed by Redis.

A voice session holds the multi-turn conversation between the user and the
planning assistant during the voice onboarding flow.  Sessions expire after
one hour.

Session schema (stored as JSON in Redis under ``voice_session:{id}``)::

    {
        "session_id": str,
        "mode": "realtime" | "transcription",
        "status": "collecting" | "ready",
        "messages": [
            {"role": "user" | "assistant", "content": str}
        ],
        "collected_texts": [str, ...],   # user turns joined for pipeline
        "turn": int                       # current turn index
    }
"""

from __future__ import annotations

import json
import uuid
from typing import Literal, Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

_SESSION_TTL = 3600  # 1 hour
_PREFIX = "voice_session:"

VoiceMode = Literal["realtime", "transcription"]
SessionStatus = Literal["collecting", "ready"]


class VoiceSessionManager:
    """CRUD operations for voice sessions in Redis."""

    async def _r(self):
        """Return the async Redis client."""
        from app.services.redis_client import get_redis
        return await get_redis()

    # ── Create ────────────────────────────────────────────────────────────

    async def create(self, mode: VoiceMode) -> dict:
        """Create a new voice session and persist it.

        Returns the full session dict including the freshly-generated
        ``session_id``.
        """
        session_id = str(uuid.uuid4())
        session = {
            "session_id": session_id,
            "mode": mode,
            "status": "collecting",
            "messages": [],
            "collected_texts": [],
            "turn": 0,
        }
        await self._save(session_id, session)
        logger.info(
            "Voice session created",
            extra={"event": {"session_id": session_id, "mode": mode}},
        )
        return session

    # ── Read ──────────────────────────────────────────────────────────────

    async def get(self, session_id: str) -> Optional[dict]:
        """Return the session dict or None if not found / expired."""
        try:
            client = await self._r()
            raw = await client.get(f"{_PREFIX}{session_id}")
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.error(
                "Failed to read voice session",
                extra={"event": {"session_id": session_id, "error": str(exc)}},
            )
            return None

    # ── Update ────────────────────────────────────────────────────────────

    async def append_message(
        self,
        session_id: str,
        role: Literal["user", "assistant"],
        content: str,
    ) -> Optional[dict]:
        """Append a message and return the updated session."""
        session = await self.get(session_id)
        if session is None:
            return None
        session["messages"].append({"role": role, "content": content})
        if role == "user":
            session["collected_texts"].append(content)
            session["turn"] += 1
        await self._save(session_id, session)
        return session

    async def mark_ready(self, session_id: str) -> Optional[dict]:
        """Mark the session as ready to proceed to the planner pipeline."""
        session = await self.get(session_id)
        if session is None:
            return None
        session["status"] = "ready"
        await self._save(session_id, session)
        logger.info(
            "Voice session marked ready",
            extra={"event": {"session_id": session_id}},
        )
        return session

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete(self, session_id: str) -> None:
        """Remove the session from Redis."""
        try:
            client = await self._r()
            await client.delete(f"{_PREFIX}{session_id}")
        except Exception as exc:
            logger.warning(
                "Failed to delete voice session",
                extra={"event": {"session_id": session_id, "error": str(exc)}},
            )

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _save(self, session_id: str, session: dict) -> None:
        """Persist session to Redis with TTL refresh."""
        client = await self._r()
        await client.set(
            f"{_PREFIX}{session_id}",
            json.dumps(session),
            ex=_SESSION_TTL,
        )

    def build_augmented_request(self, session: dict) -> str:
        """Concatenate all user turns into a single pipeline-ready request string."""
        texts = session.get("collected_texts") or []
        if not texts:
            # Fallback to user messages in the session message list
            texts = [
                msg["content"]
                for msg in session.get("messages", [])
                if msg.get("role") == "user"
            ]
        return "\n\n".join(texts)


# ── Singleton ─────────────────────────────────────────────────────────────

voice_session_manager = VoiceSessionManager()


# ── Follow-up detection helpers ───────────────────────────────────────────
# These mirror the same logic in planner/page.tsx so both ends agree.

# ── Number-word helpers ───────────────────────────────────────────────────

# Maps English spoken numbers to their digit equivalents (used in regex alts)
_WORD_DIGITS = (
    r"one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
    r"|twenty[- ]?one|twenty[- ]?two|twenty[- ]?five"
    r"|a couple of|a few|several|half a"
)


def text_has_calendar_date(text: str) -> bool:
    """Return True if ``text`` contains a specific calendar/relative date (NOT just a duration).

    This is stricter than the old text_has_dates — it requires an actual date reference
    (e.g. "June 10", "next week", "in July") not merely a trip duration like "5 days".
    """
    import re
    patterns = [
        # Exact calendar dates: "June 10", "10th June", "10/06/2026"
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}",
        r"\b\d{1,2}\s*(st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}[\/\-]\d{1,2}([\/\-]\d{2,4})?\b",
        # Relative time: "next month", "next week", "next summer"
        r"\bnext\s+(month|week|year|summer|winter|spring|fall|autumn)\b",
        r"\bthis\s+(month|week|summer|winter|spring|fall|autumn)\b",
        # Spoken relative offsets: "in 2 weeks", "in five days", "in a month"
        r"\bin\s+(\d+|a|one|two|three|four|five|six|seven|eight|nine|ten|a couple of|a few)\s+(days?|weeks?|months?)\b",
        # Spoken days: "today", "tomorrow", "day after tomorrow"
        r"\b(today|tomorrow|day\s+after\s+tomorrow)\b",
        # Month-only: "in June", "in December"
        r"\bin\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b",
        # Range expressions with date markers: "from June to July", "depart June 10"
        r"\b(from|between|depart|starting|arriving|arrive)\s+.{0,30}(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
        # Approximate month/season references
        r"\b(about|around|roughly|approximately)\s+a\s+(week|month|fortnight)\b",
        # "end of June", "early July"
        r"\b(early|mid|late|end\s+of)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def text_has_duration(text: str) -> bool:
    """Return True if ``text`` contains a trip duration (e.g. '5 days', 'two weeks') but NOT a calendar date."""
    import re
    patterns = [
        # Numeric durations: "5 days", "2 weeks", "10 nights"
        r"\b\d+[\s-]+(days?|nights?|weeks?|months?)\b",
        # Spoken/word durations: "five days", "two weeks", "a week"
        rf"\b({_WORD_DIGITS})\s+(days?|nights?|weeks?|months?)\b",
        # Indefinite article durations: "a week", "a day", "a night"
        r"\ba\s+(days?|nights?|weeks?|months?)\b",
        # Trip-type keywords that imply duration
        r"\b(weekend|day\s*trip|short\s*trip|quick\s*trip|brief\s*trip|long\s*weekend|overnight)\b",
        # Approximate numeric: "about a week", "around 5 days"
        r"\b(about|around|roughly|approximately)\s+\d+\s+(days?|nights?|weeks?)\b",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def text_has_dates(text: str) -> bool:
    """Return True if ``text`` contains travel date information (including durations).

    Kept for backwards compatibility — now returns True if either a calendar date
    OR a duration is found. But prefer text_has_calendar_date for stricter checks.
    """
    return text_has_calendar_date(text) or text_has_duration(text)


def text_has_budget(text: str) -> bool:
    """Return True if ``text`` contains a budget amount (including spoken word amounts)."""
    import re
    patterns = [
        # Currency symbol + digits: "$3000", "€2500"
        r"[$€£₹¥₩₽฿₫₺₱₦₡₲₵₿]\s*[\d,]+",
        r"\bRs\.?\s*[\d,]+",
        # Digits + currency word: "3000 dollars", "2500 USD"
        r"[\d,]+\s*(k|K)?\s+(dollars?|euros?|pounds?|rupees?|yen|yuan|won|baht|pesos?"
        r"|francs?|kroner|krone|rubles?|ringgit|lira|rand|dirhams?|riyals?|dinars?"
        r"|bucks?|usd|eur|gbp|inr|jpy|cny|aud|cad|chf|sgd|hkd|thb|vnd|php|myr"
        r"|nzd|zar|brl|mxn|aed|sar|kwd|nok|sek|pkr|lkr|bdt|idr|twd)\b",
        # Currency code + digits: "USD 3000"
        r"\b(USD|EUR|GBP|INR|JPY|CNY|AUD|CAD|CHF|SGD|HKD|THB|KRW|NZD|ZAR|BRL|MXN"
        r"|AED|SAR|PKR|LKR|BDT|IDR|TWD)\s+[\d,]+",
        # "budget: 3000" or "budget 3000"
        r"\bbudget\s*[:=]?\s*[\d,]+",
        # --- NEW: number BEFORE the word budget (very common in voice) ---
        # "3000 budget", "2.5k budget", "3000 dollar budget"
        r"[\d,]+\s*(k|K|m|M)?\s*budget\b",
        # --- NEW: spoken word amounts (voice STT) ---
        # "three thousand dollars", "five hundred euros"
        rf"\b({_WORD_DIGITS})\s+(hundred|thousand|million)\s*(dollars?|euros?|pounds?|rupees?|bucks?|usd|eur|gbp|inr)?\b",
        # "a thousand dollars", "two thousand budget"
        r"\b(a|one|two|three|four|five|six|seven|eight|nine|ten)\s+thousand\b",
        r"\b(a|one|two|three|four|five)\s+hundred\b",
        # Per-person budget clue: "1500 per person", "500 each"
        r"[\d,]+\s+(per\s+person|per\s+head|pp|each)\b",
        # Cheap/affordable / implicit budget preferences (e.g. backpacking, luxury, budget-friendly)
        r"\b(cheap|affordable|low[- ]?cost|economy|shoestring|backpacker|backpacking|budget[- ]friendly|luxury)\s+(trip|travel|vacation|budget)?\b",
        r"\bon\s+a\s+(tight|limited|small|low|shoestring)\s+budget\b",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def detect_missing_info(collected_texts: list[str]) -> dict:
    """Return which required pieces of info are still missing.

    Returns:
        has_calendar_date: True if user provided an actual date (June 10, next week, etc.)
        has_duration:      True if user provided a trip length (5 days, 2 weeks, etc.)
        has_budget:        True if user provided a budget amount
    """
    has_calendar = any(text_has_calendar_date(t) for t in collected_texts)
    has_dur = any(text_has_duration(t) for t in collected_texts)
    has_budget = any(text_has_budget(t) for t in collected_texts)
    return {
        "has_dates": has_calendar,        # strict: only actual calendar dates
        "has_duration": has_dur,
        "has_budget": has_budget,
    }


def text_has_destination(text: str) -> bool:
    """Check if the text contains a destination or travel topic, by removing dates, budgets, and common stop words."""
    import re
    # Lowercase and clean
    text = text.lower().strip()
    
    # 1. Remove punctuation only chars
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # 2. Remove budget mentions
    text = re.sub(r'\b\d+(k|m)?\b', ' ', text) # numbers
    text = re.sub(r'\b(usd|eur|gbp|inr|dollars?|euros?|pounds?|rupees?|budget|budgeted)\b', ' ', text)
    
    # 3. Remove date/duration mentions
    months = r"january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
    text = re.sub(rf'\b({months})\b', ' ', text)
    date_words = r"days?|nights?|weeks?|months?|years?|weekend|today|tomorrow|next|last|this|early|mid|late|end|from|to|between|starting|depart(ing|s)?|arriv(e|ing|s)?"
    text = re.sub(rf'\b({date_words})\b', ' ', text)
    
    # 4. Remove common stop words and travel filler words
    stop_words = {
        "i", "want", "to", "go", "travel", "trip", "fly", "visit", "a", "the", "an", "on", "in", "at", 
        "for", "with", "my", "our", "we", "would", "like", "love", "planning", "planner", "some", 
        "any", "please", "me", "us", "and", "but", "or", "about", "dream", "vacation", "you", "your",
        "tell", "show", "get", "need", "have", "plan", "here", "there", "is", "are", "was", "were", "am"
    }
    
    words = text.split()
    remaining = [w for w in words if w not in stop_words and len(w) > 1]
    
    return len(remaining) > 0


def next_follow_up_question(collected_texts: list[str]) -> Optional[str]:
    """Return the next question to ask, or None if all info is collected.

    Priority order:
    0. If no destination or meaningful travel topic -> ask for destination
    1. If no calendar date AND no duration → ask for full date range
    2. If duration given but no start date   → ask for start date only
    3. If no budget                          → ask for budget
    4. All collected                         → return None (ready to plan)
    """
    # Check for destination/travel request first
    has_destination = any(text_has_destination(t) for t in collected_texts)
    if not has_destination:
        return (
            "Where would you like to go for your dream trip? "
            "(e.g. Paris, Tokyo, or New York)"
        )

    info = detect_missing_info(collected_texts)

    has_calendar = info["has_dates"]
    has_dur = info["has_duration"]
    has_budget = info["has_budget"]

    if not has_calendar and not has_dur:
        # No date information at all — ask for full date range
        return (
            "When would you like to travel? "
            "Please provide your start and end dates "
            "(e.g. June 10\u201315, 2026)."
        )

    if not has_calendar and has_dur:
        # User gave duration ("5 days") but no actual start date — ask for it
        return (
            "When would you like to travel? "
            "Please provide your start date (e.g. June 10, 2026)."
        )

    if not has_budget:
        return (
            "What is your total budget for this trip? "
            "(e.g. $3000, or $2500 for 2 people)"
        )

    return None  # All info collected — ready to plan
