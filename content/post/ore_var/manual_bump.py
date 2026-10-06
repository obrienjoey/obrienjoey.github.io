#!/usr/bin/env python
"""
Manual bump and reprice of a historical simulation window.

Rebuilds ORE's historical simulation P&L by hand for the two-trade book in
this post, using ORE only for the base-date inputs (pillar discount factors
and projected cashflows from Input/ore_base.xml). Everything after that is
plain numpy.

What it checks:
  1. Base NPVs against ORE's npv report.
  2. The worst 10-day window, trade by trade and curve by curve, against
     historical_PnL.csv and riskFactor_PnL.csv.
  3. All 715 windows against historical_PnL.csv, and the VaR/ES that follow.
  4. A delta-normal FX sanity check on the 99% VaR.

Run run_histsimvar.py first (it writes Output/HistSimVar). This script runs
Input/ore_base.xml itself if Output/Base is missing.

How a scenario row becomes a shock (confirmed by the replication below):
  * scenarios.csv holds absolute discount factors at the 12 pillars of
    simulation.xml for every historical date, and FX spot.
  * The shock for window (d1, d2) is the ratio of row d2 to row d1, applied
    to ORE's base value at the same pillar. Discount factors and FX spot
    both move multiplicatively. An additive shift of the discount factors
    does not reproduce ORE.
  * Between pillars the curve is log-linear in the discount factor, with
    DF(0) = 1 and a flat zero rate past 30Y.
  * Two more details have to match for the replication to be exact. USD flows
    convert to EUR at S * DF_EUR(spot) / DF_USD(spot) on the shocked curves, with
    spot 3 days out, so the 2W pillars move the P&L. Floating coupons project over
    the index value and end dates with the index spanning time (at-par coupons),
    not over the raw accrual dates.
"""

import datetime as dt
import json
import math
import os
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from var_common import CLEAN_DIR as VAR_DIR, HERE, ore_quantile, read_report

BASE_DIR = os.path.join(HERE, "Output", "Base")
ASOF = dt.date(2019, 12, 30)

# curve key -> (column in curves.csv, column prefix in scenarios.csv)
CURVES = {
    "EUR": ("EUR", "DiscountCurve/EUR"),
    "USD": ("USD", "DiscountCurve/USD"),
    "EUR6M": ("EUR-EURIBOR-6M", "IndexCurve/EUR-EURIBOR-6M"),
    "USD3M": ("USD-LIBOR-3M", "IndexCurve/USD-LIBOR-3M"),
}
NICE = {"EUR": "EUR discount", "USD": "USD discount",
        "EUR6M": "EURIBOR 6M index", "USD3M": "USD LIBOR 3M index", "fx": "FX spot"}
SWAP, FWD = "XCCY_Swap_EUR_USD", "FXFWD_EURUSD_10Y"


def ensure_base_outputs():
    if os.path.exists(os.path.join(BASE_DIR, "flows.csv")):
        return
    import ORE
    os.makedirs(BASE_DIR, exist_ok=True)
    params = ORE.Parameters()
    params.fromFile(os.path.join(HERE, "Input", "ore_base.xml"))
    ORE.OREApp(params, True).run()


def years(d):
    """Actual/365 time from the as-of date, as in the simulation market."""
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    return (d - ASOF).days / 365.0


def _qd(d):
    import ORE as ql
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    return ql.Date(d.day, d.month, d.year)


def _pd(q):
    return dt.date(q.year(), int(q.month()), q.dayOfMonth())


def _spot_date():
    """T+2 on the joint EUR/USD calendar."""
    import ORE as ql
    cal = ql.JointCalendar(ql.TARGET(), ql.UnitedStates(ql.UnitedStates.Settlement))
    return _pd(cal.advance(_qd(ASOF), 2, ql.Days))


def _projection_window(row):
    """Dates ORE projects a floating coupon over (at-par coupons, QuantLib's rule).

    From the coupon's fixing date, the index value date is fixing + the index's
    fixing days on its own calendar. The end is the accrual end shifted by the same
    number of days. The forward rate is (DF(value)/DF(end) - 1) / span, with span in
    the index day count, and the amount is notional * rate * accrual. Using the raw
    accrual dates instead is wrong by up to ~0.5% of the forward sensitivity.
    """
    import ORE as ql
    idx = ql.Euribor6M() if row["Currency"] == "EUR" else ql.USDLibor(ql.Period(3, ql.Months))
    value = idx.valueDate(_qd(row["fixingDate"]))
    cal = idx.fixingCalendar()
    end = cal.advance(cal.advance(_qd(row["AccrualEndDate"]), 0, ql.Days), idx.fixingDays(), ql.Days)
    return _pd(value), _pd(end), idx.dayCounter().yearFraction(value, end)


class Setup:
    """Base-date inputs read from ORE reports, plus the historical scenario deck."""

    def __init__(self):
        ensure_base_outputs()
        sim_cur_path = os.path.join(BASE_DIR, "simmarket_curves.csv")
        if os.path.exists(sim_cur_path):
            cur = pd.read_csv(sim_cur_path)
            self.pillar_tenors = list(cur["Tenor"])
            self.pillar_t = cur["Days"].to_numpy(float) / 365.0
            self.nodes_t = np.concatenate([[0.0], self.pillar_t])
            self.base_df = {k: cur[col].to_numpy(float) for k, (col, _) in CURVES.items()}
        else:
            cur = pd.read_csv(os.path.join(BASE_DIR, "curves.csv"))
            cur.columns = [c.lstrip("#") for c in cur.columns]
            self.pillar_dates = list(cur["Date"])
            self.pillar_tenors = list(cur["Tenor"])
            self.pillar_t = np.array([years(d) for d in self.pillar_dates])
            self.nodes_t = np.concatenate([[0.0], self.pillar_t])
            self.base_df = {k: cur[col].to_numpy(float) for k, (col, _) in CURVES.items()}

        fl = pd.read_csv(os.path.join(BASE_DIR, "flows.csv"))
        # Raw USDEUR spot quote. flows.csv shows 0.89310 instead, which already has the
        # spot-date adjustment baked in (see value()), so it is not the thing to shock.
        with open(os.path.join(HERE, "Input", "HistSimVar", "market.txt")) as fh:
            quote = [ln.split()[-1] for ln in fh if ln.startswith(f"{ASOF.isoformat()} FX/RATE/EUR/USD ")][0]
        self.fx0 = 1.0 / float(quote)
        # ORE converts USD to EUR at S * DF_EUR(spot) / DF_USD(spot), using the simulated
        # curves. Spot is T+2 on the joint EUR/USD calendar: 2020-01-02, 3 days out.
        self.spot_t = (_spot_date() - ASOF).days / 365.0
        # The cash-settled forward is built from portfolio.xml, not from the report:
        # the cashflow report shows its EUR leg in USD at the forward rate, which is
        # the wrong thing to shock. The swap legs come straight from the report.
        f = fl[fl["#TradeId"] == SWAP].reset_index(drop=True)
        root = ET.parse(os.path.join(HERE, "Input", "HistSimVar", "portfolio.xml")).getroot()
        fwd = [t for t in root.iter("Trade") if t.get("id") == FWD][0].find("FxForwardData")
        fwd_pay = fwd.findtext("ValueDate")
        fwd_legs = [(fwd.findtext("BoughtCurrency"), float(fwd.findtext("BoughtAmount"))),
                    (fwd.findtext("SoldCurrency"), -float(fwd.findtext("SoldAmount")))]
        n_fwd = len(fwd_legs)
        pad = np.zeros(n_fwd)

        self.is_usd = np.concatenate([(f["Currency"] == "USD").to_numpy(), [c == "USD" for c, _ in fwd_legs]])
        self.pay_t = np.concatenate([[years(d) for d in f["PayDate"]], [years(fwd_pay)] * n_fwd])
        self.amount = np.concatenate([f["Amount"].to_numpy(float), [a for _, a in fwd_legs]])
        self.proj = np.concatenate([(f["FlowType"] == "InterestProjected").to_numpy(), [False] * n_fwd])
        coupon = np.concatenate([f["Coupon"].fillna(0).to_numpy(float), pad])
        self.accrual = np.concatenate([f["Accrual"].fillna(0).to_numpy(float), pad])
        # Forward window of each projected coupon: the index's own value date and end date,
        # not the accrual dates, plus the index day-count spanning time. See _projection_window.
        win = [_projection_window(r) if r["FlowType"] == "InterestProjected" else (0.0, 0.0, 1.0)
               for _, r in f.iterrows()]
        self.start_t = np.concatenate([[years(a) if a else 0.0 for a, _, _ in win], pad])
        self.end_t = np.concatenate([[years(b) if b else 0.0 for _, b, _ in win], pad])
        self.span = np.concatenate([[s for _, _, s in win], np.ones(n_fwd)])
        # Signed notional: amount = signed_n * coupon * accrual. Recovered from the
        # base report so the payer/receiver sign convention is ORE's own.
        with np.errstate(divide="ignore", invalid="ignore"):
            self.signed_n = np.where(self.proj, self.amount / (coupon * self.accrual), 0.0)
        self.trade = np.concatenate([f["#TradeId"].to_numpy(), [FWD] * n_fwd])

        sc = pd.read_csv(os.path.join(HERE, "Input", "HistSimVar", "scenarios.csv"))
        sc["Date"] = pd.to_datetime(sc["Date"], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")
        self.scen = sc.set_index("Date")

    # -- curves -----------------------------------------------------------
    def df(self, pillar_df, t):
        """Log-linear DF interpolation with DF(0)=1 and flat zero extrapolation."""
        log_nodes = np.log(np.concatenate([[1.0], pillar_df]))
        t = np.asarray(t, dtype=float)
        inside = np.interp(t, self.nodes_t, log_nodes)
        z_last = -log_nodes[-1] / self.nodes_t[-1]
        return np.exp(np.where(t > self.nodes_t[-1], -z_last * t, inside))

    # -- shocks -----------------------------------------------------------
    def ratios(self, d1, d2):
        """Pillar ratios row(d2)/row(d1) for every curve, and the FX ratio."""
        r = {}
        for k, (_, pref) in CURVES.items():
            cols = [f"{pref}/{i}" for i in range(12)]
            r[k] = self.scen.loc[d2, cols].to_numpy(float) / self.scen.loc[d1, cols].to_numpy(float)
        r["fx"] = float(self.scen.loc[d2, "FXSpot/USDEUR/0"] / self.scen.loc[d1, "FXSpot/USDEUR/0"])
        return r

    def market(self, d1=None, d2=None, only=None, pillar=None):
        """Shocked market state.

        only:   iterable of keys ('EUR','USD','EUR6M','USD3M','fx') to shock; others stay at base.
        pillar: (curve_key, i) to shock a single pillar only, as ORE does for risk factor attribution.
        """
        dfs = {k: v.copy() for k, v in self.base_df.items()}
        fx = self.fx0
        if d1 is None:
            return dfs, fx
        r = self.ratios(d1, d2)
        keys = set(CURVES) | {"fx"} if only is None else set(only)
        for k in CURVES:
            if pillar is not None:
                if k == pillar[0]:
                    dfs[k][pillar[1]] *= r[k][pillar[1]]
            elif k in keys:
                dfs[k] = dfs[k] * r[k]
        if (pillar is not None and pillar[0] == "fx") or (pillar is None and "fx" in keys):
            fx = self.fx0 * r["fx"]
        return dfs, fx

    # -- pricing ----------------------------------------------------------
    def value(self, market):
        dfs, fx = market
        amt = self.amount.copy()
        for k, idx in (("EUR6M", ~self.is_usd), ("USD3M", self.is_usd)):
            m = self.proj & idx
            if m.any():
                d_s = self.df(dfs[k], self.start_t[m])
                d_e = self.df(dfs[k], self.end_t[m])
                amt[m] = self.signed_n[m] * self.accrual[m] * (d_s / d_e - 1.0) / self.span[m]
        disc = np.where(self.is_usd, self.df(dfs["USD"], self.pay_t), self.df(dfs["EUR"], self.pay_t))
        # fx is the spot quote. ORE converts at the spot-date-adjusted rate on the same curves,
        # so the 2W pillars of both discount curves move every USD flow.
        t = self.spot_t
        fx_eff = fx * self.df(dfs["EUR"], t) / self.df(dfs["USD"], t)
        pv = amt * disc * np.where(self.is_usd, fx_eff, 1.0)
        return {t: float(pv[self.trade == t].sum()) for t in (SWAP, FWD)}


def window_pnl(s, base, d1, d2, **kw):
    v = s.value(s.market(d1, d2, **kw))
    return {t: v[t] - base[t] for t in v}


def load_ore_pnl():
    d = pd.read_csv(os.path.join(VAR_DIR, "historical_PnL.csv"))
    d.columns = [c.lstrip("#") for c in d.columns]
    d = d[(d["RiskClass"] == "All") & (d["RiskType"] == "All")]
    return d.pivot_table(index=["PLDate1", "PLDate2"], columns="Portfolio", values="PLAmount", aggfunc="sum")


def load_ore_factors(d1, d2):
    r = pd.read_csv(os.path.join(VAR_DIR, "riskFactor_PnL.csv"))
    r.columns = [c.lstrip("#") for c in r.columns]
    return r[(r["PLDate1"] == d1) & (r["PLDate2"] == d2)]


def main():
    s = Setup()
    base = s.value(s.market())
    npv = pd.read_csv(os.path.join(BASE_DIR, "npv.csv"))
    npv.columns = [c.lstrip("#") for c in npv.columns]
    ore_base = npv.set_index("TradeId")["NPV(Base)"].to_dict()
    out = {"base": {t: {"manual": base[t], "ore": ore_base[t]} for t in base}}

    print("1. Base NPV (EUR)")
    for t in base:
        print(f"   {t:20s} manual {base[t]:>14,.0f}   ORE {ore_base[t]:>14,.0f}")

    # 3. All windows
    ore = load_ore_pnl()
    rows = []
    for (d1, d2), r in ore.iterrows():
        p = window_pnl(s, base, d1, d2)
        rows.append({"PLDate1": d1, "PLDate2": d2,
                     "manual_swap": p[SWAP], "manual_fwd": p[FWD],
                     "ore_swap": r[SWAP], "ore_fwd": r[FWD]})
    cmp_ = pd.DataFrame(rows)
    cmp_["manual"] = cmp_["manual_swap"] + cmp_["manual_fwd"]
    cmp_["ore"] = cmp_["ore_swap"] + cmp_["ore_fwd"]
    cmp_["err"] = cmp_["manual"] - cmp_["ore"]
    cmp_.to_csv(os.path.join(BASE_DIR, "manual_vs_ore.csv"), index=False)
    n = len(cmp_)
    out["windows"] = {"n": n, "max_abs_err": float(cmp_["err"].abs().max()),
                      "mean_abs_err": float(cmp_["err"].abs().mean())}
    print(f"\n2. All {n} windows, portfolio P&L, manual minus ORE (EUR)")
    print(f"   mean |error| {cmp_['err'].abs().mean():,.0f}   max |error| {cmp_['err'].abs().max():,.0f}")
    for q in (0.05, 0.01):
        vm, vo = ore_quantile(cmp_["manual"], q), ore_quantile(cmp_["ore"], q)
        em = cmp_["manual"][cmp_["manual"] <= vm].mean()
        eo = cmp_["ore"][cmp_["ore"] <= vo].mean()
        out[f"var{int((1 - q) * 100)}"] = {"manual": -vm, "ore": -vo, "es_manual": -em, "es_ore": -eo}
        print(f"   {int((1 - q) * 100)}% VaR manual {-vm:>10,.0f}  ORE {-vo:>10,.0f}   ES manual {-em:>10,.0f}  ORE {-eo:>10,.0f}")

    # 2. Worst window
    w = cmp_.loc[cmp_["ore"].idxmin()]
    d1, d2 = w["PLDate1"], w["PLDate2"]
    r = s.ratios(d1, d2)
    out["worst"] = {"d1": d1, "d2": d2, "manual": float(w["manual"]), "ore": float(w["ore"]),
                    "manual_swap": float(w["manual_swap"]), "ore_swap": float(w["ore_swap"]),
                    "manual_fwd": float(w["manual_fwd"]), "ore_fwd": float(w["ore_fwd"])}
    print(f"\n3. Worst window {d1} to {d2}")
    print(f"   FX ratio {r['fx']:.5f}  ({(r['fx'] - 1) * 100:+.2f}% on USDEUR)")
    print("   pillar DF ratios minus 1, in bp:")
    print("   " + "tenor".ljust(8) + "".join(NICE[k].rjust(22) for k in CURVES))
    for i, ten in enumerate(s.pillar_tenors):
        print("   " + ten.ljust(8) + "".join(f"{(r[k][i] - 1) * 1e4:>22.1f}" for k in CURVES))
    print(f"   {'':8s}{'manual':>14s}{'ORE':>14s}")
    print(f"   {SWAP:20s}{w['manual_swap']:>14,.0f}{w['ore_swap']:>14,.0f}")
    print(f"   {FWD:20s}{w['manual_fwd']:>14,.0f}{w['ore_fwd']:>14,.0f}")
    print(f"   {'portfolio':20s}{w['manual']:>14,.0f}{w['ore']:>14,.0f}")

    # one factor at a time, aggregated by curve, against riskFactor_PnL.csv
    ore_f = load_ore_factors(d1, d2)
    ore_f = ore_f[ore_f["TradeId"] == SWAP].copy()
    ore_f["curve"] = ore_f["RiskFactor"].str.rsplit("/", n=1).str[0]
    ore_by_curve = ore_f.groupby("curve")["PLAmount"].sum()
    key_to_ore = {"EUR": "DiscountCurve/EUR", "USD": "DiscountCurve/USD",
                  "EUR6M": "IndexCurve/EUR-EURIBOR-6M", "USD3M": "IndexCurve/USD-LIBOR-3M",
                  "fx": "FXSpot/USDEUR"}
    attrib = []
    for k in list(CURVES) + ["fx"]:
        if k == "fx":
            m = window_pnl(s, base, d1, d2, only=["fx"])[SWAP]
        else:
            m = sum(window_pnl(s, base, d1, d2, pillar=(k, i))[SWAP] for i in range(12))
        attrib.append({"factor": NICE[k], "manual": m, "ore": float(ore_by_curve.get(key_to_ore[k], 0.0))})
    attrib = pd.DataFrame(attrib)
    out["attribution"] = attrib.to_dict("records")
    print("\n4. Swap P&L by risk factor, one at a time (EUR)")
    print(f"   {'':22s}{'manual':>12s}{'ORE':>12s}")
    for _, a in attrib.iterrows():
        print(f"   {a['factor']:22s}{a['manual']:>12,.0f}{a['ore']:>12,.0f}")
    print(f"   {'sum of factors':22s}{attrib['manual'].sum():>12,.0f}{attrib['ore'].sum():>12,.0f}")
    print(f"   {'all factors together':22s}{w['manual_swap']:>12,.0f}{w['ore_swap']:>12,.0f}")

    # 5. Sanity check
    h = 0.01
    fx_up = s.value((s.base_df, s.fx0 * (1 + h)))
    fx_dn = s.value((s.base_df, s.fx0 * (1 - h)))
    expo = sum(fx_up[t] - fx_dn[t] for t in base) / (2 * h)   # EUR P&L per unit log move in USDEUR
    fx_hist = np.array([sum(window_pnl(s, base, a, b, only=["fx"]).values()) for a, b in zip(cmp_["PLDate1"], cmp_["PLDate2"])])
    rates_hist = np.array([sum(window_pnl(s, base, a, b, only=list(CURVES)).values()) for a, b in zip(cmp_["PLDate1"], cmp_["PLDate2"])])
    fx_series = s.scen["FXSpot/USDEUR/0"]
    window = fx_series.loc[cmp_["PLDate1"].min():cmp_["PLDate2"].max()]
    daily = np.log(window).diff().dropna()
    ten = np.array([math.log(s.scen.loc[b, "FXSpot/USDEUR/0"] / s.scen.loc[a, "FXSpot/USDEUR/0"])
                    for a, b in zip(cmp_["PLDate1"], cmp_["PLDate2"])])
    sig10 = ten.std(ddof=1)
    sn_sqrt = daily.std(ddof=1) * math.sqrt(10)
    z99, z95 = 2.3263, 1.6449
    out["sanity"] = {
        "fx_exposure_eur": expo, "sigma_daily": float(daily.std(ddof=1)), "sigma_10d": float(sig10),
        "sigma_10d_sqrt": float(daily.std(ddof=1) * math.sqrt(10)),
        "param99": z99 * sig10 * abs(expo), "param95": z95 * sig10 * abs(expo),
        "param99_sqrt": z99 * sn_sqrt * abs(expo), "param95_sqrt": z95 * sn_sqrt * abs(expo),
        "fx_only99": -ore_quantile(fx_hist, 0.01), "fx_only95": -ore_quantile(fx_hist, 0.05),
        "rates_only99": -ore_quantile(rates_hist, 0.01), "rates_only95": -ore_quantile(rates_hist, 0.05),
        "total99": out["var99"]["manual"], "total95": out["var95"]["manual"],
    }
    sn = out["sanity"]
    cmp_["fx_only"], cmp_["rates_only"] = fx_hist, rates_hist
    cmp_.to_csv(os.path.join(BASE_DIR, "manual_vs_ore.csv"), index=False)
    print("\n5. Sanity check")
    print(f"   Net FX exposure: EUR {expo:,.0f} of P&L per 100% move in USDEUR (EUR {expo * 0.01:,.0f} per 1%)")
    print(f"   USDEUR daily vol {sn['sigma_daily'] * 100:.3f}%, 10-day vol {sn['sigma_10d'] * 100:.3f}% "
          f"(daily x sqrt(10) = {sn['sigma_10d_sqrt'] * 100:.3f}%)")
    print(f"   Delta-normal FX VaR   95% {sn['param95']:>10,.0f}   99% {sn['param99']:>10,.0f}")
    print(f"   Historical FX-only    95% {sn['fx_only95']:>10,.0f}   99% {sn['fx_only99']:>10,.0f}")
    print(f"   Historical rates-only 95% {sn['rates_only95']:>10,.0f}   99% {sn['rates_only99']:>10,.0f}")
    print(f"   Historical total      95% {sn['total95']:>10,.0f}   99% {sn['total99']:>10,.0f}")

    with open(os.path.join(BASE_DIR, "manual_bump_summary.json"), "w") as fh:
        json.dump(out, fh, indent=2, default=float)


if __name__ == "__main__":
    main()
