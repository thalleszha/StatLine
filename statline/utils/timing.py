from time import perf_counter
from contextlib import contextmanager

class StageTimes:
    def __init__(self):
        self.items = []
    @contextmanager
    def stage(self, name):
        t0 = perf_counter()
        try:
            yield
        finally:
            self.items.append((name, (perf_counter() - t0) * 1000))  # ms

    def print_summary(self):
        total = sum(ms for _, ms in self.items)
        for name, ms in self.items:
            print(f"{name:18s} {ms:7.2f} ms")
        print("-" * 28)
        print(f"{'TOTAL':18s} {total:7.2f} ms")
