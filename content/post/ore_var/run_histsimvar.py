#!/usr/bin/env python
"""
Historical simulation VaR runner for ORE.

Verified on open-source-risk-engine 1.8.17.0. Run from this folder so that
Input/ and Output/ resolve.

    python run_histsimvar.py           # clean VaR, Input/ore_histsimvar.xml
    python run_histsimvar.py --dirty   # theta and cashflow carry included

The dirty run writes to Output/HistSimVarDirty so both sets of results can sit
side by side.
"""

import argparse
import os
import sys

import ORE

from var_common import CLEAN_DIR, DIRTY_DIR, HERE, portfolio_pnl, read_report, var_from_pnl


def run(config, out_dir):
    cfg = os.path.join(HERE, "Input", config)
    if not os.path.exists(cfg):
        sys.exit(f"Config not found: {cfg}")
    os.makedirs(out_dir, exist_ok=True)

    params = ORE.Parameters()
    params.fromFile(cfg)
    app = ORE.OREApp(params, True)
    app.run()
    return app


def report(out_dir, label):
    # var.csv quantiles are P&L, so losses are negative. Flip the sign for display.
    var = read_report(os.path.join(out_dir, "var.csv"))
    row = var[(var["Portfolio"] == "All") & (var["RiskClass"] == "All") & (var["RiskType"] == "All")].iloc[0]
    print(f"\n{label}: portfolio, full revaluation (from var.csv)")
    print(f"  95% 10-day VaR  EUR {-row['Quantile_0.050000']:>12,.0f}")
    print(f"  99% 10-day VaR  EUR {-row['Quantile_0.010000']:>12,.0f}")
    print(f"  99% ES          EUR {-row['ExpectedShortfall_0.010000']:>12,.0f}")

    # Cross-check: rebuild the same numbers from the per-window P&L vector.
    pnl = portfolio_pnl(os.path.join(out_dir, "historical_PnL.csv"))
    v = var_from_pnl(pnl.values)
    print(f"  Recomputed from {len(pnl)} windows in historical_PnL.csv: "
          f"95% {v['var95']:,.0f}, 99% {v['var99']:,.0f}, ES {v['es99']:,.0f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dirty", action="store_true", help="include theta and period cashflows")
    args = ap.parse_args()

    if args.dirty:
        run("ore_histsimvar_dirty.xml", DIRTY_DIR)
        report(DIRTY_DIR, "Dirty VaR")
    else:
        run("ore_histsimvar.xml", CLEAN_DIR)
        report(CLEAN_DIR, "Clean VaR")
