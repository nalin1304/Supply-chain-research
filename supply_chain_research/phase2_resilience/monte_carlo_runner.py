"""Monte Carlo runner for resilience simulation.

Runs multiple DES simulations in parallel using joblib to
estimate resilience metric distributions under different
shock scenarios.
"""

from pathlib import Path

import numpy as np
from joblib import Parallel, delayed
from scipy.stats.qmc import LatinHypercube

from supply_chain_research.config import MasterConfig
from supply_chain_research.phase2_resilience.des_environment import (
    DESEnvironment,
)
from supply_chain_research.phase2_resilience.resilience_metrics import (
    ResilienceMetrics,
)
from supply_chain_research.phase2_resilience.shock_models import (
    DemandShock,
    SupplyShock,
)


def _run_single_supply_shock(
    job_id, config, distance_matrix, base_seed, lhs_params=None
):
    """Run single simulation with supply shock.
    Parameters
    ----------
    """
    seed = base_seed + job_id

    des = DESEnvironment(
        config=config,
        distance_matrix=distance_matrix,
        seed=seed,
    )

    # Use pre-sampled LHS params if available
    severity = lhs_params.get("severity") if lhs_params else None
    start_day = lhs_params.get("start_day") if lhs_params else None

    # Create and register supply shock
    shock = SupplyShock(
        warehouse_id=None,
        severity=severity,
        start_day=start_day,
        seed=seed + config.shock.supply_seed_offset,
        config=config,
    )
    des.add_shock(shock)

    # Run simulation
    results = des.run()

    # Compute resilience metrics
    metrics_calc = ResilienceMetrics()

    shock_start = (
        shock.shock_start
        if shock.shock_start is not None
        else config.shock.fallback_shock_start_day
    )
    shock_end = (
        shock.shock_end
        if shock.shock_end is not None
        else config.shock.fallback_shock_end_day
    )

    metrics = metrics_calc.compute_all(
        results, shock_start, shock_end
    )
    metrics["job_id"] = job_id
    metrics["seed"] = seed
    metrics["mean_service_level"] = results["mean_service_level"]
    metrics["total_cost"] = results["total_cost"]
    metrics["total_emissions"] = results["total_emissions"]

    return metrics


def _run_single_demand_shock(
    job_id, config, distance_matrix, base_seed, lhs_params=None
):
    """Run single simulation with demand shock.
    Parameters
    ----------
    """
    seed = base_seed + job_id

    des = DESEnvironment(
        config=config,
        distance_matrix=distance_matrix,
        seed=seed,
    )

    # Use pre-sampled LHS params if available
    multiplier = lhs_params.get("multiplier") if lhs_params else None
    start_day = lhs_params.get("start_day") if lhs_params else None

    # Create and register demand shock
    shock = DemandShock(
        customer_ids=None,
        multiplier=multiplier,
        start_day=start_day,
        seed=seed + config.shock.demand_seed_offset,
        config=config,
    )
    des.add_shock(shock)

    # Run simulation
    results = des.run()

    # Compute resilience metrics
    metrics_calc = ResilienceMetrics()

    shock_start = (
        shock.shock_start
        if shock.shock_start is not None
        else config.shock.fallback_shock_start_day
    )
    shock_end = (
        shock.shock_end
        if shock.shock_end is not None
        else config.shock.fallback_shock_end_day
    )

    metrics = metrics_calc.compute_all(
        results, shock_start, shock_end
    )
    metrics["job_id"] = job_id
    metrics["seed"] = seed
    metrics["mean_service_level"] = results["mean_service_level"]
    metrics["total_cost"] = results["total_cost"]
    metrics["total_emissions"] = results["total_emissions"]

    return metrics


class MonteCarloRunner:
    """Parallelized Monte Carlo runner for resilience analysis.
    Parameters
    ----------
    
            Parameters
            ----------
            config : type
                Description of config.
            n_runs : type
                Description of n_runs.
            n_jobs : type
                Description of n_jobs.
            base_seed : type
                Description of base_seed.
            distance_matrix : type
                Description of distance_matrix.
        """

    def __init__(
        self,
        config=None,
        n_runs=500,
        n_jobs=-1,
        base_seed=42,
        distance_matrix=None,
    ):
        """
        Parameters
        ----------
        """
        if config is None:
            config = MasterConfig()
        self.config = config
        if n_runs is None:
            n_runs = config.shock.monte_carlo_n_runs
        self.n_runs = n_runs
        self.n_jobs = n_jobs
        self.base_seed = base_seed
        self.distance_matrix = distance_matrix

    def _sample_lhs_supply(self):
        """Pre-sample start day and severity using Latin Hypercube Sampling.
        Parameters
        ----------
        """
        sampler = LatinHypercube(d=2, seed=self.base_seed)
        sample = sampler.random(n=self.n_runs)
        
        # Scale parameters
        # Severity: [0.1, 0.9]
        severities = 0.1 + sample[:, 0] * 0.8
        
        # Start Day: [offset, sim_days // 2]
        offset = self.config.shock.random_start_min_offset_days
        max_start = self.config.simulation.sim_days // 2
        start_days = (offset + sample[:, 1] * (max_start - offset)).astype(int)
        
        return [{"severity": float(s), "start_day": int(d)} for s, d in zip(severities, start_days)]

    def _sample_lhs_demand(self):
        """Pre-sample start day and multiplier using Latin Hypercube Sampling.
        Parameters
        ----------
        """
        sampler = LatinHypercube(d=2, seed=self.base_seed + 10)
        sample = sampler.random(n=self.n_runs)
        
        # Multiplier: [1.5, 5.0]
        multipliers = 1.5 + sample[:, 0] * 3.5
        
        # Start Day: [offset, sim_days // 2]
        offset = self.config.shock.random_start_min_offset_days
        max_start = self.config.simulation.sim_days // 2
        start_days = (offset + sample[:, 1] * (max_start - offset)).astype(int)
        
        return [{"multiplier": float(m), "start_day": int(d)} for m, d in zip(multipliers, start_days)]

    def run_supply_shock_analysis(self, lhs=True):
        """Run Monte Carlo analysis for supply shocks.
        Parameters
        ----------
        
                Parameters
                ----------
                lhs : type
                    Description of lhs.
            """
        lhs_params = self._sample_lhs_supply() if lhs else None
        
        results = Parallel(n_jobs=self.n_jobs)(
            delayed(_run_single_supply_shock)(
                job_id,
                self.config,
                self.distance_matrix,
                self.base_seed,
                lhs_params[job_id] if lhs_params else None
            )
            for job_id in range(self.n_runs)
        )

        return self._aggregate_results(results, "supply_shock")

    def run_demand_shock_analysis(self, lhs=True):
        """Run Monte Carlo analysis for demand shocks.
        Parameters
        ----------
        
                Parameters
                ----------
                lhs : type
                    Description of lhs.
            """
        lhs_params = self._sample_lhs_demand() if lhs else None
        
        results = Parallel(n_jobs=self.n_jobs)(
            delayed(_run_single_demand_shock)(
                job_id,
                self.config,
                self.distance_matrix,
                self.base_seed,
                lhs_params[job_id] if lhs_params else None
            )
            for job_id in range(self.n_runs)
        )

        return self._aggregate_results(results, "demand_shock")

    def run_all(self, lhs=True):
        """Run Monte Carlo analysis for all shock types.
        Parameters
        ----------
        
                Parameters
                ----------
                lhs : type
                    Description of lhs.
            """
        supply_results = self.run_supply_shock_analysis(lhs=lhs)
        demand_results = self.run_demand_shock_analysis(lhs=lhs)

        return {
            "supply_shock": supply_results,
            "demand_shock": demand_results,
        }

    def run_stress_testing_framework(self, severities=None, n_runs=10):
        """Run stress testing by sweeping shock severity from 0.1 to 1.0.
        Parameters
        ----------
        
                Parameters
                ----------
                severities : type
                    Description of severities.
                n_runs : type
                    Description of n_runs.
            """
        if severities is None:
            severities = np.linspace(0.1, 1.0, 10)
        
        stress_results = {}
        for sev in severities:
            # Create a localized config override
            cfg = self.config.model_copy(deep=True)
            cfg.shock.supply_severity = float(sev)
            
            # Run a small Monte Carlo slice at this severity
            runner = MonteCarloRunner(
                config=cfg,
                n_runs=n_runs,
                n_jobs=self.n_jobs,
                base_seed=self.base_seed,
                distance_matrix=self.distance_matrix
            )
            res = runner.run_supply_shock_analysis(lhs=False)
            stress_results[float(sev)] = {
                "mean_service_level": res["mean_service_level_mean"],
                "max_drop": res["max_drop_mean"],
                "ttr_mean": res["ttr_mean"],
                "nri_mean": float(np.mean([r["network_resilience_index"] for r in res["raw_results"]]))
            }
        return stress_results

    def _aggregate_results(self, run_results, shock_type):
        """Aggregate results and perform convergence diagnostics.
        Parameters
        ----------
        """
        tts_values = []
        ttr_values = []
        max_drops = []
        lost_demands = []
        mean_sls = []

        for r in run_results:
            tts_values.append(r["tts"])
            ttr_val = r["ttr"]
            if ttr_val >= 0:
                ttr_values.append(ttr_val)
            max_drops.append(r["max_service_level_drop"])
            lost_demands.append(r["cumulative_lost_demand"])
            mean_sls.append(r["mean_service_level"])

        tts_arr = np.array(tts_values)
        ttr_arr = np.array(ttr_values) if ttr_values else np.array([0])
        drops_arr = np.array(max_drops)
        lost_arr = np.array(lost_demands)
        sl_arr = np.array(mean_sls)

        # Convergence diagnostics: check running mean of service level
        running_means = np.cumsum(sl_arr) / (np.arange(len(sl_arr)) + 1)
        # Check stability on the last 10% of iterations compared to previous 10%
        n = len(running_means)
        if n >= 20:
            last_10 = running_means[-int(n * 0.1):]
            prev_10 = running_means[-int(n * 0.2):-int(n * 0.1)]
            mean_diff = float(np.abs(np.mean(last_10) - np.mean(prev_10)))
            converged = bool(mean_diff < 1e-3)
        else:
            mean_diff = 0.0
            converged = True

        return {
            "shock_type": shock_type,
            "n_runs": len(run_results),
            "tts_mean": float(np.mean(tts_arr)),
            "tts_std": float(np.std(tts_arr)),
            "ttr_mean": float(np.mean(ttr_arr)),
            "ttr_std": float(np.std(ttr_arr)),
            "ttr_recovered_fraction": (
                len(ttr_values) / len(run_results)
                if run_results else 0.0
            ),
            "max_drop_mean": float(np.mean(drops_arr)),
            "max_drop_std": float(np.std(drops_arr)),
            "lost_demand_mean": float(np.mean(lost_arr)),
            "lost_demand_std": float(np.std(lost_arr)),
            "mean_service_level_mean": float(np.mean(sl_arr)),
            "mean_service_level_std": float(np.std(sl_arr)),
            "convergence_diagnostics": {
                "running_means": running_means.tolist(),
                "mean_diff": mean_diff,
                "converged": converged
            },
            "raw_results": run_results,
        }

    def save_results(self, results, output_dir="data/results"):
        """
        Parameters
        ----------
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        summary = {}
        for shock_type, shock_results in results.items():
            summary[shock_type] = {
                k: v for k, v in shock_results.items()
                if k != "raw_results"
            }

        np.save(
            str(output_path / "monte_carlo_summary.npy"),
            summary,
            allow_pickle=True,
        )

        for shock_type, shock_results in results.items():
            raw = shock_results["raw_results"]
            tts_arr = np.array([r["tts"] for r in raw])
            ttr_arr = np.array([r["ttr"] for r in raw])
            np.save(
                str(output_path / f"{shock_type}_tts.npy"), tts_arr
            )
            np.save(
                str(output_path / f"{shock_type}_ttr.npy"), ttr_arr
            )
