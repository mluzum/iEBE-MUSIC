# Protocol: Standard Parameterization for Sampling Deformed Nuclear Configurations with Geometric Periodicity
# Target Framework: Event-by-Event Ultrarelativistic Heavy-Ion Initial Conditions

## 1. Objective
Generate event-by-event configurations of projectile and target nuclei where the quadrupole deformation parameters \((\beta, \gamma)\) are drawn from a flexible, continuous distribution. The framework must seamlessly handle rigid rotors, soft vibrators, and completely gamma-unstable landscapes without introducing boundary clustering artifacts at the axial limits (\(\gamma = 0°\) or 60°), making it suitable for downstream Bayesian parameter estimation.

## 2. Intrinsic Coordinate Definition
To guarantee complete axis-permutation invariance, the sampled parameters must map into the standard Bohr-Mottelson fundamental domain:
* \(\beta \ge 0\)
* \(0° \le \gamma \le 60° \)(or \(0 \le \gamma \le \pi/3\) radians)

## 3. Parameterizing the Distribution (For Bayesian Inference)
We define the distribution using a 4-parameter vector \(\vec{\theta} = { \mu_\beta, \sigma_\beta, \mu_\gamma, \sigma_\gamma }\) that describes a continuous probability landscape over a flat auxiliary space, which is subsequently mapped to the true physical manifold.

### Option A: Truncated 2D Gaussian in Cartesian Coordinate Projection
Sample independent auxiliary variables x and y, which represent the projections of deformation:
* x \(\sim \mathcal{N}(\mu_x, \sigma_x^2)\)
* y \(\sim \mathcal{N}(\mu_y, \sigma_y^2)\)

Where the hyperparameters can be directly mapped to your physical intuition of means and variances:
* \(\mu_x = \mu_\beta \cos(\mu_\gamma), \quad \sigma_x = \sigma_\beta\)
* \(\mu_y = \mu_\beta \sin(\mu_\gamma), \quad \sigma_y = \mu_\beta \cdot \sin(\sigma_\gamma)\)

### Option B: Bounded Beta Distributions (Recommended for stable emulators)
To strictly avoid infinite tails during prior exploration in a Bayesian pipeline, sample normalized variables u, v \(\in [0, 1]\) using Beta distributions:
* u \(\sim \text{Beta}(\alpha_1, \beta_1) \implies \beta_{\text{trial}} = \beta_{\text{max}} \cdot\) u
* v \(\sim \text{Beta}(\alpha_2, \beta_2) \implies \gamma_{\text{trial}} = 120^\circ \cdot\) v  (Sample over double-domain to safely cross edges)

Convert the standard hyperparameter means and variances \((\mu, \sigma^2)\) to Beta shape parameters \((\alpha, \beta)\) via:
* \(\alpha = \mu \left( \frac{\mu(1 - \mu)}{\sigma^2} - 1 \right)\)
* \(\beta = (1 - \mu) \left( \frac{\mu(1 - \mu)}{\sigma^2} - 1 \right)\)

## 4. Symmetry Mapping & Boundary Regularization Algorithm
No matter how \(\beta_{\text{trial}} and \gamma_{\text{trial}}\) are generated (even if they wander negative or way out of bounds), they must be folded into the unique physical configuration space using the following rigid axis-rotation invariants:

```python
import numpy as np

def map_to_fundamental_domain(beta_trial, gamma_trial_rad):
    """
    Maps any raw sampled beta and gamma values into the physically 
    unique fundamental domain (beta >= 0, 0 <= gamma <= 60 degrees).
    """
    # 1. Enforce positive beta
    beta = abs(beta_trial)
    
    # 2. Convert gamma to degrees for clean modulo arithmetic
    gamma_deg = np.degrees(gamma_trial_rad)
    
    # 3. Handle negative angles via reflection symmetry
    gamma_deg = abs(gamma_deg)
    
    # 4. Apply 3-fold cyclic axis permutation symmetry (120-degree periodicity)
    gamma_mod = gamma_deg % 120.0
    
    # 5. Apply reflection symmetry within the 120-degree sector (fold upper half)
    if gamma_mod > 60.0:
        gamma = 120.0 - gamma_mod
    else:
        gamma = gamma_mod
        
    return beta, np.radians(gamma)
```

## 5. Phase-Space Volume Correction (Geometric Jacobian)
If the distribution is meant to represent thermal or quantum fluctuations over a flat potential energy surface (e.g., \gamma-unstable nuclei), the raw sampled configuration must be re-weighted by the standard 5D quadrupole Riemannian volume element:

\[ dV = \beta^4 |\sin(3\gamma)| d\beta d\gamma \]

For a completely \gamma-flat/unstable landscape, your target probability distribution should evaluate to:
\[ P(\gamma) \propto |\sin(3\gamma)| \]
Ensure your sampling method rejects configurations or includes a likelihood weight corresponding to this Jacobian factor if you are not sampling directly from a microscopic potential energy surface.

