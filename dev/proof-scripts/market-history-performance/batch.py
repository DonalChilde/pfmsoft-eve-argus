"""Time the production batch runner against 2,000 cold-cache history updates."""

from _benchmark import run_benchmark

if __name__ == "__main__":
    run_benchmark("batch")
