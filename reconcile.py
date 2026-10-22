#!/usr/bin/env python3
"""Reconcile a month record against the JV accountant's own reference data → exceptions.json.

This is CUSTOMER code, not Pulse. Pulse reads the paper; these three rules are the customer's own
controls, written against the customer's own reference files (division order, contract rate sheet,
AFE election). The demo says so out loud: extraction is the vendor's job, reconciliation is not.

  python3 reconcile.py --run runs/<run_id> [--refs synth/reference]

Reads  runs/<run_id>/month.json  (never edits it) and the three reference JSONs.
Writes runs/<run_id>/exceptions.json per the exceptions contract.

Rules (rules_version 1):
  rule_1_decimal  per JIB line: expected_net = round(gross x doi.decimal, 2); fire when the printed
                  owner_decimal differs from the DOI decimal at 4 places, or |net - expected| > 0.01.
                  Route: jv_accountant.
  rule_2_rate     per field-ticket line item that has a contract rate for (vendor, description, unit):
                  fire when rate > contract_rate + 0.005. Route: supply_chain.
  rule_3_afe_ref  per JIB line: fire when afe_ref differs from the elected AFE number, or the account
                  code is not one of the AFE's cost-line account codes. Route: jv_accountant.
  extraction      not a rule: a required field came back null, or a list came back shorter than the
                  rows the document prints. Route: field for tickets and hauling logs, jv_accountant
                  for AFE, JIB and invoice.

No approver is ever typed here. Exceptions are written status "open"; a human decides them in the
queue and signs the decision with a name the software refuses to default.

Deterministic, stdlib only, offline.
"""
import argparse, re
import json
import pathlib
import sys

RULES_VERSION = '1'

ROOT = pathlib.Path(__file__).resolve().parent

# Route table: which role owns an extraction exception on this document class.
EXTRACTION_ROUTE = {
    'field_ticket': 'field',
    'hauling_log': 'field',
    'afe': 'jv_accountant',
    'afe_cover': 'jv_accountant',
    'jib_statement': 'jv_accountant',
    'invoice': 'jv_accountant',
}

# Required scalar fields per document class, and the list field with the row count the document prints.
REQUIRED = {
    'afe_cover': ['letter_date', 'operator_name', 'addressee', 'afe_number', 'well_name',
                  'response_due_date', 'wi_decimal_stated', 'net_share_stated'],
    'afe': ['afe_number', 'operator_name', 'well_name', 'api_number', 'county', 'state',
            'afe_date', 'afe_type', 'total_estimate'],
    'field_ticket': ['ticket_number', 'vendor_name', 'service_date', 'well_name', 'afe_number',
                     'total', 'customer_signature_present'],
    'hauling_log': ['log_number', 'hauler_name', 'log_date', 'well_name', 'total_barrels'],
    'invoice': ['invoice_number', 'vendor_name', 'invoice_date', 'afe_number', 'well_name',
                'subtotal', 'tax', 'total'],
    'jib_statement': ['statement_period', 'operator_name', 'property_number', 'well_name',
                      'owner_name', 'owner_number', 'wi_decimal', 'gross_total', 'net_total', 'due_date'],
}

# (list field, required keys inside each row, exact printed row count or None, minimum row count)
LISTS = {
    'afe': ('cost_lines', ['line_no', 'account_code', 'description', 'category', 'amount'], 6, 6),
    'field_ticket': ('line_items', ['description', 'quantity', 'unit', 'rate', 'amount'], None, 2),
    'hauling_log': ('loads', ['load_no', 'time', 'fluid_type', 'barrels', 'destination'], None, 4),
    'invoice': ('line_items', ['ticket_ref', 'description', 'quantity', 'unit', 'rate', 'amount'], None, 1),
    'jib_statement': ('lines', ['line_no', 'afe_ref', 'account_code', 'description',
                                'gross_amount', 'owner_decimal', 'net_amount'], 8, 8),
}


def load(path):
    return json.loads(pathlib.Path(path).read_text())


def cite(doc, field_path):
    """Citation for a field path, falling back to the document's first known page."""
    cites = (doc or {}).get('citations') or {}
    c = cites.get(field_path)
    if not c:
        # fall back to the sibling field on the same row, then to any citation on the document
        if '.' in field_path:
            stem = field_path.rsplit('.', 1)[0]
            for k, v in cites.items():
                if k.startswith(stem + '.'):
                    c = v
                    break
    if c:
        return c.get('page'), c.get('bbox'), c.get('text')
    pages = (doc or {}).get('pages') or []
    return (pages[0] if pages else None), None, None


def money(x):
    return round(float(x) + 0.0, 2)


def docs_of_class(month, cls):
    out = []
    for doc_id, doc in sorted((month.get('documents') or {}).items()):
        if doc.get('class') == cls:
            out.append((doc_id, doc))
    return out


def doi_decimal(doi, owner_number=None, owner_name=None):
    owners = [o for o in (doi.get('owners') or []) if o.get('interest_type') == 'WI']
    for o in owners:
        if owner_number and o.get('owner_number') == owner_number:
            return o.get('decimal')
    for o in owners:
        if owner_name and o.get('owner_name') == owner_name:
            return o.get('decimal')
    return owners[0].get('decimal') if owners else None


def rate_index(rates_ref):
    idx = {}
    for r in rates_ref.get('rates') or []:
        idx[(rates_ref.get('vendor_name'), r.get('description'), r.get('unit'))] = r.get('contract_rate')
    return idx


def reconcile(month, doi, rates_ref, election):
    exceptions = []
    clean = []
    counts = {'rule_1_decimal': [0, 0], 'rule_2_rate': [0, 0], 'rule_3_afe_ref': [0, 0], 'extraction': [0, 0]}

    def add(rule, doc_id, field_path, doc, observed, expected, delta, role, message):
        page, bbox, text = cite(doc, field_path)
        exceptions.append({
            'id': None, 'rule': rule, 'doc_id': doc_id, 'field_path': field_path,
            'page': page, 'bbox': bbox, 'cited_text': text,
            'observed': observed, 'expected': expected, 'delta_usd': delta,
            'approver_role': role, 'status': 'open', 'message': message,
        })
        counts[rule][1] += 1

    # ---- reference values -------------------------------------------------
    jibs = docs_of_class(month, 'jib_statement')
    tickets = docs_of_class(month, 'field_ticket')
    afes = docs_of_class(month, 'afe')

    afe_codes = set()
    for _, afe in afes:
        for line in ((afe.get('values') or {}).get('cost_lines') or []):
            if line.get('account_code') is not None:
                afe_codes.add(str(line['account_code']))
    elected_afe = election.get('afe_number')
    rates = rate_index(rates_ref)

    jib_lines_total = 0
    ticket_lines_total = 0

    # ---- rule 1 and rule 3 (JIB lines) ------------------------------------
    for doc_id, doc in jibs:
        vals = doc.get('values') or {}
        decimal = doi_decimal(doi, vals.get('owner_number'), vals.get('owner_name'))
        lines = vals.get('lines') or []
        jib_lines_total += len(lines)
        for i, line in enumerate(lines):
            gross = line.get('gross_amount')
            net = line.get('net_amount')
            printed = line.get('owner_decimal')
            fp_net = f'lines[{i}].net_amount'
            fp_dec = f'lines[{i}].owner_decimal'
            counts['rule_1_decimal'][0] += 1
            fired = False
            if gross is None or net is None or printed is None or decimal is None:
                pass  # missing values are an extraction exception, not a decimal finding
            else:
                expected_net = money(float(gross) * float(decimal))
                dec_off = round(float(printed), 4) != round(float(decimal), 4)
                net_off = abs(float(net) - expected_net) > 0.01
                if dec_off or net_off:
                    fired = True
                    add('rule_1_decimal', doc_id, fp_net if net_off else fp_dec, doc,
                        {'owner_decimal': float(printed), 'net_amount': money(net), 'gross_amount': money(gross)},
                        {'owner_decimal': float(decimal), 'net_amount': expected_net},
                        money(float(net) - expected_net), 'jv_accountant',
                        (f'JIB line {line.get("line_no", i + 1)} applies owner decimal {float(printed):.6f}; '
                         f'the division order says {float(decimal):.6f}. Net billed {money(net):,.2f} against expected {expected_net:,.2f}.'
                         if dec_off else
                         f'JIB line {line.get("line_no", i + 1)} prints the right decimal ({float(decimal):.6f}) but the net does not '
                         f'follow: {money(gross):,.2f} × {float(decimal):.6f} = {expected_net:,.2f}, billed {money(net):,.2f}. '
                         f'Arithmetic or a misread gross; check the cited box.'))
            if not fired:
                clean.append({'doc_id': doc_id, 'field_path': fp_net, 'rule': 'rule_1_decimal'})
                counts['rule_1_decimal'][1] += 0

            counts['rule_3_afe_ref'][0] += 1
            ref = line.get('afe_ref')
            code = line.get('account_code')
            bad_ref = elected_afe is not None and ref is not None and ref != elected_afe
            bad_code = bool(afe_codes) and code is not None and str(code) not in afe_codes
            if bad_ref or bad_code:
                add('rule_3_afe_ref', doc_id, f'lines[{i}].afe_ref' if bad_ref else f'lines[{i}].account_code',
                    doc, {'afe_ref': ref, 'account_code': code},
                    {'afe_ref': elected_afe, 'account_code': f'one of {sorted(afe_codes)}'},
                    0.0, 'jv_accountant',
                    f'JIB line {line.get("line_no", i + 1)} does not tie to the elected AFE '
                    f'{elected_afe} or to an AFE cost-line account code.')
            else:
                clean.append({'doc_id': doc_id, 'field_path': f'lines[{i}].afe_ref', 'rule': 'rule_3_afe_ref'})

    # ---- rule 2 (ticket line rates) ---------------------------------------
    for doc_id, doc in tickets:
        vals = doc.get('values') or {}
        vendor = vals.get('vendor_name')
        items = vals.get('line_items') or []
        ticket_lines_total += len(items)
        for i, it in enumerate(items):
            key = (vendor, it.get('description'), it.get('unit'))
            contract = rates.get(key)
            if contract is None or it.get('rate') is None:
                continue  # no contract rate for this line: nothing to check
            counts['rule_2_rate'][0] += 1
            rate = float(it['rate'])
            if rate > float(contract) + 0.005:
                qty = it.get('quantity')
                delta = money((rate - float(contract)) * float(qty)) if qty is not None else None
                add('rule_2_rate', doc_id, f'line_items[{i}].rate', doc,
                    {'rate': rate, 'quantity': qty, 'amount': it.get('amount')},
                    {'contract_rate': float(contract),
                     'amount': money(float(contract) * float(qty)) if qty is not None else None},
                    delta, 'supply_chain',
                    f'Ticket line "{it.get("description")}" billed at {rate:,.2f} per {it.get("unit")}; '
                    f'the rate sheet says {float(contract):,.2f}.')
            else:
                clean.append({'doc_id': doc_id, 'field_path': f'line_items[{i}].rate', 'rule': 'rule_2_rate'})

    # ---- extraction exceptions --------------------------------------------
    for doc_id, doc in sorted((month.get('documents') or {}).items()):
        cls = doc.get('class')
        vals = doc.get('values')
        role = EXTRACTION_ROUTE.get(cls, 'jv_accountant')
        if vals is None:
            counts['extraction'][0] += 1
            add('extraction', doc_id, 'values', doc, None, 'a populated schema result', None, role,
                f'{doc_id}: no schema values came back for this document.')
            continue
        for f in REQUIRED.get(cls, []):
            counts['extraction'][0] += 1
            if vals.get(f) is None:
                add('extraction', doc_id, f, doc, None, 'a value', None, role,
                    f'{doc_id}: required field {f} came back null.')
            else:
                clean.append({'doc_id': doc_id, 'field_path': f, 'rule': 'extraction'})
        spec = LISTS.get(cls)
        if spec:
            name, keys, exact, minimum = spec
            rows = vals.get(name)
            counts['extraction'][0] += 1
            if not isinstance(rows, list):
                add('extraction', doc_id, name, doc, None, f'a list of {name}', None, role,
                    f'{doc_id}: {name} did not come back as a list.')
            elif (exact is not None and len(rows) != exact) or len(rows) < minimum:
                add('extraction', doc_id, name, doc, len(rows), exact if exact is not None else f'>= {minimum}',
                    None, role,
                    f'{doc_id}: {name} came back with {len(rows)} rows; the document prints '
                    f'{exact if exact is not None else "at least " + str(minimum)}.')
            else:
                clean.append({'doc_id': doc_id, 'field_path': name, 'rule': 'extraction'})
                for i, row in enumerate(rows):
                    for k in keys:
                        counts['extraction'][0] += 1
                        if not isinstance(row, dict) or row.get(k) is None:
                            add('extraction', doc_id, f'{name}[{i}].{k}', doc, None, 'a value', None, role,
                                f'{doc_id}: required field {name}[{i}].{k} came back null.')
                        else:
                            clean.append({'doc_id': doc_id, 'field_path': f'{name}[{i}].{k}', 'rule': 'extraction'})

    # ---- stable ids --------------------------------------------------------
    order = {'rule_1_decimal': 0, 'rule_2_rate': 1, 'rule_3_afe_ref': 2, 'extraction': 3}
    exceptions.sort(key=lambda e: (order[e['rule']], e['doc_id'], e['field_path']))
    for n, e in enumerate(exceptions, 1):
        e['id'] = f'EX-{n:03d}'

    out = {
        'run_id': month.get('run_id'),
        'synthetic': True,
        'rules_version': RULES_VERSION,
        'exceptions': exceptions,
        'clean_lines': clean,
        'summary': {
            'jib_lines': jib_lines_total,
            'ticket_lines': ticket_lines_total,
            'fired': len(exceptions),
            'clean': len(clean),
        },
    }
    return out, counts


def print_table(counts):
    w = 16
    print(f'{"rule".ljust(w)}{"checked".rjust(9)}{"fired".rjust(8)}{"clean".rjust(8)}')
    print('-' * (w + 25))
    for rule in ('rule_1_decimal', 'rule_2_rate', 'rule_3_afe_ref', 'extraction'):
        checked, fired = counts[rule]
        print(f'{rule.ljust(w)}{str(checked).rjust(9)}{str(fired).rjust(8)}{str(checked - fired).rjust(8)}')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--run', required=True, help='run directory holding month.json')
    ap.add_argument('--refs', default='synth/reference', help='directory holding doi.json, contract_rates.json, afe_election.json')
    a = ap.parse_args(argv)

    rd = pathlib.Path(a.run)
    rd = rd if rd.is_absolute() else ROOT / rd
    mp = rd / 'month.json'
    if not mp.exists():
        sys.exit(f'no month.json at {mp}')
    refs = pathlib.Path(a.refs)
    refs = refs if refs.is_absolute() else ROOT / refs
    for f in ('doi.json', 'contract_rates.json', 'afe_election.json'):
        if not (refs / f).exists():
            sys.exit(f'missing reference file {refs / f}')

    month = load(mp)
    out, counts = reconcile(month, load(refs / 'doi.json'), load(refs / 'contract_rates.json'),
                            load(refs / 'afe_election.json'))
    perts = month.get('fixture_perturbations') or []
    for e in out['exceptions']:  # a labelled fixture perturbation is named as such; never mistaken for a plant or a Pulse miss
        for label in perts:
            m = re.match(r'(F\d+)\s+([\w.\[\]]+)', label)
            if m and m.group(2) == f"{e['doc_id']}.{e['field_path']}":
                e['fixture_perturbation'] = m.group(1)
                e['message'] += f' [fixture perturbation {m.group(1)}, not a document defect]'
    if perts:
        out['fixture_perturbations'] = perts
    (rd / 'exceptions.json').write_text(json.dumps(out, indent=1) + '\n')

    print(f'reconcile  run={out["run_id"]}  rules_version={RULES_VERSION}  refs={refs}')
    print_table(counts)
    print(f'\n{out["summary"]["fired"]} exception(s) written to {rd / "exceptions.json"}')
    for e in out['exceptions']:
        d = '' if e['delta_usd'] in (None, 0.0) else f'  delta ${e["delta_usd"]:,.2f}'
        print(f'  {e["id"]}  {e["rule"]:<15} {e["doc_id"]}.{e["field_path"]:<24} -> {e["approver_role"]}{d}')
    print('\nThese three rules are customer code, not Pulse output. Pulse read the paper; the controls are yours.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
