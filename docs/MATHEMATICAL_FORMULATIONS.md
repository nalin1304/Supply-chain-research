# Comprehensive Mathematical Formulations
**Autonomous Supply Chain Optimization via Advanced Reinforcement Learning**

This document serves as a rigorous mathematical reference for all formulations, objective functions, and update rules utilized in the 14-phase autonomous supply chain project. It is intended to defend the theoretical soundness of the framework.

---

## 1. Core Inventory Routing Problem (IRP) Dynamics

The supply chain is modeled as a discrete-time Markov Decision Process (MDP). Let $t \in \{0, 1, \dots, T\}$ denote the time step.

### State Space and Inventory Transition
Let $I_i^{(t)}$ be the inventory level at node $i$ at time $t$. The physical inventory evolves according to:

$$ I_i^{(t+1)} = I_i^{(t)} + \sum_{j \in \mathcal{N}_{in}(i)} Q_{ji}^{(t - L_{ji})} - D_i^{(t)} $$

Where:
* $Q_{ji}^{(t - L_{ji})}$ is the order quantity placed from node $j$ to node $i$ arriving at time $t$ (accounting for lead time $L_{ji}$).
* $D_i^{(t)}$ is the realized stochastic demand at node $i$ at time $t$.

### Cost Function (Nominal Reward)
The instantaneous cost $C^{(t)}$ combines holding costs, stockout penalties, and transit logistics:

$$ C^{(t)} = \sum_{i \in \mathcal{V}} \left( h_i \max(I_i^{(t)}, 0) + p_i \max(-I_i^{(t)}, 0) \right) + \sum_{(j,i) \in \mathcal{E}} c_{ji} Q_{ji}^{(t)} $$

Where $h_i$ is the holding cost per unit, $p_i$ is the stockout penalty, and $c_{ji}$ is the per-unit shipping cost. The agent maximizes the negative cost: $r^{(t)} = -C^{(t)}$.

---

## 2. Proximal Policy Optimization (PPO)

The nominal controller is trained via PPO. The objective is to maximize the clipped surrogate advantage:

$$ \mathcal{L}^{CLIP}(\theta) = \hat{\mathbb{E}}_t \left[ \min(r_t(\theta) \hat{A}_t, \text{clip}(r_t(\theta), 1-\epsilon, 1+\epsilon) \hat{A}_t) \right] $$

Where $r_t(\theta) = \frac{\pi_\theta(a_t | s_t)}{\pi_{\theta_{old}}(a_t | s_t)}$ is the probability ratio, and $\hat{A}_t$ is the Generalized Advantage Estimate (GAE):

$$ \hat{A}_t = \sum_{l=0}^{\infty} (\gamma \lambda)^l \delta_{t+l} \quad \text{with} \quad \delta_t = r_t + \gamma V_\phi(s_{t+1}) - V_\phi(s_t) $$

---

## 3. CVaR-MAPPO: Tail Risk Bounding

To prevent catastrophic network failures, we extend PPO to Multi-Agent PPO (MAPPO) with a Conditional Value at Risk (CVaR) objective. Let $Z$ be the random variable representing the discounted return. 

The Value at Risk (VaR) at confidence level $\alpha$ is:
$$ \operatorname{VaR}_\alpha(Z) = \inf \{ z \in \mathbb{R} : P(Z \leq z) \geq \alpha \} $$

The CVaR is the expected return in the worst $\alpha$-fraction of scenarios:
$$ \operatorname{CVaR}_\alpha(Z) = \mathbb{E}[Z | Z \leq \operatorname{VaR}_\alpha(Z)] = \frac{1}{\alpha} \int_0^\alpha \operatorname{VaR}_\gamma(Z) \, d\gamma $$

The policy critic is heavily penalized for tail risks below the $\alpha=0.10$ threshold, explicitly guarding against black-swan supply shocks.

---

## 4. Minimax Adversarial RL ($H_\infty$ Control)

We frame robust optimization as a zero-sum stochastic game between the Defender (inventory policy $\pi_\theta$) and the Attacker (shock injector $\pi_\phi$). The objective is a minimax problem:

$$ \max_{\theta} \min_{\phi} \mathbb{E}_{\tau \sim (\pi_\theta, \pi_\phi)} \left[ \sum_{t=0}^T \gamma^t r(s_t, a_t^\theta, a_t^\phi) \right] $$

The attacker's action $a_t^\phi = \delta_t$ perturbs demand and lead times, subject to a strict infinity-norm budget:
$$ ||\delta_t||_\infty \leq \epsilon $$

This limits the adversary's capability, forcing the defender to build robustness against realistic synchronized shocks rather than impossible infinite-magnitude disruptions.

---

## 5. Offline Decision Transformers (DT)

To leverage historical offline data without fragile simulator interactions, the problem is recast as autoregressive sequence modeling. A trajectory is represented as:

$$ \tau = (\hat{R}_1, s_1, a_1, \hat{R}_2, s_2, a_2, \dots, \hat{R}_T, s_T, a_T) $$

Where $\hat{R}_t = \sum_{t'=t}^T r_{t'}$ is the Return-to-Go (RTG).

The Decision Transformer models the optimal policy $\pi_\theta(a_t | \hat{R}_t, s_t)$ by minimizing the Mean Squared Error over the offline dataset $\mathcal{D}$:

$$ \mathcal{L}^{DT}(\theta) = \mathbb{E}_{(s, a, \hat{R}) \sim \mathcal{D}} \left[ || a_t - f_\theta(\hat{R}_t, s_t) ||_2^2 \right] $$

At inference, we extract optimal behavior purely via conditioning on a high target RTG.

---

## 6. Multi-Objective Reinforcement Learning (MORL)

To balance financial costs and carbon emissions, the environment emits a vectorized reward $\vec{r}_t = [r_t^{\text{cost}}, r_t^{\text{carbon}}]^T$. We introduce a dynamic preference vector $\omega = [w_{\text{cost}}, w_{\text{carbon}}]^T$ such that $||\omega||_1 = 1$.

The scalarized advantage used in the PPO update is the $\omega$-weighted sum of independent advantages:

$$ A_t^{\text{scalar}} = w_{\text{cost}} \hat{A}_t^{\text{cost}} + w_{\text{carbon}} \hat{A}_t^{\text{carbon}} $$

Where $\hat{A}_t^{\text{cost}}$ and $\hat{A}_t^{\text{carbon}}$ are computed via GAE using separate value functions $V_\phi^{\text{cost}}(s_t)$ and $V_\phi^{\text{carbon}}(s_t)$. 

During training, $\omega \sim \text{Dirichlet}(1.0)$, forcing the agent to learn the entire Pareto manifold. At inference, $\omega$ can be shifted dynamically by a human without retraining.
