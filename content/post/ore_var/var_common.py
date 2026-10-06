"""Shared helpers for the ORE historical simulation VaR scripts."""

import math
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR = os.path.join(HERE, "Output", "HistSimVar")
DIRTY_DIR = os.path.join(HERE, "Output", "HistSimVarDirty")


def ore_quantile(values, q):
    """Empirical order-statistic quantile used for every figure in the post.

    Sort ascending (worst loss first) and take the ceil(q*n)-th observation,
    counting from 1. With n = 715 that is the 8th worst window at q = 0.01
    and the 36th worst at q = 0.05. ORE's var.csv agrees to the euro for this
    book. pandas' default linear interpolation lands about 0.2% lower.
    """
    a = np.sort(np.asarray(values, dtype=float))
    k = int(math.ceil(q * len(a))) - 1
    return float(a[max(0, min(k, len(a) - 1))])


def read_report(path):
    """Read an ORE csv report and strip the leading '#' from the first header."""
    df = pd.read_csv(path)
    df.columns = [c.lstrip("#") for c in df.columns]
    return df


def portfolio_pnl(pnl_path, risk_class="All"):
    """Portfolio P&L per window, summed over trades.

    historical_PnL.csv has one row per trade and window, with no portfolio row.
    RiskType 'All' is full revaluation. In this ORE build the RiskClass slices
    'InterestRate' and 'FX' repeat the 'All' numbers, so 'All' is the only
    class worth using here. Risk-factor attribution comes from
    riskFactor_PnL.csv instead.
    """
    df = read_report(pnl_path)
    sub = df[(df["RiskClass"] == risk_class) & (df["RiskType"] == "All")]
    return sub.groupby(["PLDate1", "PLDate2"])["PLAmount"].sum()


def var_from_pnl(pnl):
    """95% and 99% VaR and 99% ES from a P&L vector, as positive losses."""
    pnl = np.asarray(pnl, dtype=float)
    v95, v99 = ore_quantile(pnl, 0.05), ore_quantile(pnl, 0.01)
    return {"var95": -v95, "var99": -v99, "es99": -pnl[pnl <= v99].mean()}
