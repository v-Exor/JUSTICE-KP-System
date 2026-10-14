import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env")


DIARIZATION_MODEL_ID = "pyannote/speaker-diarization-community-1"


@lru_cache(maxsize=1)
def get_diarization_pipeline():
    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HuggingFace_Token")
    if not token:
        return None

    import torchaudio
    import numpy as np

    if not hasattr(torchaudio, "set_audio_backend"):
        torchaudio.set_audio_backend = lambda *_args, **_kwargs: None
    if not hasattr(torchaudio, "get_audio_backend"):
        torchaudio.get_audio_backend = lambda: "soundfile"
    if not hasattr(np, "NaN"):
        np.NaN = np.nan

    import torch
    from pyannote.audio import Pipeline
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    # PyTorch 2.6+ defaults to weights-only checkpoint loading. The official
    # Community-1 segmentation checkpoint includes these three pyannote metadata
    # types, so allowlist only those known classes instead of disabling safe
    # checkpoint loading globally.
    torch.serialization.add_safe_globals([Specifications, Problem, Resolution])

    return Pipeline.from_pretrained(DIARIZATION_MODEL_ID, token=token)


def has_diarization_token() -> bool:
    return bool(os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HuggingFace_Token"))


def diarize_audio(audio_path: str, max_speakers: int = 3, speaker_count: int | None = None) -> List[Dict]:
    pipeline = get_diarization_pipeline()
    if pipeline is None:
        # Keep the demo usable even before the Hugging Face token is configured.
        return [{"speaker": "Speaker 1", "start": 0.0, "end": 999999.0}]

    import torchaudio

    waveform, sample_rate = torchaudio.load(audio_path)
    audio_input = {"waveform": waveform, "sample_rate": sample_rate}

    if speaker_count:
        output = pipeline(audio_input, num_speakers=speaker_count)
    else:
        output = pipeline(audio_input, min_speakers=1, max_speakers=max_speakers)

    # Community-1 provides an exclusive one-speaker-at-a-time timeline made for
    # reconciling diarization with ASR word timestamps. Do not silently fall back
    # to the legacy 3.1 output shape because that would reintroduce ambiguous
    # overlapping turns into the word-to-speaker merge.
    diarization = getattr(output, "exclusive_speaker_diarization", None)
    if diarization is None:
        raise RuntimeError(
            f"{DIARIZATION_MODEL_ID} did not return exclusive speaker diarization. "
            "Confirm that pyannote.audio 4.x and the Community-1 model are installed."
        )

    speaker_map = {}
    speakers = []

    for turn, _, raw_speaker in diarization.itertracks(yield_label=True):
        if raw_speaker not in speaker_map:
            next_number = min(len(speaker_map) + 1, max_speakers)
            speaker_map[raw_speaker] = f"Speaker {next_number}"

        speakers.append(
            {
                "speaker": speaker_map[raw_speaker],
                "start": round(float(turn.start), 2),
                "end": round(float(turn.end), 2),
            }
        )

    return speakers
