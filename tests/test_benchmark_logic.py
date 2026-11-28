import importlib.util
import unittest
from pathlib import Path

# Load standalone calculation module without importing Flask or opening a database.
path = Path(__file__).resolve().parents[1] / 'app' / 'benchmark_logic.py'
spec = importlib.util.spec_from_file_location('benchmark_logic', path)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

class BenchmarkTests(unittest.TestCase):
    def test_sort_correctness(self):
        for f in (b.bubble_sort, b.merge_sort, b.quick_sort):
            for data in ([], [1], [4, 2, 2, -1, 8], list(range(10, 0, -1))):
                self.assertEqual(f(data.copy()), sorted(data))
    def test_search_correctness(self):
        for f in (b.linear_search, b.binary_search):
            self.assertEqual(f([1, 3, 5], 3), 1)
            self.assertEqual(f([1, 3, 5], 7), -1)
    def test_benchmark_units(self):
        result = b.run_benchmark('sorting', 100, 30, 0.7)
        self.assertEqual(len(result['rows']), 3)
        for row in result['rows']:
            self.assertAlmostEqual(row['energy_kwh'], 30*row['wall_ms']/3_600_000_000)
            self.assertAlmostEqual(row['carbon_kg'], row['energy_kwh']*0.7)
    def test_search_workload(self):
        result = b.run_benchmark('searching', 100, 30, 0.7)
        self.assertEqual(result['operations'], 500)
        self.assertEqual(len(result['rows']), 2)
    def test_validation(self):
        for args in [('bad',100,30,.7), ('sorting',10000,30,.7), ('sorting',100,float('nan'),.7), ('sorting',100,0,.7), ('sorting',100,30,float('inf'))]:
            with self.assertRaises(ValueError): b.validate_input(*args)

if __name__ == '__main__': unittest.main()
