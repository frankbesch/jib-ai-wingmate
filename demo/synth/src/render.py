#!/usr/bin/env python3
"""Render the seven synthetic Caprock documents from book.json.

One HTML template per document type -> headless Chrome -> PDF -> pypdf packets
-> magick scan variants (the same pass build_corpus.py uses).

Outputs (all under synth/):
  caprock/01_afe_cover.pdf ... caprock/07_jib.pdf
  caprock/packets/day01.pdf day12.pdf day30.pdf
  caprock-scan/<same names>
  manifest.json

Everything is offline. No network, no credential, no approver name is written
into any approval field: approval blocks render blank for a human to sign.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

SYNTH = Path(__file__).resolve().parents[1]
BOOK = SYNTH / "src" / "book.json"
CLEAN = SYNTH / "caprock"
SCAN = SYNTH / "caprock-scan"
BUILD = SYNTH / "src" / "_html"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FOOTER_TEXT = "Synthetic demonstration document — not an actual record"
HAND_FONT = "Marker Felt"

DOCS = [
    ("afe_cover", "01_afe_cover.pdf", "afe_cover", "day01"),
    ("afe", "02_afe.pdf", "afe", "day01"),
    ("ticket_a", "03_ticket_a.pdf", "field_ticket", "day12"),
    ("ticket_b", "04_ticket_b.pdf", "field_ticket", "day12"),
    ("hauling_log", "05_hauling_log.pdf", "hauling_log", "day12"),
    ("invoice", "06_invoice.pdf", "invoice", "day12"),
    ("jib", "07_jib.pdf", "jib_statement", "day30"),
]
PACKETS = [
    ("day01", ["afe_cover", "afe"]),
    ("day12", ["ticket_a", "ticket_b", "hauling_log", "invoice"]),
    ("day30", ["jib"]),
]

# --------------------------------------------------------------------------
# helpers


def e(x):
    return html.escape(str(x))


def usd(x):
    return f"{x:,.2f}"


def qty(x):
    return f"{x:g}"


def dec6(x):
    return f"{x:.6f}"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


CSS = """
@page { size: Letter; margin: 0.55in 0.6in 0.70in 0.6in; }
* { box-sizing: border-box; }
html, body { margin:0; padding:0; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; font-size: 9.2pt;
       color: #111; line-height: 1.32; }
.footer { position: fixed; bottom: 0; left: 0; right: 0; text-align: center;
          font-size: 6.6pt; color: #666; letter-spacing: .02em;
          border-top: 0.5pt solid #bbb; padding-top: 3px; }
.pagebreak { page-break-before: always; }
h1 { font-size: 13pt; margin: 0 0 2px 0; letter-spacing: .06em; text-transform: uppercase; }
h2 { font-size: 9.6pt; margin: 14px 0 4px 0; letter-spacing: .08em;
     text-transform: uppercase; border-bottom: 1pt solid #222; padding-bottom: 2px; }
.rule { border-top: 1.6pt solid #111; margin: 6px 0 10px 0; }
.thin { border-top: 0.6pt solid #999; margin: 8px 0; }
.letterhead { display:flex; justify-content: space-between; align-items: flex-end; }
.letterhead .co { font-size: 12.5pt; font-weight: 700; letter-spacing: .04em; }
.letterhead .addr { font-size: 7.6pt; color:#444; text-align: right; line-height:1.3; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 3.2px 5px; vertical-align: top; }
table.grid { border: 0.8pt solid #333; }
table.grid th { background: #e9e9e9; border: 0.5pt solid #333; font-size: 7.8pt;
                text-transform: uppercase; letter-spacing: .04em; text-align: left; }
table.grid td { border: 0.5pt solid #999; font-size: 8.8pt; }
td.r, th.r { text-align: right; }
td.c, th.c { text-align: center; }
table.kv td { padding: 1.6px 4px; font-size: 8.8pt; border-bottom: 0.4pt solid #ddd; }
table.kv td.k { width: 34%; color:#333; font-weight:600; text-transform: uppercase;
                font-size: 7.4pt; letter-spacing:.04em; }
.two { display: flex; gap: 20px; }
.two > div { flex: 1; }
.tot td { font-weight: 700; background: #f2f2f2; }
.sub td { font-weight: 600; }
.sec td { background:#efefef; font-weight:700; text-transform:uppercase; font-size:7.8pt;
          letter-spacing:.05em; }
.sig { margin-top: 22px; }
.sigline { border-bottom: 0.8pt solid #333; height: 22px; }
.siglabel { font-size: 7.2pt; color:#444; text-transform: uppercase; letter-spacing:.05em;
            padding-top: 2px; }
.note { font-size: 7.6pt; color:#444; margin-top: 8px; }
p { margin: 7px 0; }
.stamp { font-size: 7.4pt; color:#555; text-align:right; }
.hand { font-family: "Marker Felt", "Chalkboard SE", "SignPainter", cursive;
        color: #16357a; font-size: 13.5pt; display: inline-block;
        transform: rotate(-4.5deg); transform-origin: 60% 60%; letter-spacing: .04em; }
.contbanner { font-size: 7.6pt; color:#555; text-align:right; margin-bottom:6px; }
"""


def page(title, body):
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{e(title)}</title>"
            f"<style>{CSS}</style></head><body>"
            f"<div class='footer'>{e(FOOTER_TEXT)}</div>{body}</body></html>")


def letterhead(name, lines):
    addr = "<br>".join(e(l) for l in lines)
    return (f"<div class='letterhead'><div class='co'>{e(name)}</div>"
            f"<div class='addr'>{addr}</div></div><div class='rule'></div>")


OPER_ADDR = ["1400 Sablewind Plaza, Suite 610", "Midland, Texas 79701",
             "Joint Interest Billing Department"]
VENDOR_ADDR = ["2210 South Loop Road", "Pecos, Texas 79772", "Remit per invoice terms"]
HAULER_ADDR = ["Route 3, Box 118", "Pecos, Texas 79772"]

# --------------------------------------------------------------------------
# templates


def t_afe_cover(b):
    d = b["documents"]["afe_cover"]
    a = b["documents"]["afe"]
    body = letterhead(d["operator_name"], OPER_ADDR)
    body += f"<div class='stamp'>{e(d['letter_date'])}</div>"
    body += ("<p>" + e(d["addressee"]) + "<br>Attention: Joint Interest Owner Representative"
             "<br>Owner Number " + e(b["entities"]["owner_number"]) + "</p>")
    body += (f"<p><b>Re: Authorization for Expenditure {e(d['afe_number'])} &mdash; "
             f"{e(d['well_name'])} &mdash; Recompletion</b></p>")
    body += ("<p>As operator of the captioned well, we enclose an Authorization for Expenditure "
             "covering a proposed recompletion of the existing wellbore into the upper interval. "
             "The estimate covers rig, wireline, stimulation, fluid handling, and the tangible "
             "equipment listed on the attached form.</p>")
    body += (f"<table class='kv' style='margin:10px 0; width:74%'>"
             f"<tr><td class='k'>AFE number</td><td>{e(d['afe_number'])}</td></tr>"
             f"<tr><td class='k'>Well</td><td>{e(d['well_name'])}</td></tr>"
             f"<tr><td class='k'>AFE type</td><td>{e(a['afe_type'])}</td></tr>"
             f"<tr><td class='k'>Total gross estimate</td><td>${usd(a['total_estimate'])}</td></tr>"
             f"<tr><td class='k'>Your working interest</td>"
             f"<td>{dec6(d['wi_decimal_stated'])}</td></tr>"
             f"<tr><td class='k'>Your net share of estimate</td>"
             f"<td>${usd(d['net_share_stated'])}</td></tr>"
             f"<tr><td class='k'>Response due</td><td>{e(d['response_due_date'])}</td></tr>"
             f"</table>")
    body += ("<p>Please return one executed copy of the AFE marked to elect or decline "
             "participation on or before the response date shown above. Costs will be billed on "
             "the monthly joint interest billing statement for the property under the operating "
             "agreement.</p>")
    body += ("<p>Direct questions on the estimate to the joint interest billing department at the "
             "address above.</p>")
    body += ("<div class='sig'><div class='two'>"
             "<div><div class='sigline'></div>"
             "<div class='siglabel'>Operator representative signature</div></div>"
             "<div><div class='sigline'></div>"
             "<div class='siglabel'>Date</div></div></div>"
             "<div class='note'>Signature block intentionally blank. An approver name is typed by "
             "a person, never pre-filled.</div></div>")
    return page("AFE cover letter", body)


def t_afe(b):
    a = b["documents"]["afe"]
    body = letterhead(a["operator_name"], OPER_ADDR)
    body += "<h1>Authorization for Expenditure</h1>"
    body += ("<div class='two'>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>AFE number</td><td>{e(a['afe_number'])}</td></tr>"
             f"<tr><td class='k'>AFE date</td><td>{e(a['afe_date'])}</td></tr>"
             f"<tr><td class='k'>AFE type</td><td>{e(a['afe_type'])}</td></tr>"
             f"<tr><td class='k'>Operator</td><td>{e(a['operator_name'])}</td></tr>"
             f"</table></div>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Well</td><td>{e(a['well_name'])}</td></tr>"
             f"<tr><td class='k'>API number</td><td>{e(a['api_number'])}</td></tr>"
             f"<tr><td class='k'>County</td><td>{e(a['county'])}</td></tr>"
             f"<tr><td class='k'>State</td><td>{e(a['state'])}</td></tr>"
             f"</table></div></div>")

    def rows(cat):
        out = ""
        for c in a["cost_lines"]:
            if c["category"] != cat:
                continue
            out += (f"<tr><td class='c'>{c['line_no']}</td><td class='c'>{e(c['account_code'])}</td>"
                    f"<td>{e(c['description'])}</td><td class='c'>{e(c['category'])}</td>"
                    f"<td class='r'>{usd(c['amount'])}</td></tr>")
        return out

    intang = sum(c["amount"] for c in a["cost_lines"] if c["category"] == "intangible")
    tang = sum(c["amount"] for c in a["cost_lines"] if c["category"] == "tangible")

    body += "<h2>Estimated cost detail</h2>"
    body += ("<table class='grid'><tr><th class='c' style='width:7%'>Line</th>"
             "<th class='c' style='width:12%'>Account</th><th>Description</th>"
             "<th class='c' style='width:14%'>Category</th>"
             "<th class='r' style='width:18%'>Amount (USD)</th></tr>"
             "<tr class='sec'><td colspan='5'>Intangible costs</td></tr>"
             + rows("intangible")
             + f"<tr class='sub'><td colspan='4'>Subtotal, intangible</td>"
               f"<td class='r'>{usd(intang)}</td></tr>"
             "<tr class='sec'><td colspan='5'>Tangible costs</td></tr>"
             + rows("tangible")
             + f"<tr class='sub'><td colspan='4'>Subtotal, tangible</td>"
               f"<td class='r'>{usd(tang)}</td></tr>"
             f"<tr class='tot'><td colspan='4'>Total estimate</td>"
             f"<td class='r'>{usd(a['total_estimate'])}</td></tr></table>")
    body += ("<div class='note'>Amounts are gross to the property. Each owner is billed its share "
             "under the operating agreement and the division of interest of record.</div>")

    # page 2
    body += "<div class='pagebreak'></div>"
    body += f"<div class='contbanner'>{e(a['afe_number'])} &mdash; page 2 of 2</div>"
    body += letterhead(a["operator_name"], OPER_ADDR)
    body += "<h2>Scope of work</h2>"
    body += ("<p>Move in and rig up workover unit. Kill well and pull existing production string. "
             "Run cast-iron bridge plug and isolate the lower interval. Perforate the upper "
             "interval and stimulate per the treatment schedule. Run new tubing and downhole "
             "equipment, reset the wellhead, return the well to production, and haul recovered "
             "fluid to a permitted disposal facility.</p>")
    body += "<h2>Basis of estimate</h2>"
    body += ("<p>Service costs are estimated from the current master service agreement rate sheet "
             "for the area. Tangible equipment is estimated at quoted replacement cost. The "
             "estimate excludes contingency, overhead, and any cost of a sidetrack should the "
             "isolation attempt fail.</p>")
    body += "<h2>Owner election and approval</h2>"
    body += ("<table class='grid'>"
             "<tr><th style='width:34%'>Item</th><th>Entry</th></tr>"
             "<tr><td>Election (participate / decline)</td><td style='height:26px'></td></tr>"
             "<tr><td>Owner working interest</td><td style='height:26px'></td></tr>"
             "<tr><td>Owner net share of estimate</td><td style='height:26px'></td></tr>"
             "<tr><td>Approved by (print name)</td><td style='height:26px'></td></tr>"
             "<tr><td>Title</td><td style='height:26px'></td></tr>"
             "<tr><td>Signature</td><td style='height:30px'></td></tr>"
             "<tr><td>Date</td><td style='height:26px'></td></tr></table>")
    body += ("<div class='note'>Approval fields are blank by design. A person types the approver "
             "name; no system defaults one.</div>")
    return page("AFE", body)


def t_ticket(b, key):
    t = b["documents"][key]
    hw = b["handwriting"]
    body = letterhead(t["vendor_name"], VENDOR_ADDR)
    body += "<h1>Field Service Ticket</h1>"
    body += ("<div class='two'>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Ticket number</td><td>{e(t['ticket_number'])}</td></tr>"
             f"<tr><td class='k'>Service date</td><td>{e(t['service_date'])}</td></tr>"
             f"<tr><td class='k'>Vendor</td><td>{e(t['vendor_name'])}</td></tr>"
             f"</table></div>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Well</td><td>{e(t['well_name'])}</td></tr>"
             f"<tr><td class='k'>AFE number</td><td>{e(t['afe_number'])}</td></tr>"
             f"<tr><td class='k'>Operator</td>"
             f"<td>{e(b['entities']['operator_name'])}</td></tr>"
             f"</table></div></div>")
    body += "<h2>Services performed</h2>"
    rows = ""
    for i, it in enumerate(t["line_items"]):
        is_hand = (key == hw["doc_id"] and i == hw["line_index"])
        q = (f"<span class='hand'>{qty(it['quantity'])}</span>" if is_hand
             else qty(it["quantity"]))
        rows += (f"<tr><td>{e(it['description'])}</td>"
                 f"<td class='c' style='height:23px'>{q}</td>"
                 f"<td class='c'>{e(it['unit'])}</td>"
                 f"<td class='r'>{usd(it['rate'])}</td>"
                 f"<td class='r'>{usd(it['amount'])}</td></tr>")
    body += ("<table class='grid'><tr><th>Description</th>"
             "<th class='c' style='width:13%'>Quantity</th>"
             "<th class='c' style='width:11%'>Unit</th>"
             "<th class='r' style='width:15%'>Rate (USD)</th>"
             "<th class='r' style='width:17%'>Amount (USD)</th></tr>"
             + rows
             + f"<tr class='tot'><td colspan='4'>Ticket total</td>"
               f"<td class='r'>{usd(t['total'])}</td></tr></table>")
    body += ("<div class='note'>Quantities recorded at the wellsite. Rates per the master service "
             "agreement rate sheet in effect on the service date.</div>")
    body += ("<div class='sig'><div class='two'>"
             "<div><div class='sigline'></div>"
             "<div class='siglabel'>Customer representative signature</div></div>"
             "<div><div class='sigline'></div>"
             "<div class='siglabel'>Printed name and date</div></div></div></div>")
    return page(f"Field ticket {t['ticket_number']}", body)


def t_hauling(b):
    h = b["documents"]["hauling_log"]
    body = letterhead(h["hauler_name"], HAULER_ADDR)
    body += "<h1>Fluid Hauling Log</h1>"
    body += ("<div class='two'>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Log number</td><td>{e(h['log_number'])}</td></tr>"
             f"<tr><td class='k'>Log date</td><td>{e(h['log_date'])}</td></tr>"
             f"</table></div>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Well</td><td>{e(h['well_name'])}</td></tr>"
             f"<tr><td class='k'>Hauler</td><td>{e(h['hauler_name'])}</td></tr>"
             f"</table></div></div>")
    body += "<h2>Loads</h2>"
    rows = ""
    for l in h["loads"]:
        rows += (f"<tr><td class='c'>{l['load_no']}</td><td class='c'>{e(l['time'])}</td>"
                 f"<td>{e(l['fluid_type'])}</td>"
                 f"<td class='r'>{qty(l['barrels'])}</td>"
                 f"<td>{e(l['destination'])}</td></tr>")
    body += ("<table class='grid'><tr><th class='c' style='width:8%'>Load</th>"
             "<th class='c' style='width:11%'>Time</th><th style='width:26%'>Fluid type</th>"
             "<th class='r' style='width:15%'>Barrels</th><th>Destination</th></tr>"
             + rows
             + f"<tr class='tot'><td colspan='3'>Total barrels</td>"
               f"<td class='r'>{qty(h['total_barrels'])}</td><td></td></tr></table>")
    body += ("<div class='note'>Volumes are gauged tank measurements at pickup. Disposal facility "
             "receipts are retained by the hauler.</div>")
    body += ("<div class='sig'><div class='two'>"
             "<div><div class='sigline'></div>"
             "<div class='siglabel'>Driver signature</div></div>"
             "<div><div class='sigline'></div>"
             "<div class='siglabel'>Facility receipt clerk</div></div></div></div>")
    return page("Hauling log", body)


def t_invoice(b):
    v = b["documents"]["invoice"]
    body = letterhead(v["vendor_name"], VENDOR_ADDR)
    body += "<h1>Invoice</h1>"
    body += ("<div class='two'>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Invoice number</td><td>{e(v['invoice_number'])}</td></tr>"
             f"<tr><td class='k'>Invoice date</td><td>{e(v['invoice_date'])}</td></tr>"
             f"<tr><td class='k'>Terms</td><td>Net 30</td></tr>"
             f"</table></div>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Bill to</td>"
             f"<td>{e(b['entities']['operator_name'])}</td></tr>"
             f"<tr><td class='k'>Well</td><td>{e(v['well_name'])}</td></tr>"
             f"<tr><td class='k'>AFE number</td><td>{e(v['afe_number'])}</td></tr>"
             f"</table></div></div>")
    body += "<h2>Billed detail</h2>"
    rows = ""
    for it in v["line_items"]:
        rows += (f"<tr><td class='c'>{e(it['ticket_ref'])}</td><td>{e(it['description'])}</td>"
                 f"<td class='c'>{qty(it['quantity'])}</td><td class='c'>{e(it['unit'])}</td>"
                 f"<td class='r'>{usd(it['rate'])}</td>"
                 f"<td class='r'>{usd(it['amount'])}</td></tr>")
    body += ("<table class='grid'><tr><th class='c' style='width:14%'>Ticket</th>"
             "<th>Description</th><th class='c' style='width:10%'>Qty</th>"
             "<th class='c' style='width:9%'>Unit</th>"
             "<th class='r' style='width:14%'>Rate (USD)</th>"
             "<th class='r' style='width:16%'>Amount (USD)</th></tr>"
             + rows
             + f"<tr class='sub'><td colspan='5'>Subtotal</td>"
               f"<td class='r'>{usd(v['subtotal'])}</td></tr>"
             f"<tr class='sub'><td colspan='5'>Sales tax</td>"
             f"<td class='r'>{usd(v['tax'])}</td></tr>"
             f"<tr class='tot'><td colspan='5'>Invoice total</td>"
             f"<td class='r'>{usd(v['total'])}</td></tr></table>")
    body += ("<div class='note'>Supporting field tickets are attached. Rates per the master "
             "service agreement rate sheet.</div>")
    return page("Invoice", body)


def t_jib(b):
    j = b["documents"]["jib"]
    body = letterhead(j["operator_name"], OPER_ADDR)
    body += "<h1>Joint Interest Billing Statement</h1>"
    body += ("<div class='two'>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Statement period</td><td>{e(j['statement_period'])}</td></tr>"
             f"<tr><td class='k'>Statement date</td><td>{e(j['statement_date'])}</td></tr>"
             f"<tr><td class='k'>Property number</td><td>{e(j['property_number'])}</td></tr>"
             f"<tr><td class='k'>Well</td><td>{e(j['well_name'])}</td></tr>"
             f"</table></div>"
             f"<div><table class='kv'>"
             f"<tr><td class='k'>Owner</td><td>{e(j['owner_name'])}</td></tr>"
             f"<tr><td class='k'>Owner number</td><td>{e(j['owner_number'])}</td></tr>"
             f"<tr><td class='k'>Working interest</td><td>{dec6(j['wi_decimal'])}</td></tr>"
             f"<tr><td class='k'>Payment due</td><td>{e(j['due_date'])}</td></tr>"
             f"</table></div></div>")
    body += "<h2>Charges for the period</h2>"
    rows = ""
    for l in j["lines"]:
        rows += (f"<tr><td class='c'>{l['line_no']}</td><td class='c'>{e(l['afe_ref'])}</td>"
                 f"<td class='c'>{e(l['account_code'])}</td><td>{e(l['description'])}</td>"
                 f"<td class='r'>{usd(l['gross_amount'])}</td>"
                 f"<td class='c'>{dec6(l['owner_decimal'])}</td>"
                 f"<td class='r'>{usd(l['net_amount'])}</td></tr>")
    body += ("<table class='grid'><tr><th class='c' style='width:6%'>Line</th>"
             "<th class='c' style='width:15%'>AFE ref</th>"
             "<th class='c' style='width:9%'>Account</th><th>Description</th>"
             "<th class='r' style='width:14%'>Gross (USD)</th>"
             "<th class='c' style='width:12%'>Owner decimal</th>"
             "<th class='r' style='width:14%'>Net (USD)</th></tr>"
             + rows
             + f"<tr class='tot'><td colspan='4'>Totals</td>"
               f"<td class='r'>{usd(j['gross_total'])}</td><td></td>"
               f"<td class='r'>{usd(j['net_total'])}</td></tr></table>")
    body += ("<div class='note'>Net amount is the owner share of the gross charge at the decimal "
             "shown on each line. Charges are billed under the operating agreement for the "
             "property.</div>")

    # page 2
    body += "<div class='pagebreak'></div>"
    body += (f"<div class='contbanner'>{e(j['property_number'])} &mdash; "
             f"{e(j['statement_period'])} &mdash; page 2 of 2</div>")
    body += letterhead(j["operator_name"], OPER_ADDR)
    body += "<h2>Account summary</h2>"
    body += ("<table class='grid'>"
             "<tr><th>Item</th><th class='r' style='width:26%'>Amount (USD)</th></tr>"
             f"<tr><td>Prior balance</td><td class='r'>0.00</td></tr>"
             f"<tr><td>Current period net charges</td>"
             f"<td class='r'>{usd(j['net_total'])}</td></tr>"
             f"<tr><td>Payments and credits</td><td class='r'>0.00</td></tr>"
             f"<tr class='tot'><td>Balance due {e(j['due_date'])}</td>"
             f"<td class='r'>{usd(j['net_total'])}</td></tr></table>")
    body += "<h2>Remittance</h2>"
    body += ("<p>Reference the property number and owner number on the remittance advice. "
             "Direct billing questions to the joint interest billing department within 24 months "
             "of the statement date, as provided by the accounting procedure attached to the "
             "operating agreement.</p>")
    body += "<h2>Owner review</h2>"
    body += ("<table class='grid'>"
             "<tr><th style='width:34%'>Item</th><th>Entry</th></tr>"
             "<tr><td>Reviewed by (print name)</td><td style='height:26px'></td></tr>"
             "<tr><td>Title</td><td style='height:26px'></td></tr>"
             "<tr><td>Date</td><td style='height:26px'></td></tr>"
             "<tr><td>Disposition</td><td style='height:26px'></td></tr></table>")
    body += ("<div class='note'>Review fields are blank by design. A person types the approver "
             "name; no system defaults one.</div>")
    return page("JIB statement", body)


TEMPLATES = {
    "afe_cover": t_afe_cover,
    "afe": t_afe,
    "ticket_a": lambda b: t_ticket(b, "ticket_a"),
    "ticket_b": lambda b: t_ticket(b, "ticket_b"),
    "hauling_log": t_hauling,
    "invoice": t_invoice,
    "jib": t_jib,
}

# --------------------------------------------------------------------------


def chrome_pdf(html_path: Path, out_pdf: Path):
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={out_pdf}", f"file://{html_path}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not out_pdf.exists():
        sys.exit(f"chrome failed for {html_path}\n{r.stdout}\n{r.stderr}")


def scan_pass(src: Path, dst: Path):
    # Same pass build_corpus.py uses: 150 dpi, gray, 0.6 deg skew, gaussian noise, JPEG q75.
    # Two additions are forced by Chrome-produced PDFs and were verified from the page images:
    #   * flatten onto white first - Chrome writes an alpha channel, and without the flatten
    #     every shaded table cell rasterizes solid black;
    #   * -attenuate before +noise, then -type Grayscale - otherwise the noise operator
    #     re-expands the frame to RGB and magick's PDF writer emits a JPEG whose declared
    #     width is a third of the real one, so the page renders as three tiled copies.
    subprocess.run(["magick", "-density", "150", str(src),
                    "-background", "white", "-alpha", "remove", "-alpha", "off",
                    "-colorspace", "Gray",
                    "-background", "white", "-rotate", "0.6",
                    "-attenuate", "0.15", "+noise", "Gaussian",
                    "-colorspace", "Gray", "-type", "Grayscale",
                    "-quality", "75", "-compress", "JPEG", str(dst)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scan", action="store_true")
    a = ap.parse_args()

    book = json.loads(BOOK.read_text())
    for p in (CLEAN, CLEAN / "packets", SCAN, SCAN / "packets", BUILD):
        p.mkdir(parents=True, exist_ok=True)

    pages_of = {}
    for doc_id, fname, cls, packet in DOCS:
        h = BUILD / f"{doc_id}.html"
        h.write_text(TEMPLATES[doc_id](book))
        out = CLEAN / fname
        if out.exists():
            out.unlink()
        chrome_pdf(h, out)
        n = len(PdfReader(str(out)).pages)
        pages_of[doc_id] = n
        print(f"{fname}: {n} page(s)")

    expect = {"afe_cover": 1, "afe": 2, "ticket_a": 1, "ticket_b": 1,
              "hauling_log": 1, "invoice": 1, "jib": 2}
    bad = {k: v for k, v in pages_of.items() if v != expect[k]}
    if bad:
        sys.exit(f"page-count mismatch (expected {expect}): {bad}")

    # packets
    packet_rows = []
    for pid, ids in PACKETS:
        w = PdfWriter()
        cursor = 1
        split_truth, doc_pages = {}, {}
        for did in ids:
            cls = next(c for d, f, c, p in DOCS if d == did)
            src = CLEAN / next(f for d, f, c, p in DOCS if d == did)
            rng = list(range(cursor, cursor + pages_of[did]))
            for pg in PdfReader(str(src)).pages:
                w.add_page(pg)
            split_truth.setdefault(cls, []).extend(rng)
            doc_pages[did] = rng
            cursor += pages_of[did]
        out = CLEAN / "packets" / f"{pid}.pdf"
        with open(out, "wb") as fh:
            w.write(fh)
        packet_rows.append({"packet_id": pid, "file": out, "pages": cursor - 1,
                            "split_truth": split_truth, "doc_pages": doc_pages})
        print(f"packet {pid}: {cursor-1} pages, split {split_truth}")

    # scans
    if not a.no_scan:
        for _, fname, _, _ in DOCS:
            scan_pass(CLEAN / fname, SCAN / fname)
        for row in packet_rows:
            scan_pass(row["file"], SCAN / "packets" / f"{row['packet_id']}.pdf")
        print("scan variants written")

    # manifest
    doc_pages_all = {}
    for row in packet_rows:
        doc_pages_all.update(row["doc_pages"])
    docs = []
    for doc_id, fname, cls, packet in DOCS:
        c, s = CLEAN / fname, SCAN / fname
        docs.append({
            "doc_id": doc_id, "file": f"synth/caprock/{fname}",
            "scan_file": f"synth/caprock-scan/{fname}", "class": cls, "packet": packet,
            "pages": doc_pages_all[doc_id],
            "page_count": pages_of[doc_id],
            "sha256": sha256(c), "scan_sha256": sha256(s) if s.exists() else None,
        })
    packets = []
    for row in packet_rows:
        sp = SCAN / "packets" / f"{row['packet_id']}.pdf"
        packets.append({
            "packet_id": row["packet_id"],
            "file": f"synth/caprock/packets/{row['packet_id']}.pdf",
            "scan_file": f"synth/caprock-scan/packets/{row['packet_id']}.pdf",
            "pages": row["pages"], "split_truth": row["split_truth"],
            "sha256": sha256(row["file"]), "scan_sha256": sha256(sp) if sp.exists() else None,
        })
    manifest = {
        "built": dt.date.today().isoformat(),
        "synthetic": True,
        "story": book["story"],
        "documents": docs,
        "packets": packets,
        "references": {
            "book": "synth/src/book.json",
            "planted": "synth/planted.json",
            "doi": "synth/reference/doi.json",
            "contract_rates": "synth/reference/contract_rates.json",
            "afe_election": "synth/reference/afe_election.json",
        },
        "planted_sha256": sha256(SYNTH / "planted.json"),
        "licence": "synthetic, no licence needed",
    }
    (SYNTH / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"manifest: {SYNTH/'manifest.json'}")
    print(f"planted sha256 {manifest['planted_sha256']}")


if __name__ == "__main__":
    main()
