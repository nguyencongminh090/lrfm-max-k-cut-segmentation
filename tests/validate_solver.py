"""Validate the from-scratch local-search max-k-cut solver.

Checks three things, with NO dependency on Gurobi/CBC:
  1. CORRECTNESS  -- against brute-force global optimum (k**n enumeration) on
     tiny instances, plus a structured instance with a known optimal cut.
  2. SPEED        -- wall-clock at realistic reduced-graph scales.
  3. ROBUSTNESS   -- how reliably multi-start hits the best cut, vs #restarts.

Run:  python -m tests.validate_solver
"""
from __future__ import annotations

import time
from itertools import product

import numpy as np
import pandas as pd

from src.graph import reduce_graph, ReducedGraph
from src.maxkcut import solve_maxkcut, _cut_value


# --------------------------------------------------------------------------- #
# Independent oracles
# --------------------------------------------------------------------------- #
def cut_vectorized(W: np.ndarray, labels: np.ndarray) -> float:
    """Crossing-edge weight, computed independently of _cut_value (cross-check)."""
    return float((W * (labels[:, None] != labels[None, :])).sum() / 2.0)


def brute_force(W: np.ndarray, k: int) -> float:
    """Provable global-optimum cut by enumerating all k**n assignments."""
    n = len(W)
    best = -np.inf
    for assign in product(range(k), repeat=n):
        best = max(best, cut_vectorized(W, np.asarray(assign)))
    return best


def _rg_from_scores(score_mat: np.ndarray) -> ReducedGraph:
    df = pd.DataFrame(score_mat, columns=[f"v{i}" for i in range(score_mat.shape[1])])
    df.index.name = "CustomerID"
    return reduce_graph(df)


def _rg_from_W(W: np.ndarray) -> ReducedGraph:
    """Wrap a raw weight matrix as a ReducedGraph (1 member per vertex)."""
    n = len(W)
    return ReducedGraph(scores=np.zeros((n, 1)), counts=np.ones(n, int),
                        W=W, members=[[i] for i in range(n)], variables=["w"])


# --------------------------------------------------------------------------- #
# 1. Correctness
# --------------------------------------------------------------------------- #
def test_correctness(n_instances: int = 40) -> bool:
    rng = np.random.default_rng(7)
    print("1. CORRECTNESS  (local-search best cut vs brute-force global optimum)")
    all_ok = True

    # (a) _cut_value must equal the independent vectorized cut
    Wc = rng.integers(0, 9, size=(12, 12)).astype(float); Wc = (Wc + Wc.T); np.fill_diagonal(Wc, 0)
    lab = rng.integers(0, 3, size=12)
    assert abs(_cut_value(Wc, lab, 3) - cut_vectorized(Wc, lab)) < 1e-9, "_cut_value mismatch!"
    print("   [a] _cut_value == independent crossing-edge formula  ... OK")

    # (b) random tiny instances vs brute force
    fails = 0
    for _ in range(n_instances):
        n = int(rng.integers(6, 10)); k = int(rng.integers(2, 5))
        W = rng.integers(0, 10, size=(n, n)).astype(float); W = W + W.T; np.fill_diagonal(W, 0)
        opt = brute_force(W, k)
        _, got, _ = solve_maxkcut(_rg_from_W(W), k, solver="local")
        if abs(got - opt) > 1e-6:
            fails += 1
            print(f"   [b] MISS  n={n} k={k}  local={got:.0f} < opt={opt:.0f}  (gap {opt-got:.0f})")
    print(f"   [b] {n_instances - fails}/{n_instances} tiny instances hit the PROVEN optimum"
          f"  ... {'OK' if fails == 0 else 'SUBOPTIMAL'}")
    all_ok &= fails == 0

    # (c) structured instance: 3 tight clusters placed far apart, k=3.
    #     Optimal solution separates them perfectly -> intra weight 0 -> cut == total.
    blocks = np.array([[1, 1, 1]] * 5 + [[5, 5, 5]] * 5 + [[1, 5, 1]] * 5)
    rg = _rg_from_scores(blocks)
    total = rg.W.sum() / 2
    _, got, _ = solve_maxkcut(rg, 3, solver="local")
    ok_c = abs(got - total) < 1e-6
    print(f"   [c] 3 separated clusters, k=3: cut={got:.0f} total={total:.0f}"
          f"  (perfect separation) ... {'OK' if ok_c else 'FAIL'}")
    all_ok &= ok_c
    return bool(all_ok)


# --------------------------------------------------------------------------- #
# 2. Speed
# --------------------------------------------------------------------------- #
def test_speed() -> None:
    print("\n2. SPEED  (wall-clock at reduced-graph scale, 200 restarts)")
    rng = np.random.default_rng(0)
    # warm up the Numba JIT so compile time is excluded from the timings below
    _warm = pd.DataFrame(rng.integers(1, 6, size=(50, 4)), index=np.arange(50))
    _warm.index.name = "CustomerID"
    t0 = time.time(); solve_maxkcut(reduce_graph(_warm), 3, solver="local")
    print(f"   (JIT warm-up compile: {time.time()-t0:.1f}s, excluded below)")
    print(f"   {'customers':>9} {'n_super':>8} {'k':>3} {'cut':>14} {'time':>8}")
    for n in (5878,):
        for nvars, tag in ((3, "RFM"), (4, "LRFM")):
            sm = pd.DataFrame(rng.integers(1, 6, size=(n, nvars)),
                              index=np.arange(n))
            sm.index.name = "CustomerID"
            rg = reduce_graph(sm)
            for k in (2, 4, 10):
                t = time.time()
                _, cut, _ = solve_maxkcut(rg, k, solver="local")
                print(f"   {n:>9} {rg.n_super:>8} {k:>3} {cut:>14,.0f} {time.time()-t:>7.2f}s"
                      f"   <- {tag}")


# --------------------------------------------------------------------------- #
# 3. Robustness to #restarts
# --------------------------------------------------------------------------- #
def test_robustness() -> None:
    from src.maxkcut import _solve_local_search
    print("\n3. ROBUSTNESS  (does multi-start reliably reach the same best cut?)")
    rng = np.random.default_rng(3)
    sm = pd.DataFrame(rng.integers(1, 6, size=(2000, 4)), index=np.arange(2000))
    sm.index.name = "CustomerID"
    rg = reduce_graph(sm)
    k = 4
    # reference best from a heavy run
    _, ref, _ = _solve_local_search(rg, k, n_restarts=500, seed=999)
    print(f"   reference best cut (500 restarts): {ref:,.0f}")
    print(f"   {'restarts':>8} {'best/10 seeds':>14} {'worst/10 seeds':>15} {'%hit ref':>9}")
    for r in (1, 10, 50, 200):
        cuts = [_solve_local_search(rg, k, n_restarts=r, seed=s)[1] for s in range(10)]
        hit = sum(abs(c - ref) < 1e-6 for c in cuts)
        print(f"   {r:>8} {max(cuts):>14,.0f} {min(cuts):>15,.0f} {hit*10:>8}%")


if __name__ == "__main__":
    ok = test_correctness()
    test_speed()
    test_robustness()
    print(f"\n=== CORRECTNESS VERDICT: {'PASS' if ok else 'FAIL'} ===")
