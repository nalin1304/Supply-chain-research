# Cover Letter

Dear Editor-in-Chief, *Transportation Research Part E: Logistics and
Transportation Review*,

We are pleased to submit the enclosed manuscript, *An Integrated
Multi-Objective Optimization and Deep Reinforcement Learning Framework
for Green, Resilient Supply Chain Management: Evidence from Indian
Logistics Networks*, for consideration as an original research article.

Indian logistics absorbs approximately 14 per cent of national GDP,
well above the 8-10 per cent benchmark in mature freight economies,
and is responsible for roughly 260 million tonnes of carbon-dioxide
emissions per year from road freight alone, a figure projected to
quadruple by 2047 on the present trajectory. A planner today is asked
to act on three pressures at once: tighter Bharat Stage VI emission
standards that have shifted the cost-emission trade-off in favour of
load-factor improvement, ESG disclosure obligations cascading down
from listed shippers to their tier-1 logistics partners, and
e-commerce service-level expectations that have raised the marginal
cost of stockouts. The published green-VRP and resilience literature
is methodologically mature in isolation, but no single framework
couples the three pressures on a calibrated network of comparable
size and reports a unified statistical-validation protocol that lets
a planner act on the result with confidence.

The manuscript closes that integration gap with three theoretical
contributions. First, a marginal cost-carbon repair operator that
preserves Pareto diversity by assigning each individual a private
scalarisation weight, addressing the diversity-collapse pathology
that proportional repair exhibits when the weight is shared across
the population. Second, a joint-normalised hypervolume indicator
that makes cross-algorithm comparisons scale-invariant under the
heterogeneous objective ranges (logistics cost on the order of
ten-to-the-six rupees, carbon on the order of ten-to-the-five
kilograms) that the green-VRP literature otherwise treats with raw
hypervolume. Third, a journal-grade statistical-validation protocol
with a Friedman omnibus test whose power is empirically estimated
through a 10,000-iteration Monte Carlo simulation, paired Wilcoxon
post-hoc tests under a global Holm-Bonferroni correction, and a Sobol
global sensitivity analysis that replaces the conventional
one-at-a-time sweep. Implementation correctness is established on
CVRPLIB Augerat Set-A (mean gap of 5.1 per cent across all 27
instances), and external validity is established on a Delhivery
secondary network (10 hubs, 150 customers, joint-normalised
hypervolume 0.880 plus or minus 0.099).

The manuscript fits the venue squarely. *Transportation Research Part
E* has emphasised green-VRP and resilience formulations on calibrated
networks in its recent issues, and the present work extends that
agenda by coupling the multi-objective routing layer to a SimPy-based
discrete-event resilience simulator and a PPO inventory controller
under a single statistical protocol. The bi-objective formulation is
a faithful generalisation of the bi-objective pollution-routing
problem onto a calibrated Indian network with verified MEET, COPERT 5,
HBEFA 4.2, and IPCC AR6 emission anchors, and the disruption-stress
head-to-head between PPO and a tuned (R, s, S) baseline is the
empirical lynchpin we expect *Part E* readers to find decision-relevant.

The manuscript is original work that has not been published elsewhere
and is not under consideration at any other journal. All authors have
approved the submission. The full codebase, data sources, and
reproduction recipe are available in the repository referenced in the
data-availability statement.

We would be delighted to address any reviewer comments and look
forward to your editorial decision.

Sincerely,

Nalin Aggarwal
[Affiliation], Mumbai, India
