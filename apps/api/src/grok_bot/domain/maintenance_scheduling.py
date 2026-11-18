import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ALIASES = {"eastern": "America/New_York", "central": "America/Chicago", "mountain": "America/Denver", "pacific": "America/Los_Angeles"}
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DATE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|today|tomorrow|(?:next\s+|this\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b", re.I)
ZONE = re.compile(r"\b(?:[A-Za-z_]+(?:/[A-Za-z_+-]+)+|UTC|Eastern|Central|Mountain|Pacific)\b", re.I)
CLOCK = r"(?:noon|midnight|\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)?)"
RANGE = re.compile(r"(?<![\w:-])(?P<start>" + CLOCK + r")\s*(?:[-–—]|to\b|and\b)\s*(?P<end>" + CLOCK + r")(?![\w:-])", re.I)
INTENT = re.compile(r"\b(?:i\s+(?:can|could|will)\s+(?:come|visit|stop by|head|be there)|i['’]ll\s+(?:come|visit|stop by|head|be there)|i(?:['’]m| am)\s+(?:free|available)|(?:i am |i['’]m )?available|how about|(?:can|could)\s+i\s+(?:come|visit|stop by))\b", re.I)
NEGATIVE = re.compile(r"\b(?:not|no|cannot|can't|can’t|won't|won’t|unavailable|cancel\w*|instead|if|unless|maybe|might|possibly|depending|would you|can you|could you)\b", re.I)


def _focused(message):
    remaining = RANGE.sub(" ", DATE.sub(" ", ZONE.sub(" ", message)))
    remaining = re.sub(r"\b(?:on|at|from|between|in|time|the|works|work|perfectly|for|me|yes|okay|ok|please|thanks|thank|you|it['’]s|is|to|visit)\b", " ", remaining, flags=re.I)
    return not re.search(r"[\w]", remaining)


def _clock(value):
    value = re.sub(r"[.\s]", "", value.lower())
    if value in {"noon", "midnight"}:
        return (12 if value == "noon" else 0), 0, "named"
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm)?", value)
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    period = match[3]
    if minute > 59 or (period and not 1 <= hour <= 12) or (not period and hour > 23):
        return None
    if period:
        hour = hour % 12 + (12 if period == "pm" else 0)
    return hour, minute, period or ("24" if re.fullmatch(r"\d{2}:\d{2}", value) or hour == 0 or hour > 12 else None)


def _local(visit_date, clock, zone):
    naive = datetime.combine(visit_date, time(clock[0], clock[1]))
    first, second = naive.replace(tzinfo=zone, fold=0), naive.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset() or first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != naive:
        return None
    return first


def parse_chat_visit(message, now, previous_offer=None):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("The scheduling clock must be timezone-aware")
    if not isinstance(message, str) or not message.strip() or len(message) > 5000:
        return {"offer": None, "question": None}
    message = message.strip()
    period = re.fullmatch(r"([ap])\.?m\.?[.!]?", message, re.IGNORECASE)
    if period and isinstance(previous_offer, dict) and isinstance(previous_offer.get("text"), str):
        previous_range = RANGE.search(DATE.sub(" ", previous_offer["text"]))
        if previous_range and _clock(previous_range["end"]) and _clock(previous_range["end"])[2] is None:
            message = previous_range.group(0) + period[1].lower() + "m"
    if NEGATIVE.search(message) or re.search(r"\b(?:started|began|since|happened)\b", message, re.I):
        return {"offer": None, "question": None}
    focused = _focused(message)
    if not INTENT.search(message) and not focused:
        return {"offer": None, "question": None}
    if not INTENT.search(message) and not (DATE.search(message) or RANGE.search(message) or ZONE.search(message)):
        return {"offer": None, "question": None}
    context = ""
    if focused and isinstance(previous_offer, dict):
        previous_text = previous_offer.get("text", "")
        if isinstance(previous_text, str) and previous_text.strip() and len(previous_text) <= 1000 and not NEGATIVE.search(previous_text):
            context = previous_text
        elif isinstance(previous_offer.get("timezone"), str):
            context = previous_offer["timezone"][:100]
            try:
                previous_start = datetime.fromisoformat(previous_offer["starts_at"])
                previous_end = datetime.fromisoformat(previous_offer["ends_at"])
                if previous_start.tzinfo and previous_end.tzinfo:
                    context += f" {previous_start.date().isoformat()} {previous_start:%H:%M}-{previous_end:%H:%M}"
            except (KeyError, TypeError, ValueError):
                pass
    draft_dates = DATE.findall(message) or DATE.findall(context)
    draft_ranges = list(RANGE.finditer(DATE.sub(" ", message))) or list(RANGE.finditer(DATE.sub(" ", context)))
    draft_zones = ZONE.findall(message) or ZONE.findall(context)
    draft_text = " ".join([*draft_dates, *[item.group(0) for item in draft_ranges], *draft_zones])[:1000] or message[:1000]
    ranges = list(RANGE.finditer(DATE.sub(" ", message))) or list(RANGE.finditer(DATE.sub(" ", context)))
    if len(ranges) != 1:
        return {"draft_text": draft_text, "offer": None, "question": "What start and end time work for the visit, including AM or PM?"}
    zones = ZONE.findall(message) or ZONE.findall(context)
    if len(set(zone.lower() for zone in zones)) != 1:
        return {"draft_text": draft_text, "offer": None, "question": "Which timezone should I use for the visit?"}
    zone_name = ALIASES.get(zones[0].lower(), "UTC" if zones[0].upper() == "UTC" else zones[0])
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        return {"draft_text": draft_text, "offer": None, "question": "Which IANA timezone or US timezone name should I use for the visit?"}
    dates = DATE.findall(message) or DATE.findall(context)
    if len(dates) != 1:
        return {"draft_text": draft_text, "offer": None, "question": "What date would you like to visit?"}
    if not DATE.search(message) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dates[0]):
        return {"draft_text": DATE.sub(" ", draft_text).strip(), "offer": None, "question": "Please give the calendar date for the visit, such as 2026-11-20."}
    date_text = dates[0].lower()
    local_now = now.astimezone(zone)
    if date_text in {"today", "tomorrow"}:
        visit_date = local_now.date() + timedelta(days=date_text == "tomorrow")
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_text):
        try:
            visit_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            return {"draft_text": draft_text, "offer": None, "question": "What valid calendar date should I use for the visit?"}
    else:
        weekday = WEEKDAYS.index(date_text.split()[-1])
        offset = (weekday - local_now.weekday()) % 7
        if date_text.startswith("next "):
            return {"draft_text": draft_text, "offer": None, "question": "What calendar date do you mean by next " + WEEKDAYS[weekday].capitalize() + "?"}
        visit_date = local_now.date() + timedelta(days=offset)
    start, end = _clock(ranges[0]["start"]), _clock(ranges[0]["end"])
    if start is None or end is None:
        return {"draft_text": draft_text, "offer": None, "question": "What valid start and end time should I use for the visit?"}
    if start[2] is None and end[2] in {"am", "pm"}:
        start = (start[0] % 12 + (12 if end[2] == "pm" else 0), start[1], end[2])
    if start[2] is None or end[2] is None:
        return {"draft_text": draft_text, "offer": None, "question": "Are the visit times AM or PM? You can also use a 24-hour time range."}
    starts_at = _local(visit_date, start, zone)
    end_date = visit_date + timedelta(days=1) if ranges[0]["end"].lower() == "midnight" else visit_date
    ends_at = _local(end_date, end, zone)
    if starts_at is None or ends_at is None:
        return {"draft_text": draft_text, "offer": None, "question": "That time is ambiguous or unavailable because of daylight saving time. What other visit time works?"}
    duration = ends_at.astimezone(timezone.utc) - starts_at.astimezone(timezone.utc)
    if duration <= timedelta(0) or duration > timedelta(hours=24):
        return {"draft_text": draft_text, "offer": None, "question": "What start and end time should I use for a visit lasting no more than 24 hours?"}
    if starts_at.astimezone(timezone.utc) <= now.astimezone(timezone.utc):
        return {"draft_text": draft_text, "offer": None, "question": "That visit time has already passed. What future date and time work?"}
    return {"offer": {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(), "timezone": zone_name, "displaytext": f"{visit_date.isoformat()} {starts_at:%H:%M}–{ends_at:%H:%M} {zone_name}", "status": "REQUESTED"}, "question": None}
