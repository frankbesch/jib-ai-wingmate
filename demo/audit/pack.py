#!/usr/bin/env python3
"""Build the month's audit pack: one FEDS-styled PDF a JV accountant can hand to an auditor.

  python3 audit/pack.py --run runs/<run_id> [--out runs/<run_id>/audit-pack.pdf]
                        [--decisions audit/decisions.jsonl]

Reads (never edits): runs/<run_id>/month.json, runs/<run_id>/exceptions.json,
runs/<run_id>/scorecard.json (optional), the decision log, and the packet PDFs named in
month.json. Writes runs/<run_id>/audit-pack.html, the PDF, its page PNGs (via the FEDS
render script), the citation thumbnails, and runs/<run_id>/audit-pack.json for the console.

Pages
  1      cover: property, owner, period, run id, synthetic banner, go/no-go, credits and cost
  2..    exception list: one row per exception, with the decision from the log or OPEN
  ..     citation thumbnails: every JIB line and every ticket line, cropped from the packet page
  last   approver trail: every decision row for this run verbatim, plus the honesty lines

No approver name is ever written here. Decisions are read from the log a human typed; an
exception with no decision row prints OPEN. Everything in this pack is synthetic.

Exits non-zero when the render receipt flags a page.
"""
import argparse
import base64
import datetime as dt
import html
import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent          # .../demo
TEMPLATE = pathlib.Path(__file__).resolve().parent / 'pack_template.html'
RENDER = os.environ.get('AUDIT_RENDER_SH', '')  # HTML-to-PDF render script; not shipped

THUMBS_PER_PAGE = 5          # contract allows up to 8; 5 keeps a full-width strip readable
THUMB_COL_IN = 7.26          # printable column width, letter minus the 0.62in side margins
THUMB_AVAIL_IN = 8.10        # column height left for thumbnails after the header and the band (8.40 touched the footer rule, 09-05)
THUMB_CAP_IN = 0.30          # caption plus row gap
EXC_PER_PAGE = 8
TAIL_INLINE_MAX = 4          # above this many rows the control summary takes its own page
PAD = 0.06                   # citation bbox padding, page fractions
DPI = 110

ROLE_TODO = {
    'jv_accountant': 'check the printed decimal and net against the division order, then sign',
    'supply_chain': 'check the billed rate against the rate sheet, then sign',
    'field': 'check the printed quantity in the field, key it, then sign',
}

RULE_LABEL = {
    'rule_1_decimal': 'rule 1 · owner decimal',
    'rule_2_rate': 'rule 2 · contract rate',
    'rule_3_afe_ref': 'rule 3 · AFE reference',
    'extraction': 'extraction exception',
}


# ---------------------------------------------------------------- small helpers

def esc(v):
    return html.escape('' if v is None else str(v), quote=False)


def money(v):
    if v is None:
        return '—'
    return ('-$' if v < 0 else '$') + f'{abs(float(v)):,.2f}'


def flat(v):
    """Render an observed/expected payload as one compact line."""
    if v is None:
        return '—'
    if isinstance(v, dict):
        return '; '.join(f'{k} {fmt_scalar(x)}' for k, x in v.items())
    return fmt_scalar(v)


def fmt_scalar(x):
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isinstance(x, float):
        return f'{x:,.6f}'.rstrip('0').rstrip('.') if abs(x) < 1 else f'{x:,.2f}'
    if isinstance(x, int):
        return f'{x:,}'
    return str(x)


def chunks_balanced(items, cap):
    """Split into as few chunks as possible, then even them out."""
    if not items:
        return []
    n = max(1, -(-len(items) // cap))
    base, extra = divmod(len(items), n)
    out, i = [], 0
    for k in range(n):
        size = base + (1 if k < extra else 0)
        out.append(items[i:i + size])
        i += size
    return out


# ---------------------------------------------------------------- inputs

def load_run(run_dir):
    month = json.loads((run_dir / 'month.json').read_text())
    exc_path = run_dir / 'exceptions.json'
    if not exc_path.exists():
        sys.exit(f'no exceptions.json in {run_dir}: run  python3 reconcile.py --run {run_dir}  first')
    exceptions = json.loads(exc_path.read_text())
    score = {}
    sc = run_dir / 'scorecard.json'
    if sc.exists():
        try:
            score = json.loads(sc.read_text())
        except json.JSONDecodeError:
            score = {}
    return month, exceptions, score


def signed(row):
    """A decision counts only when a person typed a name. A blank approver is not a signature."""
    return bool(str(row.get('approver') or '').strip())


def load_decisions(path, run_id):
    rows = []
    if not path or not path.exists():
        return rows
    for ln, raw in enumerate(path.read_text().splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            print(f'  skipped unparseable decision row at line {ln}')
            continue
        if row.get('run_id') == run_id:
            rows.append(row)
    rows.sort(key=lambda r: str(r.get('ts') or ''))
    return rows


# ---------------------------------------------------------------- thumbnails

def page_png(packet_pdf, page, cache_dir, cache):
    key = (str(packet_pdf), page)
    if key in cache:
        return cache[key]
    out_stem = cache_dir / f'{packet_pdf.stem}-p{page}'
    subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-r', str(DPI),
                    '-png', '-singlefile', str(packet_pdf), str(out_stem)], check=True)
    png = out_stem.with_suffix('.png')
    cache[key] = png
    return png


def crop_data_uri(png_path, bbox, out_path, aspect=None):
    """Crop the cited region, padded 6%, and say whether the crop caught any ink.

    When an aspect is asked for, the padded box grows (or, at the padding only, shrinks) around
    the same centre so the crop fills its frame instead of letterboxing. The cited box itself is
    never cut into.
    """
    from PIL import Image, ImageDraw
    im = Image.open(png_path)
    w, h = im.size
    x0, y0, x1, y1 = bbox
    # Row strip (2026-09-05): the crop spans the printed row's full width so the reader sees the line the value
    # sits on, and the cited box itself is outlined. A cell-only crop was a single number blown up to page width.
    box = [max(0, int(0.05 * w)), max(0, int((y0 - PAD) * h)),
           min(w, int(0.95 * w)), min(h, int((y1 + PAD) * h))]
    if aspect and box[2] > box[0] and box[3] > box[1]:
        cy = (box[1] + box[3]) / 2
        bw = box[2] - box[0]
        want_h = bw / aspect
        raw_h = max(2.0, (y1 - y0) * h)          # never crop inside the cited box
        want_h = max(want_h, raw_h)
        top, bot = cy - want_h / 2, cy + want_h / 2
        if top < 0:
            top, bot = 0, min(h, want_h)
        if bot > h:
            bot, top = h, max(0, h - want_h)
        box[1], box[3] = int(top), int(bot)
    if box[2] <= box[0] or box[3] <= box[1]:
        return None, False
    crop = im.crop(box).convert('RGB')
    d = ImageDraw.Draw(crop)
    d.rectangle([int(x0 * w) - box[0] - 3, int(y0 * h) - box[1] - 3, int(x1 * w) - box[0] + 3, int(y1 * h) - box[1] + 3],
                outline=(181, 93, 67), width=3)   # FEDS terra, the cited box
    crop.save(out_path, 'PNG')
    gray = crop.convert('L')
    ink = sum(1 for px in gray.getdata() if px < 160)  # noqa: PIL 14 deprecation; fine through 2027
    blank = ink < 0.0015 * gray.width * gray.height
    return ('data:image/png;base64,' + base64.b64encode(out_path.read_bytes()).decode()), blank


def line_thumbs(month, run_dir):
    """One thumbnail per JIB line and per field-ticket line item."""
    wants = []
    for doc_id, doc in month.get('documents', {}).items():
        cls = doc.get('class')
        vals = doc.get('values') or {}
        if cls == 'jib_statement':
            for i in range(len(vals.get('lines') or [])):
                wants.append((doc_id, cls, f'lines[{i}]',
                              [f'lines[{i}].net_amount', f'lines[{i}].owner_decimal',
                               f'lines[{i}].gross_amount', f'lines[{i}].description']))
        elif cls == 'field_ticket':
            for i in range(len(vals.get('line_items') or [])):
                wants.append((doc_id, cls, f'line_items[{i}]',
                              [f'line_items[{i}].rate', f'line_items[{i}].amount',
                               f'line_items[{i}].description']))

    cache_dir = run_dir / 'audit-thumbs'
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True)
    cache, thumbs = {}, []
    pages = chunks_balanced(list(range(len(wants))), THUMBS_PER_PAGE)
    frame_in = {}
    for group in pages:
        n = len(group)
        fh = max(0.9, min(2.6, (THUMB_AVAIL_IN - n * THUMB_CAP_IN) / n))
        for i in group:
            frame_in[i] = fh
    for idx, (doc_id, cls, line_key, prefer) in enumerate(wants):
        doc = month['documents'][doc_id]
        cits = doc.get('citations') or {}
        path = next((p for p in prefer if p in cits), None)
        if path is None:
            path = next((p for p in cits if p.startswith(line_key + '.')), None)
        cit = cits.get(path) if path else None
        packet = doc.get('packet')
        pfile = (month.get('packets', {}).get(packet) or {}).get('file')
        fh = frame_in.get(idx, 1.4)
        entry = {'doc_id': doc_id, 'doc_class': cls, 'line': line_key, 'frame_in': fh,
                 'field_path': path or f'{line_key} (no citation)',
                 'page': (cit or {}).get('page'), 'text': (cit or {}).get('text', ''),
                 'uri': None, 'blank': False}
        bbox = (cit or {}).get('bbox')
        if cit and bbox and pfile:
            pdf = ROOT / pfile
            if pdf.exists():
                png = page_png(pdf, int(cit['page']), cache_dir, cache)
                safe = entry['field_path'].replace('[', '_').replace(']', '')
                entry['uri'], entry['blank'] = crop_data_uri(
                    png, bbox, cache_dir / f'{doc_id}-{safe}.png',
                    aspect=THUMB_COL_IN / fh)
        thumbs.append(entry)
    return thumbs, cache_dir


# ---------------------------------------------------------------- page builders

def shell(page_html, stamp, foot_left, foot_right):
    return (f'<div class="page"><div class="tab"></div>'
            f'<p class="stamp">{esc(stamp)}</p><div class="main">{page_html}</div>'
            f'<div class="footer"><span>{esc(foot_left)}</span>'
            f'<span>{esc(foot_right)}</span></div></div>')


def cover_page(month, exceptions, score, decisions, thumbs):
    jib = next((d for d in month.get('documents', {}).values()
                if d.get('class') == 'jib_statement'), {})
    v = jib.get('values') or {}
    fixture = bool(month.get('synthetic_responses'))
    banner = ('Synthetic documents; SYNTHETIC fixture responses' if fixture
              else 'Synthetic documents; live Pulse responses')
    ex = exceptions.get('exceptions', [])
    decided_ids = {r.get('exception_id') for r in decisions if signed(r)}
    n_open = sum(1 for e in ex if e['id'] not in decided_ids)

    meta = [
        ('Property', v.get('property_number')), ('Well', v.get('well_name')),
        ('Owner', v.get('owner_name')), ('Owner number', v.get('owner_number')),
        ('Statement period', v.get('statement_period')), ('Operator', v.get('operator_name')),
        ('Working interest (header)', f"{v.get('wi_decimal'):.6f}" if isinstance(v.get('wi_decimal'), (int, float)) else '—'),
        ('Payment due', v.get('due_date')),
        # run id, mode, set, and rules version live in the stamp and the page-2 kicker; dropped here 2026-09-05 so the
        # eleven-line go/no-go table and the packets table fit the cover without clipping the credits band.
    ]
    meta_html = ''.join(f'<div><span class="k">{esc(k)}</span>'
                        f'<span class="v">{esc(x if x is not None else "—")}</span></div>'
                        for k, x in meta)

    tiles = [(str(len(ex)), 'exceptions'), (str(n_open), 'open'),
             (f"{month.get('cycle_seconds', 0):.0f}s", 'cycle time'),
             (money(month.get('cost_usd_at_list')), 'list cost')]
    tiles_html = ''.join(f'<div class="tile"><div class="n">{esc(n)}</div>'
                         f'<div class="l">{esc(l)}</div></div>' for n, l in tiles)

    gng = score.get('go_no_go') or (score.get('summary') or {}).get('go_no_go') or []
    if gng:
        rows = ''.join(
            '<tr><td>{}</td><td class="num">{}</td><td class="num">{}</td>'
            '<td>{}</td></tr>'.format(
                esc(g.get('line')),
                esc(fmt_scalar(g['target']) if g.get('target') is not None else 'report only'),
                esc(fmt_scalar(g['measured']) if g.get('measured') is not None else 'not measured'),
                esc(g.get('verdict')))
            for g in gng)
        gng_html = ('<table><tr><th>Line</th><th class="num">Target</th>'
                    '<th class="num">Measured</th><th>Verdict</th></tr>' + rows + '</table>')
    else:
        gng_html = '<p class="note">No go/no-go block in this run scorecard.</p>'

    prows = ''
    for name, p in (month.get('packets') or {}).items():
        cu = sum(float((p.get(k) or {}).get('credits_used') or 0)
                 for k in ('extract', 'split', 'schema'))
        splits = (p.get('split') or {}).get('splits') or {}
        span = ', '.join(k.replace('_statement', '').replace('field_ticket_', 'ticket ') for k, pg in splits.items() if pg)  # topics with pages only
        prows += ('<tr><td>{}</td><td class="num">{}</td><td class="num">{}</td>'
                  '<td class="num">{}</td><td>{}</td></tr>').format(
            esc(name), esc(p.get('pages')), esc(f'{cu:g}'),
            esc(f"{p.get('cycle_seconds', 0):g}s"), esc(span))
    credits = month.get('credits') or {}
    crow = ' · '.join(f'{k} {fmt_scalar(x)}' for k, x in credits.items())

    fixture_resp = bool(month.get('synthetic_responses'))
    perts = month.get('fixture_perturbations') or []
    cost_band = (f'Credits by call: {crow}. Crops: {len(thumbs)}.' +
                 (' Fixture responses: cycle and credits are not timings or costs; the misses above are perturbations '
                  + ', '.join(x.split(' ')[0] for x in perts) + '.' if fixture_resp else ''))
    body = f'''<p class="kicker">Joint interest billing · month close</p>
<h1>Audit pack — {esc(v.get('well_name') or 'well')}, {esc(v.get('statement_period') or 'period')}</h1>
<p class="lede">Every page behind this month's JIB, the exceptions the controls raised, and the
citation each number came from.</p>
<div class="banner"><strong>{esc(banner)}</strong>. No figure, name, or document on these pages
describes a real property, operator, vendor, or person.</div>
<div class="tiles">{tiles_html}</div>
<h2>Statement under review</h2>
<div class="meta">{meta_html}</div>
<h2>Go / no-go</h2>
{gng_html}
<h2>Packets, credits, and cost</h2>
<table><tr><th>Packet</th><th class="num">Pages</th><th class="num">Credits</th>
<th class="num">Cycle</th><th>Documents</th></tr>{prows}</table>
<div class="band">{esc(cost_band)}</div>'''
    # Rule definitions print on the last exceptions page (2026-09-05): an auditor reads the test beside the
    # findings, and the page had a 1.6in void once the fixture noise was retired. The cover lost four meta rows
    # (run id, mode, set, rules version live in the stamp and kicker) so the eleven-line go/no-go table fits.
    rules_html = '''<h2>The three controls, as run</h2>
<table><tr><th style="width:18%">Rule</th><th>Test</th><th style="width:20%">Reference</th><th style="width:14%">Route</th></tr>
<tr><td>rule 1 · owner decimal</td><td>net = gross × owner decimal to the cent; printed decimal = division order</td><td>division of interest</td><td>jv_accountant</td></tr>
<tr><td>rule 2 · contract rate</td><td>ticket line rate ≤ contract rate for vendor, service, unit</td><td>contract rate sheet</td><td>supply_chain</td></tr>
<tr><td>rule 3 · AFE reference</td><td>JIB line cites the elected AFE and one of its account codes</td><td>AFE election, AFE lines</td><td>jv_accountant</td></tr></table>
'''
    return body, rules_html


def exception_pages(exceptions, decisions, extra_html='', month=None):
    ex = exceptions.get('exceptions', [])
    by_id = {}
    for r in decisions:
        if signed(r):
            by_id[r.get('exception_id')] = r    # rows are ts-sorted; last signed one wins
    summary = exceptions.get('summary') or {}
    pages = []
    groups = chunks_balanced(ex, EXC_PER_PAGE) or [[]]
    for gi, group in enumerate(groups):
        rows = ''
        for e in group:
            d = by_id.get(e['id'])
            if d:
                cell = ('<span class="pill done">{}</span><br>{}<br>{}'.format(
                    esc(d.get('disposition')), esc(d.get('approver')), esc(d.get('ts'))))
            else:
                cell = '<span class="pill open">open</span>'
            rows += (
                '<tr><td>{id}</td><td>{rule}</td><td>{doc} · p{pg}<br><span class="mono">{fp}</span></td>'
                '<td class="tight">{obs}</td><td class="tight">{exp}</td>'
                '<td class="num">{delta}</td>'
                '<td>{role}</td><td>{dec}</td></tr>'
                '<tr class="sub"><td></td><td colspan="7">{msg}</td></tr>').format(
                id=esc(e.get('id')), rule=esc(RULE_LABEL.get(e.get('rule'), e.get('rule'))),
                doc=esc(e.get('doc_id')), fp=esc(e.get('field_path')),
                pg=esc(e.get('page') if e.get('page') is not None else '—'),
                obs=esc(flat(e.get('observed'))), exp=esc(flat(e.get('expected'))),
                delta=esc(money(e.get('delta_usd'))), role=esc(e.get('approver_role')),
                dec=cell, msg=esc(e.get('message')))
        if not group:
            rows = ('<tr><td colspan="8">No exception fired in this run. '
                    'Every checked line matched the reference data.</td></tr>')
        head = ('<table><tr><th style="width:7%">ID</th><th style="width:12%">Rule</th>'
                '<th style="width:18%">Document</th>'
                '<th style="width:20%">Observed</th><th style="width:16%">Expected</th>'
                '<th class="num" style="width:8%">Delta</th><th style="width:9%">Route</th>'
                '<th style="width:11%">Decision</th></tr>' + rows + '</table>')
        tail = ''
        if gi == len(groups) - 1:  # controls are always built; inline-vs-split is decided below
            route_rows = ''
            for role, todo in ROLE_TODO.items():
                mine = [e for e in ex if e.get('approver_role') == role
                        and e['id'] not in by_id]
                if not mine and not any(e.get('approver_role') == role for e in ex):
                    continue
                net = sum(float(e.get('delta_usd') or 0) for e in mine)
                route_rows += ('<tr><td>{}</td><td class="num">{}</td>'
                               '<td class="num">{}</td><td>{}</td></tr>').format(
                    esc(role), esc(len(mine)), esc(money(net)), esc(todo))
            route_rows = route_rows or ('<tr><td colspan="4">No open exception is routed to '
                                        'any role.</td></tr>')
            fired = {r: sum(1 for e in ex if e.get('rule') == r)
                     for r in ('rule_1_decimal', 'rule_2_rate', 'rule_3_afe_ref', 'extraction')}
            controls = f'''<p>Rule 1 read {esc(summary.get('jib_lines', 'every'))} JIB lines against the division order, fired {esc(fired['rule_1_decimal'])}.
Rule 2 read {esc(summary.get('ticket_lines', 'every'))} ticket lines against the rate sheet, fired {esc(fired['rule_2_rate'])}.
Rule 3 read the same JIB lines against the elected AFE, fired {esc(fired['rule_3_afe_ref'])}. The extraction check read every
required field and printed row count, fired {esc(fired['extraction'])}. Clean checks recorded: {esc(len(exceptions.get('clean_lines') or []))}.</p>
<h2>Where each open exception goes</h2>
<table><tr><th style="width:22%">Role</th><th class="num" style="width:10%">Open</th>
<th class="num" style="width:14%">Net delta</th><th>What the role has to do</th></tr>{route_rows}</table>
{extra_html}
<div class="band">Pulse read the paper and cited it; the controls and this pack are customer code.</div>'''
        last = gi == len(groups) - 1
        band = '<div class="band">Pulse read the paper and cited it; the controls and this pack are customer code.</div>'
        controls = controls.replace(band, '') if last else ''
        lede = ('<p class="lede">One row per exception. The decision column is read from the decision log; a row a '
                'human has not signed prints open.</p>')
        kick = f'<p class="kicker">Exceptions · rules version {esc(exceptions.get("rules_version"))}</p><h1>What the controls stopped</h1>'
        if not last:
            pages.append(f'{kick}{lede}{head}{band}')
            continue
        routes_start = controls.index('<h2>Where each open exception goes</h2>')
        rules_start = controls.index('<h2>The three controls, as run</h2>')
        checks_html, routes_html, rules_html = controls[:routes_start], controls[routes_start:rules_start], controls[rules_start:]
        # one-line route summary for the busier pages
        by_role = {}
        for e in ex:
            if e['id'] not in by_id:
                r = by_role.setdefault(e.get('approver_role'), [0, 0.0]); r[0] += 1; r[1] += float(e.get('delta_usd') or 0)
        route_line = ('<p class="note">Open by role: ' + ' · '.join(f'{esc(k)} {n} ({money(v)})' for k, (n, v) in by_role.items()) +
                      '. An exception stays open until a person signs it in the queue, which refuses a blank name.</p>')
        n = len(group)
        # Page budgets measured 2026-09-05 on letter paper at the template's type sizes (compact rows ≈ 0.75in each):
        if n <= 2:      # exceptions + checks + route table + rules + AFE lines; lines page = JIB + tickets + hauling loads + totals
            pages.append(f'{kick}{lede}{head}<h2>What the controls checked</h2>{checks_html}{routes_html}{rules_html}{afe_lines_html(month)}{band}')
            pages.append(lines_page(month, ex, '', band, ('jib', 'tickets', 'hauling', 'totals')))
        elif n == 3:    # the rules table moves to the lines page; hauling loads drop from it (measured 2026-09-05)
            pages.append(f'{kick}{lede}{head}<h2>What the controls checked</h2>{checks_html}{routes_html}{afe_lines_html(month)}{band}')
            pages.append(lines_page(month, ex, rules_html, band, ('jib', 'tickets', 'totals')))
        elif n <= 5:    # exceptions + checks + routes (table up to four rows, one line at five) + rules; lines page = AFE + JIB + tickets
            pages.append(f'{kick}{lede}{head}<h2>What the controls checked</h2>{checks_html}{routes_html if n <= 4 else route_line}{rules_html}{band}')
            pages.append(lines_page(month, ex, '', band, ('afe', 'jib', 'tickets')))
        else:           # six or more: exceptions + checks + route line; rules + AFE + JIB; tickets + hauling (the last page may run short)
            pages.append(f'{kick}{lede}{head}<h2>What the controls checked</h2>{checks_html}{route_line}{band}')
            pages.append(lines_page(month, ex, rules_html, band, ('afe', 'jib')))
            pages.append(lines_page(month, ex, '', band, ('tickets', 'hauling')))
    return pages


def lines_page(month, ex, prefix_html, band, tables):
    """'Every line, as read': the requested line tables (afe, jib, tickets, hauling) with the rule verdict per line."""
    parts = {'afe': lambda: afe_lines_html(month), 'jib': lambda: jib_lines_html(month, ex),
             'tickets': lambda: ticket_lines_html(month, ex), 'hauling': lambda: hauling_lines_html(month, ex),
             'totals': lambda: totals_html(month)}
    body = ''.join(parts[t]() for t in tables)
    return (f'<p class="kicker">Lines · as extracted by Pulse · the clean count is the evidence</p><h1>Every line, as read</h1>'
            f'<div class="lines">{prefix_html}{body}</div>{band}')


def totals_html(month):
    """The printed totals as read, one row per document, beside the sum of the lines the model returned."""
    docs = month.get('documents') or {}
    rows = []
    def add(doc_id, label, printed_key, list_key, item_key):
        v = (docs.get(doc_id) or {}).get('values') or {}
        items = v.get(list_key) or []
        summed = sum(float(x.get(item_key) or 0) for x in items) if items else None
        rows.append((doc_id, label, v.get(printed_key), summed, len(items)))
    add('afe', 'AFE total estimate', 'total_estimate', 'cost_lines', 'amount')
    add('jib', 'JIB gross total', 'gross_total', 'lines', 'gross_amount')
    add('jib', 'JIB net total', 'net_total', 'lines', 'net_amount')
    html = ''
    for doc_id, label, printed, summed, n in rows:
        tie = '—' if printed is None or summed is None else ('ties' if abs(float(printed) - summed) < 0.01 else f'off by {float(printed) - summed:,.2f}')
        if label.startswith('Invoice'):
            tie = 'lines + tax' if printed is not None else '—'
        html += '<tr><td>{}</td><td>{}</td><td class="num">{}</td><td class="num">{}</td><td class="num">{}</td><td>{}</td></tr>'.format(
            esc(doc_id), esc(label), esc(fmt_scalar(printed)), esc(fmt_scalar(summed)), esc(n), esc(tie))
    return ('<h2>Totals, as read</h2><table><tr><th style="width:12%">Document</th><th>Total</th><th class="num" style="width:14%">Printed</th>'
            '<th class="num" style="width:14%">Sum of lines</th><th class="num" style="width:8%">Rows</th><th style="width:16%">Check</th></tr>' + html + '</table>')


def hauling_lines_html(month, ex):
    rows = ''
    for doc_id, doc in (month.get('documents') or {}).items():
        if doc.get('class') != 'hauling_log':
            continue
        fired = _fired_index(ex, doc_id, 'loads')
        for i, ld in enumerate((doc.get('values') or {}).get('loads') or []):
            rows += '<tr><td class="num">{}</td><td>{}</td><td>{}</td><td class="num">{}</td><td>{}</td><td>{}</td></tr>'.format(
                esc(ld.get('load_no')), esc(ld.get('time')), esc(ld.get('fluid_type')), esc(fmt_scalar(ld.get('barrels'))), esc(ld.get('destination')), _verdict(fired, i))
    if not rows:
        return ''
    return ('<h2>Hauling-log loads, as read</h2><table><tr><th class="num" style="width:7%">Load</th><th style="width:9%">Time</th><th style="width:22%">Fluid</th>'
            '<th class="num" style="width:10%">Barrels</th><th>Destination</th><th style="width:17%">Verdict</th></tr>' + rows + '</table>')


def _fired_index(ex, doc_id, list_key):
    out = {}
    for e in ex:
        if e.get('doc_id') == doc_id and e.get('field_path', '').startswith(list_key + '['):
            i = int(e['field_path'].split('[')[1].split(']')[0])
            out.setdefault(i, []).append(RULE_LABEL.get(e.get('rule'), e.get('rule')))
    return out


def _verdict(fired, i):
    return ('<span class="pill open">' + esc('; '.join(sorted(set(fired[i])))) + '</span>') if i in fired else '<span class="pill done">clean</span>'


def money2(x):
    """Money-style two decimals for rates and amounts, whatever numeric type the API returned."""
    try:
        return f'{float(x):,.2f}'
    except (TypeError, ValueError):
        return fmt_scalar(x)


def afe_lines_html(month):
    rows = ''
    for doc_id, doc in (month.get('documents') or {}).items():
        if doc.get('class') != 'afe':
            continue
        for ln in (doc.get('values') or {}).get('cost_lines') or []:
            rows += '<tr><td class="num">{}</td><td>{}</td><td>{}</td><td>{}</td><td class="num">{}</td></tr>'.format(
                esc(ln.get('line_no')), esc(ln.get('account_code')), esc(ln.get('description')), esc(ln.get('category')), esc(fmt_scalar(ln.get('amount'))))
    if not rows:
        return ''
    return ('<h2>AFE cost lines (the approved reference)</h2><table><tr><th class="num" style="width:6%">Line</th><th style="width:10%">Account</th>'
            '<th>Description</th><th style="width:14%">Category</th><th class="num" style="width:14%">Estimate</th></tr>' + rows + '</table>')


def ticket_lines_html(month, ex):
    rows = ''
    for doc_id, doc in (month.get('documents') or {}).items():
        if doc.get('class') != 'field_ticket':
            continue
        fired = _fired_index(ex, doc_id, 'line_items')
        for i, ln in enumerate((doc.get('values') or {}).get('line_items') or []):
            rows += ('<tr><td>{}</td><td>{}</td><td class="num">{}</td><td>{}</td><td class="num">{}</td><td class="num">{}</td><td>{}</td></tr>').format(
                esc(doc_id), esc(ln.get('description')), esc(fmt_scalar(ln.get('quantity'))), esc(ln.get('unit')),
                esc(money2(ln.get('rate'))), esc(money2(ln.get('amount'))), _verdict(fired, i))
    if not rows:
        return ''
    return ('<h2>Field-ticket lines, as read</h2><table><tr><th style="width:11%">Ticket</th><th>Description</th><th class="num" style="width:9%">Qty</th>'
            '<th style="width:7%">Unit</th><th class="num" style="width:10%">Rate</th><th class="num" style="width:11%">Amount</th><th style="width:17%">Verdict</th></tr>' + rows + '</table>')


def jib_lines_html(month, ex):
    """Every JIB line as extracted, with the rule verdict per line."""
    if not month:
        return ''
    rows = ''
    for doc_id, doc in (month.get('documents') or {}).items():
        if doc.get('class') != 'jib_statement':
            continue
        fired = _fired_index(ex, doc_id, 'lines')
        for i, ln in enumerate((doc.get('values') or {}).get('lines') or []):
            rows += ('<tr><td class="num">{}</td><td>{}</td><td>{}</td><td>{}</td><td class="num">{}</td><td class="num">{}</td>'
                     '<td class="num">{}</td><td>{}</td></tr>').format(
                esc(ln.get('line_no')), esc(ln.get('afe_ref')), esc(ln.get('account_code')), esc(ln.get('description')),
                esc(fmt_scalar(ln.get('gross_amount'))), esc(f"{ln.get('owner_decimal'):.6f}" if isinstance(ln.get('owner_decimal'), (int, float)) else '—'),
                esc(fmt_scalar(ln.get('net_amount'))), _verdict(fired, i))
    if not rows:
        return ''
    return ('<h2>JIB lines, as read</h2><table><tr><th class="num" style="width:6%">Line</th><th style="width:15%">AFE ref</th>'
            '<th style="width:9%">Account</th><th>Description</th><th class="num" style="width:12%">Gross</th>'
            '<th class="num" style="width:10%">Decimal</th><th class="num" style="width:12%">Net</th><th style="width:13%">Verdict</th></tr>'
            + rows + '</table>')


def thumb_pages(thumbs):
    pages = []
    groups = chunks_balanced(thumbs, THUMBS_PER_PAGE) or [[]]
    for gi, group in enumerate(groups):
        body = ''
        for t in group:
            cap = 'p{} · {} · {}'.format(t.get('page') if t.get('page') is not None else '?',
                                         t.get('field_path'), t.get('text') or '(no text)')
            if t.get('uri') and not t.get('blank'):
                frame = f'<div class="frame"><img src="{t["uri"]}" alt="citation crop"></div>'
            elif t.get('uri'):
                cap += ' · crop caught no ink'
                frame = ('<div class="nogeo"><span class="pill">cited box sits over blank paper'
                         '</span><span class="big">{}</span><span>The citation carries a page and '
                         'a box. Nothing is printed inside that box on page {} of the packet, so '
                         'this value cannot be traced to the paper.</span></div>').format(
                    esc(t.get('text') or '(no cited text)'),
                    esc(t.get('page') if t.get('page') is not None else '?'))
            else:
                frame = ('<div class="nogeo"><span class="pill">element cited, no geometry</span>'
                         '<span class="big">{}</span><span>The citation names the element and its '
                         'text, with no box to crop.</span></div>').format(
                    esc(t.get('text') or '(no cited text)'))
            body += ('<div class="thumb">{f}<div class="cap"><span>{c}</span>'
                     '<span class="who">{w}</span></div></div>').format(
                f=frame, c=esc(cap), w=esc(f"{t['doc_id']} · {t['doc_class']}"))
        blanks = sum(1 for t in group if t.get('blank'))
        fh = group[0].get('frame_in', 1.4) if group else 1.4
        body = f'<div class="thumbs" style="--fh:{fh:.2f}in">{body}</div>' if body else (
            '<p>No line-level citation was returned for this run.</p>')
        note = ('The crop is the packet page at the cited box, padded 6 percent. '
                f'{blanks} of {len(group)} boxes on this page sit over blank paper and are '
                'reported as untraceable rather than shown as an empty crop.'
                if blanks else 'Every crop on this page caught the printed row.')
        pages.append(f'''<p class="kicker">Citations · page {gi + 1} of {len(groups)}</p>
<h1>Where each billed line came from</h1>
<p class="lede">Every JIB line and every field-ticket line, cropped from the packet page Pulse
cited. Caption reads page, field path, and the text behind the value.</p>{body}
<div class="band">{esc(note)} Synthetic demonstration document — not an actual record.</div>''')
    return pages


def trail_page(exceptions, decisions, month):
    ex = exceptions.get('exceptions', [])
    inventory = ''.join(
        '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td class="num">{}</td>'
        '<td class="num">{}</td></tr>'.format(
            esc(doc_id), esc(d.get('class')), esc(d.get('packet')),
            esc(', '.join(str(x) for x in (d.get('pages') or [])) or '—'),
            esc(len(d.get('citations') or {})),
            esc(f"{float(d.get('seconds') or 0):g}"))
        for doc_id, d in (month.get('documents') or {}).items()) or (
        '<tr><td colspan="6">No document in this run.</td></tr>')
    decided = {r.get('exception_id') for r in decisions if signed(r)}
    if decisions:
        rows = ''.join(
            ('<tr><td>{ts}</td><td>{eid}</td><td>{ap}<br><span class="mono">{role}</span></td>'
             '<td>{dis}</td><td>{shown}</td><td>{ent}</td></tr>'
             '<tr class="sub"><td></td><td colspan="5">{why}</td></tr>').format(
                ts=esc(r.get('ts')),
                eid=esc(r.get('exception_id')),
                ap=(esc(r.get('approver')) if signed(r)
                    else '<span class="pill open">blank, unsigned</span>'),
                role=esc(r.get('approver_role')), dis=esc(r.get('disposition')),
                shown=esc(flat(r.get('value_shown'))), ent=esc(flat(r.get('value_entered'))),
                why=esc(r.get('reason')))
            for r in decisions)
        trail = ('<table><tr><th style="width:19%">Timestamp (UTC)</th><th style="width:10%">Exception</th>'
                 '<th style="width:19%">Approver</th><th style="width:16%">Disposition</th>'
                 '<th style="width:18%">Value shown</th><th style="width:18%">Value entered</th></tr>'
                 + rows + '</table>')
    else:
        trail = ('<p>The decision log holds no row for this run. Every exception below is '
                 'waiting on the named role. The software refuses a blank approver and never '
                 'supplies one, so an unsigned exception stays open.</p>')
    roster = ''.join(
        '<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            esc(e.get('id')), esc(RULE_LABEL.get(e.get('rule'), e.get('rule'))),
            esc(e.get('approver_role')),
            'decided' if e.get('id') in decided else 'open, unsigned')
        for e in ex) or '<tr><td colspan="4">No exception in this run.</td></tr>'
    return f'''<p class="kicker">Approver trail · {esc(month.get('run_id'))}</p>
<h1>Who signed what</h1>
<p class="lede">Every decision row recorded for this run, verbatim from the append-only log.</p>
{trail}
<h2>Standing of each exception</h2>
<table><tr><th style="width:12%">ID</th><th style="width:32%">Rule</th>
<th style="width:26%">Owning role</th><th style="width:30%">Standing</th></tr>{roster}</table>
<h2>What was read this month</h2>
<table><tr><th style="width:16%">Document</th><th style="width:20%">Class</th>
<th style="width:12%">Packet</th><th style="width:14%">Packet pages</th>
<th class="num" style="width:12%">Citations</th><th class="num" style="width:12%">Seconds</th></tr>{inventory}</table>
<h2>What a decision row records</h2>
<table><tr><th style="width:26%">Field</th><th>Meaning</th></tr>
<tr><td>ts</td><td>UTC timestamp written when the queue accepted the decision</td></tr>
<tr><td>run_id</td><td>the month record the decision belongs to</td></tr>
<tr><td>approver</td><td>the name a person typed; the queue refuses a blank and defaults none</td></tr>
<tr><td>approver_role</td><td>the role the exception was routed to</td></tr>
<tr><td>exception_id</td><td>the exception the decision answers</td></tr>
<tr><td>disposition</td><td>approved-as-is, approved-after-edit, routed, or disputed</td></tr>
<tr><td>value_shown</td><td>the extracted value the approver saw next to its citation</td></tr>
<tr><td>value_entered</td><td>the value the approver keyed, when it differs from the one shown</td></tr>
<tr><td>reason</td><td>the approver's own words</td></tr>
<tr><td>synthetic</td><td>true for every row produced by this demonstration</td></tr></table>
<div class="honesty">
<p>Reconciliation and queue are customer code. Pulse ships the parser and the citations.</p>
<p>Every number on these pages is synthetic.</p>
</div>'''


# ---------------------------------------------------------------- build

def build_html(month, exceptions, score, decisions, thumbs, run_id):
    cover, rules_html = cover_page(month, exceptions, score, decisions, thumbs)
    pages = [cover]
    pages += exception_pages(exceptions, decisions, rules_html, month)
    pages += thumb_pages(thumbs)
    pages.append(trail_page(exceptions, decisions, month))
    stamp = f'Audit pack v1 · {run_id} · synthetic'
    built = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    total = len(pages)
    out = ''.join(
        shell(p, stamp, 'Synthetic demonstration document — not an actual record',
              f'Built {built} · page {i + 1} of {total}')
        for i, p in enumerate(pages))
    tpl = TEMPLATE.read_text()
    return tpl.replace('{{TITLE}}', f'Audit pack — {run_id}').replace('{{PAGES}}', out), total


def main():
    ap = argparse.ArgumentParser(description='Build the audit pack PDF for one run.')
    ap.add_argument('--run', required=True, help='runs/<run_id>')
    ap.add_argument('--out', default=None, help='output PDF (default runs/<run_id>/audit-pack.pdf)')
    ap.add_argument('--decisions', default=str(ROOT / 'audit/decisions.jsonl'))
    args = ap.parse_args()

    run_dir = pathlib.Path(args.run)
    if not run_dir.is_absolute():
        run_dir = (ROOT / args.run).resolve()
    if not (run_dir / 'month.json').exists():
        sys.exit(f'no month.json in {run_dir}')
    month, exceptions, score = load_run(run_dir)
    run_id = month.get('run_id') or run_dir.name
    dec_path = pathlib.Path(args.decisions)
    if not dec_path.is_absolute():
        dec_path = (ROOT / args.decisions).resolve()
    decisions = load_decisions(dec_path, run_id)

    thumbs, _ = line_thumbs(month, run_dir)
    html_text, pages = build_html(month, exceptions, score, decisions, thumbs, run_id)
    html_path = run_dir / 'audit-pack.html'
    html_path.write_text(html_text)
    out_pdf = pathlib.Path(args.out) if args.out else run_dir / 'audit-pack.pdf'
    if not out_pdf.is_absolute():
        out_pdf = (ROOT / out_pdf).resolve()

    if not RENDER:
        sys.exit('audit pack: set AUDIT_RENDER_SH to an HTML-to-PDF render script (see .env.example)')
    proc = subprocess.run([str(RENDER), str(html_path), str(out_pdf), '--pages', str(pages)],
                          capture_output=True, text=True)
    receipt = (proc.stdout or '') + (proc.stderr or '')
    print(receipt, end='' if receipt.endswith('\n') else '\n')

    ex = exceptions.get('exceptions', [])
    decided_ids = {r.get('exception_id') for r in decisions if signed(r)}
    clean = proc.returncode == 0
    flagged = [ln.strip() for ln in receipt.splitlines() if 'FLAG' in ln]
    summary = {
        'pdf': str(out_pdf.relative_to(ROOT)), 'pages': pages, 'exceptions': len(ex),
        'decided': sum(1 for e in ex if e['id'] in decided_ids),
        'open': sum(1 for e in ex if e['id'] not in decided_ids),
        'thumbnails': len(thumbs),
        'receipt': {'clean': clean, 'exit_code': proc.returncode,
                    'flags': flagged, 'text': receipt.rstrip('\n').replace(str(ROOT) + '/', '')},
        'run_id': run_id, 'html': str(html_path.relative_to(ROOT)), 'synthetic': True,
    }
    (run_dir / 'audit-pack.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(f"audit-pack.json written: {run_dir / 'audit-pack.json'}")
    if not clean:
        sys.exit(1)


if __name__ == '__main__':
    main()
