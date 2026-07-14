import os
import ORE as ore
import csv

# Ensure Output directory exists
os.makedirs("Output", exist_ok=True)

# 1. Run the ORE App to build the curve and price portfolio
params = ore.Parameters()
params.fromFile("Input/ore.xml")
app = ore.OREApp(params)
app.run()

print("\n--- ORE Run Completed Successfully ---\n")

# 2. Inspect the bootstrapped curve
analytic = app.getAnalytic("NPV")
market = analytic.getMarket()
curve = market.discountCurve("USD")

print("Discount Factors and Zero Rates (as of 2023-01-31):")
print(f"{'Tenor':<8} {'Time (y)':<10} {'Discount Factor':<18} {'Zero Rate (%)':<15}")
print("-" * 55)

tenors = {
    "1M": 1/12,
    "3M": 0.25,
    "6M": 0.5,
    "1Y": 1.0,
    "2Y": 2.0,
    "5Y": 5.0,
    "10Y": 10.0,
    "30Y": 30.0
}

for name, t in tenors.items():
    df = curve.discount(t)
    zero = curve.zeroRate(t, ore.Compounded, ore.Annual).rate()
    print(f"{name:<8} {t:<10.4f} {df:<18.8f} {zero*100:<15.4f}%")

print("\n---------------------------------------\n")

# 3. Read NPV report and verify repricing
npv_file = "Output/npv.csv"
if os.path.exists(npv_file):
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
