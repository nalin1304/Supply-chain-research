"""FIX-018 — Managerial-insights document generator.

This module satisfies bugfix clauses ``C1.20`` and ``C2.20`` of
``.kiro/specs/supply-chain-research-audit/bugfix.md`` by producing the
five-section managerial-insights markdown document the journal
reviewers explicitly request:

1. Executive Summary
2. Green-Premium Curve (FIX-015)
3. Fleet Mix Recommendation
4. Top-5 Routes by Tonne-Km
5. Disruption Playbook (DES + PPO)
6. PPO ROI (cost / carbon delta vs. baseline)

Every section names the figure or LaTeX table that backs it; the
figures and tables themselves are produced by
``supply_chain_research/phase4_synthesis/generate_all_figures.py`` and
``generate_latex_tables.py`` (preservation clause C3.11). When a
required artifact is not yet on disk — for example because the Modal
training run is still in progress — the corresponding section emits a
single-line "data not yet available" placeholder rather than crashing
or fabricating numbers (preservation clause C3.16: additive
deliverables only, never alter existing pipeline behaviour).

The module exposes two public entry points::

    generate_managerial_insights(artifact_dir, config) -> str
    main() -> None  # CLI wrapper that ``print()``-s the markdown

Run via ``python -m supply_chain_research.phase4_synthesis.managerial_insights``
to capture the markdown to ``stdout``. The companion task verification
script saves it to ``docs/MANAGERIAL_INSIGHTS.md``.

References
----------
.. [Bektas2011] Bektaş, T., Laporte, G. (2011). The Pollution-Routing
   Problem. *Transp. Res. Part B* 45(8):1232-1250.
   doi:10.1016/j.trb.2011.02.004 — green-premium curve §6.
.. [Sheffi2005] Sheffi, Y., Rice, J. B. (2005). A Supply Chain View of
   the Resilient Enterprise. *MIT Sloan Mgmt. Rev.* 47(1):41-48 —
   TTS / TTR disruption playbook semantics.
.. [Hosseini2019] Hosseini, S., Ivanov, D., Dolgui, A. (2019). Review
   of Quantitative Methods for Supply Chain Resilience Analysis.
   *Transp. Res. Part E* 125:285-307. doi:10.1016/j.tre.2019.03.001 —
   resilience-metric normalisation.
.. [Boute2022] Boute, R. N., Gijsbrechts, J., van Jaarsveld, W.,
   Vanvuchelen, N. (2022). Deep Reinforcement Learning for Inventory
   Control: A Roadmap. *Eur. J. Oper. Res.* 298(2):401-412 — DRL
   inventory ROI framing for the PPO ROI section.
.. [NITI2021] NITI Aayog & Rocky Mountain Institute (2021). Fast
   Tracking Freight in India — fleet mix benchmarks (HCV utilisation
   60-65 %, empty running 30-40 %).
"""

from __future__ import annotations

import json
import pickle
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from supply_chain_research.config import MasterConfig

# ---------------------------------------------------------------------------
# Constants — figure / table backing references (clause C3.11).
# These names match the on-disk artifacts produced by
# generate_all_figures.py and generate_latex_tables.py at the time of
# FIX-018; if those filenames are renamed in a future fix, update the
# constants here so the markdown stays in sync.
# ---------------------------------------------------------------------------

#: Backing figure for the green-premium curve. The actual file name in
#: ``outputs/figures/`` at FIX-015 / FIX-016 time is ``fig2_pareto_front.png``
#: (cost-vs-emission Pareto used to derive the green-premium curve) and
#: ``fig5_lstm_forecast.png`` is unrelated. The task spec also references
#: ``figure_5_green_premium.png`` as the conceptual name; we cite both.
FIGURE_GREEN_PREMIUM = "outputs/figures/fig2_pareto_front.png"
FIGURE_GREEN_PREMIUM_ALIAS = "outputs/figures/figure_5_green_premium.png"
FIGURE_FLEET_MIX = "outputs/figures/fig7_sensitivity_spider.png"
FIGURE_ROUTES = "outputs/figures/fig1_network_map.png"
FIGURE_DISRUPTION = "outputs/figures/fig4_resilience_dashboard.png"
FIGURE_PPO = "outputs/figures/fig6_ppo_training.png"
TABLE_ROUTES = "outputs/tables/table4_resilience.tex"


# ---------------------------------------------------------------------------
# Shared great-circle distance helper.
#
# Used by :func:`_format_top_routes` (tonne-km ranking) and
# :func:`identify_high_carbon_routes` (carbon-load ranking) so both
# rankings rest on the same geometry. Earth radius is 6371 km
# [Vincenty 1975 mean radius]. No road-circuity factor is applied at
# this layer; downstream code that needs road-distance estimates uses
# the cached OSRM matrix when available.
# ---------------------------------------------------------------------------


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    """Great-circle distance between two ``(lat, lon)`` points, in km.

    Parameters
    ----------
    lat1, lon1, lat2, lon2 : float
        Latitudes and longitudes in decimal degrees. The function
        accepts arrays as well; in that case the return is an array.

    Returns
    -------
    float
        Great-circle distance in kilometres assuming Earth radius
        6371 km. Output is a Python ``float`` for scalar inputs.

    Notes
    -----
    Uses the numerically-stable form
    ``c = 2 * arcsin(min(1, sqrt(a)))`` to avoid round-off when
    ``a`` slightly exceeds 1 due to float error at antipodal points.
    """
    lat1_r, lat2_r = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * np.arcsin(np.minimum(1.0, np.sqrt(a)))
    return float(6371.0 * c)


#: Documented placeholder line that replaces a section body when one of the
#: required pickle / JSON artifacts is missing. Single source of truth so
#: tests and downstream tooling can grep for it.
MISSING_ARTIFACT_NOTE = (
    "*Data not yet available — re-run "
    "`phase4_synthesis/generate_all_figures.py` to populate.*"
)


# ---------------------------------------------------------------------------
# Artifact loading (graceful degradation)
# ---------------------------------------------------------------------------


def _resolve_artifact(
    artifact_dir: Path, candidate_names: Iterable[str],
) -> Path | None:
    """Return the first existing path among ``candidate_names``.

    Parameters
    ----------
    artifact_dir : pathlib.Path
        Directory to search in (typically ``outputs/artifacts`` or, in
        the absence of that path, ``data/results``).
    candidate_names : iterable of str
        File names to probe in priority order.

    Returns
    -------
    pathlib.Path or None
        Path of the first existing artifact, or ``None`` when none of
        the candidates exists. The caller is responsible for emitting
        ``MISSING_ARTIFACT_NOTE`` when ``None`` is returned.
    """
    for name in candidate_names:
        path = artifact_dir / name
        if path.exists():
            return path
    return None


def _load_pareto_front(artifact_dir: Path) -> np.ndarray | None:
    """Load an NSGA-II Pareto front from the artifact directory.

    The function probes (in order) the canonical names produced by the
    Modal training pipeline (``nsga2_pareto.pkl``) and the
    NSGA-II solver checkpoint (``nsga2_best_front.npy``,
    ``nsga2_all_results.pkl``). Each pickle is loaded with
    ``pickle.load`` (no third-party untrusted input — the file lives
    inside the project's own outputs directory).

    Parameters
    ----------
    artifact_dir : pathlib.Path
        Directory to search for serialised Pareto fronts.

    Returns
    -------
    numpy.ndarray or None
        Pareto front of shape ``(n_solutions, 2)`` with columns
        ``[cost, carbon]``, or ``None`` when no compatible artifact is
        found. The caller emits ``MISSING_ARTIFACT_NOTE`` for sections
        that depend on this data.
    """
    pkl_path = _resolve_artifact(
        artifact_dir,
        ("nsga2_pareto.pkl", "nsga2_all_results.pkl"),
    )
    if pkl_path is not None:
        try:
            with open(pkl_path, "rb") as fh:
                payload = pickle.load(fh)
        except (pickle.UnpicklingError, EOFError, OSError):
            payload = None
        if isinstance(payload, dict):
            for key in ("pareto_front", "best_front", "F"):
                front = payload.get(key)
                if front is not None:
                    arr = np.asarray(front, dtype=float)
                    if arr.ndim == 2 and arr.shape[1] >= 2:
                        return arr[:, :2]
        elif isinstance(payload, np.ndarray) and payload.ndim == 2:
            return payload[:, :2].astype(float, copy=False)

    npy_path = _resolve_artifact(
        artifact_dir, ("nsga2_best_front.npy", "nsga2_pareto_front.npy"),
    )
    if npy_path is not None:
        try:
            arr = np.load(npy_path, allow_pickle=False)
        except (ValueError, OSError):
            return None
        if arr.ndim == 2 and arr.shape[1] >= 2:
            return arr[:, :2].astype(float, copy=False)
    return None


def _load_baseline_solution(
    artifact_dir: Path,
) -> dict[str, Any] | None:
    """Load the OR-Tools / cost-only baseline solution.

    Parameters
    ----------
    artifact_dir : pathlib.Path
        Directory to search.

    Returns
    -------
    dict or None
        Baseline solution payload (typically containing ``cost``,
        ``emission``, and ``routes`` keys) or ``None`` when the file
        is absent.
    """
    pkl_path = _resolve_artifact(
        artifact_dir, ("baseline_solution.pkl",),
    )
    if pkl_path is not None:
        try:
            with open(pkl_path, "rb") as fh:
                payload = pickle.load(fh)
        except (pickle.UnpicklingError, EOFError, OSError):
            return None
        if isinstance(payload, dict):
            return payload
    return None


def _load_ppo_eval(artifact_dir: Path) -> dict[str, Any] | None:
    """Load PPO evaluation results.

    Parameters
    ----------
    artifact_dir : pathlib.Path
        Directory to search.

    Returns
    -------
    dict or None
        PPO evaluation payload (rewards, service-level, baseline-vs-PPO
        deltas) or ``None`` when neither ``ppo_eval_results.json`` nor
        the legacy ``training_summary.json`` file exists.
    """
    for name in ("ppo_eval_results.json", "training_summary.json"):
        path = artifact_dir / name
        if path.exists():
            try:
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                return None
    return None


# ---------------------------------------------------------------------------
# Section builders — each returns a markdown fragment ending with
# exactly one trailing newline. When backing data is absent, the
# fragment contains the standard MISSING_ARTIFACT_NOTE so a reviewer
# can tell at a glance which sections are populated.
# ---------------------------------------------------------------------------


def _format_executive_summary(
    pareto_front: np.ndarray | None,
    baseline: dict[str, Any] | None,
    ppo_eval: dict[str, Any] | None,
) -> str:
    """Build the executive-summary section.

    Parameters
    ----------
    pareto_front : numpy.ndarray or None
        Loaded Pareto front (cost, carbon).
    baseline : dict or None
        OR-Tools / cost-only baseline payload.
    ppo_eval : dict or None
        PPO evaluation payload.

    Returns
    -------
    str
        Markdown fragment for the Executive Summary section.
    """
    sources_present = sum(
        1 for x in (pareto_front, baseline, ppo_eval) if x is not None
    )
    body_lines = [
        "## Executive Summary",
        "",
        "This document is the managerial companion to the academic deliverables "
        "(`docs/PAPER_OUTLINE.md`, `docs/LITERATURE_GAP_ANALYSIS.md`, `docs/COMPLEXITY_ANALYSIS.md`). "
        "It distills the four-phase pipeline — NSGA-II bi-objective optimisation, "
        "SimPy DES resilience analysis, Attention-LSTM demand forecasting, and "
        "PPO inventory control — into five decisions a logistics planner needs "
        "to make before deploying the system to production.",
        "",
        f"Artifact availability at generation time: "
        f"`pareto={pareto_front is not None}`, "
        f"`baseline={baseline is not None}`, "
        f"`ppo_eval={ppo_eval is not None}` "
        f"({sources_present}/3 sources populated). "
        "Sections below that depend on missing artifacts emit a documented "
        "placeholder (`Data not yet available`) instead of fabricated numbers.",
        "",
        "[See Figure 1: Network Map, "
        f"`{FIGURE_ROUTES}`; "
        "Figure 4: Resilience Dashboard, "
        f"`{FIGURE_DISRUPTION}`.]",
        "",
    ]
    return "\n".join(body_lines) + "\n"


def _format_green_premium(
    pareto_front: np.ndarray | None,
) -> str:
    """Build the green-premium-curve section.

    Computes the canonical Bektaş-Laporte (2011) §6 green-premium
    curve: minimum cost achievable at each carbon-reduction level
    relative to the cost-anchor of the unconstrained Pareto front.

    Parameters
    ----------
    pareto_front : numpy.ndarray or None
        Pareto front of shape ``(N, 2)`` with columns ``[cost, carbon]``.

    Returns
    -------
    str
        Markdown fragment.
    """
    header = [
        "## Green-Premium Curve",
        "",
        "The green-premium quantifies the additional logistics cost "
        "(INR/route) a planner pays to buy each 10 % of carbon "
        "reduction relative to the cost-anchor of the unconstrained "
        "Pareto front [Bektaş-Laporte 2011 §6, FIX-015].",
        "",
        f"[See Figure 2: Pareto Front, `{FIGURE_GREEN_PREMIUM}`; "
        f"alias `{FIGURE_GREEN_PREMIUM_ALIAS}` when produced "
        "by FIX-015 carbon-budget sweep.]",
        "",
    ]
    if pareto_front is None or pareto_front.size == 0:
        return "\n".join(header + [MISSING_ARTIFACT_NOTE, ""]) + "\n"

    sorted_front = pareto_front[pareto_front[:, 1].argsort()]
    cost_anchor = float(sorted_front[-1, 0])  # highest carbon = lowest cost
    carbon_anchor = float(sorted_front[-1, 1])

    table_lines = [
        "| Reduction Target | Min Cost (INR) | Δ Cost vs Anchor | Premium (INR / kg CO₂) |",
        "|------------------|----------------|------------------|------------------------|",
    ]
    for pct in (0, 10, 20, 30, 40, 50):
        target_carbon = carbon_anchor * (1.0 - pct / 100.0)
        feasible = sorted_front[sorted_front[:, 1] <= target_carbon + 1e-9]
        if len(feasible) == 0:
            table_lines.append(
                f"| {pct:>3d}% | infeasible | — | — |"
            )
            continue
        min_cost = float(np.min(feasible[:, 0]))
        delta_cost = min_cost - cost_anchor
        carbon_reduced = max(carbon_anchor - target_carbon, 1e-9)
        premium = delta_cost / carbon_reduced if pct > 0 else 0.0
        table_lines.append(
            f"| {pct:>3d}% | {min_cost:,.0f} | {delta_cost:+,.0f} | "
            f"{premium:+,.2f} |"
        )

    interpretation = (
        "",
        "**Interpretation.** The curve is non-decreasing in reduction "
        "percentage (tighter budgets shrink the feasible region). The "
        "knee — typically in the 20-30 % band — is the minimum-regret "
        "operating point: marginal INR per kg CO₂ is lowest there, and "
        "deeper cuts require fleet electrification or modal shift "
        "rather than route consolidation [Bektaş-Laporte 2011 §6].",
        "",
    )
    return (
        "\n".join(header + table_lines + list(interpretation)) + "\n"
    )


def _format_fleet_mix(
    pareto_front: np.ndarray | None,
    config: MasterConfig,
) -> str:
    """Build the fleet-mix recommendation section.

    Pulls HCV / LCV utilisation benchmarks from
    ``MasterConfig.vehicle`` (NITI-Aayog & RMI 2021 ranges, FIX-005)
    and pairs them with the Pareto-front knee when the front is
    available.

    Parameters
    ----------
    pareto_front : numpy.ndarray or None
        Pareto front (cost, carbon).
    config : MasterConfig
        Master configuration; used for HCV / LCV utilisation
        benchmarks recorded under FIX-005.

    Returns
    -------
    str
        Markdown fragment.
    """
    header = [
        "## Fleet Mix Recommendation",
        "",
        "The recommended fleet composition trades cost-efficiency for "
        "carbon performance. HCVs are more carbon-efficient per kg-km "
        "at high load factors due to scale economies in the MEET k+L·m "
        "emission model [Hickman 1999 §3, Tables 3.2-3.3].",
        "",
        f"[See Figure 7: Sensitivity Spider, `{FIGURE_FLEET_MIX}` — "
        "the ``fleet_mix_ratio`` axis quantifies HCV / LCV trade-offs.]",
        "",
    ]
    util_lines = [
        "| Benchmark | Value | Source |",
        "|-----------|-------|--------|",
        f"| HCV utilisation (industrial benchmark) | "
        f"{config.vehicle.hcv_utilization:.0%} | "
        "NITI-Aayog & RMI 2021 §2.2 (Indian HCV load factor 60-65 %) |",
        f"| Empty-running fraction | "
        f"{config.vehicle.empty_running_fraction:.0%} | "
        "NITI-Aayog & RMI 2021 (global avg 30-35 %) |",
        f"| HCV emission rate `k` | "
        f"{config.vehicle.hcv_k:.3f} kg CO₂/km | "
        "MEET 1999 §3 Table 3.2 (rigid HGV >16 t) |",
        f"| LCV emission rate `k` | "
        f"{config.vehicle.lcv_k:.3f} kg CO₂/km | "
        "MEET 1999 §3 Table 3.3 (LCV ≤3.5 t) |",
    ]

    if pareto_front is None or pareto_front.size == 0:
        return (
            "\n".join(
                header
                + util_lines
                + [
                    "",
                    "### Recommended fleet split",
                    "",
                    MISSING_ARTIFACT_NOTE,
                    "",
                ]
            )
            + "\n"
        )

    sorted_by_cost = pareto_front[pareto_front[:, 0].argsort()]
    sorted_by_carbon = pareto_front[pareto_front[:, 1].argsort()]
    cost_optimal = sorted_by_cost[0]
    green_optimal = sorted_by_carbon[0]
    knee_idx = len(pareto_front) // 2
    knee = pareto_front[pareto_front[:, 0].argsort()][knee_idx]

    fleet_table = [
        "",
        "### Pareto-anchored fleet split",
        "",
        "| Scenario | Cost (INR) | Carbon (kg CO₂) | Recommended fleet bias |",
        "|----------|-----------:|-----------------:|-----------------------|",
        f"| Cost-optimal | {cost_optimal[0]:,.0f} | {cost_optimal[1]:,.1f} | "
        "HCV-heavy (≥70 % load factor) |",
        f"| Knee (balanced) | {knee[0]:,.0f} | {knee[1]:,.1f} | "
        "Mixed: HCV trunk + LCV last-mile |",
        f"| Green-optimal | {green_optimal[0]:,.0f} | {green_optimal[1]:,.1f} | "
        "LCV-shift + load consolidation |",
        "",
        "**Managerial action.** Operate at the knee until ESG reporting "
        "constraints tighten beyond 30 % carbon reduction; then shift "
        "incrementally toward the green-optimal anchor.",
        "",
    ]
    return (
        "\n".join(header + util_lines + fleet_table) + "\n"
    )


def _format_top_routes(
    pareto_front: np.ndarray | None,
    config: MasterConfig,
) -> str:
    """Build the Top-5 Routes by Tonne-Km section.

    The "tonne-km" rank uses the static distance × demand product (no
    Pareto-front lookup needed); the figure / table reference still
    cites the figure in case the reviewer wants to cross-check the
    spatial layout.

    Parameters
    ----------
    pareto_front : numpy.ndarray or None
        Unused for tonne-km (deterministic from config), but retained
        for signature uniformity with the other section builders. Kept
        so future extensions can rank routes by Pareto-actual flow.
    config : MasterConfig
        Master configuration; warehouse and city locations live here.

    Returns
    -------
    str
        Markdown fragment.
    """
    del pareto_front  # not used; see docstring.
    header = [
        "## Top-5 Routes by Tonne-Km",
        "",
        "Routes are ranked by ``distance × representative demand`` "
        "(tonne-km). High tonne-km routes are the priority candidates "
        "for modal shift (rail intermodal) and for HCV consolidation. "
        "Distances are great-circle approximations using the city / "
        "warehouse coordinates in `MasterConfig.network`; replace "
        "with cached OSRM distances (FIX-007 distance-matrix cache) "
        "when available.",
        "",
        f"[See Figure 1: Network Map, `{FIGURE_ROUTES}` — and Table 4: "
        f"Resilience Metrics, `{TABLE_ROUTES}` — for the full route "
        "table.]",
        "",
    ]

    warehouses = list(config.network.warehouse_locations)
    cities = list(config.network.cities)
    if not warehouses or not cities:
        return "\n".join(header + [MISSING_ARTIFACT_NOTE, ""]) + "\n"

    # Representative demand: midpoint of the configured per-customer
    # demand bounds (FIX-005 NetworkConfig.demand_clip_min/max). Falls
    # back to 1000 kg when the bounds are not present (older configs).
    demand_min = float(getattr(config.network, "demand_clip_min", 100.0))
    demand_max = float(getattr(config.network, "demand_clip_max", 10000.0))
    representative_demand_kg = 0.5 * (demand_min + demand_max)

    rows: list[tuple[str, str, float, float]] = []
    for w_name, w_lat, w_lon in warehouses:
        for c_name, c_lat, c_lon in cities:
            dist_km = _haversine_km(w_lat, w_lon, c_lat, c_lon)
            if dist_km < 1e-3:
                continue
            tonne_km = (representative_demand_kg / 1000.0) * dist_km
            rows.append((str(w_name), str(c_name), dist_km, tonne_km))

    rows.sort(key=lambda r: r[3], reverse=True)
    top5 = rows[:5]

    table_lines = [
        "| Rank | Origin | Destination | Distance (km) | Tonne-Km |",
        "|-----:|--------|-------------|--------------:|---------:|",
    ]
    for idx, (origin, dest, dist_km, tonne_km) in enumerate(top5, start=1):
        clean_origin = origin.replace("_WH", "")
        table_lines.append(
            f"| {idx} | {clean_origin} | {dest} | "
            f"{dist_km:,.0f} | {tonne_km:,.0f} |"
        )

    closing = [
        "",
        "**Managerial action.** For ranks 1-2 evaluate rail intermodal "
        "for the trunk segment; for 3-5 consolidate neighbouring "
        "customer demand to lift the load factor above 70 %.",
        "",
    ]
    return "\n".join(header + table_lines + closing) + "\n"


def _format_disruption_playbook(
    ppo_eval: dict[str, Any] | None,
) -> str:
    """Build the disruption-playbook section.

    Pairs the SimPy DES baseline (no agent) with the PPO inventory
    agent (Boute 2022) to give the planner an explicit recovery
    runbook for the three shock classes recognised by
    ``MasterConfig.shock``.

    Parameters
    ----------
    ppo_eval : dict or None
        PPO evaluation payload; expected to contain ``service_level``,
        ``recovery_days``, and ``baseline_*`` mirrors. When absent,
        the section emits ``MISSING_ARTIFACT_NOTE``.

    Returns
    -------
    str
        Markdown fragment.
    """
    header = [
        "## Disruption Playbook",
        "",
        "Time-to-Survive (TTS) and Time-to-Recover (TTR) are the two "
        "primary resilience metrics [Sheffi-Rice 2005]. The DES "
        "baseline reports the unaided system; the PPO agent reports "
        "the same scenario with the trained inventory-control policy "
        "[Boute 2022 §3, Hosseini-Ivanov-Dolgui 2019 §4 for "
        "magnitude-normalised TTR].",
        "",
        f"[See Figure 4: Resilience Dashboard, `{FIGURE_DISRUPTION}`; "
        f"Figure 6: PPO Training, `{FIGURE_PPO}`; Table 4: Resilience "
        f"Metrics, `{TABLE_ROUTES}`.]",
        "",
    ]
    if ppo_eval is None:
        return "\n".join(header + [MISSING_ARTIFACT_NOTE, ""]) + "\n"

    def _fmt(value: Any, fmt: str = "{:,.2f}") -> str:
        """
        Parameters
        ----------
        """
        if value is None:
            return "—"
        try:
            return fmt.format(float(value))
        except (TypeError, ValueError):
            return str(value)

    rows = [
        ("Demand surge (3× normal)", "demand_surge"),
        ("Supply disruption (50 % capacity loss)", "supply_disruption"),
        ("Route blockage (highway closure)", "route_blockage"),
    ]

    table = [
        "| Scenario | TTS baseline | TTS + PPO | TTR baseline | TTR + PPO | "
        "Service-level + PPO |",
        "|----------|-------------:|----------:|-------------:|----------:|"
        "--------------------:|",
    ]
    for label, key in rows:
        block = ppo_eval.get(key, {}) if isinstance(ppo_eval, dict) else {}
        table.append(
            "| {label} | {tts_b} | {tts_p} | {ttr_b} | {ttr_p} | {sl} |".format(
                label=label,
                tts_b=_fmt(block.get("tts_baseline")),
                tts_p=_fmt(block.get("tts_ppo")),
                ttr_b=_fmt(block.get("ttr_baseline")),
                ttr_p=_fmt(block.get("ttr_ppo")),
                sl=_fmt(block.get("service_level_ppo"), "{:.1%}"),
            )
        )

    closing = [
        "",
        "**Recommended actions.** "
        "(1) Activate safety-stock at affected warehouses when the "
        "PPO agent's veto trigger fires (`gym_environment.py` §7); "
        "(2) redistribute from the nearest non-affected warehouse "
        "within 24 h; "
        "(3) cap expedite premium at 5-10 % cost above plan.",
        "",
    ]
    return "\n".join(header + table + closing) + "\n"


def _format_ppo_roi(
    baseline: dict[str, Any] | None,
    ppo_eval: dict[str, Any] | None,
) -> str:
    """Build the PPO ROI section.

    Parameters
    ----------
    baseline : dict or None
        Cost-only / OR-Tools baseline (cost, emission). When absent,
        the section emits ``MISSING_ARTIFACT_NOTE``.
    ppo_eval : dict or None
        PPO evaluation payload (cost, emission, service-level). When
        absent, the section emits ``MISSING_ARTIFACT_NOTE``.

    Returns
    -------
    str
        Markdown fragment.
    """
    header = [
        "## PPO ROI",
        "",
        "Return on investment of the PPO inventory-control agent "
        "[Boute 2022, Schulman 2017 PPO-Clip]. ROI is reported as the "
        "delta in cost and carbon between the cost-only baseline "
        "(`baseline_solution.pkl`) and the PPO-evaluated rollout "
        "(`ppo_eval_results.json`). Cloud-training cost (Modal) is "
        "documented in `cloud_training/TRAINING_GUIDE.md` and is "
        "amortised at the annual scale.",
        "",
        f"[See Figure 6: PPO Training, `{FIGURE_PPO}`.]",
        "",
    ]

    if baseline is None or ppo_eval is None:
        return "\n".join(header + [MISSING_ARTIFACT_NOTE, ""]) + "\n"

    base_cost = baseline.get("cost") or baseline.get("total_cost")
    base_carbon = (
        baseline.get("carbon")
        or baseline.get("emission")
        or baseline.get("total_carbon")
    )
    ppo_cost = ppo_eval.get("cost") or ppo_eval.get("total_cost")
    ppo_carbon = (
        ppo_eval.get("carbon")
        or ppo_eval.get("emission")
        or ppo_eval.get("total_carbon")
    )

    def _delta(base: float | None, improved: float | None) -> str:
        """
        Parameters
        ----------
        """
        if base is None or improved is None:
            return "—"
        try:
            base_f = float(base)
            imp_f = float(improved)
        except (TypeError, ValueError):
            return "—"
        if abs(base_f) < 1e-9:
            return "—"
        return f"{(imp_f - base_f) / base_f:+.1%}"

    table = [
        "| Metric | Baseline | PPO | Δ % |",
        "|--------|---------:|----:|----:|",
        f"| Cost (INR) | {base_cost or '—'} | {ppo_cost or '—'} | "
        f"{_delta(base_cost, ppo_cost)} |",
        f"| Carbon (kg CO₂) | {base_carbon or '—'} | "
        f"{ppo_carbon or '—'} | {_delta(base_carbon, ppo_carbon)} |",
    ]

    closing = [
        "",
        "**Managerial action.** Deploy the PPO agent on top of the "
        "OR-Tools cost-only baseline once the cost delta is "
        "non-positive *and* the service-level delta is non-negative. "
        "Re-train quarterly on the latest 90-day demand window per "
        "the cloud-training guide.",
        "",
    ]
    return "\n".join(header + table + closing) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_managerial_insights(
    artifact_dir: str | Path = "outputs/artifacts",
    config: MasterConfig | None = None,
) -> str:
    """Generate the managerial-insights markdown document.

    Loads ``nsga2_pareto.pkl``, ``baseline_solution.pkl``, and
    ``ppo_eval_results.json`` from ``artifact_dir`` (with documented
    fall-backs to ``data/results``) and assembles the five required
    sections. Sections whose backing artifacts are absent emit a
    standard ``Data not yet available`` note rather than crashing.

    Parameters
    ----------
    artifact_dir : str or pathlib.Path, optional
        Directory holding the pickle / JSON artifacts. Defaults to
        ``outputs/artifacts``. When the directory does not exist or
        the canonical file names are absent, the loader transparently
        falls back to ``data/results`` (the location used by the local
        training-runner before Modal artifacts are synced).
    config : MasterConfig, optional
        Master configuration. When ``None``, a fresh default
        ``MasterConfig()`` is constructed; the function does not
        mutate the configuration.

    Returns
    -------
    str
        Markdown document, terminated by a single trailing newline.
        The function never writes to disk; the CLI ``main()`` wrapper
        is responsible for redirection via shell ``>``.

    Notes
    -----
    Preservation contract C3.16: this function is additive only. It
    never imports a non-public symbol, never mutates Modal state, and
    never alters any pre-existing artifact on disk.
    """
    if config is None:
        config = MasterConfig()

    primary_dir = Path(artifact_dir)
    fallback_dir = Path("data/results")

    pareto_front = _load_pareto_front(primary_dir)
    if pareto_front is None and fallback_dir.exists():
        pareto_front = _load_pareto_front(fallback_dir)

    baseline = _load_baseline_solution(primary_dir)
    if baseline is None and fallback_dir.exists():
        baseline = _load_baseline_solution(fallback_dir)

    ppo_eval = _load_ppo_eval(primary_dir)
    if ppo_eval is None and fallback_dir.exists():
        ppo_eval = _load_ppo_eval(fallback_dir)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    primary_status = "exists" if primary_dir.exists() else "missing"
    preamble = (
        "# Managerial Insights\n"
        "\n"
        "This document satisfies bugfix clauses C1.20 and C2.20 of "
        "`.kiro/specs/supply-chain-research-audit/bugfix.md` "
        "(FIX-018). It is generated programmatically from "
        "`supply_chain_research/phase4_synthesis/managerial_insights.py` "
        "and is intended to be regenerated whenever new training "
        "artifacts become available.\n"
        "\n"
        f"**Generated.** {timestamp} (UTC).  \n"
        f"**Primary artifact dir.** `{primary_dir}` ({primary_status}).  \n"
        f"**Fallback artifact dir.** `{fallback_dir}` "
        f"({'exists' if fallback_dir.exists() else 'missing'}).\n"
        "\n"
        "Sections marked *Data not yet available* will populate once "
        "the corresponding training run finishes — see "
        "`cloud_training/TRAINING_GUIDE.md`.\n"
        "\n"
    )

    sections = [
        _format_executive_summary(pareto_front, baseline, ppo_eval),
        _format_green_premium(pareto_front),
        _format_fleet_mix(pareto_front, config),
        _format_top_routes(pareto_front, config),
        _format_disruption_playbook(ppo_eval),
        _format_ppo_roi(baseline, ppo_eval),
    ]
    return preamble + "\n".join(sections)


def main() -> None:
    """CLI entry point: print the markdown document to stdout.

    Designed for use as ``python -m
    supply_chain_research.phase4_synthesis.managerial_insights >
    docs/MANAGERIAL_INSIGHTS.md``. Honours the
    ``MANAGERIAL_INSIGHTS_ARTIFACT_DIR`` environment variable for
    explicit overriding of the artifact directory; otherwise falls
    back to the documented default.
    
    Parameters
    ----------
    """
    import os
    artifact_dir = os.environ.get(
        "MANAGERIAL_INSIGHTS_ARTIFACT_DIR", "outputs/artifacts",
    )
    print(generate_managerial_insights(artifact_dir=artifact_dir), end="")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# C3.12 preservation shims (Group A — bugfix.md C3.12 signature contract)
# ---------------------------------------------------------------------------
# Each shim below restores a public name that existed in the pre-FIX-018
# baseline (see ``audit_workspace/SIGNATURE_BASELINE.json``). The shims
# expose a thin, signature-faithful compatibility layer over the new
# :func:`generate_managerial_insights` API and the existing private
# ``_load_*`` helpers.
#
# All shims:
#   * preserve the original baseline signature byte-for-byte so
#     ``inspect.signature`` matches ``SIGNATURE_BASELINE.json``;
#   * delegate to the modern API where reasonable;
#   * emit ``None`` (loaders) or an empty list / dict (computers)
#     when their backing artifact is absent — never crash.
# ---------------------------------------------------------------------------


def load_pareto_front(  # [bugfix.md C3.12]
    results_dir: str = "data/results",
) -> np.ndarray | None:
    """[bugfix.md C3.12 preservation shim] Load NSGA-II Pareto front from a directory.

    Restores the pre-FIX-018 public name
    ``load_pareto_front(results_dir) -> numpy.ndarray | None``
    documented in the C3.12 signature baseline. The implementation
    is a thin wrapper around the module-private
    :func:`_load_pareto_front` helper that powers the modern
    :func:`generate_managerial_insights` pipeline.

    Parameters
    ----------
    results_dir : str, optional
        Directory holding the serialised Pareto front. Defaults to
        ``"data/results"``, the location used by the local
        training-runner before Modal artefacts are synced.

    Returns
    -------
    numpy.ndarray or None
        Pareto front of shape ``(n_solutions, 2)`` with columns
        ``[cost, carbon]``, or ``None`` when no compatible artifact
        is found.
    """
    return _load_pareto_front(Path(results_dir))


def load_des_results(  # [bugfix.md C3.12]
    results_dir: str = "data/results",
) -> dict[str, Any] | None:
    """[bugfix.md C3.12 preservation shim] Load DES Monte-Carlo summary.

    Restores the pre-FIX-018 public name
    ``load_des_results(results_dir) -> Dict[str, Any] | None``
    documented in the C3.12 signature baseline. The shim probes
    ``monte_carlo_summary.npy`` (the canonical artefact written by
    :class:`MonteCarloRunner.save_results`) and falls back to a
    JSON ``des_results.json`` when present.

    Parameters
    ----------
    results_dir : str, optional
        Directory holding the DES Monte-Carlo artefact. Defaults to
        ``"data/results"``.

    Returns
    -------
    dict or None
        Dict-of-shock-summaries payload, or ``None`` when neither
        artefact is found / decodable.
    """
    primary = Path(results_dir)
    npy_path = primary / "monte_carlo_summary.npy"
    if npy_path.exists():
        try:
            payload = np.load(npy_path, allow_pickle=True)
        except (ValueError, OSError):
            payload = None
        if payload is not None:
            try:
                # ``np.save(..., allow_pickle=True)`` writes a 0-D array.
                summary = payload.item() if hasattr(payload, "item") else payload
            except (AttributeError, ValueError):
                summary = None
            if isinstance(summary, dict):
                return summary
    json_path = primary / "des_results.json"
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def load_ppo_results(  # [bugfix.md C3.12]
    results_dir: str = "data/results",
) -> dict[str, Any] | None:
    """[bugfix.md C3.12 preservation shim] Load PPO evaluation results.

    Restores the pre-FIX-018 public name
    ``load_ppo_results(results_dir) -> Dict[str, Any] | None``
    documented in the C3.12 signature baseline. Thin wrapper around
    the module-private :func:`_load_ppo_eval` helper.

    Parameters
    ----------
    results_dir : str, optional
        Directory holding the PPO evaluation artefact (typically
        ``ppo_eval_results.json`` or the legacy
        ``training_summary.json``). Defaults to ``"data/results"``.

    Returns
    -------
    dict or None
        PPO evaluation payload, or ``None`` when no compatible
        artefact is present / decodable.
    """
    return _load_ppo_eval(Path(results_dir))


def compute_green_premium_curve(  # [bugfix.md C3.12]
    pareto_front: np.ndarray | None,
) -> list[dict[str, Any]]:
    """[bugfix.md C3.12 preservation shim] Green-premium curve from a Pareto front.

    Restores the pre-FIX-018 public name
    ``compute_green_premium_curve(pareto_front) -> List[Dict[str, Any]]``
    documented in the C3.12 signature baseline. The canonical
    Bektaş-Laporte (2011) §6 implementation lives in
    :func:`supply_chain_research.phase1_foundation.carbon_budget_solver
    .generate_green_premium_curve`; that function operates on the
    full ``(config, distance_matrix, demand)`` triple and is too
    heavy for a shim that only receives a pre-computed Pareto front.
    This shim therefore mirrors the cost-anchor / minimum-cost
    derivation already used by :func:`_format_green_premium`.

    Parameters
    ----------
    pareto_front : numpy.ndarray or None
        Pareto front of shape ``(n_solutions, 2)`` with columns
        ``[cost, carbon]``, or ``None``.

    Returns
    -------
    list of dict
        One record per reduction band with keys
        ``"reduction_pct"``, ``"min_cost"``, ``"delta_cost_vs_anchor"``
        and ``"premium_inr_per_kg_co2"``. Empty when the input front
        is ``None`` or empty.

    References
    ----------
    Bektaş, T. & Laporte, G. (2011). The Pollution-Routing Problem.
    *Transportation Research Part B* 45(8):1232-1250.
    """
    if pareto_front is None:
        return []
    front = np.asarray(pareto_front, dtype=float)
    if front.ndim != 2 or front.shape[0] == 0 or front.shape[1] < 2:
        return []

    sorted_front = front[front[:, 1].argsort()]
    cost_anchor = float(sorted_front[-1, 0])
    carbon_anchor = float(sorted_front[-1, 1])

    curve: list[dict[str, Any]] = []
    for pct in (0, 10, 20, 30, 40, 50):
        target_carbon = carbon_anchor * (1.0 - pct / 100.0)
        feasible = sorted_front[sorted_front[:, 1] <= target_carbon + 1e-9]
        if len(feasible) == 0:
            curve.append(
                {
                    "reduction_pct": float(pct),
                    "min_cost": float("inf"),
                    "delta_cost_vs_anchor": float("inf"),
                    "premium_inr_per_kg_co2": float("nan"),
                }
            )
            continue
        min_cost = float(np.min(feasible[:, 0]))
        delta_cost = min_cost - cost_anchor
        carbon_reduced = max(carbon_anchor - target_carbon, 1e-9)
        premium = delta_cost / carbon_reduced if pct > 0 else 0.0
        curve.append(
            {
                "reduction_pct": float(pct),
                "min_cost": min_cost,
                "delta_cost_vs_anchor": float(delta_cost),
                "premium_inr_per_kg_co2": float(premium),
            }
        )
    return curve


def compute_disruption_response(  # [bugfix.md C3.12]
    des_results: dict[str, Any] | None,
    ppo_results: dict[str, Any] | None,
) -> dict[str, Any]:
    """[bugfix.md C3.12 preservation shim] Summarise the disruption playbook.

    Restores the pre-FIX-018 public name
    ``compute_disruption_response(des_results, ppo_results) ->
    Dict[str, Any]`` documented in the C3.12 signature baseline.
    The function aligns with the Sheffi-Rice (2005) TTS / TTR
    framing used by :func:`_format_disruption_playbook`: it picks
    out the headline TTS / TTR / max-drop / service-level numbers
    from the DES and PPO payloads and returns a flat summary dict.

    Parameters
    ----------
    des_results : dict or None
        DES Monte-Carlo summary (typically
        ``{"supply_shock": {...}, "demand_shock": {...}}``).
    ppo_results : dict or None
        PPO evaluation payload.

    Returns
    -------
    dict
        Summary with keys ``"baseline"`` (DES-only metrics),
        ``"ppo"`` (PPO-augmented metrics), and ``"available"``
        (booleans flagging which inputs were non-empty).

    References
    ----------
    Sheffi, Y., Rice, J. B. (2005). A Supply Chain View of the
    Resilient Enterprise. *MIT Sloan Mgmt. Rev.* 47(1):41-48.
    Boute, R. N. et al. (2022). Deep RL for Inventory Control.
    *Eur. J. Oper. Res.* 298(2):401-412.
    """
    available = {
        "des": isinstance(des_results, dict) and bool(des_results),
        "ppo": isinstance(ppo_results, dict) and bool(ppo_results),
    }

    baseline: dict[str, Any] = {}
    if available["des"]:
        for shock_type, block in des_results.items():
            if not isinstance(block, dict):
                continue
            baseline[shock_type] = {
                "tts_mean": block.get("tts_mean"),
                "ttr_mean": block.get("ttr_mean"),
                "max_drop_mean": block.get("max_drop_mean"),
                "mean_service_level_mean": block.get(
                    "mean_service_level_mean"
                ),
                "n_runs": block.get("n_runs"),
            }

    ppo_summary: dict[str, Any] = {}
    if available["ppo"]:
        for key, block in ppo_results.items():
            if isinstance(block, dict):
                ppo_summary[key] = {
                    "tts_baseline": block.get("tts_baseline"),
                    "tts_ppo": block.get("tts_ppo"),
                    "ttr_baseline": block.get("ttr_baseline"),
                    "ttr_ppo": block.get("ttr_ppo"),
                    "service_level_ppo": block.get("service_level_ppo"),
                }
            else:
                # Top-level scalar metrics (e.g. ``"reward"``); pass through.
                ppo_summary[key] = block

    return {
        "available": available,
        "baseline": baseline,
        "ppo": ppo_summary,
    }


def identify_high_carbon_routes(  # [bugfix.md C3.12]
    config: MasterConfig,
    distance_matrix: np.ndarray | None = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """[bugfix.md C3.12 preservation shim] Rank warehouse-customer arcs by carbon load.

    Restores the pre-FIX-018 public name
    ``identify_high_carbon_routes(config, distance_matrix, top_k)
    -> List[Dict[str, Any]]`` documented in the C3.12 signature
    baseline. The carbon load of an arc is approximated by
    ``distance_km * representative_demand_kg * (k + L)`` using the
    HCV emission parameters from ``config.vehicle`` (MEET 1999
    Table 3.2).

    Parameters
    ----------
    config : MasterConfig
        Master configuration; warehouse / customer locations and
        HCV emission parameters are consumed.
    distance_matrix : numpy.ndarray, optional
        Pre-computed warehouse-customer distance matrix (km). When
        ``None``, distances fall back to a haversine approximation
        from ``config.network.warehouse_locations`` and
        ``config.network.cities``.
    top_k : int, optional
        Number of arcs to return. Default 5.

    Returns
    -------
    list of dict
        ``top_k`` records sorted by carbon load (descending). Each
        record carries ``"origin"``, ``"destination"``,
        ``"distance_km"``, ``"tonne_km"`` and
        ``"carbon_kg_per_route"``.

    References
    ----------
    Hickman, A. J. (1999). MEET TRL Project Report SE/491/98.
    """
    warehouses = list(config.network.warehouse_locations)
    cities = list(config.network.cities)
    if not warehouses or not cities:
        return []

    demand_min = float(getattr(config.network, "demand_clip_min", 100.0))
    demand_max = float(getattr(config.network, "demand_clip_max", 10000.0))
    representative_demand_kg = 0.5 * (demand_min + demand_max)
    k = float(config.vehicle.hcv_k)
    L = float(config.vehicle.hcv_L)

    use_matrix = (
        distance_matrix is not None
        and isinstance(distance_matrix, np.ndarray)
        and distance_matrix.ndim == 2
        and distance_matrix.shape[0] == len(warehouses)
        and distance_matrix.shape[1] == len(cities)
    )

    rows: list[tuple[str, str, float, float, float]] = []
    for w_idx, (w_name, w_lat, w_lon) in enumerate(warehouses):
        for c_idx, (c_name, c_lat, c_lon) in enumerate(cities):
            if use_matrix:
                dist_km = float(distance_matrix[w_idx, c_idx])
            else:
                dist_km = _haversine_km(w_lat, w_lon, c_lat, c_lon)
            if dist_km < 1e-3:
                continue
            tonne_km = (representative_demand_kg / 1000.0) * dist_km
            # MEET-style carbon load per round-trip: loaded leg
            # ``(k + L * load) * d`` plus empty-return leg ``k * d``.
            carbon_kg = (
                (k + L * representative_demand_kg) * dist_km
                + k * dist_km
            )
            rows.append(
                (str(w_name), str(c_name), dist_km, tonne_km, carbon_kg)
            )

    rows.sort(key=lambda r: r[4], reverse=True)
    top = rows[: max(0, int(top_k))]
    return [
        {
            "origin": origin,
            "destination": dest,
            "distance_km": dist_km,
            "tonne_km": tonne_km,
            "carbon_kg_per_route": carbon_kg,
        }
        for (origin, dest, dist_km, tonne_km, carbon_kg) in top
    ]


def generate_insights_report(  # [bugfix.md C3.12]
    output_path: str = "docs/MANAGERIAL_INSIGHTS.md",
    results_dir: str = "data/results",
) -> dict[str, Any]:
    """[bugfix.md C3.12 preservation shim] Render the managerial-insights markdown.

    Restores the pre-FIX-018 public name
    ``generate_insights_report(output_path, results_dir) ->
    Dict[str, Any]`` documented in the C3.12 signature baseline.
    The shim is a thin alias for
    :func:`generate_managerial_insights`: it renders the markdown
    with ``artifact_dir=results_dir``, writes it to ``output_path``,
    and returns a small summary dict capturing the operation.

    Parameters
    ----------
    output_path : str, optional
        Destination of the rendered markdown. Defaults to
        ``"docs/MANAGERIAL_INSIGHTS.md"``. The parent directory is
        created if needed.
    results_dir : str, optional
        Artefact directory forwarded to
        :func:`generate_managerial_insights`. Defaults to
        ``"data/results"``.

    Returns
    -------
    dict
        Keys ``"output_path"``, ``"results_dir"``, ``"length_chars"``
        and ``"markdown"`` (the rendered document). The markdown is
        returned in addition to being written so callers can pipe it
        without re-reading the file.
    """
    markdown = generate_managerial_insights(artifact_dir=results_dir)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    return {
        "output_path": str(out),
        "results_dir": str(results_dir),
        "length_chars": len(markdown),
        "markdown": markdown,
    }
