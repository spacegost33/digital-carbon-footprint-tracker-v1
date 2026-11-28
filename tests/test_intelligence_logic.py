import unittest
from datetime import date, timedelta
from app.intelligence_logic import energy_estimate, analyse_days, recommendations

class IntelligenceTests(unittest.TestCase):
    def test_energy(self): self.assertAlmostEqual(energy_estimate(30, 8), .24)
    def test_invalid(self):
        for pair in [(0,1),(float('nan'),2),(10,25),(10,float('inf'))]:
            with self.assertRaises(ValueError): energy_estimate(*pair)
    def test_missing(self):
        self.assertIsNone(analyse_days({}, date(2026,11,28))['score'])
        self.assertIsNone(analyse_days({}, date(2026,11,28))['forecast'])
    def test_complete(self):
        today=date(2026,11,28)
        daily={today-timedelta(days=i): 1 if i<=7 else 2 for i in range(1,15)}
        a=analyse_days(daily,today)
        self.assertEqual(a['change'],-50)
        self.assertEqual(a['score'],75)
        self.assertEqual(a['forecast'],7)
        self.assertEqual(a['streak'],14)
        self.assertTrue(recommendations({'computing':7},a))
if __name__=='__main__': unittest.main()
