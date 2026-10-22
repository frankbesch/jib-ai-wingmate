#!/usr/bin/env python3
"""Draw the README pictures as light and dark SVG.

Usage: python3 -B docs/diagrams/charts.py
Writes one pair of equal height: the pipeline beside the reconcile rules on
the synthetic month. Every figure is copied from a committed file in this
repo, and main() checks that each one still appears on its cited line. The
drawing code is quoin_readme.py, a copy of the Quoin README module.
"""
from pathlib import Path

from quoin_readme import THEMES, BLUE, OCHRE, pair, panels, steps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TEST = "tests/test_reconcile.py"
PLANTED = "synth/planted.json"

# (rule, lines checked, lines flagged, flagged label, [(file, line, text that must be on it)])
RULES = [
    ("Rule 1, owner decimal (JIB lines)", 8, 1, "flagged: $964.40 over",
     [(TEST, 76, "counts['rule_1_decimal'] == [8, 1]"), (TEST, 75, "e['delta_usd'] == 964.40"),
      (PLANTED, 17, '"overbilling_usd": 964.4')]),
    ("Rule 2, contract rate (ticket lines)", 6, 1, "flagged: $150.00 over",
     [(TEST, 90, "counts['rule_2_rate'] == [6, 1]"), (TEST, 89, "e['delta_usd'] == 150.00"),
      (PLANTED, 30, '"overbilling_usd": 150.0')]),
    ("Rule 3, AFE reference (JIB lines)", 8, 0, "flagged: none planted",
     [(TEST, 96, "counts['rule_3_afe_ref'] == [8, 0]")]),
]

FLOW_DESC = ("The well-file pipeline. A permit packet comes in: a Texas RRC drilling permit with its plats, "
             "or a synthetic oil and gas month. A document parser classifies each document, splits the "
             "packet by page, and extracts a schema for each class. Every value keeps a citation to its "
             "page box. The scorer grades fields and citations against truth, and reconcile rules check "
             "the money. A named reviewer approves or routes each exception into an append-only audit "
             "file. Fixture mode replays stored responses with no key and no network.")
RULES_DESC = ("Reconcile rules on the synthetic Caprock month, from the committed test. Rule 1, owner "
              "decimal: 8 JIB lines checked, 1 flagged, 964.40 dollars overbilled. Rule 2, contract rate: "
              "6 ticket lines checked, 1 flagged, 150.00 dollars overbilled. Rule 3, AFE reference: 8 JIB "
              "lines checked, 0 flagged, and none was planted.")


def flow(c, spread=0.0, h=0):
    return steps(dict(
        title="Permit packet to approved record",
        steps=[("Packet in", "RRC permit and plats, or a synthetic month", None, "external"),
               ("Document parser", "classify, split by page, extract", None, "bus"),
               ("Schema per class, with citations", "each value keeps its page box", None, "backend"),
               ("Score and reconcile", "fields and citations vs truth; money rules", None, "security"),
               ("Named reviewer decides", "approve or route; append-only audit file", None, "database")],
        note="Fixture mode replays stored responses: no key, no network.",
        desc=FLOW_DESC), c, spread, h)


def rules(c, spread=0.0, h=0):
    return panels(dict(
        title="Reconcile rules, synthetic month",
        sub="Lines checked and lines flagged. Two errors were planted; both are flagged.",
        panels=[(name, [BLUE, OCHRE], [("lines checked", n, str(n)), (label, f, str(f))])
                for name, n, f, label, _ in RULES],
        notes=["One linear scale. Source: tests/test_reconcile.py and synth/planted.json."],
        desc=RULES_DESC), c, spread, h)


def main():
    for name, _, _, _, cites in RULES:
        for f, n, s in cites:
            assert s in (ROOT / f).read_text().splitlines()[n - 1], (name, f, n, s)
    for theme, c in THEMES.items():
        for name, s in zip(("pipeline", "reconcile"), pair(flow, rules, c)):
            (HERE / f"{name}-{theme}.svg").write_text(s)
    print("built pipeline | reconcile, light and dark; every figure found on its cited line")


if __name__ == "__main__":
    main()
