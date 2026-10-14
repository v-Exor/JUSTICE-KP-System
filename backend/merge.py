from typing import Dict, List


def _overlap_seconds(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def merge_transcript_and_speakers(transcript: List[Dict], speakers: List[Dict]) -> List[Dict]:
    word_units = []

    for segment in transcript:
        words = segment.get("words") or []
        if words:
            for word in words:
                word_units.append(
                    {
                        "start": float(word["start"]),
                        "end": float(word["end"]),
                        "text": word["text"],
                        "confidence": word.get("confidence"),
                    }
                )
        else:
            word_units.append(
                {
                    "start": float(segment["start"]),
                    "end": float(segment["end"]),
                    "text": segment["text"].strip(),
                    "confidence": segment.get("confidence"),
                }
            )

    assigned_units = []
    for unit in word_units:
        assigned_units.append(
            {
                "speaker": _speaker_for_time_range(unit["start"], unit["end"], speakers),
                "start": round(unit["start"], 2),
                "end": round(unit["end"], 2),
                "text": unit["text"],
                "confidence": unit.get("confidence"),
            }
        )

    return _group_adjacent_segments(assigned_units)


def _speaker_for_time_range(start: float, end: float, speakers: List[Dict]) -> str:
    best_speaker = "Speaker 1"
    best_overlap = 0.0
    midpoint = (start + end) / 2

    for speaker in speakers:
        overlap = _overlap_seconds(start, end, float(speaker["start"]), float(speaker["end"]))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker["speaker"]
        elif best_overlap == 0.0 and float(speaker["start"]) <= midpoint <= float(speaker["end"]):
            best_speaker = speaker["speaker"]

    return best_speaker


def _group_adjacent_segments(segments: List[Dict]) -> List[Dict]:
    grouped = []

    for segment in segments:
        if grouped and grouped[-1]["speaker"] == segment["speaker"]:
            grouped[-1]["end"] = segment["end"]
            grouped[-1]["text"] = f'{grouped[-1]["text"]} {segment["text"]}'.strip()
            confidences = grouped[-1].setdefault("confidences", [])
            if segment.get("confidence") is not None:
                confidences.append(float(segment["confidence"]))
        else:
            copy = segment.copy()
            if copy.get("confidence") is not None:
                copy["confidences"] = [float(copy["confidence"])]
            grouped.append(copy)

    for segment in grouped:
        confidences = segment.pop("confidences", [])
        if confidences:
            segment["confidence"] = round(sum(confidences) / len(confidences), 4)

    return grouped
