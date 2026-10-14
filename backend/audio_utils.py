import subprocess
from pathlib import Path
import wave


def convert_to_wav(input_path: str) -> str:
    source = Path(input_path)
    output = source.with_suffix(".wav")

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        "highpass=f=70,lowpass=f=7900,loudnorm=I=-18:TP=-2:LRA=11",
        str(output),
    ]

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "FFmpeg audio conversion failed.")

    return str(output)


def wav_duration_seconds(audio_path: str) -> float | None:
    path = Path(audio_path)
    if path.suffix.lower() != ".wav" or not path.is_file():
        return None
    try:
        with wave.open(str(path), "rb") as audio:
            frame_rate = audio.getframerate()
            if frame_rate <= 0:
                return None
            return round(audio.getnframes() / frame_rate, 2)
    except (OSError, wave.Error):
        return None
