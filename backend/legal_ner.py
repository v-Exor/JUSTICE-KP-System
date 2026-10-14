import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from keyword_detector import detect_sensitive_keywords


CATEGORY_HINTS = {
    "debt": ["utang", "hulugan", "bayad", "loan", "debt", "pesos", "php"],
    "boundary": ["boundary", "hangganan", "bakod", "lupa", "property line"],
    "family_dispute": ["asawa", "anak", "pamilya", "family", "spouse"],
    "physical_injury": ["sinaktan", "pananakit", "injured", "hurt", "sugatan"],
    "nuisance": ["ingay", "basura", "nuisance", "istorbo"],
    "threat": ["banta", "binantaan", "threat", "threatened"],
    "property_damage": ["sinira", "damage", "property damage", "basag", "nasira"],
    "online_defamation": ["cyber libel", "online libel", "facebook post", "social media", "online defamation"],
    "neighbor_altercation": ["kapitbahay", "neighbor", "alitan", "away kapitbahay", "altercation"],
    "harassment_unjust_vexation": ["harassment", "pang-aabala", "ginugulo", "unjust vexation", "vexation"],
    "business_defamation": ["business slander", "oral defamation", "sinisiraan ang negosyo", "business defamation"],
}

THREAT_TERMS = ["banta", "binantaan", "threat", "threatened", "tatakutin"]
SETTLEMENT_TERMS = ["hulugan", "installment", "bayaran", "settlement", "kasunduan", "areglo"]
BARANGAY_ROLE_PREFIXES = {
    "captain",
    "chairman",
    "chairperson",
    "kagawad",
    "mediator",
    "official",
    "secretary",
    "tanod",
    "treasurer",
}
MANILA_TIMEZONE = ZoneInfo("Asia/Manila")


def _unique_in_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique


def _clean_barangay_name(value: str) -> str:
    cleaned = value.strip(" \t\r\n,.;:")
    for marker in [" kagabi", " kanina", " kahapon", " ngayon", " noong", " nung"]:
        index = cleaned.lower().find(marker)
        if index >= 0:
            cleaned = cleaned[:index]
    words = cleaned.split()
    if len(words) > 4:
        cleaned = " ".join(words[:4])
    return cleaned.strip(" \t\r\n,.;:")


def _is_barangay_role(value: str) -> bool:
    first_word = re.split(r"[\s/]+", value.strip(), maxsplit=1)[0].lower()
    return first_word in BARANGAY_ROLE_PREFIXES


def apply_authoritative_case_entities(
    entities: dict[str, Any],
    barangay_name: str,
    created_at: date | datetime,
) -> dict[str, Any]:
    """Replace transcript guesses with authoritative saved case facts."""
    authoritative = dict(entities)
    normalized_barangay = barangay_name.strip()
    authoritative["barangay_names"] = [normalized_barangay] if normalized_barangay else []

    if isinstance(created_at, datetime):
        timestamp = created_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        case_date = timestamp.astimezone(MANILA_TIMEZONE).date()
    else:
        case_date = created_at
    authoritative["dates"] = [case_date.isoformat()]
    return authoritative


def extract_legal_entities(transcript_text: str) -> dict[str, Any]:
    text = transcript_text.strip()
    lower_text = text.lower()

    debt_amounts = [
        float(match.replace(",", ""))
        for match in re.findall(
            r"(?:php|p)\s*([0-9][0-9,]*(?:\.[0-9]+)?)|([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:pesos?|php)",
            lower_text,
        )
        for match in match
        if match
    ]

    barangay_names = _unique_in_order(
        cleaned
        for match in re.findall(
            r"\b(?:barangay|brgy\.?)\s+([a-z0-9][a-z0-9 .'-]{1,40})",
            text,
            flags=re.IGNORECASE,
        )
        if (cleaned := _clean_barangay_name(match)) and not _is_barangay_role(cleaned)
    )

    date_patterns = [
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    ]
    dates = _unique_in_order(
        match
        for pattern in date_patterns
        for match in re.findall(pattern, lower_text, flags=re.IGNORECASE)
    )

    category_hints = [
        category
        for category, hints in CATEGORY_HINTS.items()
        if any(re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", lower_text) for hint in hints)
    ]

    keyword_result = detect_sensitive_keywords(text)
    violence_keywords = keyword_result["detected_keywords"]
    threat_keywords = [
        term for term in THREAT_TERMS if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lower_text)
    ]

    speaker_roles = _unique_in_order(
        re.findall(r"^\s*([^:\n]{2,40})\s*:", text, flags=re.MULTILINE)
    )

    settlement_terms = [
        term for term in SETTLEMENT_TERMS if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lower_text)
    ]

    return {
        "debt_amounts_php": debt_amounts,
        "debt_amount_php": debt_amounts[0] if debt_amounts else None,
        "barangay_names": barangay_names,
        "case_category_hints": category_hints,
        "violence_keywords": violence_keywords,
        "threat_keywords": threat_keywords,
        "speaker_roles": speaker_roles,
        "dates": dates,
        "settlement_payment_terms": settlement_terms,
    }
