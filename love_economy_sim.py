# -*- coding: utf-8 -*-
"""
Love-OS Economic Simulator — Final Enhanced Edition
"Friction Zero" Economy: R (Field Coherence) as the central variable
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from dataclasses import dataclass

@dataclass
class LoveEconomyParams:
    # Initial Conditions
    K: float = 100.0      # Capital Stock
    N: float = 100.0      # Labor
    A: float = 1.0        # Technology
    D: float = 80.0       # Private Debt
    C_carbon: float = 10.0
    R: float = 0.75       # Initial Field Coherence (Synchronization)

    # Production
    alpha: float = 0.35   # Capital share
    delta: float = 0.06   # Depreciation

    # Demand
    c_w: float = 0.88     # MPC from wages
    c_pi: float = 0.35    # MPC from profits
    inv_sens: float = 0.18

    # Externalities & Policy
    damage_sens: float = 0.0018
    energy_intensity: float = 0.48

    # Synchronization Dynamics
    R_restoration_policy: float = 0.045   # Policy investment in coherence
    R_restoration_bau: float = 0.008
    R_target: float = 0.96


class LoveEconomySim:
    def __init__(self, steps: int = 120, dt: float = 1.0):
        self.steps = steps
        self.dt = dt
        self.p = LoveEconomyParams()

    def run(self, policy_mode: str = "BAU") -> pd.DataFrame:
        p = self.p
        K, D, C_carbon, R, WS = p.K, p.D, p.C_carbon, p.R, 0.68
        A, EI = p.A, p.energy_intensity

        hist = {key: [] for key in ["t", "Y_eff", "D_Y", "R", "Carbon", "WageShare", "Real_r"]}

        for t in range(self.steps):
            # Supply Side
            damage = 1.0 / (1.0 + p.damage_sens * C_carbon)
            Y_pot = A * damage * (K ** p.alpha) * (p.N ** (1 - p.alpha))

            # Demand Side
            W_bill = Y_pot * WS
            Pi_bill = Y_pot * (1 - WS)
            Cons = p.c_w * W_bill + p.c_pi * Pi_bill
            Inv = p.inv_sens * Pi_bill + 0.025 * Y_pot
            AD = Cons + Inv

            # --- Core Love-OS Variable: Field Coherence R ---
            Y_eff = R * min(Y_pot, AD)                     # Synchronization-constrained output

            # Debt dynamics (r vs g)
            g_Y = (Y_eff - hist["Y_eff"][-1]) / hist["Y_eff"][-1] if t > 0 else 0.025
            r_eff = 0.035 if policy_mode == "INTEGRATED" else 0.055   # Policy keeps r ≤ g
            repayment = 0.018 * Y_eff
            D += (r_eff * D - repayment) * self.dt

            # Carbon & Decarbonization
            emissions = Y_eff * EI
            C_carbon += emissions * self.dt
            EI *= (1.0 - 0.012 if policy_mode == "INTEGRATED" else 0.003)

            # Synchronization Dynamics (The Heart of Love-OS)
            R_target = 0.96 if policy_mode == "INTEGRATED" else 0.55
            R_rest = p.R_restoration_policy if policy_mode == "INTEGRATED" else p.R_restoration_bau
            R += R_rest * (R_target - R) + np.random.normal(0, 0.008)
            R = np.clip(R, 0.15, 1.0)

            # Wage Share (Anti-Profit Paradox)
            dWS = 0.0008 if policy_mode == "INTEGRATED" else -0.0025
            WS += dWS * self.dt
            WS = np.clip(WS, 0.42, 0.78)

            # Record
            hist["t"].append(t)
            hist["Y_eff"].append(Y_eff)
            hist["D_Y"].append(D / Y_eff)
            hist["R"].append(R)
            hist["Carbon"].append(C_carbon)
            hist["WageShare"].append(WS)
            hist["Real_r"].append(r_eff)

        return pd.DataFrame(hist)


def plot_comparison():
    sim = LoveEconomySim(steps=150)
    df_bau = sim.run("BAU")
    df_pol = sim.run("INTEGRATED")

    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Love-OS Economic Simulator: BAU vs Integrated (R-Coherence) Policy", fontsize=16)

    # Effective Output
    axs[0,0].plot(df_bau["t"], df_bau["Y_eff"], 'r--', label='BAU (Low R, Friction Economy)')
    axs[0,0].plot(df_pol["t"], df_pol["Y_eff"], 'g-', label='Integrated (High R, Zero-Friction Economy)')
    axs[0,0].set_title("Effective Output")
    axs[0,0].legend()

    # Debt-to-GDP
    axs[0,1].plot(df_bau["t"], df_bau["D_Y"], 'r--', label='BAU (Explosive Debt)')
    axs[0,1].plot(df_pol["t"], df_pol["D_Y"], 'g-', label='Integrated (Stable)')
    axs[0,1].set_title("Debt / Effective Output Ratio")
    axs[0,1].legend()

    # Synchronization R
    axs[1,0].plot(df_bau["t"], df_bau["R"], 'r--', label='BAU (Fragmentation)')
    axs[1,0].plot(df_pol["t"], df_pol["R"], 'g-', label='Integrated (Coherence)')
    axs[1,0].set_title("Field Coherence R (Core Love-OS Variable)")
    axs[1,0].set_ylim(0, 1)
    axs[1,0].legend()

    # Carbon Stock
    axs[1,1].plot(df_bau["t"], df_bau["Carbon"], 'r--', label='BAU')
    axs[1,1].plot(df_pol["t"], df_pol["Carbon"], 'g-', label='Integrated')
    axs[1,1].set_title("Accumulated Carbon")
    axs[1,1].legend()

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    plot_comparison()
