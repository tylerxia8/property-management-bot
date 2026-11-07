"""Literal matches and typo-tolerant clarification, never fuzzy assignment."""

import re
import unicodedata

from rapidfuzz import fuzz, process, utils

CLARIFICATION = "Which listing should this inquiry use? No unit was selected."
MAX_CANDIDATES = 1000


def normalize(value: str) -> str:
    return utils.default_process(unicodedata.normalize("NFKC", value).casefold())


def resolve_hint(hint: str, rows) -> dict:
    unresolved = {"match": None, "ambiguous": True, "clarification": CLARIFICATION}
    if len(hint) > 512:
        return unresolved
    query = normalize(hint).strip()
    if not query or len(rows) > MAX_CANDIDATES:
        return unresolved
    numbers = set(re.findall(r"\b\d+\b", query))
    candidates = [row for row in rows if numbers <= set(re.findall(r"\b\d+\b", normalize(row["display_label"])))]
    exact = [row for row in candidates if query in normalize(row["display_label"])]
    if len(exact) == 1:
        return {"match": exact[0], "ambiguous": False, "clarification": ""}
    if len(query) < 4:
        return unresolved
    choices = {index: normalize(row["display_label"]) for index, row in enumerate(candidates)}
    ranked = process.extract(query, choices, scorer=fuzz.WRatio, score_cutoff=75, limit=3)
    labels = list(dict.fromkeys(candidates[index]["display_label"] for _, _, index in ranked))
    if labels:
        unresolved["clarification"] += " Possible listings (please confirm): " + "; ".join(labels) + "."
    return unresolved
