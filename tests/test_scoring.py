import unittest
from datetime import date

from app.scoring import score_project


class ScoringTests(unittest.TestCase):
    def test_preconstruction_large_recent_project_ranks_high(self):
        project={
            "commercial_stage":"PRECONSTRUCTION",
            "power_mw":120.0,
            "technology":"WIND",
            "last_seen":"2026-10-01",
        }
        got=score_project(
            project,event_types={"EXPROPRIATION"},
            ree_context_available=True,as_of=date(2026,10,3),
        )
        self.assertEqual(got["priority"],"A")
        self.assertGreaterEqual(got["score"],70)
        self.assertEqual(got["components"]["advanced_milestone"],15)

    def test_blocked_is_zero_independently_from_size(self):
        got=score_project(
            {"commercial_stage":"BLOCKED","power_mw":500,"technology":"PV","last_seen":"2026-10-03"},
            event_types={"CONSTRUCTION_AUTH"},ree_context_available=True,as_of=date(2026,10,3),
        )
        self.assertEqual(got["score"],0)
        self.assertEqual(got["priority"],"BLOCKED")

    def test_score_does_not_change_lifecycle_input(self):
        project={"commercial_stage":"PERMITTING","power_mw":None,"technology":"PV","last_seen":"2026-07-01"}
        before=dict(project)
        score_project(project,as_of=date(2026,10,3))
        self.assertEqual(project,before)


if __name__=="__main__":
    unittest.main()
