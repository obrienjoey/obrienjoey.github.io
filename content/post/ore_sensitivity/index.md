---
title: "Sensitivity Analysis in ORE"
subtitle: "Zero-rate deltas to tradeable par risk in ORE, verified by an independent 15Y market-quote bump"
summary: "Run ORE's native zero-domain interest-rate sensitivities for a single-curve EUR-ESTER OIS, then follow the Jacobian par conversion that maps those deltas onto the liquid OIS quotes a trader can actually bump. Close the loop with an independent 15Y manual bump-and-reval: a ±1bp bump of the actual OIS quote whose re-valued NPV lands within 0.7% of the par table's total. Includes both config passes, the Jacobian matrix, cleaned zero- and par-domain tables, and the finite-difference check."
date: 2026-08-25T00:00:00Z
draft: false
tags: ["ORE", "quant finance", "interest rates", "sensitivity", "Risk", "Python"]
math: true
series: ["ORE Fundamentals"]
---

Once you can price a portfolio in Open Source Risk Engine (ORE), the next step is measuring its risk. Sensitivity analysis tracks how portfolio value (NPV) shifts when market risk factors (rates, FX, volatilities) move by a small amount, and these numbers are the raw inputs for fundamental risk calculations. Having supported clients through vendor replacements, we have seen first-hand that sensitivity reconciliation is one of the harder steps of any migration: the figures are dense, easy to get subtly wrong, and every downstream risk metric inherits any error that slips in.

Because ORE is entirely open-source, none of this needs to be taken on faith. Rather than treating the sensitivity engine as another "black box", we can inspect every shift, conversion weight, and report it produces. In this post, we pull from ORE's own [MarketRisk examples](https://github.com/OpenSourceRisk/Engine/tree/master/Examples/MarketRisk) to walk through the full pipeline from zero rates to par rates. We run the native zero-domain sensitivity analytic on a single-curve teaching trade, inspect `sensitivity.csv`, and examine the output: a delta per zero-rate grid tenor split between discount and index factors. Next, we convert those zero-domain deltas into tradeable par-domain risk using ORE's Jacobian par conversion: the configuration, the Jacobian matrix itself, and the resulting `parsensitivity.csv` table. Finally, we close the loop with an independent check: bump the 15Y OIS market quote by 1 bp, re-value the trade from scratch, and compare the observed NPV change against the par table.

> ### Walkthrough Objectives
> In this guide, we will:
> 1. Configure the simulation market (`simulation.xml`) and sensitivity analytic (`sensitivity.xml`) for zero-domain output on a single-curve EUR-ESTER OIS.
> 2. Turn on ORE's Jacobian par conversion to produce `parsensitivity.csv`, `jacobi.csv`, and `jacobi_inverse.csv`.
> 3. Verify the par table independently by bumping the 15Y OIS quote ±1 bp and repricing the trade from scratch.
>
> All scripts and configuration files used in this guide are available for download in the resources section below.

---

## 1. The single-curve teaching trade

In production markets, interest rate swaps frequently use dual-curve setups (such as EUR-ESTER discounting with EURIBOR forecasting). While standard for pricing, dual curves complicate sensitivity analysis because the curves are coupled during calibration: shifting one market rate moves discounting and forecasting simultaneously, making the split between the `DiscountCurve` and `IndexCurve` factors ORE reports harder to isolate.

To keep the mechanics clear, we use a single-curve EUR-ESTER OIS where discounting and forecasting reference the same `EUR-ESTER` curve (following the single-curve principles explored in our [curve-bootstrapping post](/post/ore_sofr_bootstrap/)). The trade started on 2023-02-21 and matures on 2043-02-21, a 20-year tenor valued as of 2025-02-10 on 10,000,000 EUR notional. We receive 2.1% fixed annually on an `A360` day counter and pay the EUR-ESTER float annually, also `A360`, with one fixing day.

Because the trade is linear, the sensitivity computed here is delta: the first-order change in NPV for a 1 bp move in a rate. Vega (volatility sensitivity) applies to non-linear trades and will be covered in a later post.

Keeping a single curve makes the discount-versus-index factor split straightforward to interpret. Even though both factors resolve to the same underlying market curve, ORE reports them separately.

---

## 2. Config pass 1: zero-domain sensitivity setup

Running sensitivities in ORE requires two configurations alongside the portfolio: the simulation market (the risk-factor grid) and the sensitivity analytic (which factors to shift and by how much). The complete files are included in the bundle ([download below](#summary-and-code)); here is pass 1 for zero-domain output.

### Simulation market (`simulation.xml`)

Before running risk calculations, ORE expresses the market as a simulation market snapshot. Building the full market repeatedly is computationally expensive (bootstrapping curves, building volatility surfaces, and linking handles). In a sensitivity run with dozens of factor shifts, ORE builds the market once and takes a static snapshot. Shifting a factor then nudges a single grid node while holding the rest of the snapshot constant.

ORE evaluates discount factors at each grid tenor and rebuilds the curve with anchors at those points. Each anchor becomes a shiftable risk factor. That grid is configured in `simulation.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<Simulation>
  <Market>
    <BaseCurrency>EUR</BaseCurrency>
    <Currencies>
      <Currency>EUR</Currency>
    </Currencies>
    <YieldCurves>
      <Configuration>
        <Tenors>6M,1Y,2Y,3Y,5Y,7Y,10Y,15Y,20Y,30Y</Tenors>
        <Interpolation>LogLinear</Interpolation>
        <Extrapolation>Y</Extrapolation>
      </Configuration>
    </YieldCurves>
    <Indices>
      <Index>EUR-ESTER</Index>
    </Indices>
  </Market>
</Simulation>
```

Here is what each block configures:

* **`BaseCurrency`**: The base currency of the snapshot (`EUR`), anchoring discounting and any FX risk factors.
* **`Currencies`**: The currencies included in the simulation market. Only `EUR` is needed here since the trade discounts and forecasts on `EUR-ESTER`.
* **`YieldCurves > Configuration`**: How yield curves are represented on the grid:
  * **`Tenors`**: The zero-rate grid (`6M,1Y,2Y,3Y,5Y,7Y,10Y,15Y,20Y,30Y`). Shifts apply only at these tenors.
  * **`Interpolation`**: How curves interpolate between grid nodes. `LogLinear` (piecewise-constant forward rates) is standard for OIS curves. ORE supports `LogLinear` or `LinearZero`.
  * **`Extrapolation`**: Curve behaviour past the final tenor (`FlatFwd` or `FlatZero`). The legacy boolean `Y` maps to `FlatFwd` with a log warning. For this trade, whose final cash flow is at 20Y (inside the 30Y grid), extrapolation does not trigger.
* **`Indices`**: The forecast indices tracked as risk factors (`EUR-ESTER`). Each index becomes an independent risk factor (`IndexCurve/EUR-ESTER`).

Three details about this snapshot matter here:

1. It re-expresses curves on a grid rather than re-bootstrapping them. The curves originate from `marketdata.csv` and `curveconfig.xml`. The simulation market only changes where points are sampled and how they interpolate.
2. The grid defines the universe of shifts. The sensitivity analytic shifts only the tenors defined here, so `ShiftTenors` in `sensitivity.xml` must match this grid.
3. The file is shared across analytics. The same `simulation.xml` feeds both sensitivity analysis (`marketConfigFile`) and historical VaR (`simulationConfigFile`).

### Sensitivity analytic (`sensitivity.xml`)

`sensitivity.xml` specifies which factors to shift and the shift size. For zero-domain output, we declare both the discount curve and the forecast index with an absolute 1 bp shift (`ShiftSize` of `0.0001`):

```xml
<?xml version="1.0" encoding="utf-8"?>
<SensitivityAnalysis>
  <DiscountCurves>
    <DiscountCurve ccy="EUR">
      <ShiftType>Absolute</ShiftType>
      <ShiftSize>0.0001</ShiftSize>
      <ShiftTenors>6M,1Y,2Y,3Y,5Y,7Y,10Y,15Y,20Y,30Y</ShiftTenors>
    </DiscountCurve>
  </DiscountCurves>
  <IndexCurves>
    <IndexCurve index="EUR-ESTER">
      <ShiftType>Absolute</ShiftType>
      <ShiftSize>0.0001</ShiftSize>
      <ShiftTenors>6M,1Y,2Y,3Y,5Y,7Y,10Y,15Y,20Y,30Y</ShiftTenors>
    </IndexCurve>
  </IndexCurves>
</SensitivityAnalysis>
```

{{< callout type="info" title="ParConversion in the shipped files" >}}
The downloadable `sensitivity.xml` includes a `<ParConversion>` block, and `ore.xml` includes `parSensitivity=Y`. This block does not affect `sensitivity.csv`. We activate it in [config pass 2](#6-config-pass-2-turning-on-par-conversion) to generate `parsensitivity.csv`.
{{< /callout >}}

### Wiring it up (`ore.xml`)

In `ore.xml`, we activate the sensitivity analytic and specify the input and output filenames:

```xml
<Analytic type="sensitivity">
  <Parameter name="active">Y</Parameter>
  <Parameter name="marketConfigFile">simulation.xml</Parameter>
  <Parameter name="sensitivityConfigFile">sensitivity.xml</Parameter>
  <Parameter name="sensitivityOutputFile">sensitivity.csv</Parameter>
  <Parameter name="outputSensitivityThreshold">0.000001</Parameter>
</Analytic>
```

`outputSensitivityThreshold` filters the output: any factor whose delta is smaller than `0.000001` in absolute value is dropped from `sensitivity.csv`. Every tenor on this trade is comfortably above that bar; on larger portfolios the same setting keeps the file down to the rows that matter.

Running `run_sensitivity.py` executes ORE and generates `Output/sensitivity.csv`.

---

## 3. Reading the output: risk factors and units

`sensitivity.csv` contains one row per (factor, tenor) pair. Because we are using a single curve, both `DiscountCurve/EUR` and `IndexCurve/EUR-ESTER` reference the same underlying curve, but ORE tracks them separately:

* **`DiscountCurve/EUR` delta**: Sensitivity of NPV to a shift in the discounting zero rate, $\frac{\partial \text{NPV}}{\partial r_{\text{disc}}}$.
* **`IndexCurve/EUR-ESTER` delta**: Sensitivity of NPV to a shift in the forecasting zero rate, $\frac{\partial \text{NPV}}{\partial r_{\text{forecast}}}$ (used to project floating cash flows).

Factor names follow the pattern `Handle/Name/Index/Tenor`, such as `DiscountCurve/EUR/7/15Y` and `IndexCurve/EUR-ESTER/7/15Y`. The middle `Index` field is the zero-based position of that tenor in the simulation-market grid: `7` means the 8th pillar, since the grid `6M,1Y,2Y,3Y,5Y,7Y,10Y,15Y,20Y,30Y` is numbered 0 through 9 and 15Y falls at position 7.

**Units**: With `<ShiftType>Absolute</ShiftType>` and `ShiftSize` set to `0.0001` (1 bp), each delta value represents the EUR change in NPV per 1 bp absolute shift in that zero rate.

One parameter you will not find in our `sensitivity.xml` is `<ShiftScheme>`, which selects the finite-difference method (`Forward`, `Backward`, or `Central`) and defaults to `Forward`. The default suits us for raw zero sensitivities. `Central` averages up and down shifts to cancel second-order curvature, requiring two repricings per factor; we examine central differences in [section 9](#verification-bump-and-reval).

A quick orientation on the raw file before the cleaned tables: `sensitivity.csv` carries ten columns (`TradeId`, `IsPar`, `Factor_1`, `ShiftSize_1`, `Factor_2`, `ShiftSize_2`, `Currency`, `Base NPV`, `Delta`, `Gamma`) with one row per trade and factor. `Base NPV` repeats the unshifted trade value on every row, and the paired `Factor_2`/`ShiftSize_2` columns are reserved for cross-gamma terms, where ORE shifts two factors at once. With a single trade and one factor per row, those extra columns are constant or empty here, so the tables in this post show the `Factor` and `Delta` columns only. A sample, showing both factors at three tenors:

| Factor | Delta (EUR) |
|---|---|
| `DiscountCurve/EUR/0/6M` | 0.29 |
| `IndexCurve/EUR-ESTER/0/6M` | 4.37 |
| `DiscountCurve/EUR/1/1Y` | 9.28 |
| `IndexCurve/EUR-ESTER/1/1Y` | -12.99 |
| `DiscountCurve/EUR/7/15Y` | 198.33 |
| `IndexCurve/EUR-ESTER/7/15Y` | -7030.45 |

This XML schema extends to other asset classes with minimal changes. ORE's standard `SensiSmile` example ([`Examples/MarketRisk/Input/SensiSmile/sensitivity.xml`](https://github.com/OpenSourceRisk/Engine/blob/master/Examples/MarketRisk/Input/SensiSmile/sensitivity.xml)) applies the same structure to FX spots, swaption and cap/floor volatility surfaces, credit curves, and equity prices. Shocking an FX rate, for instance, needs only a single extra block declaring a 1% relative move on EURUSD:

```xml
<FxSpots>
  <FxSpot ccypair="EURUSD">
    <ShiftType>Relative</ShiftType>
    <ShiftSize>0.01</ShiftSize>
  </FxSpot>
</FxSpots>
```

No `<ShiftTenors>` is required here because a spot is a single node rather than a curve, and the resulting delta is the base-currency NPV change per 1% move in the rate. One naming detail: ORE orders each pair with the simulation market's base currency last, so in our EUR-based setup a USD shock is reported as the factor `FXSpot/USDEUR/0/spot` in `sensitivity.csv` (`EURUSD` would appear with a USD base currency). The simulation market needs no matching block: FX spot factors are inferred from the `<Currencies>` list, so adding `USD` alongside `EUR` in `simulation.xml` brings the pair into play.

---

## 4. Zero-domain results: cleaned table and risk shape

Because both factors share one underlying curve in reality, shifting the physical rate moves discounting and forecasting together. The combined delta per tenor is the algebraic sum of the discount and index deltas:

| Tenor | Discount delta (EUR) | Index delta (EUR) | Total (EUR) |
|---|---|---|---|
| 6M | 0.29 | 4.37 | 4.66 |
| 1Y | 9.28 | -12.99 | -3.71 |
| 2Y | -0.42 | -28.04 | -28.46 |
| 3Y | -9.44 | -105.54 | -114.98 |
| 5Y | -3.02 | -199.66 | -202.68 |
| 7Y | 21.04 | -343.29 | -322.25 |
| 10Y | 117.40 | -788.31 | -670.91 |
| 15Y | 198.33 | -7,030.45 | -6,832.12 |
| 20Y | 31.01 | -5,539.49 | -5,508.48 |

### Risk shape

Three observations stand out:

1. Risk concentrates at the long end. The largest negative deltas are at 15Y and 20Y, near the swap maturity where cash-flow weights are greatest. Because the swap terminates at 20Y, ORE reports no 30Y sensitivity.
2. The receiver loses value when rates rise. The trade receives fixed and pays floating; higher interest rates increase floating payments, reducing NPV.
3. The index factor dominates, while discounting partially offsets. At 15Y, the index delta is `-7,030.45` EUR compared to `+198.33` EUR for discounting. Forecasting floating cash flows accounts for the majority of the risk on this receiver swap.

{{< callout type="info" title="Discount vs Index on a single curve" >}}
The discount and index columns represent two components of the same `EUR-ESTER` curve. Adding them together gives the total sensitivity to a single physical rate move. On a multi-curve portfolio, the same separation lets you isolate basis risk.
{{< /callout >}}

---

## 5. Converting zero deltas into hedge instructions

A zero-domain table answers the modeller's question, which grid node moved, but not the trader's: what do I buy or sell? Zero rates are interpolated constructions, not instruments anyone can trade. To hedge risk in the market, desks trade liquid par instruments like OIS swaps, so the risk has to be re-expressed in their terms before it becomes an instruction.

This zero-to-par step exists because a zero rate on the simulation grid is an interpolated construction, not a quote anyone can trade. It is a rates-curve problem, not a general one. For risk factors that are the traded quote themselves, such as an FX spot, an equity price, or a commodity price, shifting the handle moves exactly the instrument a desk would hedge, so the raw delta in `sensitivity.csv` already reads as a par bump and no Jacobian is involved. The conversion below applies only to the factor types ORE can rebuild as par instruments: yield, credit, and inflation curves and cap/floor volatilities.

Directly bumping every par quote in the bootstrap and repricing the portfolio would be slow on large books, requiring a full curve rebuild per quote per trade. Instead, ORE computes a linear change of basis using the Jacobian matrix ($J$). The Jacobian maps zero-rate shifts to par-rate shifts, allowing quick conversion of zero sensitivities into par sensitivities.

---

## 6. Config pass 2: turning on par conversion

Generating `parsensitivity.csv`, `jacobi.csv`, and `jacobi_inverse.csv` requires adding a `<ParConversion>` block to each factor in `sensitivity.xml` and setting `parSensitivity=Y` in `ore.xml`.

### Extending `sensitivity.xml`

We add a `<ParConversion>` block to both `DiscountCurve/EUR` and `IndexCurve/EUR-ESTER`:

```xml
<ParConversion>
  <Instruments>OIS,OIS,OIS,OIS,OIS,OIS,OIS,OIS,OIS,OIS</Instruments>
  <SingleCurve>true</SingleCurve>
  <Conventions>
    <Convention id="OIS">EUR-ESTER-OIS</Convention>
  </Conventions>
</ParConversion>
```

* **`Instruments`**: Ten `OIS` tokens corresponding to the ten simulation grid tenors (`6M` through `30Y`).
* **`SingleCurve`**: Setting this to `true` prices the par instruments off the same `EUR-ESTER` curve used for discounting.
* **`Conventions`**: Maps the `OIS` token to the `EUR-ESTER-OIS` convention defined in `conventions.xml` (annual fixed leg, `A360`, modified following).

### Available instrument types

For interest rate curve factors, `<Instruments>` supports these contract types:

| Token | Par instrument built by ORE | Supported factors |
|---|---|---|
| `OIS` | Overnight-indexed swap on the specified index | Discount, index, yield curves |
| `IRS` | Fixed-vs-floating swap on an Ibor index | Discount, index, yield curves |
| `DEP` | Zero-coupon deposit | Discount, index, yield curves |
| `FRA` | Forward rate agreement | Discount, index, yield curves |
| `TBS` | Tenor basis swap (such as 6M vs 3M) | Discount, index, yield curves |
| `XBS` | Cross-currency basis swap | Discount, yield curves |
| `FXF` | FX forward | Discount curves only |

Other factor families carry their own par instruments: credit curve factors accept any code and interpret it as a CDS; zero inflation index curves build CPI swaps; year-on-year inflation curves and their cap/floor volatilities use `ZIS` or `YYS`; and cap/floor volatility factors use a flat `CapFloor`, where an overnight-indexed underlying also needs a `<RateComputationPeriod>`.

Instrument codes can also carry an arbitrary suffix that binds them to different conventions of the same type: listing `FRA1,FRA2` prices those tenors off conventions `FRA1` and `FRA2` respectively.

Rules for configuring par instruments:

* Token and convention types must align. `OIS` requires an `<OIS>` convention, `IRS` requires `<Swap>`, `DEP` requires `<Deposit>`, `FRA` requires `<FRA>`, `TBS` requires `<TenorBasisSwap>`, `XBS` requires `<CrossCurrencyBasis>`, and `FXF` requires `<FX>`. Mismatches fail when ORE builds the par instruments.
* The index behind the token must match its type. `OIS` requires an overnight index; pointing it at an Ibor index fails, and Ibor instruments must use `IRS`, `DEP`, or `FRA`.

### How conventions determine the Jacobian {#conventions-to-jacobian}

The `<Conventions>` mapping determines how ORE builds par instruments. `ParSensitivityInstrumentBuilder` resolves each token to its template in `conventions.xml` (such as `MakeOIS` for `OIS`), extracting payment frequencies, day counters, and settlement lags.

This is where convention discipline pays off; every payment lag, day counter, and settlement detail in `conventions.xml` feeds straight into the entries of $J$. Our [curve bootstrapping post](/post/ore_sofr_bootstrap/) covers these convention blocks in detail, down to how each parameter shapes the instruments ORE builds from your quotes.

ORE determines the fair fixed rate $c_i$ that zeros each instrument's NPV as a function of the zero rates on the grid. To compute the Jacobian matrix $J$, ORE bumps each zero rate $z_j$ by 1 bp, reprices each par instrument, and records the resulting par rate change $\partial c_i / \partial z_j$.

Modifying a convention (such as switching from `A360` to `A365` or changing payment frequency) alters cash-flow timings and changes the resulting Jacobian entries.

### Wiring it up (`ore.xml`)

We add four parameters to the sensitivity analytic in `ore.xml`:

```xml
<Analytic type="sensitivity">
  <Parameter name="active">Y</Parameter>
  <Parameter name="marketConfigFile">simulation.xml</Parameter>
  <Parameter name="sensitivityConfigFile">sensitivity.xml</Parameter>
  <Parameter name="sensitivityOutputFile">sensitivity.csv</Parameter>
  <Parameter name="outputSensitivityThreshold">0.000001</Parameter>
  <Parameter name="parSensitivity">Y</Parameter>
  <Parameter name="parSensitivityOutputFile">parsensitivity.csv</Parameter>
  <Parameter name="outputJacobi">Y</Parameter>
  <Parameter name="jacobiOutputFile">jacobi.csv</Parameter>
  <Parameter name="jacobiInverseOutputFile">jacobi_inverse.csv</Parameter>
</Analytic>
```

Running `run_sensitivity.py` now outputs:

* **`parsensitivity.csv`**: Sensitivities expressed in terms of par instrument rates.
* **`jacobi.csv`**: The Jacobian matrix ($\partial c / \partial z$).
* **`jacobi_inverse.csv`**: The inverse Jacobian ($\partial z / \partial c$).

---

## 7. The Jacobian: changing basis from zero to par

The fair rate of a 15Y OIS ($c_{\text{15Y}}$) depends on the zero rates $z_j$ discounting its cash flows. Applying the chain rule to portfolio value $V$:

$$
\frac{\partial V}{\partial z_j} = \sum_i \frac{\partial V}{\partial c_i}\cdot\frac{\partial c_i}{\partial z_j}
\quad\Longleftrightarrow\quad
\nabla_z V = J^{T} \nabla_c V
$$

where the Jacobian is $J_{ji}=\frac{\partial c_i}{\partial z_j}$.

Inverting the relationship yields the par sensitivities:

$$ \nabla_c V = \left( J^{-1} \right)^{T} \nabla_z V. $$

ORE constructs the par instruments, perturbs each grid zero rate by 1 bp, calculates $\partial c_i / \partial z_j$ numerically to populate $J$, and computes $J^{-1}$. The zero deltas of each risk factor are then converted through its corresponding inverse Jacobian: the `DiscountCurve/EUR` deltas through the discount factor's $J^{-1}$, the `IndexCurve/EUR-ESTER` deltas through its own.

As with ORE's calibration reports, nothing here is hidden. The full matrices are written to `jacobi.csv` and `jacobi_inverse.csv`, so every weight in the conversion can be inspected, and verified by hand, rather than trusted blindly.

### 15Y column example

In `jacobi_inverse.csv`, the 15Y par factor contains three non-zero entries:

| Raw zero factor | ∂z / ∂c (weight) |
|---|---|
| 15Y | 1.128823 |
| 20Y | -0.102531 |
| 30Y | -0.060106 |

This upper triangular structure reflects ORE's bootstrapping order. Shifting a par quote at tenor $t$ only affects zero rates at $t$ and longer maturities.

Because the swap has no cash flows past 20Y, its 30Y zero delta is zero. Applying the weights to the discount factor gives:

$$ 1.128823 \times (+198.33) + (-0.102531) \times (+31.01) = 220.70 $$

For the index factor:

$$ 1.128823 \times (-7030.45) + (-0.102531) \times (-5539.49) = -7368.16 $$

These match the deltas in `parsensitivity.csv` (`DiscountCurve/EUR/7/15Y = 220.70` and `IndexCurve/EUR-ESTER/7/15Y = -7368.16`).

{{< callout type="info" title="Conversion properties" >}}
1. Par conversion reallocates risk. It transforms existing zero-domain deltas into par space without repricing the underlying portfolio.
2. The conversion runs per risk factor. The two factors from section 3, `DiscountCurve/EUR` and `IndexCurve/EUR-ESTER`, each carry their own zero deltas and are converted through their own $J^{-1}$. Here they happen to share the same `EUR-ESTER` curve, so their conversion weights come out identical; on a multi-curve book the two matrices would differ, which is how basis risk would show up.
{{< /callout >}}

---

## 8. Par-domain results: cleaned table and risk shape

Summing the discount and index deltas from `parsensitivity.csv` gives the total par delta at each tenor:

| Tenor | Discount delta (EUR) | Index delta (EUR) | Total par delta (EUR) |
|---|---|---|---|
| 6M | 0.48 | -0.97 | -0.49 |
| 1Y | 8.57 | 9.34 | 17.91 |
| 2Y | -1.63 | 16.25 | 14.62 |
| 3Y | -12.62 | -8.49 | -21.11 |
| 5Y | -10.10 | 7.91 | -2.19 |
| 7Y | 10.68 | 1.30 | 11.98 |
| 10Y | 111.25 | -73.45 | 37.80 |
| 15Y | 220.70 | -7,368.16 | -7,147.46 |
| 20Y | 37.07 | -6,622.58 | -6,585.51 |

### Reading the par table

1. Overall risk direction is preserved. The primary risk remains at 15Y and 20Y, with the receiver losing value as rates rise.
2. The index factor remains dominant. At 15Y, the index delta is `-7,368.16` EUR while discounting contributes `+220.70` EUR.
3. The 15Y delta represents tradeable risk. The total delta of `-7,147.46` EUR indicates that a 1 bp increase in the 15Y OIS market quote decreases swap NPV by approximately 7,150 EUR.
4. No 30Y sensitivity appears. With no cash flows past 20Y, the trade carries no 30Y risk.

---

## 9. Verification: the 15Y manual bump-and-reval check {#verification-bump-and-reval}

To verify the `-7,147.46` EUR par delta independently, we can bump the actual 15Y OIS market quote in `marketdata.csv` (`IR_SWAP/RATE/EUR/ESTER/2D/1D/15Y`) by ±1 bp, rebuild the curve, and reprice the trade.

The calculation flow in `validate_par_sensi.py`:

```python
v0 = npv_at(0)         # base:            -443,626.98
vp = npv_at(+1)        # +1bp quote:      -450,818.40
vm = npv_at(-1)        # -1bp quote:      -436,427.78

forward   = vp - v0          # one-sided: -7,191.42
central   = (vp - vm) / 2    # two-sided: -7,195.31
```

`npv_at(shift_bp)` modifies `marketdata.csv`, runs ORE's pricing engine, and reads the resulting NPV from `npv.csv`. Comparing against the par table:

| Metric | Measured NPV change (EUR) | Difference vs par delta (EUR) | Relative difference |
|---|---|---|---|
| Central difference (two-sided) | -7,195.31 | -47.85 | 0.67% |
| Forward difference (one-sided) | -7,191.42 | -43.96 | 0.61% |
| Total par delta (section 8) | -7,147.46 | N/A | N/A |

The measured bump matches the par table to within 0.7%. 

### Why is there a slight difference?

The main reason for the small variance (~48 EUR or 0.67%) is the **linearisation** inherent in the analytic Jacobian conversion versus a **full curve rebuild**:

1. **Linearised Jacobian conversion (ORE)**: The par sensitivity table calculates risk via a first-order linear approximation (the Jacobian matrix $J = \partial \text{par} / \partial \text{zero}$). It converts zero-rate sensitivities into par sensitivities via the chain rule on a fixed simulation grid without recalibrating the yield curve from scratch.
2. **Full curve re-bootstrapping (Bump & Reval)**: In contrast, the manual bump-and-reval modifies the actual market quote in `marketdata.csv` and re-runs the entire bootstrap process. This recalibrates all dependent discount factors through the curve's interpolation routine before repricing the trade.

The 0.67% difference simply reflects this difference between a fast first-order linear approximation and a full non-linear curve recalibration.

In summary, bumping the 15Y OIS quote by 1 bp moves this receiver by roughly -7,150 to -7,200 EUR, closely matching the -7,147.46 EUR calculated by the Jacobian. This confirms that ORE's par conversion produces an accurate, tradeable risk figure without the overhead of re-bootstrapping curves for every risk factor.

---

## 10. Summary and code {#summary-and-code}

This post walked through the complete zero-to-par sensitivity process in ORE:

* **Config pass 1**: Configured `simulation.xml` and `sensitivity.xml` for zero-domain deltas, separating discount and forecast factors.
* **Config pass 2**: Added `<ParConversion>` with OIS templates to generate `parsensitivity.csv` and the Jacobian matrices (`jacobi.csv`, `jacobi_inverse.csv`).
* **Validation**: Bumped the 15Y OIS market quote by ±1 bp in a manual bump-and-reval, verifying that the full re-bootstrap NPV change (-7,195.31 EUR) matches the Jacobian par delta (-7,147.46 EUR) within 0.7%.

With par-domain deltas proven against an independent repricing like this, the tables can feed scenario ladders, VaR, and stress testing directly: they quote risk against liquid instruments a desk can actually trade. Vega on non-linear trades comes in a later post.

### Source Code
All configuration files and Python scripts demonstrated in this post are available for download:
{{< code-download url="ore_sensitivity_files.zip" >}}

---

### Need Help with ORE Integration?
Dropping a risk engine into an established data landscape is rarely plug-and-play. Bespoke trade representations, legacy databases, and user-specific market conventions all get in the way of a clean feed.

If you are evaluating ORE for your team, or need a custom trade translation layer, **[reach out](/contact)**. We build robust ORE integration layers and validation pipelines tailored to your stack.
