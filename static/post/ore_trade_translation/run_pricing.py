import ORE as ore
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
INPUT_DIR = BASE_DIR / "Input"
OUTPUT_DIR = BASE_DIR / "Output"

def main():
    if not (INPUT_DIR / "portfolio.xml").exists():
        print("Error: portfolio.xml not found. Run translate_trades.py first.")
        exit(1)

    print("Running ORE Trade Pricing...")
    params = ore.Parameters()
    params.fromFile(str(INPUT_DIR / "ore.xml"))
    app = ore.OREApp(params)
    app.run()
    print("--- ORE Trade Translation & Pricing Completed Successfully! ---")

    df_npv = pd.read_csv(OUTPUT_DIR / "npv.csv")
    print("\nCalculated NPV Results:")
    print(df_npv[['#TradeId', 'TradeType', 'NPV', 'NpvCurrency']])

if __name__ == "__main__":
    main()
