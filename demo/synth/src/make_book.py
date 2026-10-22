#!/usr/bin/env python3
"""Generate the single book of record for the synthetic Caprock operator's month.

Everything downstream (documents, reference inputs, truth, fixtures, reconcile)
derives from book.json so the seven documents agree with each other.

Writes:
  synth/src/book.json
  synth/planted.json
  synth/reference/doi.json
  synth/reference/contract_rates.json
  synth/reference/afe_election.json

No real company, person, vendor, or operator names appear here. Nothing in this
file touches a network or a credential.
"""
import hashlib
import json
from pathlib import Path

SYNTH = Path(__file__).resolve().parents[1]

R2 = lambda x: round(x + 1e-9, 2)


def build():
    operator = "Sablewind Operating LLC"
    owner = "Caprock Resources LLC"
    owner_number = "OW-10287"
    property_number = "TX-04412"
    well = "Caprock 14-2H"
    api = "42-389-41207"
    county, state = "Reeves", "TX"
    afe_number = "AFE-2026-0417"
    vendor = "Pecos Ridge Well Services LLC"
    hauler = "Sandhill Vacuum Transport LLC"
    decimal = 0.25
    bad_decimal = 0.26

    # ---- AFE ------------------------------------------------------------
    cost_lines = [
        {"line_no": 1, "account_code": "4310", "description": "Recompletion rig and daily rate",
         "category": "intangible", "amount": 128400.00},
        {"line_no": 2, "account_code": "4315", "description": "Wireline and perforating",
         "category": "intangible", "amount": 96750.00},
        {"line_no": 3, "account_code": "4320", "description": "Stimulation and treating services",
         "category": "intangible", "amount": 142500.00},
        {"line_no": 4, "account_code": "4325", "description": "Fluid hauling and disposal",
         "category": "intangible", "amount": 38200.00},
        {"line_no": 5, "account_code": "4410", "description": "Tubing and downhole equipment",
         "category": "tangible", "amount": 52300.00},
        {"line_no": 6, "account_code": "4420", "description": "Wellhead and surface equipment",
         "category": "tangible", "amount": 28650.00},
    ]
    total_estimate = R2(sum(c["amount"] for c in cost_lines))

    afe = {
        "afe_number": afe_number, "operator_name": operator, "well_name": well,
        "api_number": api, "county": county, "state": state,
        "afe_date": "June 1, 2026", "afe_type": "Recompletion",
        "total_estimate": total_estimate, "cost_lines": cost_lines,
    }

    afe_cover = {
        "letter_date": "June 1, 2026", "operator_name": operator, "addressee": owner,
        "afe_number": afe_number, "well_name": well,
        "response_due_date": "June 16, 2026",
        "wi_decimal_stated": 0.250000,
        "net_share_stated": R2(total_estimate * decimal),
    }

    # ---- Field tickets --------------------------------------------------
    def li(desc, qty, unit, rate):
        return {"description": desc, "quantity": qty, "unit": unit,
                "rate": rate, "amount": R2(qty * rate)}

    ta_items = [
        li("Workover rig operator, hourly", 11, "hour", 145.00),
        li("Rig fuel surcharge", 1, "each", 385.00),
        li("Tool rental, packer assembly", 2, "day", 425.00),
    ]
    ticket_a = {
        "ticket_number": "PRW-88421", "vendor_name": vendor, "service_date": "2026-06-09",
        "well_name": well, "afe_number": afe_number, "line_items": ta_items,
        "total": R2(sum(i["amount"] for i in ta_items)),
        "customer_signature_present": False,  # signature lines render blank (no names, no marks); the paper and the book agree
    }

    # P2 plant: pump truck billed at 310.00 against a 285.00 contract rate.
    # H1 plant: the 240 bbl quantity on line index 1 is handwritten.
    tb_items = [
        li("Pump truck, hourly", 6, "hour", 310.00),
        li("Fluid pumped, treated water", 240, "bbl", 4.75),
        li("Standby time", 1.5, "hour", 190.00),
    ]
    ticket_b = {
        "ticket_number": "PRW-88437", "vendor_name": vendor, "service_date": "2026-06-10",
        "well_name": well, "afe_number": afe_number, "line_items": tb_items,
        "total": R2(sum(i["amount"] for i in tb_items)),
        "customer_signature_present": False,  # signature lines render blank (no names, no marks); the paper and the book agree
    }

    # ---- Hauling log ----------------------------------------------------
    loads = [
        {"load_no": 1, "time": "06:40", "fluid_type": "Produced water", "barrels": 118.0,
         "destination": "Sandhill SWD No. 3"},
        {"load_no": 2, "time": "09:15", "fluid_type": "Produced water", "barrels": 122.5,
         "destination": "Sandhill SWD No. 3"},
        {"load_no": 3, "time": "11:50", "fluid_type": "Flowback water", "barrels": 115.0,
         "destination": "Sandhill SWD No. 3"},
        {"load_no": 4, "time": "14:20", "fluid_type": "Flowback water", "barrels": 124.5,
         "destination": "Sandhill SWD No. 3"},
        {"load_no": 5, "time": "16:35", "fluid_type": "Produced water", "barrels": 110.0,
         "destination": "Sandhill SWD No. 3"},
    ]
    hauling_log = {
        "log_number": "SVT-4471", "hauler_name": hauler, "log_date": "2026-06-10",
        "well_name": well, "loads": loads,
        "total_barrels": R2(sum(l["barrels"] for l in loads)),
    }

    # ---- Invoice: one line per ticket line item, values copied verbatim ---
    inv_items = []
    for tk in (ticket_a, ticket_b):
        for it in tk["line_items"]:
            inv_items.append({
                "ticket_ref": tk["ticket_number"], "description": it["description"],
                "quantity": it["quantity"], "unit": it["unit"],
                "rate": it["rate"], "amount": it["amount"],
            })
    subtotal = R2(sum(i["amount"] for i in inv_items))
    tax = R2(subtotal * 0.0825)
    invoice = {
        "invoice_number": "INV-20260612-PRW", "vendor_name": vendor,
        "invoice_date": "2026-06-12", "afe_number": afe_number, "well_name": well,
        "line_items": inv_items, "subtotal": subtotal, "tax": tax,
        "total": R2(subtotal + tax),
    }

    # ---- JIB statement --------------------------------------------------
    gross = [
        ("4310", "Recompletion rig and daily rate", 74320.00),
        ("4315", "Wireline and perforating", 51880.00),
        ("4320", "Stimulation and treating services", 96440.00),
        ("4325", "Fluid hauling and disposal", 22150.00),
        ("4410", "Tubing and downhole equipment", 43760.00),
        ("4420", "Wellhead and surface equipment", 18900.00),
        ("4310", "Rig supervision and site services", 12480.00),
        ("4320", "Chemicals and treating fluids", 9640.00),
    ]
    P1_INDEX = 2  # zero-based index of the wrong-decimal line
    jib_lines = []
    for i, (code, desc, g) in enumerate(gross):
        d = bad_decimal if i == P1_INDEX else decimal
        jib_lines.append({
            "line_no": i + 1, "afe_ref": afe_number, "account_code": code,
            "description": desc, "gross_amount": R2(g),
            "owner_decimal": round(d, 6), "net_amount": R2(g * d),
        })
    jib = {
        "statement_period": "June 2026", "operator_name": operator,
        "property_number": property_number, "well_name": well, "owner_name": owner,
        "owner_number": owner_number, "wi_decimal": 0.250000, "lines": jib_lines,
        "gross_total": R2(sum(l["gross_amount"] for l in jib_lines)),
        "net_total": R2(sum(l["net_amount"] for l in jib_lines)),
        "due_date": "2026-07-30",
        "statement_date": "2026-06-30",
    }

    book = {
        "synthetic": True,
        "story": ("Caprock Resources LLC, a non-operator, holds a 25.000000% working interest in "
                  "one horizontal well. Over one month it receives an AFE, the field paper behind "
                  "a vendor invoice, and a JIB statement that is overbilled twice."),
        "entities": {
            "operator_name": operator, "owner_name": owner, "owner_number": owner_number,
            "property_number": property_number, "well_name": well, "api_number": api,
            "county": county, "state": state, "vendor_name": vendor, "hauler_name": hauler,
            "afe_number": afe_number, "wi_decimal": decimal,
        },
        "documents": {
            "afe_cover": afe_cover, "afe": afe, "ticket_a": ticket_a, "ticket_b": ticket_b,
            "hauling_log": hauling_log, "invoice": invoice, "jib": jib,
        },
        "handwriting": {"doc_id": "ticket_b", "line_index": 1, "field": "quantity",
                        "true_value": tb_items[1]["quantity"]},
        "reference": {
            "doi": {
                "property_number": property_number, "well_name": well,
                "owners": [{"owner_name": owner, "owner_number": owner_number,
                            "interest_type": "WI", "decimal": decimal}],
                "synthetic": True,
            },
            "contract_rates": {
                "vendor_name": vendor, "effective_date": "2026-01-01",
                "rates": [
                    {"description": "Workover rig operator, hourly", "unit": "hour", "contract_rate": 145.00},
                    {"description": "Rig fuel surcharge", "unit": "each", "contract_rate": 385.00},
                    {"description": "Tool rental, packer assembly", "unit": "day", "contract_rate": 425.00},
                    {"description": "Pump truck, hourly", "unit": "hour", "contract_rate": 285.00},
                    {"description": "Fluid pumped, treated water", "unit": "bbl", "contract_rate": 4.75},
                    {"description": "Standby time", "unit": "hour", "contract_rate": 190.00},
                ],
                "synthetic": True,
            },
            "afe_election": {
                "afe_number": afe_number, "owner_name": owner, "election": "participate",
                "wi_decimal": decimal, "election_date": "2026-06-08", "synthetic": True,
            },
        },
    }

    # ---- planted list ---------------------------------------------------
    p1 = jib_lines[P1_INDEX]
    correct_net = R2(p1["gross_amount"] * decimal)
    p2 = tb_items[0]
    contract_rate = 285.00
    planted = {
        "sealed": True,
        "synthetic": True,
        "generated_from": "synth/src/book.json",
        "note": ("Rule 3 (AFE reference / account code) has ZERO plants: all 8 JIB lines carry the "
                 "approved AFE number and an account code that appears in the AFE cost lines. "
                 "Rule 3 must fire on nothing."),
        "P1": {
            "rule": "rule_1_decimal", "doc_id": "jib", "line_index": P1_INDEX,
            "line_no": p1["line_no"], "field_path": f"lines[{P1_INDEX}].owner_decimal",
            "printed_owner_decimal": 0.260000, "correct_owner_decimal": 0.250000,
            "gross_amount": p1["gross_amount"], "printed_net_amount": p1["net_amount"],
            "correct_net_amount": correct_net,
            "overbilling_usd": R2(p1["net_amount"] - correct_net),
            "approver_role": "jv_accountant",
        },
        "P2": {
            "rule": "rule_2_rate", "doc_id": "ticket_b", "line_index": 0,
            "field_path": "line_items[0].rate", "description": p2["description"],
            "unit": p2["unit"], "quantity": p2["quantity"],
            "billed_rate": p2["rate"], "contract_rate": contract_rate,
            "overbilling_usd": R2((p2["rate"] - contract_rate) * p2["quantity"]),
            "also_appears_on": {"doc_id": "invoice", "line_index": 3},
            "approver_role": "supply_chain",
        },
        "H1": {
            "kind": "handwriting", "doc_id": "ticket_b", "line_index": 1,
            "field_path": "line_items[1].quantity", "field": "quantity",
            "true_value": tb_items[1]["quantity"], "unit": tb_items[1]["unit"],
            "description": tb_items[1]["description"],
            "note": "The quantity is a pen entry; the rate on the same line stays typed.",
        },
        "totals": {
            "overbilling_usd": R2(R2(p1["net_amount"] - correct_net)
                                  + R2((p2["rate"] - contract_rate) * p2["quantity"])),
            "rule_3_plants": 0,
        },
    }
    return book, planted


def main():
    book, planted = build()
    (SYNTH / "src").mkdir(parents=True, exist_ok=True)
    (SYNTH / "reference").mkdir(parents=True, exist_ok=True)

    bp = SYNTH / "src" / "book.json"
    bp.write_text(json.dumps(book, indent=1) + "\n")

    pp = SYNTH / "planted.json"
    pp.write_text(json.dumps(planted, indent=1) + "\n")

    for name in ("doi", "contract_rates", "afe_election"):
        (SYNTH / "reference" / f"{name}.json").write_text(
            json.dumps(book["reference"][name], indent=1) + "\n")

    digest = hashlib.sha256(pp.read_bytes()).hexdigest()
    print(f"book.json      {bp}")
    print(f"planted.json   {pp}")
    print(f"planted sha256 {digest}")

    # self-checks
    afe = book["documents"]["afe"]
    assert R2(sum(c["amount"] for c in afe["cost_lines"])) == afe["total_estimate"]
    assert len(afe["cost_lines"]) == 6
    jib = book["documents"]["jib"]
    assert len(jib["lines"]) == 8
    codes = {c["account_code"] for c in afe["cost_lines"]}
    assert all(l["account_code"] in codes for l in jib["lines"])
    assert all(l["afe_ref"] == afe["afe_number"] for l in jib["lines"])
    inv = book["documents"]["invoice"]
    assert len(inv["line_items"]) == 6
    print("self-checks OK")


if __name__ == "__main__":
    main()
