import os
import ORE as ore
import csv
import matplotlib.pyplot as plt
from pathlib import Path

# Set up base path relative to this script
BASE_DIR = Path(__file__).parent.resolve()
INPUT_DIR = BASE_DIR / "Input"
OUTPUT_DIR = BASE_DIR / "Output"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. Run the ORE App
params = ore.Parameters()
params.fromFile(str(INPUT_DIR / "ore.xml"))
app = ore.OREApp(params)
app.run()

print("\n--- ORE Run Completed Successfully ---\n")

# 2. Extract bootstrapped curve rates from calibration report
calibration_file = OUTPUT_DIR / "todaysmarketcalibration.csv"

times = []
zero_rates = []
labels = []
discount_factors = []

if calibration_file.exists():
    with open(calibration_file, "r") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Columns: MarketObjectType, MarketObjectId, ResultId, ResultKey1, ResultKey2, ResultKey3, ResultType, ResultValue
        # Filter for rows where MarketObjectId is 'USD-SOFR' and extract time, zeroRate, and discountFactor
        # We group by the ResultKey2 (quote key e.g. MM/RATE/USD/SOFR/0D/1D)
        data = {}
        for row in reader:
            if len(row) < 8:
                continue
            obj_id = row[1].strip()
            res_id = row[2].strip()
            key2 = row[4].strip()  # quote identifier
            val = row[7].strip()
            
            if obj_id == "USD-SOFR" and key2:
                if key2 not in data:
                    data[key2] = {}
                data[key2][res_id] = val
                
        # Parse the gathered values
        # Let's map key2 to short names for labelling
        def clean_label(k):
            if "0D/1D" in k and "MM" in k:
                return "ON"
            # Extract last part like 1M, 3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y
            return k.split("/")[-1]

        # Sort the data by time
        sorted_nodes = []
        for k, v in data.items():
            if "time" in v and "zeroRate" in v and "discountFactor" in v:
                t = float(v["time"])
                zr = float(v["zeroRate"])
                df = float(v["discountFactor"])
                sorted_nodes.append((t, zr, df, clean_label(k)))
        
        sorted_nodes.sort(key=lambda x: x[0])
        
        print("Discount Factors and Zero Rates (from todaysmarketcalibration.csv as of 2023-01-31):")
        print(f"{'Pillar':<8} {'Time (y)':<10} {'Discount Factor':<18} {'Zero Rate (%)':<15}")
        print("-" * 55)
        for t, zr, df, lbl in sorted_nodes:
            times.append(t)
            zero_rates.append(zr * 100)
            discount_factors.append(df)
            labels.append(lbl)
            print(f"{lbl:<8} {t:<10.4f} {df:<18.8f} {zr*100:<15.4f}%")
else:
    print("Warning: todaysmarketcalibration.csv not found! Using fallback tenors.")
    # Fallback to analytic curves
    analytic = app.getAnalytic("NPV")
    market = analytic.getMarket()
    curve = market.discountCurve("USD")
    tenors = {"1M": 1/12, "3M": 0.25, "6M": 0.5, "1Y": 1.0, "2Y": 2.0, "5Y": 5.0, "10Y": 10.0, "30Y": 30.0}
    for name, t in tenors.items():
        df = curve.discount(t)
        zero = curve.zeroRate(t, ore.Compounded, ore.Annual).rate()
        times.append(t)
        zero_rates.append(zero * 100)
        labels.append(name)
        discount_factors.append(df)

print("\n---------------------------------------\n")

# 3. Read NPV report and verify repricing
npv_file = OUTPUT_DIR / "npv.csv"
if npv_file.exists():
    print("Repricing NPV results:")
    print(f"{'Trade ID':<15} {'NPV':<15} {'Base NPV (USD)':<15}")
    print("-" * 48)
    with open(npv_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = {k.strip(): v.strip() for k, v in row.items()}
            print(f"{row.get('#TradeId'):<15} {row.get('NPV'):<15} {row.get('NPV(Base)'):<15}")
else:
    print("Error: npv.csv was not generated!")
print("\n---------------------------------------\n")

# 4. Generate Zero Curve Plot
plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
fig, ax = plt.subplots(figsize=(8.5, 4.5))

# Plot zero rates
ax.plot(times, zero_rates, marker='o', markerfacecolor='white', markeredgecolor='#0f766e', markeredgewidth=2, color='#0f766e', linewidth=2, markersize=8, label='Zero Rate (%)')

# Add labels slightly offset for readability
for i, txt in enumerate(labels):
    ax.annotate(txt, (times[i], zero_rates[i]), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9, fontweight='semibold', color='#374151')

ax.set_title("Bootstrapped USD SOFR Zero Curve (As of 2023-01-31)", fontsize=13, fontweight='bold', pad=15)
ax.set_xlabel("Time to Maturity (Years)", fontsize=11, labelpad=10)
ax.set_ylabel("Zero Rate (%)", fontsize=11, labelpad=10)

# Use a log scale for the x-axis to resolve clustering at the short end
ax.set_xscale('symlog', linthresh=1.0)
ax.set_xlim(-0.05, 35)

# Setup custom labels for the x-ticks
ax.set_xticks([0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0])
ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())

ax.grid(True, which="both", ls="--", alpha=0.5)
ax.legend(loc='upper right', frameon=True)
plt.tight_layout()

# Save plot to static post directory
plot_path = BASE_DIR / "zero_curve.png"
plt.savefig(plot_path, dpi=300)

# Also copy/save to content directory so Hugo can access it directly
content_dir = BASE_DIR.parents[2] / "content" / "post" / "ore_sofr_bootstrap"
if content_dir.exists():
    plt.savefig(content_dir / "zero_curve.png", dpi=300)
    print(f"Copied zero curve plot to: {content_dir / 'zero_curve.png'}")

print(f"Saved zero curve plot to: {plot_path}")
