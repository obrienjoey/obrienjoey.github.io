import math
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "Output_Eq"

# The option trade is priced by the companion trade-translation bundle. Its
# additional_results.csv / npv.csv are provided in the Output_Eq directory so
# they are not overwritten when run_pricing.py regenerates Output/ for the swap.

def reconcile_equity_option():
    ar_file = OUTPUT_DIR / "additional_results.csv"
    npv_file = OUTPUT_DIR / "npv.csv"

    if not ar_file.exists() or not npv_file.exists():
        print(f"Error: option output not found in {OUTPUT_DIR}.")
        print("  Expected: additional_results.csv and npv.csv containing EQ_CALL_SP5_1.")
        print("  The option outputs ship with this bundle in the Output_Eq directory.")
        return

    ar_df = pd.read_csv(ar_file)
    npv_df = pd.read_csv(npv_file)

    ar_df.columns = [str(c).strip() for c in ar_df.columns]
    npv_df.columns = [str(c).strip() for c in npv_df.columns]

    def get_param(trade_id, result_id):
        row = ar_df[(ar_df[ar_df.columns[0]].astype(str).str.strip() == trade_id) &
                    (ar_df["ResultId"].astype(str).str.strip() == result_id)]
        if row.empty:
            raise ValueError(f"Result '{result_id}' not found for trade '{trade_id}' in {ar_file.name}")
        return float(row["ResultValue"].iloc[0])

    trade_id = "EQ_CALL_SP5_1"
    premium_id = f"_{trade_id}_1"

    quantity = get_param(trade_id, "quantity")
    S = get_param(trade_id, "spot")
    K = get_param(trade_id, "strike")
    T = get_param(trade_id, "timeToExpiry")
    vol = get_param(trade_id, "volatility")
    dividend_df = get_param(trade_id, "dividendDiscount")
    risk_free_df = get_param(trade_id, "riskFreeDiscount")
    premium_paid = get_param(premium_id, "premiumAmount")
    premium_df = get_param(premium_id, "premiumDiscountFactor")
    ore_npv_row = npv_df[npv_df[npv_df.columns[0]].astype(str).str.strip() == trade_id]
    ore_npv = float(ore_npv_row["NPV"].iloc[0])

    r = -math.log(risk_free_df) / T
    q = -math.log(dividend_df) / T

    print(f"\n=== Additional Results Parameters for {trade_id} ===")
    print(f"  Spot (S):             {S:.6f}")
    print(f"  Strike (K):           {K:.6f}")
    print(f"  Time to Expiry (T):   {T:.10f}")
    print(f"  Volatility (sigma):   {vol:.6f} ({vol*100:.2f}%)")
    print(f"  Risk-Free Discount:   {risk_free_df:.10f}  (r = {r*100:.4f}%)")
    print(f"  Dividend Discount:    {dividend_df:.10f}  (q = {q*100:.4f}%)")

    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * vol**2) * T) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t

    print(f"\n=== d1 / d2 Verification ===")
    print(f"  d1:                     {d1:.10f}")
    print(f"  d2:                     {d2:.10f}")

    normal_cdf = lambda x: (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
    bsm_call = S * dividend_df * normal_cdf(d1) - K * risk_free_df * normal_cdf(d2)
    ore_unit_value = (ore_npv + premium_paid * premium_df) / quantity

    print(f"\n=== Black-Scholes-Merton Reconstruction ===")
    print(f"  BSM Call (manual): {bsm_call:.6f} USD  per unit")
    print(f"  ORE Implied Value:  {ore_unit_value:.6f} USD  per unit")
    print(f"  Difference:        {abs(bsm_call - ore_unit_value):.2e} USD")

    premium_pv = premium_paid * premium_df
    full_npv_manual = quantity * bsm_call - premium_pv

    print(f"\n=== Full Position NPV Reconciliation ===")
    print(f"  Quantity:             {quantity:.0f} contracts")
    print(f"  BSM value per unit:   {bsm_call:.6f} USD")
    print(f"  Premium amount:        {premium_paid:.2f} USD (PV = {premium_pv:.6f})")
    print(f"  Manual NPV:           {full_npv_manual:,.4f} USD")
    print(f"  ORE Reported NPV:     {ore_npv:,.4f} USD")
    print(f"  Residual:             {abs(full_npv_manual - ore_npv):.4f} USD")

if __name__ == "__main__":
    reconcile_equity_option()
