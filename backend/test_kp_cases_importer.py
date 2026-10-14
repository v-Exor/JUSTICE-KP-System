import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from database import Base  # noqa: E402
from kp_cases_importer import import_kp_cases_workbook, workbook_rows, workbook_summary  # noqa: E402
from models import (  # noqa: E402
    CaseAnalysis,
    KPResearchDataset,
    Phase3CaseRoute,
    Phase5GroundTruth,
    Phase5ValidationCase,
)


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


class KPCasesImporterTests(unittest.TestCase):
    def test_workbook_summary_reads_balanced_dataset(self):
        summary = workbook_summary()

        self.assertEqual(summary["total_rows"], 539)
        self.assertEqual(summary["by_case_type"]["debt"], 49)
        self.assertEqual(summary["by_case_type"]["VAWC/child abuse"], 49)
        self.assertEqual(summary["by_label"]["KP_COVERED_AMICABLE"], 245)
        self.assertEqual(summary["by_label"]["NON_KP_REFERRAL"], 196)

    def test_workbook_rows_have_expected_headers(self):
        rows = workbook_rows()
        first = rows[0]

        self.assertIn("case_id", first)
        self.assertIn("justice_kp_label", first)
        self.assertIn("recommended_system_action", first)
        self.assertEqual(first["case_id"], "KP-25-004-PSWT")

    def test_limited_import_populates_phase2_phase3_phase5_and_research_tables(self):
        db = make_session()
        try:
            stats = import_kp_cases_workbook(db, limit=6)

            self.assertEqual(stats["imported"], 6)
            self.assertEqual(db.query(CaseAnalysis).count(), 6)
            self.assertEqual(db.query(Phase3CaseRoute).count(), 6)
            self.assertEqual(db.query(Phase5ValidationCase).count(), 6)
            self.assertEqual(db.query(Phase5GroundTruth).count(), 6)
            self.assertEqual(db.query(KPResearchDataset).count(), 6)
        finally:
            db.close()

    def test_import_is_idempotent_when_skip_existing_is_true(self):
        db = make_session()
        try:
            first = import_kp_cases_workbook(db, limit=3)
            second = import_kp_cases_workbook(db, limit=3)

            self.assertEqual(first["imported"], 3)
            self.assertEqual(second["imported"], 0)
            self.assertEqual(second["skipped_existing"], 3)
            self.assertEqual(db.query(Phase5ValidationCase).count(), 3)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
