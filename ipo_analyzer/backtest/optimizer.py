"""贝叶斯优化器：GP + EI 搜索最优五维权重"""
import logging
import math
import numpy as np
from numpy.linalg import cholesky, solve

from .engine import run_backtest
from .metrics import compute_objective, compute_objective_cv
from .models import OptimizationResult

logger = logging.getLogger(__name__)

WEIGHT_KEYS = ["trade", "fundamental", "valuation", "theme", "data_quality"]
N_DIM = len(WEIGHT_KEYS)


def _lhs_sample(n, dim, lower=0.05, upper=0.80):
    """Latin Hypercube Sampling"""
    samples = np.zeros((n, dim))
    rng = np.random.default_rng(42)
    for d in range(dim):
        cut = np.linspace(0, 1, n + 1)
        for i in range(n):
            samples[i, d] = lower + (upper - lower) * rng.uniform(cut[i], cut[i + 1])
    for i in range(n):
        rng.shuffle(samples[i])
    return samples


def _normalize_weights(raw_dict):
    """将原始值归一化为和为1的权重向量"""
    vals = np.array([raw_dict[k] for k in WEIGHT_KEYS], dtype=float)
    total = vals.sum()
    if total < 1e-9:
        vals = np.ones(N_DIM) / N_DIM
    else:
        vals = vals / total
    return {k: float(v) for k, v in zip(WEIGHT_KEYS, vals)}


def _weights_to_array(weights):
    return np.array([weights[k] for k in WEIGHT_KEYS])


def _array_to_weights(arr):
    return {k: float(arr[i]) for i, k in enumerate(WEIGHT_KEYS)}


def _rbf_kernel(x1, x2, length_scale=1.0, signal_variance=1.0):
    """RBF (squared exponential) kernel"""
    sqdist = np.sum(x1**2, axis=1).reshape(-1, 1) + np.sum(x2**2, axis=1) - 2 * np.dot(x1, x2.T)
    return signal_variance * np.exp(-0.5 * sqdist / length_scale**2)


def _evaluate_weights(dataset, weights, use_cv, qualify_threshold):
    """评估一组权重的目标函数值"""
    if use_cv:
        return compute_objective_cv(dataset, weights, qualify_threshold)
    result = run_backtest(dataset, weights, qualify_threshold)
    return compute_objective(result)


def optimize_weights(
    dataset,
    initial_samples=20,
    iterations=30,
    use_cv=True,
    qualify_threshold=50,
    default_weights=None,
):
    """贝叶斯优化搜索最优五维权重"""
    if default_weights is None:
        default_weights = {
            "trade": 0.25, "fundamental": 0.35,
            "valuation": 0.25, "theme": 0.10, "data_quality": 0.05,
        }

    np.random.seed(42)

    logger.info("贝叶斯优化：LHS 初始采样 %d 组权重", initial_samples)
    raw_samples = _lhs_sample(initial_samples, N_DIM, 0.05, 0.80)
    X = []
    y = []
    for i in range(initial_samples):
        raw = {WEIGHT_KEYS[d]: float(raw_samples[i, d]) for d in range(N_DIM)}
        w = _normalize_weights(raw)
        obj = _evaluate_weights(dataset, w, use_cv, qualify_threshold)
        X.append(_weights_to_array(w))
        y.append(obj)

    X = np.array(X)
    y = np.array(y)

    best_idx = int(np.argmax(y))
    best_weights = _array_to_weights(X[best_idx])
    best_obj = float(y[best_idx])
    convergence = [[int(0), best_obj]]

    logger.info("贝叶斯优化：开始 %d 轮迭代", iterations)
    for iteration in range(iterations):
        n_eval = len(X)
        length_scale = max(0.1, 1.0 / math.sqrt(n_eval))
        K = _rbf_kernel(X, X, length_scale=length_scale, signal_variance=1.0)
        K += np.eye(n_eval) * 1e-6

        try:
            L = cholesky(K)
        except np.linalg.LinAlgError:
            K += np.eye(n_eval) * 1e-4
            L = cholesky(K)

        alpha = solve(L.T, solve(L, y))

        y_mean = float(y.mean())
        y_std = float(y.std())
        if y_std < 1e-9:
            y_std = 1.0
        y_norm = (y - y_mean) / y_std

        n_candidates = 500
        candidates = _lhs_sample(n_candidates, N_DIM, 0.05, 0.80)
        candidate_weights = []
        for i in range(n_candidates):
            raw = {WEIGHT_KEYS[d]: float(candidates[i, d]) for d in range(N_DIM)}
            candidate_weights.append(_normalize_weights(raw))

        best_y = float(np.max(y_norm))
        ei_values = np.zeros(n_candidates)

        for i in range(n_candidates):
            w_arr = _weights_to_array(candidate_weights[i]).reshape(1, -1)
            k_star = _rbf_kernel(w_arr, X, length_scale=length_scale, signal_variance=1.0)
            k_star_star = _rbf_kernel(w_arr, w_arr, length_scale=length_scale, signal_variance=1.0)

            v = solve(L, k_star.T)
            mu = np.dot(k_star, alpha).item()
            mu = mu * y_std + y_mean
            sigma2 = (k_star_star - np.dot(v.T, v)).item()
            sigma2 = max(sigma2, 1e-8)
            sigma = math.sqrt(sigma2) * y_std

            if sigma < 1e-8:
                ei_values[i] = 0.0
            else:
                z = (mu - best_y * y_std - y_mean) / sigma if sigma > 1e-6 else 0.0
                from math import erf
                sqrt2 = math.sqrt(2.0)
                cdf_z = 0.5 * (1.0 + erf(z / sqrt2))
                phi_z = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * z * z)
                ei_values[i] = sigma * (z * cdf_z + phi_z)

        next_idx = int(np.argmax(ei_values))
        next_weights = candidate_weights[next_idx]

        obj = _evaluate_weights(dataset, next_weights, use_cv, qualify_threshold)

        X = np.vstack([X, _weights_to_array(next_weights).reshape(1, -1)])
        y = np.append(y, obj)

        if obj > best_obj:
            best_obj = float(obj)
            best_weights = dict(next_weights)
            logger.info("  迭代 %d: 新最优 objective=%.4f, weights=%s",
                        iteration + 1, best_obj, best_weights)

        convergence.append([int(initial_samples + iteration + 1), best_obj])

    default_obj = _evaluate_weights(dataset, default_weights, use_cv, qualify_threshold)
    cv_objective = best_obj if use_cv else 0.0
    improvement = 0.0
    if abs(default_obj) > 1e-9:
        improvement = (best_obj - default_obj) / abs(default_obj) * 100

    return OptimizationResult(
        weights=best_weights,
        objective=best_obj,
        default_objective=default_obj,
        improvement_pct=round(improvement, 2),
        convergence=convergence,
        cv_objective=cv_objective,
        sample_count=len(dataset),
    )
