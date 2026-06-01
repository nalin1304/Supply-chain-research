"""Resilience metrics computation for supply chain simulation.

Computes Time-To-Survive (TTS), Time-To-Recover (TTR), and
additional resilience indicators from DES simulation results.

TTS / TTR definitions from:
Sheffi & Rice (2005). A Supply Chain View of the Resilient Enterprise.
MIT Sloan Management Review, 47(1), 41-48.

TTR normalized variant (TTR_n = TTR / shock_magnitude) from:
Hosseini et al. (2019). Review of quantitative methods for supply chain
resilience analysis. Transportation Research Part E, 125, 285-307.
DOI: 10.1016/j.tre.2019.03.001
"""

import numpy as np


class ResilienceMetrics:
    """Compute resilience metrics from simulation service level data.

    Metrics:
        TTS: Time system maintains >90% service level after shock.
        TTR: Time from shock end until >95% pre-shock baseline.
        Max drop: Maximum service level decline during shock.
        Cumulative lost demand: Total unfulfilled orders during event.
        Recovery trajectory: Daily service level post-shock.

    Parameters
    ----------
    service_level_threshold : float, optional
        TTS threshold (default 0.90).
    recovery_threshold : float, optional
        TTR recovery fraction of the pre-shock baseline
        (default 0.95).

    Attributes
    ----------
    service_level_threshold, recovery_threshold : float
        Stored thresholds (see Parameters).
    """

    def __init__(
        self,
        service_level_threshold=0.90,
        recovery_threshold=0.95,
    ):
        """Initialize metrics calculator.

        Args:
            service_level_threshold: TTS threshold (default 0.90).
            recovery_threshold: TTR recovery fraction of pre-shock
                baseline (default 0.95).
        """
        self.service_level_threshold = service_level_threshold
        self.recovery_threshold = recovery_threshold

    def compute_tts(
        self,
        daily_service_level,
        shock_start_day,
    ):
        """Compute Time-To-Survive.

        TTS is the number of consecutive days after shock start
        that the system maintains service level above the threshold.

        Definition follows Sheffi & Rice (2005), MIT Sloan Management
        Review, 47(1), 41-48.

        Args:
            daily_service_level: Array of daily service levels
                (post-warmup).
            shock_start_day: Day the shock begins (post-warmup index).

        Returns:
            TTS in days. 0 if service level drops immediately.
        """
        sl = np.asarray(daily_service_level)
        if shock_start_day >= len(sl):
            return 0

        tts = 0
        for day_idx in range(shock_start_day, len(sl)):
            if sl[day_idx] >= self.service_level_threshold:
                tts += 1
            else:
                break

        return tts

    def compute_ttr(
        self,
        daily_service_level,
        shock_end_day,
        pre_shock_baseline=None,
    ):
        """Compute Time-To-Recover.

        TTR is the time from shock end until service level returns
        to >95% of the pre-shock baseline.

        Definition follows Sheffi & Rice (2005), MIT Sloan Management
        Review, 47(1), 41-48.

        Args:
            daily_service_level: Array of daily service levels
                (post-warmup).
            shock_end_day: Day the shock ends (post-warmup index).
            pre_shock_baseline: Pre-shock average service level.
                If None, computed from data before shock.

        Returns:
            TTR in days. -1 if system never recovers within data.
        """
        sl = np.asarray(daily_service_level)

        if pre_shock_baseline is None:
            # Use mean of first portion as baseline
            baseline_end = min(shock_end_day, len(sl))
            if baseline_end > 0:
                pre_shock_baseline = float(np.mean(sl[:baseline_end]))
            else:
                pre_shock_baseline = 1.0

        recovery_target = pre_shock_baseline * self.recovery_threshold

        if shock_end_day >= len(sl):
            return -1

        ttr = 0
        for day_idx in range(shock_end_day, len(sl)):
            if sl[day_idx] >= recovery_target:
                return ttr
            ttr += 1

        return -1  # Never recovered

    def compute_ttr_normalized(self, ttr_days: float, shock_magnitude: float) -> float:
        """Compute normalized Time to Recovery.

        TTR_n = TTR / shock_magnitude, allowing comparison across shocks
        of different severities.

        Parameters
        ----------
        ttr_days : float
            Raw TTR in days.
        shock_magnitude : float
            For supply shock: fraction of capacity lost (e.g., 0.5 for 50% loss).
            For demand shock: excess demand fraction (e.g., 2.0 for 300% demand).

        Returns
        -------
        float
            Normalized TTR (days per unit shock magnitude).

        Raises
        ------
        ValueError
            If shock_magnitude is not positive.

        References
        ----------
        .. [1] Hosseini et al. (2019). Review of quantitative methods for
               supply chain resilience analysis. Transportation Research
               Part E, 125, 285-307. DOI: 10.1016/j.tre.2019.03.001
        """
        if shock_magnitude <= 0:
            raise ValueError(f"shock_magnitude must be positive; got {shock_magnitude}")
        return ttr_days / shock_magnitude

    def compute_max_drop(
        self,
        daily_service_level,
        shock_start_day,
        shock_end_day,
    ):
        """Compute maximum service level drop during shock period.

        Args:
            daily_service_level: Array of daily service levels.
            shock_start_day: Shock start day index.
            shock_end_day: Shock end day index.

        Returns:
            Maximum service level drop (positive value).
        """
        sl = np.asarray(daily_service_level)

        # Pre-shock baseline
        if shock_start_day > 0:
            baseline = float(np.mean(sl[:shock_start_day]))
        else:
            baseline = 1.0

        # Find minimum during shock
        end_idx = min(shock_end_day + 1, len(sl))
        start_idx = min(shock_start_day, len(sl))
        if start_idx >= end_idx:
            return 0.0

        shock_period = sl[start_idx:end_idx]
        if len(shock_period) == 0:
            return 0.0

        min_sl = float(np.min(shock_period))
        return max(0.0, baseline - min_sl)

    def compute_cumulative_lost_demand(
        self,
        daily_orders,
        daily_fulfilled,
        shock_start_day,
        shock_end_day,
    ):
        """Compute total unfulfilled demand during shock period.

        Args:
            daily_orders: Array of daily order counts.
            daily_fulfilled: Array of daily fulfilled counts.
            shock_start_day: Shock start day index.
            shock_end_day: Shock end day index.

        Returns:
            Total unfulfilled orders during shock.
        """
        orders = np.asarray(daily_orders)
        fulfilled = np.asarray(daily_fulfilled)

        end_idx = min(shock_end_day + 1, len(orders))
        start_idx = min(shock_start_day, len(orders))

        if start_idx >= end_idx:
            return 0

        period_orders = orders[start_idx:end_idx]
        period_fulfilled = fulfilled[start_idx:end_idx]

        lost = np.sum(period_orders) - np.sum(period_fulfilled)
        return max(0, int(lost))

    def compute_recovery_trajectory(
        self,
        daily_service_level,
        shock_end_day,
        window=30,
    ):
        """Extract recovery trajectory after shock ends.

        Args:
            daily_service_level: Array of daily service levels.
            shock_end_day: Day the shock ends.
            window: Number of days to track after shock.

        Returns:
            Array of service levels for the recovery period.
        """
        sl = np.asarray(daily_service_level)
        end_idx = min(shock_end_day + window, len(sl))
        start_idx = min(shock_end_day, len(sl))

        if start_idx >= len(sl):
            return np.array([])

        return sl[start_idx:end_idx].copy()

    def compute_all(
        self,
        results,
        shock_start_day,
        shock_end_day,
    ):
        """Compute all resilience metrics for a simulation run.

        Args:
            results: Dictionary from DESEnvironment.run() containing
                daily_service_level, daily_orders, daily_fulfilled.
            shock_start_day: Shock start day (post-warmup).
            shock_end_day: Shock end day (post-warmup).

        Returns:
            Dictionary with all resilience metrics.
        """
        sl = results["daily_service_level"]
        orders = results["daily_orders"]
        fulfilled = results["daily_fulfilled"]
        costs = results.get("daily_costs", np.array([]))

        # Pre-shock baseline
        if shock_start_day > 0:
            pre_shock_sl = float(np.mean(sl[:shock_start_day]))
            normal_daily_cost = float(np.mean(costs[:shock_start_day])) if len(costs) > 0 else 10000.0
        else:
            pre_shock_sl = 1.0
            normal_daily_cost = float(np.mean(costs)) if len(costs) > 0 else 10000.0

        tts = self.compute_tts(sl, shock_start_day)
        ttr = self.compute_ttr(sl, shock_end_day, pre_shock_sl)
        max_drop = self.compute_max_drop(
            sl, shock_start_day, shock_end_day
        )
        lost_demand = self.compute_cumulative_lost_demand(
            orders, fulfilled, shock_start_day, shock_end_day
        )
        recovery = self.compute_recovery_trajectory(sl, shock_end_day)

        # 1. Network Resilience Index (NRI)
        nri = float(np.sum(sl[shock_start_day:]) / (len(sl[shock_start_day:]) * pre_shock_sl)) if pre_shock_sl > 0 and len(sl[shock_start_day:]) > 0 else 1.0

        # 2. Economic Resilience (Rose 2004)
        total_cost = float(results.get("total_cost", 0.0))
        normal_cost = normal_daily_cost * len(costs)
        if len(costs) > 0:
            economic_resilience = float(normal_cost / max(1.0, total_cost))
        else:
            economic_resilience = 1.0

        # 3. Adaptive Capacity
        adaptive_capacity = float(max_drop / ttr) if ttr > 0 else (1.0 if ttr == 0 else 0.0)

        # 4. Vulnerability Index (Chopra & Sodhi 2004)
        vulnerability_index = float(max_drop / pre_shock_sl) if pre_shock_sl > 0 else 0.0

        # 5. Robustness Coefficient (Vlajic et al. 2012)
        robustness_coefficient = float(1.0 - max_drop / pre_shock_sl) if pre_shock_sl > 0 else 1.0

        # 6. Recovery Cost Ratio
        recovery_cost = max(0.0, total_cost - normal_cost)
        damage_cost = max(1.0, float(lost_demand * 100.0))
        recovery_cost_ratio = float(recovery_cost / damage_cost)

        return {
            "tts": tts,
            "ttr": ttr,
            "max_service_level_drop": max_drop,
            "cumulative_lost_demand": lost_demand,
            "pre_shock_service_level": pre_shock_sl,
            "recovery_trajectory": recovery,
            "shock_start_day": shock_start_day,
            "shock_end_day": shock_end_day,
            "network_resilience_index": nri,
            "economic_resilience": economic_resilience,
            "adaptive_capacity": adaptive_capacity,
            "vulnerability_index": vulnerability_index,
            "robustness_coefficient": robustness_coefficient,
            "recovery_cost_ratio": recovery_cost_ratio,
        }


def conover_percentile_ci(
    sorted_data: np.ndarray,
    p: float = 0.95,
    confidence: float = 0.95,
) -> tuple:
    """Nonparametric CI on the p-th percentile via order statistics
    (Conover 1999, Practical Nonparametric Statistics, 3rd ed., §3.4).

    Returns (lower, upper) order-statistic indices' values forming a
    distribution-free CI for the p-th percentile of the population.

    Parameters
    ----------
    sorted_data : np.ndarray
        Already-sorted (ascending) sample.
    p : float
        Percentile of interest (default 0.95).
    confidence : float
        Confidence level (default 0.95).

    Returns
    -------
    tuple of (point_estimate, lower_bound, upper_bound).
    """
    from scipy.stats import binom
    n = len(sorted_data)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    point = float(np.percentile(sorted_data, 100 * p, method="lower"))
    if n < 5:
        return point, point, point

    alpha = 1.0 - confidence
    # Find lower order index l such that P(Bin(n, p) < l) <= alpha/2
    # and upper index u such that P(Bin(n, p) >= u) <= alpha/2.
    lower_idx = int(binom.ppf(alpha / 2, n, p))
    upper_idx = int(binom.ppf(1 - alpha / 2, n, p)) + 1
    lower_idx = max(0, lower_idx - 1)
    upper_idx = min(n - 1, upper_idx)
    return point, float(sorted_data[lower_idx]), float(sorted_data[upper_idx])


def report_ttr_summary(ttr_values: np.ndarray) -> dict:
    """Audit 1.8: report mean + 95th-percentile TTR with Conover CI.

    Parameters
    ----------
    ttr_values : np.ndarray
        Per-run TTR values (negative values indicate non-recovery and
        are excluded from the percentile but counted in the recovery
        fraction).

    Returns
    -------
    dict with keys: n_runs, n_recovered, recovered_fraction,
                    ttr_mean, ttr_std, ttr_p95, ttr_p95_ci_low,
                    ttr_p95_ci_high.
    """
    arr = np.asarray(ttr_values, dtype=float)
    n_runs = len(arr)
    recovered = arr[arr >= 0]
    n_rec = len(recovered)
    if n_rec == 0:
        return {
            "n_runs": int(n_runs),
            "n_recovered": 0,
            "recovered_fraction": 0.0,
            "ttr_mean": float("nan"),
            "ttr_std": float("nan"),
            "ttr_p95": float("nan"),
            "ttr_p95_ci_low": float("nan"),
            "ttr_p95_ci_high": float("nan"),
        }
    sorted_rec = np.sort(recovered)
    p95, ci_lo, ci_hi = conover_percentile_ci(sorted_rec, p=0.95)
    return {
        "n_runs": int(n_runs),
        "n_recovered": int(n_rec),
        "recovered_fraction": float(n_rec / n_runs),
        "ttr_mean": float(np.mean(recovered)),
        "ttr_std": float(np.std(recovered)),
        "ttr_p95": float(p95),
        "ttr_p95_ci_low": float(ci_lo),
        "ttr_p95_ci_high": float(ci_hi),
    }
