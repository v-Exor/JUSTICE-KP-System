from functools import lru_cache
import math
import os
from typing import Dict, List

from faster_whisper import WhisperModel


@lru_cache(maxsize=1)
def get_whisper_model() -> WhisperModel:
    # "small" is still practical locally and is noticeably better for Filipino/Taglish than "base".
    model_name = os.getenv("WHISPER_MODEL", "small")
    return WhisperModel(model_name, device="cpu", compute_type="int8")


def transcribe_audio(audio_path: str) -> List[Dict]:
    model = get_whisper_model()
    configured_language = os.getenv("WHISPER_LANGUAGE", "auto").strip().lower()
    segments, _ = model.transcribe(
        audio_path,
        language=None if configured_language in {"", "auto", "none"} else configured_language,
        task="transcribe",
        initial_prompt=(
            "Katarungang Pambarangay hearing in Filipino, Tagalog, English, and Taglish. "
            "Speaker role phrases include Desk Officer, Barangay Secretary, Kagawad, "
            "Barangay Secretary/Mediator, Complainant, Magrereklamo po ako, Respondent, "
            "Respondent/Inirereklamo. Common words include barangay, reklamo, utang, "
            "bayad, kasunduan, lupon, mediation, hearing."
        ),
        vad_filter=True,
        vad_parameters={
            "threshold": 0.35,
            "min_speech_duration_ms": 150,
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 300,
        },
        beam_size=5,
        temperature=0.0,
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        no_speech_threshold=0.7,
        word_timestamps=True,
    )

    results = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue

        results.append(
            {
                "start": round(float(segment.start), 2),
                "end": round(float(segment.end), 2),
                "text": text,
                "confidence": round(max(0.0, min(1.0, math.exp(float(getattr(segment, "avg_logprob", 0.0))))), 4),
                "words": [
                    {
                        "start": round(float(word.start), 2),
                        "end": round(float(word.end), 2),
                        "text": word.word.strip(),
                        "confidence": round(float(getattr(word, "probability", 0.0)), 4)
                        if getattr(word, "probability", None) is not None
                        else None,
                    }
                    for word in (segment.words or [])
                    if word.word.strip()
                ],
            }
        )

    return results
