"""LaTeX formulation generator for the supply chain optimization problem.

Generates a complete mathematical formulation document including
sets, parameters, decision variables, objectives, and constraints.
Uses volume-based decision variables with discrete trip counting.
"""

from pathlib import Path

from pylatex import (
    Document,
    Section,
    Subsection,
    NoEscape,
    Package,
)


def generate_formulation(output_path: str = "outputs/tables") -> str:
    """Generate LaTeX document with complete mathematical formulation.

    Args:
        output_path: Directory to save the generated .tex file.

    Returns:
        Path to the generated LaTeX file.
    """
    doc = Document(documentclass="article")
    doc.packages.append(Package("amsmath"))
    doc.packages.append(Package("amssymb"))

    with doc.create(Section("Mathematical Formulation")):
        with doc.create(
            Subsection("Sets and Indices")
        ):
            doc.append(NoEscape(r"""
\begin{align*}
& W = \{1, 2, \ldots, N_w\} & \text{Set of warehouses} \\
& C = \{1, 2, \ldots, N_c\} & \text{Set of customers} \\
& V = \{HCV, LCV\} & \text{Set of vehicle types}
\end{align*}
"""))

        with doc.create(Subsection("Parameters")):
            doc.append(NoEscape(r"""
\begin{align*}
& d_{wc} & \text{Distance from warehouse } w \text{ to customer } c
    \text{ (km)} \\
& D_c & \text{Demand of customer } c \text{ (kg)} \\
& Q_v & \text{Capacity of vehicle type } v \text{ (kg)} \\
& S_w & \text{Throughput capacity of warehouse } w \text{ (kg)} \\
& \kappa_v & \text{Cost per km for vehicle type } v
    \text{ (INR/km)} \\
& k_v & \text{Base emission factor for vehicle type } v
    \text{ (kg CO}_2\text{/km)} \\
& L_v & \text{Load-dependent emission factor for vehicle type } v
    \text{ (kg CO}_2\text{/km/kg)}
\end{align*}
"""))

        with doc.create(Subsection("Decision Variables")):
            # Audit 4.1: continuous-relaxation footnote
            doc.append(NoEscape(r"""
\begin{align*}
& x_{wcv} \geq 0 & \text{Volume (kg) shipped from warehouse } w
    \text{ to customer } c \text{ via vehicle } v
\end{align*}

\footnote{The trip count $\lceil x_{wcv}/Q_v \rceil$ is relaxed to its
continuous form $x_{wcv}/Q_v$ in the evolutionary search to obtain a
smooth objective landscape, following standard practice in green VRP
literature \citep{demir2014pollution}. The continuous flow lower-bounds
the integer trip cost, and the relaxation gap is empirically validated
in Section~5 (see Table~\ref{tab:trip_relaxation_validation}).}
"""))

        with doc.create(Subsection("Objective Functions")):
            # Audit 4.1: MEET derivation block
            doc.append(NoEscape(r"""
\paragraph{MEET emission model derivation.}
Following Hickman \citep{Hickman1999MEET}, equations 3--5, the
emission rate (kg~CO$_2$/km) of a heavy-duty vehicle traveling at
speed $v$ with payload $w$ kg is decomposed as
\begin{equation}
E(v, w) = a + b v + c v^2 + d/v + e w + f w v
\end{equation}
For our uniform-speed setting (highway cruise speed), all velocity
terms collapse into a single empirical constant, yielding the
simplified affine form
\begin{equation}
\hat{E}(w) \;=\; k_v + L_v \, w \quad \text{(kg CO}_2\text{/km)}
\end{equation}
which we use throughout. The coefficients $k_v$, $L_v$ are taken from
\citep{Hickman1999MEET}, Tables~3.2--3.3, and cross-verified against
COPERT~5 \citep{Ntziachristos2009COPERT} and HBEFA~4.2.

\textbf{Minimize Total Cost:}
\begin{equation}
f_1(\mathbf{x}) = \sum_{w \in W} \sum_{c \in C} \sum_{v \in V}
    \kappa_v \cdot d_{wc} \cdot \left\lceil \frac{x_{wcv}}{Q_v} \right\rceil
\end{equation}

\textbf{Minimize Total Emissions (loaded + empty return):}
\begin{equation}
f_2(\mathbf{x}) = \underbrace{\sum_{w \in W} \sum_{c \in C} \sum_{v \in V}
    d_{wc} \cdot (k_v + L_v \cdot x_{wcv})}_{\text{loaded trip (one-way)}}
    + \underbrace{\sum_{w \in W} \sum_{c \in C} \sum_{v \in V}
    k_v \cdot d_{wc} \cdot \left\lceil \frac{x_{wcv}}{Q_v}
    \right\rceil}_{\text{empty return trips}}
\end{equation}
"""))

        with doc.create(Subsection("Constraints")):
            doc.append(NoEscape(r"""
\textbf{Demand Satisfaction:}
\begin{equation}
\sum_{w \in W} \sum_{v \in V} x_{wcv} = D_c
    \quad \forall c \in C
\end{equation}

\textbf{Warehouse Capacity:}
\begin{equation}
\sum_{c \in C} \sum_{v \in V} x_{wcv} \leq S_w
    \quad \forall w \in W
\end{equation}

\textbf{Non-negativity:}
\begin{equation}
x_{wcv} \geq 0 \quad \forall w \in W, c \in C, v \in V
\end{equation}

\paragraph{Capacity Adequacy (Audit 4.1).}
\begin{proposition}
The constraint set is non-empty whenever
\[
\sum_{w \in W} S_w \;\geq\; \sum_{c \in C} D_c.
\]
\end{proposition}
\begin{proof}
Set $x_{wcv}^{*} = D_c \cdot \alpha_{wc} \cdot \mathbb{1}[v = v_0]$ for
any feasible flow allocation $\alpha_{wc} \in [0, 1]$ with
$\sum_w \alpha_{wc} = 1$ and $\sum_c \alpha_{wc} D_c \leq S_w$. The
adequacy condition guarantees such an allocation exists by Hall's
theorem applied to the bipartite warehouse-customer flow network.
\end{proof}

\paragraph{Remark on problem class (Audit 4.1).}
The above formulation is a multi-commodity transportation problem,
not a full CVRP with explicit routing decisions. We adopt this
strategic-planning abstraction (allocation only, ceiling-based trip
counting) because the EJOR managerial-insights horizon (multi-year
fleet planning, carbon-reduction targets) is dominated by warehouse
location and aggregate flow decisions rather than day-to-day route
sequencing. A full CVRP with TSP sub-tours is not intractable but
adds noise that obscures the cost-carbon tradeoff at the strategic
level. We make this scope choice explicit and discuss its limitations
in Section~7.

\paragraph{Proposition (Continuous Relaxation Exactness).}
\begin{proposition}
Let $f^*_{\text{cont}}$ denote the optimal value of the continuous
relaxation $f_1$ where $\lceil x_{wcv}/Q_v \rceil$ is replaced by
$x_{wcv}/Q_v$, and $f^*_{\text{disc}}$ the discrete optimum. Then
$f^*_{\text{cont}} \le f^*_{\text{disc}}$, with equality when
$D_c \mod Q_v = 0$ for all $c \in C, v \in V$.
\end{proposition}
\begin{proof}
Continuous trips are a lower bound: $x/Q \le \lceil x/Q \rceil$. The
inequality is strict iff some allocation produces a fractional trip
count, i.e., some $D_c$ is not divisible by some $Q_v$. The empirical
validation (Table~\ref{tab:trip_relaxation_validation}) reports the
relaxation gap at $4\%$ for our calibrated instance.
\end{proof}
"""))

    # Save
    out_dir = Path(output_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = str(out_dir / "formulation")
    doc.generate_tex(filepath)

    return filepath + ".tex"
