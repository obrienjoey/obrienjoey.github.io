import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
POST_DIR = REPO_ROOT / "content" / "post" / "ore_sensitivity"
INDEX_MD = POST_DIR / "index.md"
BUNDLE_ZIP = POST_DIR / "ore_sensitivity_files.zip"
TOTAL_COL = "Total par delta (EUR)"

HANDLE_TO_SHORT = {
    "DiscountCurve/EUR": "DiscountCurve",
    "IndexCurve/EUR-ESTER": "IndexCurve",
}
SHORT_TO_HANDLE = {v: k for k, v in HANDLE_TO_SHORT.items()}
TENOR_TO_INDEX = {
    "6M": 0, "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 4, "7Y": 5, "10Y": 6, "15Y": 7, "20Y": 8,
}


def parse_rate(cell: str) -> float:
    return float(cell.replace(",", "").strip())


def is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def parse_published_table() -> tuple[list[str], list[list[str]]]:
    text = INDEX_MD.read_text(encoding="utf-8")
    lines = text.splitlines()
    for line_no, line in enumerate(lines):
        if line.lstrip().startswith("|") and TOTAL_COL in line:
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            rows = []
            cursor = line_no + 1
            while cursor < len(lines) and lines[cursor].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[cursor].strip().strip("|").split("|")]
                if not is_separator(cells):
                    rows.append(cells)
                cursor += 1
            if rows:
                return headers, rows
    raise AssertionError(f"par-domain table with '{TOTAL_COL}' not found in {INDEX_MD}")


def regen_outputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(BUNDLE_ZIP) as bundle:
            bundle.extractall(temp_dir)
        result = subprocess.run(
            [sys.executable, "run_sensitivity.py"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"run_sensitivity.py failed (rc={result.returncode}): {result.stderr[-2000:]}"
            )
        par = pd.read_csv(Path(temp_dir) / "Output" / "parsensitivity.csv")
        par.columns = [c.strip() for c in par.columns]
        jacobi = pd.read_csv(Path(temp_dir) / "Output" / "jacobi_inverse.csv")
        jacobi.columns = [c.strip() for c in jacobi.columns]
        return par, jacobi


def bundle_delta(par: pd.DataFrame, handle_short: str, handle_idx: int, tenor: str) -> float:
    handle_key = SHORT_TO_HANDLE[handle_short]
    rows = par[par["Factor_1"] == f"{handle_key}/{handle_idx}/{tenor}"]
    if rows.empty:
        raise AssertionError(f"no par row for {handle_key}/{handle_idx}/{tenor}")
    return rows["Delta"].iloc[0]


class ParTableMatchesBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import ORE  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("ORE python module not installed")
        cls.headers, cls.rows = parse_published_table()
        cls.par, cls.jacobi = regen_outputs()

    def test_table_header_parallels_zero_table(self):
        self.assertEqual(
            self.headers,
            ["Tenor", "Discount delta (EUR)", "Index delta (EUR)", TOTAL_COL],
        )

    def test_tenors_match_handle_rows(self):
        published = [r[0] for r in self.rows]
        self.assertEqual(published, list(TENOR_TO_INDEX))
        for tenor, handle_idx in TENOR_TO_INDEX.items():
            for handle_short in HANDLE_TO_SHORT.values():
                bundle_delta(self.par, handle_short, handle_idx, tenor)

    def test_discount_and_index_cells_match_bundle(self):
        for row in self.rows:
            tenor, discount_cell, index_cell, _ = row
            handle_idx = TENOR_TO_INDEX[tenor]
            for short, cell in [("DiscountCurve", discount_cell), ("IndexCurve", index_cell)]:
                delta = bundle_delta(self.par, short, handle_idx, tenor)
                self.assertAlmostEqual(parse_rate(cell), delta, places=2, msg=f"{short} {tenor}")

    def test_total_par_delta_is_discount_plus_index_from_bundle(self):
        for row in self.rows:
            tenor, discount_cell, index_cell, total_cell = row
            handle_idx = TENOR_TO_INDEX[tenor]
            expected = parse_rate(discount_cell) + parse_rate(index_cell)
            self.assertAlmostEqual(parse_rate(total_cell), expected, places=2, msg=f"total {tenor}")
            bundle_total = bundle_delta(self.par, "DiscountCurve", handle_idx, tenor) + bundle_delta(
                self.par, "IndexCurve", handle_idx, tenor
            )
            self.assertAlmostEqual(parse_rate(total_cell), bundle_total, places=2, msg=tenor)

    def test_worked_example_weights_match_jacobi_inverse(self):
        jacobi = self.jacobi
        jacobi.columns = ["raw", "par", "weight"]
        for handle_short in HANDLE_TO_SHORT.values():
            par_factor = f"{SHORT_TO_HANDLE[handle_short]}/7"
            weights = jacobi[jacobi["par"] == par_factor].set_index("raw")["weight"]
            self.assertAlmostEqual(weights[f"{SHORT_TO_HANDLE[handle_short]}/7"], 1.128823, places=6)
            self.assertAlmostEqual(weights[f"{SHORT_TO_HANDLE[handle_short]}/8"], -0.102531, places=6)
            self.assertAlmostEqual(weights[f"{SHORT_TO_HANDLE[handle_short]}/9"], -0.060106, places=6)


if __name__ == "__main__":
    unittest.main()