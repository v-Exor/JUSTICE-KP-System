from datetime import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from legal_ner import apply_authoritative_case_entities, extract_legal_entities  # noqa: E402


class LegalEntityExtractionTests(unittest.TestCase):
    def test_speaker_role_is_not_mistaken_for_barangay_name(self):
        entities = extract_legal_entities(
            "Barangay Secretary/Mediator: Ngayon po natin pag-uusapan ang reklamo."
        )

        self.assertEqual(entities["barangay_names"], [])
        self.assertEqual(entities["dates"], [])

    def test_saved_case_facts_replace_transcript_guesses(self):
        entities = {
            "barangay_names": ["Secretary", "Secretary Corazon David"],
            "dates": ["ngayon"],
            "speaker_roles": ["Barangay Secretary/Mediator"],
        }

        corrected = apply_authoritative_case_entities(
            entities,
            "Landayan",
            datetime(2026, 8, 28, 16, 30),
        )

        self.assertEqual(corrected["barangay_names"], ["Landayan"])
        self.assertEqual(corrected["dates"], ["2026-08-29"])
        self.assertEqual(corrected["speaker_roles"], ["Barangay Secretary/Mediator"])


if __name__ == "__main__":
    unittest.main()
