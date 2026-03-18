# -*- coding: utf-8 -*-
"""
Integral Fund Backtester (Love-OS: EIT / PSF-Zero / R->0)
- EWMA (RiskMetrics) drift/vol/cov estimation
- Fractional Kelly allocation with leverage cap
- No-trade band with proportional transaction costs
- PSF-Zero (phase sync) health metrics via Hilbert transform
- Outputs: PNG (equity & drawdown & PSF), CSV (metrics)
"""

import os, json, argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import hilbert

# -------------------------
# 0) CLI
# -------------------------
def get_args():
    ap = argparse.ArgumentParser(description="Integral Fund Backtester (Love-OS)")
    ap.add_argument("--prices", type=str, default="prices.csv", help="CSV of daily prices.")
    ap.add_argument("--lam_mean", type=float, default=0.97, help="EWMA lambda for mean")
    ap.add_argument("--lam_cov", type=float, default=0.97, help="EWMA lambda for covariance")
    ap.add_argument("--frac_kelly", type=float, default=0.5, help="Fractional Kelly (0<k<=1)")
    ap.add_argument("--lev_cap", type=float, default=1.0, help="Leverage cap on sum of long weights")
    ap.add_argument("--band", type=float, default=0.02, help="No-trade band width (e.g., 0.02=±2%)")
    ap.add_argument("--tcost_bps", type=float, default=5.0, help="Transaction cost [bps one-way]")
    ap.add_argument("--plot", action="store_true", default=True, help="Save plots (PNG)")
    ap.add_argument("--outdir", type=str, default="results", help="Output directory")
    ap.add_argument("--rf_annual", type=float, default=0.0, help="Annual risk-free rate")
    return ap.parse_args()

# -------------------------
# 1) Data loading & returns
# -------------------------
def load_prices(path):
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    df = df.dropna(axis=1, how="all").fillna(method="ffill")
    return df

def ensure_cash(prices: pd.DataFrame) -> pd.DataFrame:
    if "CASH" not in prices.columns:
        prices = prices.copy()
        prices["CASH"] = 1.0
    return prices

# -------------------------
# 2) EWMA estimators (EIT)
# -------------------------
def ewma_mean(arr: np.ndarray, lam: float) -> np.ndarray:
    T, N = arr.shape
    m = np.zeros((T, N), dtype=np.float64)
    m[0] = arr[0]
    for t in range(1, T):
        m[t] = lam * m[t-1] + (1 - lam) * arr[t]
    return m

def ewma_cov(arr: np.ndarray, lam: float) -> np.ndarray:
    T, N = arr.shape
    covs = np.zeros((T, N, N), dtype=np.float64)
    covs[0] = np.cov(arr[:min(20, T)].T)
    for t in range(1, T):
        x = arr[t][:, None]
        covs[t] = lam * covs[t-1] + (1 - lam) * (x @ x.T)
    return covs

# -------------------------
# 3) Fractional Kelly weights
# -------------------------
def solve_kelly(mu_vec, cov_mat, frac_kelly=0.5, lev_cap=1.0, rf=0.0, cash_idx=None):
    mu_ex = mu_vec - rf
    eps = 1e-8
    try:
        invS = np.linalg.inv(cov_mat + eps * np.eye(cov_mat.shape[0]))
    except np.linalg.LinAlgError:
        invS = np.linalg.pinv(cov_mat + eps * np.eye(cov_mat.shape[0]))
    
    w = invS @ mu_ex
    w = np.clip(w, 0.0, None) * frac_kelly
    
    if cash_idx is None:
        total_long = float(np.sum(w))
        if total_long > lev_cap: w *= (lev_cap / total_long)
    else:
        w_nc = w.copy()
        w_nc[cash_idx] = 0.0
        total_nc = float(np.sum(w_nc))
        if total_nc > lev_cap: w_nc *= (lev_cap / total_nc)
        w = w_nc
        w[cash_idx] = max(0.0, 1.0 - np.sum(w_nc))
        
    s = np.sum(w)
    if cash_idx is None and s > 0: w /= s
    return w

# -------------------------
# 4) No-trade band (R -> 0)
# -------------------------
def ntr_rebalance(w_now, w_tgt, band):
    diff = w_tgt - w_now
    if np.max(np.abs(diff)) <= band:
        return w_now.copy(), False
    w_new = w_now + np.clip(diff, -band, band)
    s = np.sum(w_new)
    if s > 1.0: w_new /= s
    return w_new, True

# -------------------------
# 5) PSF-Zero (Phase Sync)
# -------------------------
def psf_zero(returns_df: pd.DataFrame, win=63):
    X = returns_df.copy().fillna(0.0)
    cols = X.columns.tolist()
    ph = pd.DataFrame(index=X.index, columns=cols, dtype=float)
    
    for c in cols:
        sig = X[c].values
        sig = sig - pd.Series(sig).rolling(win, min_periods=1).mean().values
        ph[c] = np.angle(hilbert(sig))

    psf = pd.Series(index=X.index, dtype=float)
    for t in range(len(X)):
        row = ph.iloc[:t+1].tail(win)
        if row.shape[0] < 2: continue
        vals = row.values
        K = vals.shape[1]
        acc = [np.cos(vals[-1, i] - vals[-1, j]) for i in range(K) for j in range(i+1, K)]
        if acc: psf.iloc[t] = np.mean(acc)
    return psf

# -------------------------
# 6) Backtest Engine
# -------------------------
def backtest(prices: pd.DataFrame, args):
    prices = ensure_cash(prices)
    assets = prices.columns.tolist()
    cash_idx = assets.index("CASH") if "CASH" in assets else None
    rets = prices.pct_change().dropna()
    arr = rets.values 
    
    mu_ewma = ewma_mean(arr, args.lam_mean)
    covs_ewma = ewma_cov(arr, args.lam_cov)
    T, N = arr.shape
    
    w = np.zeros(N)
    if cash_idx is not None: w[cash_idx] = 1.0
    nav, turnover, trade_flags = np.ones(T), np.zeros(T), np.zeros(T, dtype=int)
    w_hist = np.zeros((T, N))
    psf = psf_zero(rets[assets], win=63)

    for t in range(T):
        w_tgt = solve_kelly(mu_ewma[t], covs_ewma[t], args.frac_kelly, args.lev_cap, args.rf_annual/252.0, cash_idx)
        w_new, traded = ntr_rebalance(w, w_tgt, args.band)
        
        delta = np.abs(w_new - w)
        tc = (args.tcost_bps / 10000.0) * np.sum(delta)
        w = w_new
        trade_flags[t] = int(traded)
        turnover[t] = np.sum(delta)
        
        rp = float(np.dot(w, arr[t])) - tc
        nav[t] = nav[t-1]*(1+rp) if t>0 else (1+rp)
        w_hist[t] = w
        
        if t < T-1:
            w = w * (1 + arr[t])
            s = np.sum(w)
            if s > 0: w /= s
            else:
                w = np.zeros(N)
                if cash_idx is not None: w[cash_idx] = 1.0

    return {"index": rets.index, "assets": assets, "nav": nav, "w_hist": w_hist, "turnover": turnover, "psf": psf.loc[rets.index].values}

# -------------------------
# 7) Execute & Save
# -------------------------
def main():
    args = get_args()
    os.makedirs(args.outdir, exist_ok=True)
    
    print("[INIT] Loading prices...")
    prices = load_prices(args.prices)
    
    print("[RUN] Executing Integral Fund Backtest...")
    bt = backtest(prices, args)
    
    # Save Equity Curve Plot
    if args.plot:
        fig, ax = plt.subplots(3,1, figsize=(11,10), sharex=True)
        eq = pd.Series(bt["nav"], index=bt["index"])
        eq.plot(ax=ax[0], color='tab:blue', lw=1.5)
        ax[0].set_title("Integral Fund: Net-of-Costs Equity Curve")
        ax[0].grid(True, alpha=0.3)

        dd = 1 - eq/eq.cummax()
        dd.plot(ax=ax[1], color='tab:red', lw=1.2)
        ax[1].fill_between(eq.index, 0, dd, color='tab:red', alpha=0.25)
        ax[1].set_title(f"Drawdown (Max={dd.max():.2%})")
        ax[1].grid(True, alpha=0.3)

        psf_series = pd.Series(bt["psf"], index=eq.index).rolling(21).mean()
        psf_series.plot(ax=ax[2], color='tab:green', lw=1.2)
        ax[2].axhline(0.7, ls='--', color='gray', alpha=0.6)
        ax[2].axhline(0.3, ls='--', color='gray', alpha=0.6)
        ax[2].set_ylim(-1.05, 1.05)
        ax[2].set_title("PSF-Zero (rolling mean): Health Range of Phase Sync")
        ax[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plot_path = os.path.join(args.outdir, "integral_fund_report.png")
        fig.savefig(plot_path, dpi=140)
        print(f"[SUCCESS] Plot saved to {plot_path}")

if __name__ == "__main__":
    main()
