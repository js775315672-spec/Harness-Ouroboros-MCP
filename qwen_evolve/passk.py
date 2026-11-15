"""Measure the model, not the harness: pass rate with a confidence interval."""
import math


def pass_rate_wilson(successes, trials, z=1.96):
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("invalid counts")
    p = successes / trials
    denom = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


def unbiased_pass_at_k(n, c, k):
    """Chen et al. estimator: probability >=1 of k sampled attempts passes."""
    if not 0 <= c <= n or not 1 <= k <= n:
        raise ValueError("invalid counts")
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)
