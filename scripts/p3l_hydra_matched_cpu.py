"""Compare the same two offline Hydra suites under a shared CPU limit."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import resource
import statistics
import time

from p3l_hydra_run_lanes import SUITES, identity, run_suite, sha


def cpu_seconds():
    data = resource.getrusage(resource.RUSAGE_CHILDREN)
    return data.ru_utime + data.ru_stime


def measure(workers):
    start_cpu = cpu_seconds()
    start = time.perf_counter()
    if workers == 1:
        results = [run_suite(key) for key in SUITES]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(run_suite, SUITES))
    return {"wall_seconds": round(time.perf_counter() - start, 6),
            "child_cpu_seconds": round(cpu_seconds() - start_cpu, 6),
            "counts": dict(zip(SUITES, [item[1] for item in results]))}


def main():
    head, run = identity()
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise ValueError("the matched rehearsal needs two available logical CPUs")
    os.sched_setaffinity(0, cpus)
    if os.sched_getaffinity(0) != set(cpus):
        raise ValueError("failed to apply the same CPU affinity to both modes")
    samples = {1: [], 2: []}
    expected = {"w06_public_probe": 5, "w05_receipt_gate": 12}
    for index in range(6):
        for workers in ((1, 2) if index % 2 == 0 else (2, 1)):
            sample = measure(workers)
            if sample["counts"] != expected:
                raise ValueError("serial and parallel workloads differ")
            samples[workers].append(sample)
    median = {key: statistics.median(item["wall_seconds"] for item in values)
              for key, values in samples.items()}
    cpu_median = {key: statistics.median(item["child_cpu_seconds"] for item in values)
                  for key, values in samples.items()}
    data = {"head": head, "run_id": run, "samples": samples, "logical_cpu_count": len(cpus),
            "runner": os.environ["RUNNER_NAME"], "trials_per_mode": 6, "tests_per_trial": 17,
            "median_wall_seconds": median, "median_child_cpu_seconds": cpu_median,
            "wall_speedup_serial_over_parallel": round(median[1] / median[2], 3),
            "test_source_sha256": {key: sha((Path("tests") / suite).read_bytes())
                                   for key, suite in SUITES.items()}, "model_calls": 0}
    print(json.dumps(data, sort_keys=True))


if __name__ == "__main__":
    main()
