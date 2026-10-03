import unittest

from app.reporting import build_province_view_from_rows


class ProvinceViewTests(unittest.TestCase):
    def test_known_mw_and_missing_mw_are_separate(self):
        rows=[
            {"province":"Zaragoza","technology":"PV","power_mw":50.0,"commercial_stage":"PERMITTING"},
            {"province":"Zaragoza","technology":"WIND","power_mw":None,"commercial_stage":"AUTHORIZED"},
            {"province":"Zaragoza","technology":"HYBRID","power_mw":20.0,"commercial_stage":"PRECONSTRUCTION"},
            {"province":None,"technology":"PV","power_mw":99.0,"commercial_stage":"EARLY"},
        ]
        got=build_province_view_from_rows(rows)
        self.assertEqual(len(got),1)
        z=got[0]
        self.assertEqual(z["projects"],3)
        self.assertEqual(z["known_mw"],70.0)
        self.assertEqual(z["projects_without_mw"],1)
        self.assertEqual(z["pv"],1)
        self.assertEqual(z["wind"],1)
        self.assertEqual(z["bess_hybrid"],1)
        self.assertEqual(z["authorized"],1)
        self.assertEqual(z["preconstruction"],1)


if __name__=="__main__":
    unittest.main()
