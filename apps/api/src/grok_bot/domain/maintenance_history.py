import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from grok_bot.domain.maintenance_guidance import FAMILIES, explicit_resolution, matching_families


SENSITIVE = re.compile(r"\b(?:password|passcode|access code|door code|entry code|wifi|wi-fi|network name|ssid|phone|email|medical|diagnos\w*|medication|hospital|allerg\w*|asthma|pregnan\w*|cancer)\b|https?://|\S+@\S+|(?:\+?\d[\s().-]*){7,}|\b\d+\s+\w+(?:\s+\w+){0,3}\s+(?:street|st|road|rd|avenue|ave|drive|dr|lane|ln|way|court|ct)\b", re.I)
UNRELATED = re.compile(r"\b(?:my|our) (?:own )?(?:home|house|apartment|place)\b|\b(?:back home|used to|last year|previous stay)\b", re.I)
DEFECT = re.compile(r"\b(?:broken|broke|leak\w*|clog\w*|block\w*|stuck|overflow\w*|malfunction\w*|missing|damaged|cracked|drip\w*|flicker\w*|sparks?|tripped|won't|will not|doesn't|does not|isn't|is not|cannot|can't|not working|not heating|not cooling|no hot water|no heat|no power|no water|too cold|too hot|locked out)\b", re.I)
UNCERTAIN = re.compile(r"\b(?:not|no|never|isn't|aren't|don't|dont|hasn't|won't|think|apparently|supposed|according|still|again|returned|recurr\w*|previously|thought|says|said|claims|if|hope|maybe|might|should|would|will|tomorrow|scheduled)\b", re.I)
DANGEROUS = re.compile(r"\b(?:chemical\w*|bleach|ammonia|drano|gas|panel\w*|breaker\w*|wiring|wire\w*|ladder\w*|dismantl\w*|disassembl\w*|socket|unscrew|pilot light|reset.*furnace)\b", re.I)
RESPONSES = {
    "handoff": "Host arranged or requested professional assistance; completion was not established by this action.",
    "observation": "Host requested a photo, visible label, or description of the issue.",
    "replacement": "Host discussed a replacement or delivery; working operation was not established by this action.",
    "controls": "Host discussed normal operating controls; any property-specific instructions require independent verification.",
    "unsafe_omitted": "Historical instructions were omitted for safety; qualified human assessment is required.",
    "unknown": "No safe issue-linked host response was identified in the bounded follow-up window.",
}
SYMPTOMS = {
    "water": "Water leakage, drainage, or overflow was reported.",
    "operation": "Failure of normal operation was reported.",
    "damage": "Damage, a missing item, or a stuck component was reported.",
    "pest": "Pest activity was reported.",
    "odor": "An unwanted odor was reported.",
    "mold": "Mold or dampness was reported.",
}
OUTCOMES = {
    "guest_confirmed": "A later guest message explicitly confirmed normal operation or repair of this same issue.",
    "host_reported": "A later host message explicitly reported repair of this same issue; guest confirmation was not found.",
    "unknown": "No explicit issue-specific repair confirmation was found in the bounded follow-up window.",
}


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Invalid maintenance history timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid maintenance history timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError("Maintenance history timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


def _identifier(value):
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Invalid maintenance history identifier")
    return value


def _read_json(path, maximum_bytes):
    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum_bytes + 1)
        if len(raw) > maximum_bytes:
            raise ValueError("Maintenance history file exceeds size limit")
        return json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Cannot read maintenance history data") from None


def import_history(source, output, organization_id):
    organization_id = str(UUID(str(organization_id)))
    source = Path(source)
    output = Path(output)
    if output.resolve() == source.resolve() or source.resolve() in output.resolve().parents:
        raise ValueError("Maintenance history output must be outside the source archive")
    if not source.is_dir():
        raise ValueError("Maintenance history source must be a directory")
    paths = []
    for path in source.glob("*.json"):
        paths.append(path)
        if len(paths) > 50000:
            raise ValueError("Maintenance history source exceeds file limit")
    counts = Counter(files=len(paths), messages=0, sensitive_messages_summarized=0, candidate_cases=0)
    cases = defaultdict(list)
    unique_messages = set()
    unique_cases = set()
    for path in sorted(paths):
        data = _read_json(path, 8 * 1024 * 1024)
        if not isinstance(data, dict) or not isinstance(data.get("record"), dict) or not isinstance(data.get("messages"), list):
            raise ValueError("Invalid maintenance history conversation")
        record = data["record"]
        messages = data["messages"]
        if len(messages) > 10000:
            raise ValueError("Maintenance history conversation exceeds message limit")
        conversation_id = _identifier(record.get("conversation_id") or record.get("id"))
        properties = record.get("properties", [])
        if properties is None:
            properties = []
        if not isinstance(properties, list) or any(not isinstance(item, dict) for item in properties):
            raise ValueError("Invalid maintenance history properties")
        property_id = _identifier(properties[0]["id"]) if properties and properties[0].get("id") else None
        ordered = []
        for message in messages:
            if not isinstance(message, dict):
                raise ValueError("Invalid maintenance history message")
            body = message.get("body")
            if body is not None and not isinstance(body, str):
                raise ValueError("Invalid maintenance history message body")
            if body and len(body) > 100000:
                raise ValueError("Maintenance history message exceeds size limit")
            timestamp = _timestamp(message.get("created_at"))
            stable_id = _identifier(message.get("id"))
            counts["messages"] += 1
            if counts["messages"] > 2000000:
                raise ValueError("Maintenance history source exceeds message limit")
            unique_messages.add(stable_id)
            if not isinstance(message.get("sender_type"), str):
                raise ValueError("Invalid maintenance history sender")
            if not body or message["sender_type"] not in {"guest", "host"}:
                continue
            if SENSITIVE.search(body):
                counts["sensitive_messages_summarized"] += 1
            ordered.append((timestamp, stable_id, message["sender_type"], body))
        ordered.sort(key=lambda item: (item[0], item[1]))
        seen = set()
        for index, (created_at, message_id, sender, body) in enumerate(ordered):
            if sender != "guest" or UNRELATED.search(body):
                continue
            for clause in re.split(r"[.!?;\n]+|\bbut\b", body, flags=re.I):
                for key in matching_families(clause):
                    if key in seen or (message_id, key) in unique_cases or (not DEFECT.search(clause) and key not in {"pest", "odor", "mold"}):
                        continue
                    if key in {"pest", "mold"} and not re.search(r"\b(?:found|saw|seeing|noticed|there (?:is|are)|(?:we|i) (?:have|see))\b", clause, re.I):
                        continue
                    if key == "odor" and not re.search(r"\b(?:bad|awful|terrible|strong|smoky|smoke|sewage|sewer|musty|unpleasant|foul|stink\w*)\b", clause, re.I):
                        continue
                    if explicit_resolution(clause):
                        continue
                    if re.search(r"\b(?:dishes|plates|glasses|cups)\b", clause, re.I) and not re.search(r"\b(?:leak\w*|won't|doesn't|not working|not draining|error)\b", clause, re.I):
                        continue
                    seen.add(key)
                    unique_cases.add((message_id, key))
                    symptom = key if key in {"pest", "odor", "mold"} else "operation"
                    if re.search(r"\b(?:leak\w*|drip\w*|clog\w*|overflow\w*|drain\w*)\b", clause, re.I):
                        symptom = "water"
                    elif re.search(r"\b(?:broken|damaged|missing|stuck|cracked)\b", clause, re.I):
                        symptom = "damage"
                    responses = set()
                    outcome = "unknown"
                    context_keys = set(matching_families(body))
                    for offset, (later_at, _, later_sender, later_body) in enumerate(ordered[index + 1:index + 31], 1):
                        if later_at - created_at > timedelta(days=7):
                            break
                        if UNRELATED.search(later_body):
                            continue
                        for later_clause in re.split(r"[.!?;\n]+|\bbut\b", later_body, flags=re.I):
                            later_keys = matching_families(later_clause)
                            if later_keys:
                                context_keys = set(later_keys)
                            elif offset <= 5 and context_keys == {key} and later_at - created_at <= timedelta(hours=24) and (explicit_resolution(later_clause) or re.search(r"\b(?:send someone|repairman|technician|plumber|maintenance|photo|picture)\b", later_clause, re.I)):
                                later_keys = [key]
                            if key not in later_keys:
                                continue
                            if len(later_keys) == 1 and explicit_resolution(later_clause) and "?" not in later_body and (len(matching_families(later_body)) > 1 or not UNCERTAIN.search(later_body)):
                                if later_sender == "guest":
                                    outcome = "guest_confirmed"
                                elif outcome == "unknown":
                                    outcome = "host_reported"
                            elif DEFECT.search(later_clause):
                                outcome = "unknown"
                            if later_sender != "host":
                                continue
                            if DANGEROUS.search(later_clause):
                                responses.add("unsafe_omitted")
                                continue
                            if re.search(r"\b(?:technician|plumber|repairman|maintenance|contractor|electrician|send someone)\b", later_clause, re.I):
                                responses.add("handoff")
                            if re.search(r"\b(?:photo|picture|label|model|describe)\b", later_clause, re.I):
                                responses.add("observation")
                            if re.search(r"\b(?:replacement|replace|ordered|delivered|delivery)\b", later_clause, re.I):
                                responses.add("replacement")
                            if re.search(r"\b(?:normal|setting|display|remote|thermostat|control)\b", later_clause, re.I):
                                responses.add("controls")
                    counts["candidate_cases"] += 1
                    if counts["candidate_cases"] > 200000:
                        raise ValueError("Maintenance history source exceeds candidate limit")
                    cases[key].append({"key": key, "title": FAMILIES[key][1], "symptom": SYMPTOMS[symptom], "response": " ".join(RESPONSES[item] for item in sorted(responses or {"unknown"})), "outcome": outcome, "outcome_evidence": OUTCOMES[outcome], "source_message_id": message_id, "conversation_id": conversation_id, "property_name": "Historical property", "property_id": property_id, "created_at": created_at.isoformat()})
    selected = []
    for rows in cases.values():
        rows.sort(key=lambda row: (row["outcome"] == "guest_confirmed", row["created_at"]), reverse=True)
    while len(selected) < 10000 and any(cases.values()):
        for key in sorted(cases):
            if cases[key] and len(selected) < 10000:
                selected.append(cases[key].pop(0))
    counts["cases"] = len(selected)
    counts["unique_message_count"] = len(unique_messages)
    payload = {"version": 1, "organization_id": organization_id, "source_counts": dict(counts), "cases": selected}
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".maintenance-history-", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(payload, stream, ensure_ascii=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return dict(counts)


@lru_cache(maxsize=4)
def _load_index(path, modified_ns, size, inode):
    data = _read_json(Path(path), 24 * 1024 * 1024)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("cases"), list) or len(data["cases"]) > 10000:
        raise ValueError("Invalid maintenance history index")
    try:
        UUID(data["organization_id"])
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Invalid maintenance history organization") from None
    for row in data["cases"]:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str) or row["key"] not in FAMILIES or not isinstance(row.get("outcome"), str) or row["outcome"] not in OUTCOMES:
            raise ValueError("Invalid maintenance history case")
        if row.get("title") != FAMILIES[row["key"]][1] or row.get("symptom") not in SYMPTOMS.values() or row.get("outcome_evidence") != OUTCOMES[row["outcome"]]:
            raise ValueError("Invalid maintenance history summary")
        response = row.get("response")
        if not isinstance(response, str) or not response or len(response) > 1000:
            raise ValueError("Invalid maintenance history response")
        remainder = response
        for allowed in RESPONSES.values():
            remainder = remainder.replace(allowed, "")
        if remainder.strip():
            raise ValueError("Invalid maintenance history response")
        _identifier(row.get("source_message_id"))
        _identifier(row.get("conversation_id"))
        _timestamp(row.get("created_at"))
    return data


def retrieve_history(path, organization_id, problem_keys, limit=3):
    if not path:
        return []
    try:
        organization_id = str(UUID(str(organization_id)))
        location = Path(path).resolve()
        stat = location.stat()
    except (ValueError, OSError):
        raise ValueError("Maintenance history configuration is invalid") from None
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
        raise ValueError("Invalid maintenance history retrieval limit")
    if not isinstance(problem_keys, (list, tuple, set)) or any(not isinstance(key, str) or key not in FAMILIES for key in problem_keys):
        raise ValueError("Invalid maintenance history problem keys")
    data = _load_index(str(location), stat.st_mtime_ns, stat.st_size, stat.st_ino)
    if data["organization_id"] != organization_id:
        raise ValueError("Maintenance history organization does not match")
    matches = [row for row in data["cases"] if row["key"] in problem_keys]
    matches.sort(key=lambda row: (row["outcome"] == "guest_confirmed", row["created_at"]), reverse=True)
    selected = []
    groups = {key: [row for row in matches if row["key"] == key] for key in sorted(problem_keys)}
    while len(selected) < limit and any(groups.values()):
        for rows in groups.values():
            if rows and len(selected) < limit:
                selected.append(rows.pop(0))
    return [{**{key: row[key] for key in ("key", "title", "symptom", "response", "outcome", "outcome_evidence", "source_message_id", "conversation_id", "created_at")}, "property_name": "Historical property", "historical_case": True, "property_specific_unverified": True} for row in selected]
