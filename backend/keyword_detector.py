import re
from collections import Counter
from typing import Any


SENSITIVE_KEYWORDS = [
    "sinaktan",
    "binugbog",
    "pinagbubugbog",
    "sinuntok",
    "sinipa",
    "sinampal",
    "kinurot",
    "tinadyakan",
    "hinampas",
    "pinukpok",
    "sinakal",
    "tinulak",
    "kinaladkad",
    "pinaso",
    "pinahirapan",
    "binato",
    "pinalo",
    "hinataw",
    "sugatan",
    "nasaktan",
    "nasugatan",
    "dumugo",
    "nabalian",
    "napuruhan",
    "banta",
    "binantaan",
    "pananakit",
    "violence",
    "abuse",
    "threatened",
    "hurt",
    "siniko",
    "bata",
    "pagsiko",
    "injured",
]


def detect_sensitive_keywords(transcript_text: str) -> dict[str, Any]:
    normalized = transcript_text.lower()
    counts: Counter[str] = Counter()

    for keyword in SENSITIVE_KEYWORDS:
        pattern = re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)", flags=re.IGNORECASE)
        matches = pattern.findall(normalized)
        if matches:
            counts[keyword] += len(matches)

    detected_keywords = [keyword for keyword in SENSITIVE_KEYWORDS if counts[keyword] > 0]
    keyword_count = sum(counts.values())

    return {
        "detected_keywords": detected_keywords,
        "keyword_count": keyword_count,
        "vawc_trigger": keyword_count > 0,
    }
