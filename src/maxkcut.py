"""Solve the max-k-cut problem (BQO formulation) on the reduced graph.

Baseline paper, Sec. 2.2, formulation (BQO):

    max  f(x) = sum_{(i,j) in E} w_ij * (1 - sum_{l=1..k} x_il x_jl)
    s.t. sum_{l=1..k} x_il = 1            for every vertex i
         x_il in {0, 1}

Maximising the weight of edges that CROSS clusters == minimising intra-cluster
weight, i.e. putting dissimilar customers in different groups. The objective
value f equals the total weight of edges whose endpoints land in different
clusters (the "cut").

Three solver backends (select via `solver=`):
  * "local"  (DEFAULT) -- our own multi-start local-search heuristic, pure NumPy,
               no license, no external solver. Near-optimal on the small reduced
               graph (<=125 vertices for RFM, <=625 for LRFM).
  * "gurobi" -- exact MILP/MIQP (paper used Gurobi). Needs a real license; the
               free pip license is size-limited and cannot handle this problem.
  * "cbc"    -- exact via PuLP + open-source CBC (linearized). No license; slow.

All three return the objective in the SAME units, so they are directly
comparable -- use "gurobi"/"cbc" on small instances to certify that "local"
reaches the true optimum.
"""
from __future__ import annotations

import numpy as np

from . import config
from .graph import ReducedGraph

try:                                   # Numba JIT for the local-search kernel
    from numba import njit
    _HAVE_NUMBA = True
except Exception:                      # graceful fallback: no-op decorator
    _HAVE_NUMBA = False

    def njit(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda fn: fn


def solve_maxkcut(
    rg: ReducedGraph,
    k: int,
    time_limit: int = config.GUROBI_TIME_LIMIT,
    seed: int = config.RANDOM_SEED,
    verbose: bool = False,
    solver: str = config.SOLVER,
):
    """Solve max-k-cut on reduced graph `rg`. Returns (labels, objective, gap).

    labels : np.ndarray (n_super,) cluster index in [0, k) per super-vertex
    objective : best cut value found (== paper's BQO objective f)
    gap : optimality gap (0.0 == proven optimal; NaN for the heuristic)

    solver : "local" (our from-scratch heuristic, no license -- DEFAULT),
             "gurobi" (exact, needs a real license), or
             "cbc" (exact open-source via PuLP; no license, slow).
    """
    if solver == "local":
        return _solve_local_search(rg, k, seed=seed, verbose=verbose)
    if solver == "cbc":
        return _solve_cbc(rg, k, time_limit, verbose)
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "gurobipy is required for the baseline. Install with "
            "`pip install gurobipy` and activate a (free academic) license. "
            "See WORKFLOW.md for the open-source fallback."
        ) from e

    n = rg.n_super
    W = rg.W

    m = gp.Model("max_k_cut")
    m.Params.OutputFlag = 1 if verbose else 0
    m.Params.TimeLimit = time_limit
    m.Params.Seed = seed

    # x[i, l] = 1 if super-vertex i is in cluster l
    x = m.addVars(n, k, vtype=GRB.BINARY, name="x")
    m.addConstrs((x.sum(i, "*") == 1 for i in range(n)), name="assign")

    # objective: sum over i<j of w_ij * (1 - sum_l x_il x_jl)
    obj = gp.QuadExpr()
    for i in range(n):
        for j in range(i + 1, n):
            w = W[i, j]
            if w == 0:
                continue
            same = gp.quicksum(x[i, l] * x[j, l] for l in range(k))
            obj += w * (1 - same)
    m.setObjective(obj, GRB.MAXIMIZE)

    # Symmetry breaking: pin super-vertex 0 to cluster 0 (optional, speeds search)
    x[0, 0].LB = 1

    m.optimize()

    labels = np.array(
        [next(l for l in range(k) if x[i, l].X > 0.5) for i in range(n)]
    )
    return labels, m.ObjVal, m.MIPGap


def _cut_value(W: np.ndarray, labels: np.ndarray, k: int) -> float:
    """Total weight of edges crossing clusters = paper's BQO objective f."""
    total = W.sum() / 2.0
    intra = 0.0
    for l in range(k):
        idx = np.where(labels == l)[0]
        if idx.size > 1:
            intra += W[np.ix_(idx, idx)].sum() / 2.0
    return total - intra


@njit(cache=True)
def _ls_kernel(W, k, n_restarts, max_passes, kl_sweeps, seed):
    """Numba-compiled multi-start local search + Kernighan-Lin swaps.

    Maintains C[i, l] = total weight from vertex i into cluster l.

    Move (vertex relocation): for vertex v in cluster a, moving it to cluster b
      changes the cut by (C[v, a] - C[v, b]); pick b = argmin_l C[v, l].
    Swap (Kernighan-Lin): swapping u (in a) with w (in b, a != b) changes the cut
      by  (C[u,a]-C[u,b]) + (C[w,b]-C[w,a]) + 2*W[u,w].  This escapes local optima
      that single-vertex moves cannot (e.g. two clusters that would each like the
      other's member but neither can move alone without losing cut).
    Every accepted move/swap strictly increases the cut => convergence guaranteed;
    `max_passes`/`kl_sweeps` are safety caps. Many random restarts keep the best.
    """
    n = W.shape[0]
    np.random.seed(seed)
    total = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            total += W[i, j]

    best_cut = -1.0e18
    best_labels = np.zeros(n, dtype=np.int64)
    C = np.zeros((n, k))
    order = np.arange(n)

    for _r in range(n_restarts):
        labels = np.random.randint(0, k, n)
        C[:, :] = 0.0
        for i in range(n):
            for j in range(n):
                C[i, labels[j]] += W[i, j]

        improving = True
        rounds = 0
        while improving and rounds < max_passes:
            improving = False
            rounds += 1

            # ---- single-vertex relocation pass ----
            np.random.shuffle(order)
            for idx in range(n):
                v = order[idx]
                a = labels[v]
                bl = 0
                bv = C[v, 0]
                for l in range(1, k):
                    if C[v, l] < bv:
                        bv = C[v, l]; bl = l
                if bv < C[v, a] - 1e-9:
                    labels[v] = bl
                    for i in range(n):
                        C[i, a] -= W[i, v]
                        C[i, bl] += W[i, v]
                    improving = True

            # ---- Kernighan-Lin pairwise-swap passes (first improvement) ----
            for _s in range(kl_sweeps):
                swapped = False
                for u in range(n):
                    au = labels[u]
                    for w in range(u + 1, n):
                        aw = labels[w]
                        if au == aw:
                            continue
                        gain = ((C[u, au] - C[u, aw])
                                + (C[w, aw] - C[w, au])
                                + 2.0 * W[u, w])
                        if gain > 1e-9:
                            for i in range(n):
                                C[i, au] += W[i, w] - W[i, u]
                                C[i, aw] += W[i, u] - W[i, w]
                            labels[u] = aw
                            labels[w] = au
                            au = aw
                            swapped = True
                            improving = True
                if not swapped:
                    break

        # cut = total - intra ; intra = (1/2) sum_i C[i, labels[i]]
        s = 0.0
        for i in range(n):
            s += C[i, labels[i]]
        cut = total - s / 2.0
        if cut > best_cut:
            best_cut = cut
            best_labels = labels.copy()

    return best_labels, best_cut


def _ls_numpy(W, k, n_restarts, max_passes, seed):
    """Pure-NumPy fallback (no Numba, no KL). Same relocation logic as the kernel."""
    n = W.shape[0]
    rng = np.random.default_rng(seed)
    best_labels, best_cut = None, -np.inf
    for _ in range(n_restarts):
        labels = rng.integers(0, k, size=n)
        onehot = np.zeros((n, k)); onehot[np.arange(n), labels] = 1.0
        C = W @ onehot
        for _pass in range(max_passes):
            moved = False
            for v in rng.permutation(n):
                a = labels[v]; b = int(np.argmin(C[v]))
                if C[v, b] < C[v, a] - 1e-9:
                    labels[v] = b; C[:, a] -= W[:, v]; C[:, b] += W[:, v]; moved = True
            if not moved:
                break
        cut = _cut_value(W, labels, k)
        if cut > best_cut:
            best_cut, best_labels = cut, labels.copy()
    return best_labels, best_cut


def _solve_local_search(rg: ReducedGraph, k: int,
                        n_restarts: int = config.LOCAL_RESTARTS,
                        max_passes: int = 100,
                        kl_sweeps: int = config.KL_SWEEPS,
                        seed: int = config.RANDOM_SEED,
                        verbose: bool = False):
    """From-scratch max-k-cut heuristic (Numba kernel + Kernighan-Lin).

    Returns (labels[n_super], cut, NaN). The cut equals the paper's BQO objective.
    Falls back to a slower pure-NumPy relocation-only search if Numba is absent.
    """
    W = np.ascontiguousarray(rg.W, dtype=np.float64)
    if _HAVE_NUMBA:
        labels, cut = _ls_kernel(W, k, n_restarts, max_passes, kl_sweeps, seed)
    else:
        labels, cut = _ls_numpy(W, k, n_restarts, max_passes, seed)

    _, labels = np.unique(labels, return_inverse=True)   # compact to 0..m-1
    labels = labels.astype(int)
    if verbose:
        engine = "numba+KL" if _HAVE_NUMBA else "numpy"
        print(f"  local-search ({engine}): k={k} cut={cut:,.0f} "
              f"restarts={n_restarts} clusters={np.bincount(labels).tolist()}")
    return labels, float(cut), float("nan")


def _solve_cbc(rg: ReducedGraph, k: int, time_limit: int, verbose: bool):
    """Open-source fallback: linearized max-k-cut via PuLP + CBC (no license).

    Linearization of the bilinear term x_il*x_jl with y_ijl >= 0:
        y <= x_il,  y <= x_jl,  y >= x_il + x_jl - 1.
    Objective: max  sum_ij w_ij (1 - sum_l y_ijl).
    NOTE: CBC is far slower than Gurobi on this NP-hard model; intended for
    small instances / demonstration, or when a Gurobi license is unavailable.
    """
    import pulp

    n = rg.n_super
    W = rg.W
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if W[i, j] > 0]

    prob = pulp.LpProblem("max_k_cut", pulp.LpMaximize)
    x = {(i, l): pulp.LpVariable(f"x_{i}_{l}", cat="Binary")
         for i in range(n) for l in range(k)}
    y = {(i, j, l): pulp.LpVariable(f"y_{i}_{j}_{l}", lowBound=0, upBound=1)
         for (i, j) in edges for l in range(k)}

    for i in range(n):
        prob += pulp.lpSum(x[i, l] for l in range(k)) == 1
    for (i, j) in edges:
        for l in range(k):
            prob += y[i, j, l] <= x[i, l]
            prob += y[i, j, l] <= x[j, l]
            prob += y[i, j, l] >= x[i, l] + x[j, l] - 1
    x[0, 0].setInitialValue(1); x[0, 0].fixValue()  # symmetry breaking

    const = sum(W[i, j] for (i, j) in edges)
    same = pulp.lpSum(W[i, j] * y[i, j, l] for (i, j) in edges for l in range(k))
    prob += const - same

    prob.solve(pulp.PULP_CBC_CMD(msg=verbose, timeLimit=time_limit))
    labels = np.array(
        [next(l for l in range(k) if x[i, l].value() and x[i, l].value() > 0.5)
         for i in range(n)]
    )
    obj = pulp.value(prob.objective)
    gap = float("nan")  # CBC gap not surfaced here
    return labels, obj, gap


if __name__ == "__main__":
    from .data_loader import get_clean
    from .rfm import compute_raw, add_scores, score_matrix
    vars_ = config.RFM_VARS
    sm = score_matrix(add_scores(compute_raw(get_clean()), vars_), vars_)
    from .graph import reduce_graph
    rg = reduce_graph(sm)
    labels, obj, gap = solve_maxkcut(rg, k=4, verbose=True)
    print(f"k=4  obj={obj:,.0f}  gap={gap:.4f}  clusters={np.bincount(labels)}")
