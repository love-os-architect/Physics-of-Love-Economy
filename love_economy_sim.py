import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --- 1. Model Configuration & Parameters ---

class LoveEconomySim:
    def __init__(self, steps=100, dt=1.0):
        self.steps = steps
        self.dt = dt
        
        # --- Base Parameters (Initial Conditions) ---
        self.K = 100.0   # Capital Stock
        self.N = 100.0   # Labor Population
        self.A = 1.0     # Technology Level
        self.D = 80.0    # Private Debt
        self.C_carbon = 10.0 # Accumulated Carbon Stock
        self.R = 0.8     # Synchronization/Field Coherence (0-1)
        self.WageShare = 0.65 # Wage Share (Labor Share)
        
        # --- Structural Parameters ---
        self.alpha = 0.35 # Capital Share in Production
        self.delta = 0.05 # Capital Depreciation
        self.c_w = 0.9    # MPC from Wages
        self.c_pi = 0.4   # MPC from Profits
        self.inv_sens = 0.15 # Investment Sensitivity to Profit
        self.damage_sens = 0.002 # Damage per Carbon Unit
        self.energy_intensity = 0.5 # Energy per Unit Output
        
    def run_scenario(self, policy_mode="BAU"):
        """
        Runs the simulation for a specific policy scenario.
        policy_mode: "BAU" (Business As Usual) or "INTEGRATED" (Love-OS Policy)
        """
        
        # Initialize History Lists
        hist = {
            "t": [], "Y_potential": [], "Y_effective": [], 
            "D_Y_ratio": [], "R": [], "Carbon": [], 
            "WageShare": [], "Profit": [], "Real_r": []
        }
        
        # Set Dynamic Variables
        K = self.K
        D = self.D
        C_carbon = self.C_carbon
        R = self.R
        WS = self.WageShare
        A = self.A
        EI = self.energy_intensity
        
        # --- Policy Switches ---
        # 1. Carbon Tax (Internalizing Externalities)
        tau = 0.05 if policy_mode == "INTEGRATED" else 0.0
        
        # 2. Wage Floor (Preventing Profit Paradox)
        # BAU: Share drops (-0.1%/step). Policy: Stabilizes or grows.
        d_ws = 0.0005 if policy_mode == "INTEGRATED" else -0.002
        
        # 3. Macroprudential (Debt Control)
        # BAU: r > g_Y (Interest Dominance). Policy: r <= g_Y (Managed).
        base_r = 0.04 # Nominal interest baseline
        
        # 4. Synchronization Investment (Investing in R)
        # BAU: Friction increases. Policy: Standardization keeps R high.
        R_target = 0.95 if policy_mode == "INTEGRATED" else 0.60
        R_restoration = 0.05 if policy_mode == "INTEGRATED" else 0.01
        
        for t in range(self.steps):
            
            # --- A. Supply Side (Physical Constraint) ---
            # Damage function: Carbon stock reduces Effective Tech (A)
            damage_factor = 1.0 / (1.0 + self.damage_sens * C_carbon)
            A_eff = A * damage_factor
            
            # Potential Output (Cobb-Douglas)
            # Energy constraints are implicit in EI (Energy Intensity)
            Y_pot = A_eff * (K**self.alpha) * (self.N**(1-self.alpha))
            
            # --- B. Demand Side (Kaleckian / Effective Demand) ---
            # Distribute Income
            W_bill = Y_pot * WS
            Pi_bill = Y_pot * (1 - WS)
            
            # Consumption
            Cons = self.c_w * W_bill + self.c_pi * Pi_bill
            
            # Investment (Profit-driven)
            Inv = self.inv_sens * Pi_bill + 0.02 * Y_pot
            
            # Aggregate Demand
            AD = Cons + Inv
            
            # --- C. Synchronization Constraint (The "R" Factor) ---
            # Effective Output is limited by Demand AND Friction (R)
            # Y_eff = R * min(Supply, Demand)
            # If R is low, transactions fail, logic doesn't sync -> Output drops.
            Y_eff = R * min(Y_pot, AD)
            
            # Actual Realized Profit (after friction)
            Realized_Pi = Y_eff * (1 - WS)
            
            # --- D. Dynamics Updates ---
            
            # 1. Capital Accumulation
            K += (Inv - self.delta * K) * self.dt
            
            # 2. Debt Dynamics (Financial Contradiction)
            # Growth rate of Y
            g_Y = (Y_eff - hist["Y_effective"][-1])/hist["Y_effective"][-1] if t > 0 else 0.02
            
            # Interest Rate Setting
            if policy_mode == "INTEGRATED":
                # Policy Rule: r tracks g_Y to prevent explosive D/Y
                r_eff = min(base_r, max(0.01, g_Y - 0.005))
            else:
                # BAU: r is sticky and often > g_Y
                r_eff = base_r
            
            # Debt accumulation (Interest - Repayment from Surplus)
            # Simple assumption: Repayment is fraction of Output
            repayment = 0.02 * Y_eff
            D += (r_eff * D - repayment) * self.dt
            
            # 3. Carbon/Externalities
            # Emissions = Output * Energy Intensity
            emissions = Y_eff * EI
            C_carbon += emissions * self.dt
            # Tech improves EI (faster if Carbon Tax exists)
            decarb_rate = 0.01 + (0.05 if tau > 0 else 0.0)
            EI *= (1.0 - decarb_rate)
            
            # 4. Synchronization (R) Dynamics
            # Converges to target with some noise/shocks
            shock = np.random.normal(0, 0.01)
            R += (R_restoration * (R_target - R) + shock) * self.dt
            R = np.clip(R, 0.1, 1.0)
            
            # 5. Wage Share Dynamics (Profit Paradox)
            WS += d_ws * self.dt
            WS = np.clip(WS, 0.4, 0.9) # Boundaries
            
            # --- Record Data ---
            hist["t"].append(t)
            hist["Y_potential"].append(Y_pot)
            hist["Y_effective"].append(Y_eff)
            hist["D_Y_ratio"].append(D / Y_eff)
            hist["R"].append(R)
            hist["Carbon"].append(C_carbon)
            hist["WageShare"].append(WS)
            hist["Profit"].append(Realized_Pi)
            hist["Real_r"].append(r_eff)
            
        return pd.DataFrame(hist)

# --- 2. Execution & Visualization ---

def plot_simulation():
    sim = LoveEconomySim(steps=100)
    
    # Run Scenarios
    df_bau = sim.run_scenario("BAU")
    df_pol = sim.run_scenario("INTEGRATED")
    
    # Setup Plot
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Love-OS Economic Model: BAU vs. Integrated Policy', fontsize=16)
    
    # Plot 1: Effective Output (Y)
    ax = axes[0, 0]
    ax.plot(df_bau["t"], df_bau["Y_effective"], 'r--', label='BAU (Friction & Weak Demand)', linewidth=2)
    ax.plot(df_pol["t"], df_pol["Y_effective"], 'g-', label='Integrated (High R & Sync)', linewidth=2)
    ax.set_title('Effective Output (Growth & Sustainability)')
    ax.set_ylabel('Real Output')
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    # Plot 2: Debt-to-GDP Ratio (Financial Stability)
    ax = axes[0, 1]
    ax.plot(df_bau["t"], df_bau["D_Y_ratio"], 'r--', label='BAU (Explosive Debt)', linewidth=2)
    ax.plot(df_pol["t"], df_pol["D_Y_ratio"], 'g-', label='Integrated (Stable)', linewidth=2)
    ax.set_title('Debt-to-GDP Ratio (Financial Contradiction)')
    ax.set_ylabel('Ratio')
    ax.grid(True, alpha=0.3)
    
    # Plot 3: Synchronization (R)
    ax = axes[1, 0]
    ax.plot(df_bau["t"], df_bau["R"], 'r--', label='BAU (Fragmentation)', linewidth=2)
    ax.plot(df_pol["t"], df_pol["R"], 'g-', label='Integrated (Coherence)', linewidth=2)
    ax.set_title('Field Coherence R (Efficiency Factor)')
    ax.set_ylim(0, 1.1)
    ax.grid(True, alpha=0.3)
    
    # Plot 4: Carbon Stock (Externalities)
    ax = axes[1, 1]
    ax.plot(df_bau["t"], df_bau["Carbon"], 'r--', label='BAU (Accumulation)', linewidth=2)
    ax.plot(df_pol["t"], df_pol["Carbon"], 'g-', label='Integrated (Internalized)', linewidth=2)
    ax.set_title('Accumulated Carbon Stock (External Constraints)')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.show()

if __name__ == "__main__":
    plot_simulation()
