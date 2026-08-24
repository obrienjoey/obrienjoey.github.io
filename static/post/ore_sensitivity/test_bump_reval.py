"""Bundle-consistency tests for the 15Y bump-and-reval section of the
ORE sensitivity post (issue #10).

Two layers, mirroring the post's testing decision (the seam is the sensitivity
post package):

1. Narrative checklist (no ORE required): the bump-and-reval section sits after
   par results, central difference leads forward, the inline Python is a
   shortened flow, gamma appears only as FD-vs-linear context, non-goals are
   named, the page stays a draft.
2. Artifact consistency (requires the ORE python module): re-run the shipped
   bundle's run_sensitivity.py and validate_par_sensi.py and assert every
   published number in the section matches Output/bump_reval_15Y.csv.
"""

import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    from static.post.ore_sensitivity.test_par_table import (
        BUNDLE_ZIP,
        INDEX_MD,
        is_separator,
        parse_rate,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from static.post.ore_sensitivity.test_par_table import (  # type: ignore
        BUNDLE_ZIP,
        INDEX_MD,
        is_separator,
        parse_rate,
    )

import pandas as pd

SECTION_9_HEADING = "## 9. Verification: the 15Y manual bump-and-reval check"
SECTION_8_HEADING = "## 8. Par-domain results"
SECTION_10_HEADING = "## 10. Summary and code {#summary-and-code}"


def section9_text() -> str:
    text = INDEX_MD.read_text(encoding="utf-8")
    start = text.index(SECTION_9_HEADING)
    end = text.index(SECTION_10_HEADING)
    return text[start:end]


def section10_text() -> str:
    text = INDEX_MD.read_text(encoding="utf-8")
    start = text.index(SECTION_10_HEADING)
    return text[start:]


def parse_published_numbers() -> dict[str, float]:
    """Extract the numbers the post publishes from the section-9 code block."""
    text = section9_text()
    patterns = {
        "base": r"npv_at\(0\).*?#\s*base:\s*(-?[\d,]+\.\d{2})",
        "plus": r"npv_at\(\+1\).*?#\s*\+1bp quote:\s*(-?[\d,]+\.\d{2})",
        "minus": r"npv_at\(-1\).*?#\s*-1bp quote:\s*(-?[\d,]+\.\d{2})",
        "forward": r"#\s*one-sided:\s*(-?[\d,]+\.\d{2})",
        "central": r"#\s*two-sided:\s*(-?[\d,]+\.\d{2})",
        "gamma": r"#\s*curvature:\s*([-+]?[\d,]+\.\d{2})",
    }
    published = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match is None:
            raise AssertionError(f"could not find '{key}' number in section 9 code block")
        published[key] = parse_rate(match.group(1))
    return published


def parse_published_table() -> dict[str, dict[str, str]]:
    """Parse the section-9 comparison table into {row_label: {col: cell}}."""
    text = section9_text()
    lines = text.splitlines()
    for line_no, line in enumerate(lines):
        if line.lstrip().startswith("| Metric |"):
            headers = [c.strip() for c in line.strip().strip("|").split("|")][1:]
            rows = {}
            cursor = line_no + 1
            while cursor < len(lines) and lines[cursor].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[cursor].strip().strip("|").split("|")]
                if not is_separator(cells):
                    rows[cells[0]] = dict(zip(headers, cells[1:]))
                cursor += 1
            if rows:
                return rows
    raise AssertionError("section-9 comparison table not found")


def extract_and_run_bundle() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract the zip and run both shipped scripts; return par and reval."""
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(BUNDLE_ZIP) as bundle:
            bundle.extractall(temp_dir)
        for script in ["run_sensitivity.py", "validate_par_sensi.py"]:
            result = subprocess.run(
                [sys.executable, script],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise AssertionError(
                    f"{script} failed (rc={result.returncode}): {result.stderr[-2000:]}"
                )
        par = pd.read_csv(Path(temp_dir) / "Output" / "parsensitivity.csv")
        par.columns = [c.strip() for c in par.columns]
        reval = pd.read_csv(Path(temp_dir) / "Output" / "bump_reval_15Y.csv")
        reval.columns = [c.strip() for c in reval.columns]
        return par, reval


class BumpRevalNarrativeTests(unittest.TestCase):
    def test_bump_reval_section_sits_after_par_results(self):
        text = INDEX_MD.read_text(encoding="utf-8")
        self.assertLess(text.index(SECTION_8_HEADING), text.index(SECTION_9_HEADING))
        self.assertLess(text.index(SECTION_9_HEADING), text.index(SECTION_10_HEADING))

    def test_central_difference_leads_forward(self):
        text = section9_text()
        self.assertLess(
            text.index("Central difference (two-sided)"),
            text.index("Forward difference (one-sided)"),
        )
        self.assertIn("primary", text.lower())

    def test_inline_python_is_shortened(self):
        text = section9_text()
        block = re.search(r"```python\n(.*?)```", text, re.S)
        self.assertIsNotNone(block)
        self.assertLessEqual(len(block.group(1).splitlines()), 12)

    def test_gamma_only_as_fd_vs_linear_context(self):
        text = section9_text()
        self.assertLessEqual(len(re.findall(r"\bgamma\b", text)), 2)
        self.assertNotIn("###", text)

    def test_bundle_ships_both_scripts(self):
        with zipfile.ZipFile(BUNDLE_ZIP) as bundle:
            names = set(bundle.namelist())
        self.assertIn("run_sensitivity.py", names)
        self.assertIn("validate_par_sensi.py", names)

    def test_summary_mentions_bump_reval(self):
        text = section10_text()
        self.assertIn("bump-and-reval", text)
        front = INDEX_MD.read_text(encoding="utf-8")[:500]
        self.assertIn("bump-and-reval", front)

    def test_page_remains_a_draft(self):
        front = INDEX_MD.read_text(encoding="utf-8").split("---")[1]
        self.assertIn("draft: true", front)


class BumpRevalMatchesBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import ORE  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("ORE python module not installed")
        cls.par, cls.reval = extract_and_run_bundle()
        cls.published = parse_published_numbers()
        cls.table = parse_published_table()
        cls.row = cls.reval.iloc[0]

    def test_code_block_numbers_match_script_output(self):
        row = self.row
        for published_key, csv_key in [
            ("base", "base_npv"),
            ("plus", "npv_plus_1bp"),
            ("minus", "npv_minus_1bp"),
            ("forward", "forward_delta"),
            ("central", "central_delta"),
            ("gamma", "gamma_1bp"),
        ]:
            with self.subTest(key=published_key):
                self.assertAlmostEqual(
                    self.published[published_key], row[csv_key], places=2
                )

    def test_comparison_table_matches_script_output(self):
        row = self.row
        central_row = self.table["Central difference (two-sided)"]
        forward_row = self.table["Forward difference (one-sided)"]
        self.assertAlmostEqual(parse_rate(central_row["Measured NPV change (EUR)"]), row["central_delta"], places=2)
        self.assertAlmostEqual(parse_rate(central_row["Difference vs par delta (EUR)"]), row["central_abs_diff"], places=2)
        self.assertAlmostEqual(parse_rate(forward_row["Measured NPV change (EUR)"]), row["forward_delta"], places=2)
        self.assertAlmostEqual(parse_rate(forward_row["Difference vs par delta (EUR)"]), row["forward_abs_diff"], places=2)
        expected_rel = abs(row["central_abs_diff"]) / abs(row["par_delta_total_15y"]) * 100
        self.assertAlmostEqual(float(central_row["Relative difference"].strip().rstrip("%")), expected_rel, places=2)
        reference_row = self.table["Total par delta (section 8)"]
        self.assertAlmostEqual(parse_rate(reference_row["Measured NPV change (EUR)"]), row["par_delta_total_15y"], places=2)

    def test_reference_row_matches_published_par_table(self):
        par_row = self.par[
            (self.par["Factor_1"] == "DiscountCurve/EUR/7/15Y")
            | (self.par["Factor_1"] == "IndexCurve/EUR-ESTER/7/15Y")
        ]
        self.assertAlmostEqual(self.row["par_delta_total_15y"], par_row["Delta"].sum(), places=2)

    def test_curvature_claim_matches_published_numbers(self):
        published = self.published
        gap = published["forward"] - published["central"]
        self.assertAlmostEqual(published["gamma"] / 2.0, gap, delta=0.02)
        text = section9_text()
        self.assertIn("half the curvature term", text)

    def test_finite_difference_lands_within_one_percent_of_linear_number(self):
        row = self.row
        for key in ["central_abs_diff", "forward_abs_diff"]:
            rel = abs(row[key]) / abs(row["par_delta_total_15y"])
            with self.subTest(key=key):
                self.assertLess(rel, 0.01)


if __name__ == "__main__":
    unittest.main()
