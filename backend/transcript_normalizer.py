import re


# Conservative ASR cleanup for common Filipino/Taglish mishearings seen in demo recordings.
# Keep this list small and reviewable because hearing transcripts are legal/official records.
PHRASE_CORRECTIONS = {
    "lalawang linko": "dalawang linggo",
    "lalawang linggo": "dalawang linggo",
    "dalawang linko": "dalawang linggo",
    "inatangan": "inutangan",
    "inatangran": "inutangan",
    "inutangan ko ako": "inutangan po ako",
    "indipo": "hindi po",
    "hindi po siya ng bayad": "hindi po siya nagbayad",
    "nag bayad": "nagbayad",
    "binayar": "binayaran",
    "binayar niyan": "binayaran yan",
    "binyaran": "binayaran",
    "nabung": "na pong",
    "nabong": "na pong",
    "na pung": "na pong",
    "ay matagal ko": "ay matagal ko",
    "uey": "uy",
}


def _apply_phrase_corrections(text: str, corrections: dict[str, str]) -> str:
    normalized = f" {text.strip()} "

    for wrong, correct in sorted(corrections.items(), key=lambda item: len(item[0]), reverse=True):
        if not wrong.strip() or not correct.strip():
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(wrong)}(?!\w)", re.IGNORECASE)
        normalized = pattern.sub(correct, normalized)

    normalized = re.sub(r"\s+([,.!?;:])", r"\1", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_transcript_text(text: str, learned_corrections: dict[str, str] | None = None) -> str:
    normalized = _apply_phrase_corrections(text, PHRASE_CORRECTIONS)
    if learned_corrections:
        normalized = _apply_phrase_corrections(normalized, learned_corrections)
    return normalized


def normalize_segments(
    segments: list[dict],
    learned_corrections: dict[str, str] | None = None,
) -> list[dict]:
    normalized_segments = []

    for segment in segments:
        normalized = segment.copy()
        normalized["text"] = normalize_transcript_text(
            str(segment.get("text", "")),
            learned_corrections=learned_corrections,
        )
        normalized_segments.append(normalized)

    return normalized_segments
