#!/usr/bin/env python
"""
Figures for the ORE historical simulation VaR post.

Run order (from this folder):
    python run_histsimvar.py
    python run_histsimvar.py --dirty
    python manual_bump.py
    python plot_var_results.py

Figures:
    pnl_distribution.png  empirical 10-day P&L: histogram, KDE, tail, and the same windows in time
    bump_mechanics.png    the worst window by hand: pillar shocks, and swap P&L by risk factor
    var_tail.png          the 36 worst windows against a delta-normal estimate, and clean vs dirty

Quantiles use the ceil(q*n)-th worst outcome (see var_common.ore_quantile).
"""

import json
import math
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from var_common import CLEAN_DIR, DIRTY_DIR, HERE, ore_quantile, portfolio_pnl

OUT = HERE
SUMMARY = os.path.join(HERE, "Output", "Base", "manual_bump_summary.json")

INK = "#1E293B"
GRID = "#E5E7EB"
EDGE = "#CBD5E1"
HIST_FILL = "#CBD5E1"
HIST_EDGE = "#64748B"
KDE = "#0F172A"
TAIL_LIGHT = "#FEE2E2"
TAIL_DARK = "#FECACA"
TS_LINE = "#94A3B8"
VAR95 = "#D97706"
VAR99 = "#DC2626"
ES99 = "#7C3AED"
BLUE = "#2563EB"
GREEN = "#059669"


def style_ax(ax):
    ax.set_facecolor("white")
    ax.tick_params(colors=INK, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(EDGE)
    ax.grid(True, linestyle=":", linewidth=0.7, color=GRID, zorder=0)
    ax.set_axisbelow(True)


def gaussian_kde(xs, data, bw):
    """Gaussian KDE written out to avoid a scipy dependency."""
    z = (np.asarray(xs)[:, None] - np.asarray(data)[None, :]) / bw
    return np.exp(-0.5 * z ** 2).sum(axis=1) / (len(data) * bw * math.sqrt(2 * math.pi))


def window_table(out_dir):
    tot = portfolio_pnl(os.path.join(out_dir, "historical_PnL.csv")).reset_index()
    tot["PLDate2"] = pd.to_datetime(tot["PLDate2"])
    return tot.sort_values("PLDate2").reset_index(drop=True)


# --------------------------------------------------------------------------
def plot_distribution(tot):
    pnl = tot["PLAmount"].to_numpy() / 1000.0   # EUR thousands, losses negative
    n = len(pnl)
    v95, v99 = ore_quantile(pnl, 0.05), ore_quantile(pnl, 0.01)
    es99 = pnl[pnl <= v99].mean()
    n95, n99 = int((pnl <= v95).sum()), int((pnl <= v99).sum())
    worst = tot.nsmallest(3, "PLAmount")

    fig, (ax_h, ax_t) = plt.subplots(2, 1, figsize=(10, 7), facecolor="white", layout="constrained",
                                     gridspec_kw={"height_ratios": [1.5, 1.0]})

    style_ax(ax_h)
    xmin, xmax = pnl.min() - 20, pnl.max() + 20
    ax_h.axvspan(xmin, v99, color=TAIL_DARK, alpha=0.9, zorder=0)
    ax_h.axvspan(v99, v95, color=TAIL_LIGHT, alpha=0.9, zorder=0)
    _, bins, _ = ax_h.hist(pnl, bins=40, color=HIST_FILL, edgecolor=HIST_EDGE, linewidth=0.6, zorder=2,
                           label=f"{n} windows")
    bw = pnl.std(ddof=1) * n ** (-1 / 5)   # Scott's rule
    gx = np.linspace(pnl.min(), pnl.max(), 400)
    ax_h.plot(gx, gaussian_kde(gx, pnl, bw) * n * (bins[1] - bins[0]), color=KDE, linewidth=1.6,
              label="KDE (Scott bandwidth)", zorder=4)
    ax_h.plot(pnl[pnl <= v99], np.full(n99, -0.6), "|", color=VAR99, markersize=9, markeredgewidth=1.4,
              label=f"{n99} losses at or past 99% VaR", clip_on=False, zorder=5)
    ax_h.axvline(v95, color=VAR95, linestyle="--", linewidth=1.8, label=f"95% VaR EUR {-v95:.1f}k")
    ax_h.axvline(v99, color=VAR99, linestyle="--", linewidth=1.8, label=f"99% VaR EUR {-v99:.1f}k")
    ax_h.axvline(es99, color=ES99, linestyle=":", linewidth=2.0, label=f"99% ES EUR {-es99:.1f}k")
    ax_h.set_xlim(xmin, xmax)
    ax_h.set_xlabel("10-day P&L (EUR thousands, losses on the left)", fontsize=10, color=INK)
    ax_h.set_ylabel("Windows per bin", fontsize=10, color=INK)
    ax_h.set_title(f"10-day empirical P&L, {n} overlapping windows", fontsize=13, fontweight="bold",
                   color=INK, pad=10)
    ax_h.legend(frameon=True, facecolor="white", edgecolor=EDGE, fontsize=9, loc="upper right").get_frame().set_alpha(0.95)

    style_ax(ax_t)
    ax_t.plot(tot["PLDate2"], pnl, color=TS_LINE, linewidth=0.9, zorder=2)
    m95, m99 = pnl <= v95 + 1e-9, pnl <= v99 + 1e-9
    ax_t.scatter(tot["PLDate2"][m95], pnl[m95], s=14, color=VAR95, zorder=3, label=f"At or past 95% VaR ({m95.sum()})")
    ax_t.scatter(tot["PLDate2"][m99], pnl[m99], s=26, color=VAR99, zorder=4, label=f"At or past 99% VaR ({m99.sum()})")
    for y, c, ls in ((v95, VAR95, "--"), (v99, VAR99, "--"), (es99, ES99, ":")):
        ax_t.axhline(y, color=c, linestyle=ls, linewidth=1.2)
    ax_t.text(0.02, 0.95, "Worst windows\n" + "\n".join(
        f"{r['PLDate1']} to {r['PLDate2'].date()}: {r['PLAmount'] / 1000:,.0f}k" for _, r in worst.iterrows()),
        transform=ax_t.transAxes, ha="left", va="top", fontsize=8, color=INK,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=EDGE, alpha=0.95))
    ax_t.set_ylabel("10-day P&L\n(EUR thousands)", fontsize=10, color=INK)
    ax_t.set_title("The same windows in time, by window-end date", fontsize=11, fontweight="bold", color=INK, pad=8)
    ax_t.legend(frameon=True, facecolor="white", edgecolor=EDGE, fontsize=9, loc="upper right")
    fig.savefig(os.path.join(OUT, "pnl_distribution.png"), dpi=200, facecolor="white")
    plt.close(fig)
    print(f"distribution: n={n} VaR95={-v95:.1f}k VaR99={-v99:.1f}k ES99={-es99:.1f}k "
          f"mean={pnl.mean():.1f}k median={np.median(pnl):.1f}k at/past95={n95} at/past99={n99}")


# --------------------------------------------------------------------------
def plot_bump_mechanics(summary):
    from manual_bump import CURVES, NICE, Setup   # imported here so ORE is only needed if base reports are missing
    s = Setup()
    w = summary["worst"]
    r = s.ratios(w["d1"], w["d2"])
    att = {a["factor"]: a["manual"] for a in summary["attribution"]}

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5), facecolor="white", layout="constrained",
                                 gridspec_kw={"width_ratios": [1.0, 1.15]})
    # Left: the shock itself, as the change in each pillar discount factor
    style_ax(a1)
    cols = {"EUR": BLUE, "USD": VAR99, "EUR6M": "#60A5FA", "USD3M": "#F87171"}
    ls = {"EUR": "-", "USD": "-", "EUR6M": "--", "USD3M": "--"}
    x = np.arange(12)
    for k in CURVES:
        a1.plot(x, (r[k] - 1) * 1e4, ls[k], color=cols[k], marker="o", markersize=4, linewidth=1.6, label=NICE[k])
    a1.axhline(0, color=INK, linewidth=0.8)
    a1.set_xticks(x)
    a1.set_xticklabels(s.pillar_tenors, fontsize=8)
    a1.set_xlabel("Simulation pillar (simulation.xml)", fontsize=10, color=INK)
    a1.set_ylabel("Change in discount factor (bp)", fontsize=10, color=INK)
    a1.set_title(f"Rate shock, {w['d1']} to {w['d2']}", fontsize=12, fontweight="bold", color=INK, pad=8)
    a1.legend(frameon=True, facecolor="white", edgecolor=EDGE, fontsize=8.5, loc="lower left")
    a1.set_ylim(-300, 60)
    a1.text(0.98, 0.97, f"USDEUR spot {(r['fx'] - 1) * 100:+.2f}%", transform=a1.transAxes, ha="right", va="top",
            fontsize=10, color=VAR99, fontweight="bold")

    # Right: the swap P&L, one factor at a time, then the interaction, then the forward
    style_ax(a2)
    order = ["FX spot", "USD discount", "EUR discount", "USD LIBOR 3M index", "EURIBOR 6M index"]
    SHORT = {"FX spot": "FX\nspot", "USD discount": "USD\ndisc.", "EUR discount": "EUR\ndisc.", "USD LIBOR 3M index": "USD 3M\nindex",
             "EURIBOR 6M index": "EUR 6M\nindex", "Interaction": "Inter-\naction", "Swap total": "Swap", "FX forward": "FX\nforward", "Portfolio": "Portfolio"}
    steps = [(k, att[k]) for k in order]
    interaction = w["manual_swap"] - sum(v for _, v in steps)
    steps.append(("Interaction", interaction))
    steps.append(("Swap total", None))
    steps.append(("FX forward", w["manual_fwd"]))
    steps.append(("Portfolio", None))
    run, xs = 0.0, np.arange(len(steps))
    for i, (name, v) in enumerate(steps):
        if v is None:
            a2.bar(i, run / 1e3, color=INK, width=0.62, zorder=3)
            a2.text(i, run / 1e3 - 25, f"{run / 1e3:,.0f}", ha="center", va="top", fontsize=8.5, color=INK, fontweight="bold")
        else:
            bottom = run
            run += v
            a2.bar(i, v / 1e3, bottom=bottom / 1e3, color=GREEN if v >= 0 else VAR99, width=0.62, zorder=3)
            ytxt = max(bottom, run) / 1e3 + 25 if v >= 0 else min(bottom, run) / 1e3 - 25
            a2.text(i, ytxt, f"{v / 1e3:+,.0f}", ha="center", va="bottom" if v >= 0 else "top", fontsize=8.5, color=INK)
    a2.axhline(0, color=INK, linewidth=0.8)
    a2.set_xticks(xs)
    a2.set_xticklabels([SHORT[n] for n, _ in steps], fontsize=8)
    a2.set_ylabel("10-day P&L (EUR thousands)", fontsize=10, color=INK)
    a2.set_title("Where the loss comes from (manual bump and reprice)", fontsize=12, fontweight="bold", color=INK, pad=8)
    a2.set_ylim(-1480, 350)
    fig.savefig(os.path.join(OUT, "bump_mechanics.png"), dpi=200, facecolor="white")
    plt.close(fig)
    print(f"bump mechanics: swap {w['manual_swap']:,.0f} fwd {w['manual_fwd']:,.0f} portfolio {w['manual']:,.0f}")


# --------------------------------------------------------------------------
def plot_tail(tot, summary):
    pnl = tot["PLAmount"].to_numpy() / 1000.0
    n = len(pnl)
    v95, v99 = ore_quantile(pnl, 0.05), ore_quantile(pnl, 0.01)
    es99 = pnl[pnl <= v99].mean()
    k99, k95 = math.ceil(0.01 * n), math.ceil(0.05 * n)
    srt = np.sort(pnl)
    sn = summary["sanity"]

    have_dirty = os.path.exists(os.path.join(DIRTY_DIR, "historical_PnL.csv"))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5), facecolor="white", layout="constrained",
                                 gridspec_kw={"width_ratios": [1.25, 1.0]})
    # Left: the worst 40 outcomes, ranked
    style_ax(a1)
    m = 40
    rank = np.arange(1, m + 1)
    loss = -srt[:m]
    colors = [VAR99 if r <= k99 else VAR95 if r <= k95 else TS_LINE for r in rank]
    a1.vlines(rank, 0, loss, color=colors, linewidth=1.6, zorder=2)
    a1.scatter(rank, loss, c=colors, s=26, zorder=3)
    a1.hlines(-v99, 0, m + 0.4, color=VAR99, linestyle="--", linewidth=1.3)
    a1.hlines(-v95, 0, m + 0.4, color=VAR95, linestyle="--", linewidth=1.3)
    a1.hlines(sn["param99"] / 1e3, 0, m + 0.4, color=INK, linestyle=":", linewidth=1.5)
    a1.hlines(sn["param95"] / 1e3, 0, m + 0.4, color=INK, linestyle=":", linewidth=1.5)
    a1.text(m + 0.4, -v99, f" 99% VaR (rank {k99}) {-v99:,.0f}k", color=VAR99, va="center", fontsize=8.5)
    a1.text(m + 0.4, -v95, f" 95% VaR (rank {k95}) {-v95:,.0f}k", color=VAR95, va="center", fontsize=8.5)
    a1.text(m + 0.4, sn["param99"] / 1e3, f" delta-normal 99% {sn['param99'] / 1e3:,.0f}k", color=INK, va="center", fontsize=8.5)
    a1.text(m + 0.4, sn["param95"] / 1e3, f" delta-normal 95% {sn['param95'] / 1e3:,.0f}k", color=INK, va="center", fontsize=8.5)
    a1.set_xlim(0, m + 12)
    a1.set_xlabel("Rank of the window by loss (1 = worst)", fontsize=10, color=INK)
    a1.set_ylabel("10-day loss (EUR thousands)", fontsize=10, color=INK)
    a1.set_title(f"VaR is an order statistic: the 99% tail is {k99} windows", fontsize=12, fontweight="bold",
                 color=INK, pad=8)

    # Right: clean against dirty
    style_ax(a2)
    bins = np.linspace(pnl.min() - 20, pnl.max() + 20, 45)
    a2.hist(pnl, bins=bins, histtype="stepfilled", color=HIST_FILL, edgecolor=HIST_EDGE, alpha=0.8, label="Clean")
    if have_dirty:
        d = window_table(DIRTY_DIR)["PLAmount"].to_numpy() / 1000.0
        a2.hist(d, bins=bins, histtype="step", color=VAR99, linewidth=1.6, label="Dirty (theta and cashflows)")
        a2.axvline(ore_quantile(d, 0.01), color=VAR99, linestyle="--", linewidth=1.2)
        a2.axvline(v99, color=HIST_EDGE, linestyle="--", linewidth=1.2)
        shift = np.mean(d - pnl)
        a2.text(0.03, 0.95, f"Average shift {shift:+.1f}k per window\n99% VaR {-v99:,.0f}k to {-ore_quantile(d, 0.01):,.0f}k",
                transform=a2.transAxes, va="top", fontsize=9, color=INK,
                bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=EDGE, alpha=0.95))
    a2.set_xlabel("10-day P&L (EUR thousands)", fontsize=10, color=INK)
    a2.set_ylabel("Windows per bin", fontsize=10, color=INK)
    a2.set_title("Clean against dirty P&L", fontsize=12, fontweight="bold", color=INK, pad=8)
    a2.legend(frameon=True, facecolor="white", edgecolor=EDGE, fontsize=9, loc="upper right")
    # Also save standalone figures so they can sit directly inside their respective sections
    fig_tr, ax_tr = plt.subplots(figsize=(7.5, 4.5), facecolor="white", layout="constrained")
    style_ax(ax_tr)
    ax_tr.vlines(rank, 0, loss, color=colors, linewidth=1.6, zorder=2)
    ax_tr.scatter(rank, loss, c=colors, s=26, zorder=3)
    ax_tr.hlines(-v99, 0, m + 0.4, color=VAR99, linestyle="--", linewidth=1.3)
    ax_tr.hlines(-v95, 0, m + 0.4, color=VAR95, linestyle="--", linewidth=1.3)
    ax_tr.hlines(sn["param99"] / 1e3, 0, m + 0.4, color=INK, linestyle=":", linewidth=1.5)
    ax_tr.hlines(sn["param95"] / 1e3, 0, m + 0.4, color=INK, linestyle=":", linewidth=1.5)
    ax_tr.text(m + 0.4, -v99, f" 99% VaR (rank {k99}) {-v99:,.0f}k", color=VAR99, va="center", fontsize=8.5)
    ax_tr.text(m + 0.4, -v95, f" 95% VaR (rank {k95}) {-v95:,.0f}k", color=VAR95, va="center", fontsize=8.5)
    ax_tr.text(m + 0.4, sn["param99"] / 1e3, f" delta-normal 99% {sn['param99'] / 1e3:,.0f}k", color=INK, va="center", fontsize=8.5)
    ax_tr.text(m + 0.4, sn["param95"] / 1e3, f" delta-normal 95% {sn['param95'] / 1e3:,.0f}k", color=INK, va="center", fontsize=8.5)
    ax_tr.set_xlim(0, m + 13)
    ax_tr.set_xlabel("Rank of the window by loss (1 = worst)", fontsize=10, color=INK)
    ax_tr.set_ylabel("10-day loss (EUR thousands)", fontsize=10, color=INK)
    ax_tr.set_title(f"VaR is an order statistic: the 99% tail is {k99} windows", fontsize=11, fontweight="bold",
                    color=INK, pad=8)
    fig_tr.savefig(os.path.join(OUT, "tail_ranked.png"), dpi=200, facecolor="white")
    plt.close(fig_tr)

    if have_dirty:
        fig_cd, ax_cd = plt.subplots(figsize=(6.5, 4.5), facecolor="white", layout="constrained")
        style_ax(ax_cd)
        ax_cd.hist(pnl, bins=bins, histtype="stepfilled", color=HIST_FILL, edgecolor=HIST_EDGE, alpha=0.8, label="Clean")
        ax_cd.hist(d, bins=bins, histtype="step", color=VAR99, linewidth=1.6, label="Dirty (theta and cashflows)")
        ax_cd.axvline(ore_quantile(d, 0.01), color=VAR99, linestyle="--", linewidth=1.2)
        ax_cd.axvline(v99, color=HIST_EDGE, linestyle="--", linewidth=1.2)
        ax_cd.text(0.03, 0.95, f"Average shift {shift:+.1f}k per window\n99% VaR {-v99:,.0f}k to {-ore_quantile(d, 0.01):,.0f}k",
                   transform=ax_cd.transAxes, va="top", fontsize=9, color=INK,
                   bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=EDGE, alpha=0.95))
        ax_cd.set_xlabel("10-day P&L (EUR thousands)", fontsize=10, color=INK)
        ax_cd.set_ylabel("Windows per bin", fontsize=10, color=INK)
        ax_cd.set_title("Clean against dirty P&L", fontsize=11, fontweight="bold", color=INK, pad=8)
        ax_cd.legend(frameon=True, facecolor="white", edgecolor=EDGE, fontsize=9, loc="upper right")
        fig_cd.savefig(os.path.join(OUT, "clean_vs_dirty.png"), dpi=200, facecolor="white")
        plt.close(fig_cd)

    fig.savefig(os.path.join(OUT, "var_tail.png"), dpi=200, facecolor="white")
    plt.close(fig)
    print(f"tail: rank99={k99} rank95={k95} dirty={'yes' if have_dirty else 'no'}")


def main():
    pnl_path = os.path.join(CLEAN_DIR, "historical_PnL.csv")
    if not os.path.exists(pnl_path):
        raise SystemExit("Run `python run_histsimvar.py` first.")
    tot = window_table(CLEAN_DIR)
    plot_distribution(tot)
    if not os.path.exists(SUMMARY):
        print("Run `python manual_bump.py` to get the bump and tail figures.")
        return
    with open(SUMMARY) as fh:
        summary = json.load(fh)
    plot_bump_mechanics(summary)
    plot_tail(tot, summary)


if __name__ == "__main__":
    main()
