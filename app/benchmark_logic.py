"""Bounded, deterministic, predefined workloads. No user-supplied code."""
import argparse
import json
import math
import random
import statistics
import time
import tracemalloc

MAX_SIZE = 2000
MIN_SIZE = 100
REPEATS = 3


def bubble_sort(values):
    for end in range(len(values) - 1, 0, -1):
        changed = False
        for i in range(end):
            if values[i] > values[i + 1]:
                values[i], values[i + 1] = values[i + 1], values[i]
                changed = True
        if not changed:
            break
    return values


def merge_sort(values):
    if len(values) < 2:
        return values
    mid = len(values) // 2
    left, right = merge_sort(values[:mid]), merge_sort(values[mid:])
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i]); i += 1
        else:
            result.append(right[j]); j += 1
    result.extend(left[i:]); result.extend(right[j:])
    return result


def quick_sort(values):
    if len(values) < 2:
        return values
    pivot = values[len(values) // 2]
    less = [v for v in values if v < pivot]
    equal = [v for v in values if v == pivot]
    greater = [v for v in values if v > pivot]
    return quick_sort(less) + equal + quick_sort(greater)


def linear_search(values, target):
    for i, value in enumerate(values):
        if value == target:
            return i
    return -1


def binary_search(values, target):
    lo, hi = 0, len(values) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if values[mid] == target:
            return mid
        if values[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def validate_input(kind, size, watts, factor):
    if kind not in ('sorting', 'searching') or not isinstance(size, int) or not MIN_SIZE <= size <= MAX_SIZE:
        raise ValueError('Choose a supported workload and 100–2000 items.')
    watts, factor = float(watts), float(factor)
    if not (math.isfinite(watts) and 0 < watts <= 1000 and math.isfinite(factor) and 0 < factor <= 5):
        raise ValueError('Invalid assumed power or emission factor.')
    return watts, factor


def run_benchmark(kind, size, watts, factor):
    watts, factor = validate_input(kind, size, watts, factor)
    rng = random.Random(42)
    if kind == 'sorting':
        data = list(range(size)); rng.shuffle(data)
        expected = list(range(size))
        cases = [('Bubble Sort', bubble_sort), ('Merge Sort', merge_sort), ('Quick Sort', quick_sort)]
        operations = 1
        def prepare(): return data.copy()
        def invoke(fn, payload): return fn(payload)
    else:
        data = list(range(size))
        targets = [rng.randrange(-size // 4, size + size // 4) for _ in range(500)]
        expected = [t if 0 <= t < size else -1 for t in targets]
        cases = [('Linear Search', linear_search), ('Binary Search', binary_search)]
        operations = len(targets)
        def prepare(): return data
        def invoke(fn, payload): return [fn(payload, target) for target in targets]
    rows = []
    for name, fn in cases:
        wall, cpu = [], []
        for _ in range(REPEATS):
            payload = prepare()
            c0 = time.process_time_ns(); t0 = time.perf_counter_ns()
            actual = invoke(fn, payload)
            elapsed = time.perf_counter_ns() - t0; cpu_ns = time.process_time_ns() - c0
            if actual != expected:
                raise RuntimeError('Algorithm output mismatch')
            wall.append(elapsed / 1e9); cpu.append(cpu_ns / 1e9)
        # Separate allocation pass so tracing does not distort timed trials.
        payload = prepare()
        tracemalloc.start()
        try:
            actual = invoke(fn, payload)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        if actual != expected:
            raise RuntimeError('Algorithm output mismatch')
        seconds = statistics.median(wall)
        energy = watts * seconds / 3_600_000
        rows.append(dict(name=name, wall_ms=seconds * 1000, cpu_ms=statistics.median(cpu)*1000,
                         peak_bytes=peak, energy_kwh=energy, carbon_kg=energy*factor))
    rows.sort(key=lambda row: row['wall_ms'])
    slowest = rows[-1]['wall_ms']
    saving = 100 * (1 - rows[0]['wall_ms']/slowest) if slowest > 0 else 0
    return dict(kind=kind, size=size, operations=operations, repeats=REPEATS, assumed_watts=watts,
                factor=factor, rows=rows, fastest=rows[0]['name'], time_saving_pct=saving)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('kind', choices=['sorting', 'searching'])
    parser.add_argument('size', type=int)
    parser.add_argument('watts', type=float)
    parser.add_argument('factor', type=float)
    args = parser.parse_args()
    print(json.dumps(run_benchmark(args.kind, args.size, args.watts, args.factor), allow_nan=False))
