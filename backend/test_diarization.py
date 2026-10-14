import unittest
from unittest.mock import patch

import torch

import diarization


class FakeTurn:
    def __init__(self, start: float, end: float):
        self.start = start
        self.end = end


class FakeExclusiveDiarization:
    def itertracks(self, yield_label: bool = False):
        assert yield_label
        yield FakeTurn(0.25, 1.75), None, "SPEAKER_00"
        yield FakeTurn(2.0, 3.5), None, "SPEAKER_01"


class FakeCommunityOutput:
    exclusive_speaker_diarization = FakeExclusiveDiarization()


class FakeCommunityPipeline:
    def __init__(self):
        self.calls = []

    def __call__(self, audio_input, **kwargs):
        self.calls.append((audio_input, kwargs))
        return FakeCommunityOutput()


class CommunityDiarizationTests(unittest.TestCase):
    def test_community_model_identifier_is_explicit(self):
        self.assertEqual(
            diarization.DIARIZATION_MODEL_ID,
            "pyannote/speaker-diarization-community-1",
        )

    def test_uses_exclusive_diarization_with_fixed_speaker_count(self):
        pipeline = FakeCommunityPipeline()
        waveform = torch.zeros((1, 16000))

        with (
            patch.object(diarization, "get_diarization_pipeline", return_value=pipeline),
            patch("torchaudio.load", return_value=(waveform, 16000)),
        ):
            segments = diarization.diarize_audio("sample.wav", speaker_count=2)

        self.assertEqual(pipeline.calls[0][1], {"num_speakers": 2})
        self.assertEqual(
            segments,
            [
                {"speaker": "Speaker 1", "start": 0.25, "end": 1.75},
                {"speaker": "Speaker 2", "start": 2.0, "end": 3.5},
            ],
        )

    def test_rejects_legacy_output_shape(self):
        pipeline = lambda *_args, **_kwargs: object()
        waveform = torch.zeros((1, 16000))

        with (
            patch.object(diarization, "get_diarization_pipeline", return_value=pipeline),
            patch("torchaudio.load", return_value=(waveform, 16000)),
        ):
            with self.assertRaisesRegex(RuntimeError, "exclusive speaker diarization"):
                diarization.diarize_audio("sample.wav", speaker_count=2)


if __name__ == "__main__":
    unittest.main()
