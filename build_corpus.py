#!/usr/bin/env python3
"""Build the well-file demo corpus, packets, and ground truth from Texas RRC public data.

Inputs (public records, Texas Government Code ch. 552; RRC data sets are "free of charge"):
  - One night's "Drilling Permit (W1) Imaged Files" zip (W-1 facsimiles + plats), unzipped.
  - The same morning's "Drilling Permit Master and Trailer - Daily File" (daf420.dat), ASCII.
  - The RRC record-layout manual OGA049M (county codes, district codes, field positions).

Outputs (all under this directory):
  corpus/raw/<permit>/            original PDFs as published by RRC
  corpus/packets/clean/<permit>.pdf   one packet per permit: W-1 first, then plats (pypdf merge)
  corpus/packets/scan/<permit>.pdf    the same packet rasterized at 150 dpi, gray, slight skew (ImageMagick)
  corpus/manifest.json            sha256, source URL, licence line, page counts, class labels, truth paths
  truth/ascii/<permit>.json       RRC ASCII master fields (SYSTEM-EXTRACTED, the different hand)
  truth/w1/<permit>.json          W-1 form fields from the facsimile text layer + word boxes (SYSTEM-EXTRACTED)
  truth/split/<permit>.json       true page ranges per class (OBSERVED from packet assembly)
  truth/classify/<permit>.json    true class per raw document (OBSERVED from RRC file naming)

Truth rule (PF-1 / EV-1): truth is written by a different hand than the thing it grades.
The ASCII master is RRC's own data entry; the text layer is RRC's own facsimile generator.
Neither passes through Pulse. Plat truth is human-keyed and stays PLANNED until two keyers sign.

Usage:
  python3 build_corpus.py --zipdir <unzipped W-1 zip root> --ascii <daf420.dat> --manual <daf420_layout.txt> \
      --permits 918133 917176 ...   [--no-scan]
"""
import argparse, hashlib, json, pathlib, re, shutil, subprocess, sys
from datetime import date

HERE = pathlib.Path(__file__).resolve().parent
RRC_W1_URL = "https://mft.rrc.texas.gov/link/f11363bb-8120-4e8c-bbc0-a253ec0a85d4"
RRC_ASCII_URL = "https://mft.rrc.texas.gov/link/5f07cc72-2e79-4df8-ade1-9aeb792e03fc"
RRC_MANUAL_URL = "https://www.rrc.texas.gov/media/zgccdjpi/drillingpermitmasterpluslatitudeslongitudes_oga049m_july1.pdf"
LICENCE = "Texas public record (Tex. Gov't Code ch. 552); RRC data sets published free of charge; site policy: copy for noncommercial use, unaltered"

DISTRICT = {'01':'01','02':'02','03':'03','04':'04','05':'05','06':'06','07':'6E','08':'7B',
            '09':'7C','10':'08','11':'8A','12':'8B','13':'09','14':'10'}
TYPE_APP = {'01':'New Drill','02':'Deepen below casing','03':'Deepen within casing','04':'Plug back','05':'Other',
            '06':'Amended','07':'Re-Enter','08':'Sidetrack','09':'Field Transfer','10':'Amended prior to 1977',
            '11':'Drill directional sidetrack','12':'Drill horizontal','13':'Sidetrack horizontal','14':'Recompletion','15':'Reclass'}


def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def county_table(manual_txt: pathlib.Path) -> dict:
    t = manual_txt.read_text(errors='replace')
    i = t.find('TEXAS COUNTIES AND COUNTY CODES')
    out = {}
    for m in re.finditer(r'^\s*([A-Z][A-Z .\'-]+?)\s{2,}(\d{3})\s*$', t[i:], flags=re.M):
        out[m.group(2)] = m.group(1).strip()
    return out


def dt(s: str):
    s = s.strip()
    if not s or not s.isdigit() or s == '00000000':
        return None
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def parse_ascii(ascii_path: pathlib.Path, counties: dict) -> dict:
    """Parse daf420.dat. Positions follow OGA049M; the DAPERMIT block in the manual carries a doubled
    record-id line, so its printed positions run two high — verified against the W-1 facsimile
    for permit 918133 (API 42-207-33074) on 2026-09-04."""
    recs = {}
    cur = None
    for line in ascii_path.read_text(encoding='latin-1').splitlines():
        rt = line[0:2]
        if rt == '01':
            cur = line[2:9]
            recs[cur] = {
                'permit_number': cur.lstrip('0'),
                'sequence': line[9:11],
                'county_code': line[11:14],
                'county': counties.get(line[11:14], None),
                'lease_name': line[14:46].strip(),
                'district': DISTRICT.get(line[46:48], line[46:48]),
                'operator_number': line[48:54],
                'application_received_date': dt(line[58:66]),
                'operator_name': line[66:98].strip(),
                'application_status': {'P':'Pending','A':'Approved','W':'Withdrawn','D':'Dismissed','E':'Denied','C':'Closed','O':'Other','X':'Deleted','Z':'Cancelled'}.get(line[100], line[100]),
                'permit_issue_date': dt(line[119:127]),
                'fields': [],
            }
        elif rt == '02' and cur:
            r = recs[cur]
            r.update({
                'well_number': line[48:54].strip(),
                'total_depth': int(line[54:59]) if line[54:59].strip().isdigit() else None,
                'type_of_application_code': line[65:67],
                'type_of_application': TYPE_APP.get(line[65:67], line[65:67]),
                'surface_section': line[243:251].strip(),
                'surface_block': line[251:261].strip(),
                'surface_survey': line[261:316].strip(),
                'surface_abstract': line[316:322].strip(),
                'contiguous_acres': int(line[325:331]) + int(line[331:333]) / 100 if line[325:333].strip().isdigit() else None,
                'miles_from_town': int(line[333:337]) + int(line[337:339]) / 100 if line[333:339].strip().isdigit() else None,
                'direction_from_town': line[339:345].strip(),
                'nearest_town': line[345:358].strip(),
                'lease_perpendiculars': {
                    'feet_1': int(line[358:364]) + int(line[364:366]) / 100 if line[358:366].strip().isdigit() else None,
                    'direction_1': line[366:379].strip(),
                    'feet_2': int(line[379:385]) + int(line[385:387]) / 100 if line[379:387].strip().isdigit() else None,
                    'direction_2': line[387:400].strip()},
                'survey_perpendiculars': {
                    'feet_1': int(line[400:406]) + int(line[406:408]) / 100 if line[400:408].strip().isdigit() else None,
                    'direction_1': line[408:421].strip(),
                    'feet_2': int(line[421:427]) + int(line[427:429]) / 100 if line[421:429].strip().isdigit() else None,
                    'direction_2': line[429:442].strip()},
                'horizontal_well_flag': line[493] == 'Y' if len(line) > 493 else None,
                'directional_well_flag': line[481] == 'Y' if len(line) > 481 else None,
                'api_number': None,
            })
            api = line[502:510] if len(line) >= 510 else ''
            if api.strip().isdigit() and int(api) > 0:
                r['api_number'] = f"42-{api[0:3]}-{api[3:8]}"
        elif rt == '03' and cur:
            recs[cur]['fields'].append({'field_number': line[2:10], 'application_well_code': line[10], 'completion_well_code': line[11]})
        elif rt == '04' and cur and recs[cur]['fields']:
            f = recs[cur]['fields'][-1]
            f['completion_depth'] = int(line[36:41]) if line[36:41].strip().isdigit() else None
            f['field_district'] = DISTRICT.get(line[2:4], line[2:4])
            f['acres'] = int(line[47:53]) + int(line[53:55]) / 100 if line[47:55].strip().isdigit() else None
    return recs


def _rule36(txt: str):
    """Item 10 checkbox from the -layout text: the X glyph sits on the same line as 'Yes'/'No' or on the line
    above (column-aligned), so decide by column span, not by 'X Yes' adjacency (truth defect found 2026-09-05:
    the old regex never matched and every truth read false while five pages show Yes checked)."""
    lines = txt.split('\n')
    for i, l in enumerate(lines):
        m = re.search(r'Rule 36.*?\?', l)
        if not m:
            continue
        tail = l[m.end():]; base = m.end()
        my = re.search(r'\bYes\b', tail); mn = re.search(r'\bNo\b', tail)
        if not (my and mn):
            return None
        cy, cn = base + my.start(), base + mn.start()
        cand = [l] + ([lines[i - 1]] if i else [])
        xs = [x.start() for c in cand for x in re.finditer(r'\bX\b', c) if x.start() >= base - 2]
        if any(base - 2 <= x < cy for x in xs):
            return True
        if any(cy + 3 <= x < cn for x in xs):
            return False
        return None
    return None

def w1_text_truth(pdf: pathlib.Path) -> dict:
    """Read the W-1 facsimile text layer and word boxes (pdftotext -bbox-layout).
    Returns field values and normalized 4-point boxes for citation scoring.
    The facsimile is generated by RRC from submitted data, so its text layer is machine truth."""
    txt = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], capture_output=True, text=True).stdout
    bbox = subprocess.run(['pdftotext', '-bbox-layout', str(pdf), '-'], capture_output=True, text=True).stdout
    page = re.search(r'<page width="([\d.]+)" height="([\d.]+)"', bbox)
    W, H = float(page.group(1)), float(page.group(2))
    words = [(m.group(5), float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
             for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', bbox)]

    def find_box(value: str, anchor=None):
        """Locate a value string as a run of consecutive words, searching after an anchor word sequence when
        given (values such as HASKELL or SOUTH repeat on the form); return normalized box or None."""
        toks = str(value).split()
        if not toks:
            return None
        cands = []
        for i in range(len(words) - len(toks) + 1):
            if [w[0] for w in words[i:i + len(toks)]] == toks:
                xs = [w[1] for w in words[i:i + len(toks)]] + [w[3] for w in words[i:i + len(toks)]]
                ys = [w[2] for w in words[i:i + len(toks)]] + [w[4] for w in words[i:i + len(toks)]]
                cands.append([min(xs), min(ys), max(xs), max(ys)])
        if not cands:
            return None
        pick = cands[0]
        if anchor:
            a = list(anchor)
            for i in range(len(words) - len(a) + 1):
                if [w[0] for w in words[i:i + len(a)]] == a:
                    ax, ay = words[i + len(a) - 1][3], (words[i][2] + words[i][4]) / 2
                    # the value sits on the anchor's line (or the line below) and to its right; nearest such candidate wins
                    ranked = sorted(cands, key=lambda c: (abs((c[1] + c[3]) / 2 - ay) > 14, abs((c[1] + c[3]) / 2 - ay), 0 if c[0] >= ax - 2 else 1, c[0]))
                    pick = ranked[0]
                    break
        return [round(pick[0] / W, 4), round(pick[1] / H, 4), round(pick[2] / W, 4), round(pick[3] / H, 4)]

    def grab(pattern, flags=0):
        m = re.search(pattern, txt, flags)
        return m.group(1).strip() if m else None

    v = {}
    v['api_number'] = grab(r'API No\.\s*\n\s*(\d{2}-\d{3}-\d{5})')
    v['permit_number'] = grab(r'Drilling Permit #.*\n\s*(\d+)')
    v['permit_status'] = grab(r'Permit Status:\s*(\w+)')
    v['operator_number'] = grab(r'1\. RRC Operator No\..*\n\s*(\d{6})')
    m = re.search(r'1\. RRC Operator No\..*\n\s*\d{6}\s+(.+?)\s{3,}(.+?)\s*$', txt, re.M)
    v['operator_name'] = m.group(1).strip() if m else None
    m = re.search(r'4\. Lease Name[^\n]*\n([^\n]*)', txt)
    toks = re.split(r'\s{3,}', m.group(1).strip()) if m else []
    v['lease_name'] = toks[0].strip() if len(toks) >= 1 else None
    v['well_number'] = toks[1].strip() if len(toks) >= 2 else None
    m = re.search(r'8\. Total Depth[^\n]*\n((?:[^\n]*\n){0,3})', txt)
    md = re.search(r'^\s{3,}(\d{3,6})\s', m.group(1), re.M) if m else None
    v['total_depth'] = md.group(1) if md else None
    v['district'] = grab(r'11\. RRC District No\..*\n\s*(\S+)')
    v['county'] = grab(r'12\. County\s*\n\s*\S+\s+([A-Z .\'-]+?)\s{2,}')
    m = re.search(r'14\. This well is to be located\s+([\d.]+)\s+miles in a\s+(\w+)\s+direction from\s+(.+?)\s{2,}which', txt)
    v['miles_from_town'], v['direction_from_town'], v['nearest_town'] = (m.group(1), m.group(2), m.group(3).strip()) if m else (None, None, None)
    m = re.search(r'21\. Lease Perpendiculars:\s+([\d.]+)\s+ft from the\s+(\w+)\s+line and\s+([\d.]+)\s+ft from the\s+(\w+)\s+line', txt)
    v['lease_perpendiculars'] = {'feet_1': m.group(1), 'direction_1': m.group(2), 'feet_2': m.group(3), 'direction_2': m.group(4)} if m else None
    m = re.search(r'22\. Survey Perpendiculars:\s+([\d.]+)\s+ft from the\s+(\w+)\s+line and\s+([\d.]+)\s+ft from the\s+(\w+)\s+line', txt)
    v['survey_perpendiculars'] = {'feet_1': m.group(1), 'direction_1': m.group(2), 'feet_2': m.group(3), 'direction_2': m.group(4)} if m else None
    v['abstract_number'] = grab(r'18\. Abstract No\..*\n(?:.*\n)?.*?\b(A-\d+)\b')
    v['contiguous_acres'] = grab(r'unitized tract:\s+([\d.]+)')
    # purpose: "X  New Drill" pattern — the X precedes the checked label in the text layer
    purpose_line = grab(r'6\. Purpose of filing.*?:\s*(.*)$', re.M) or ''
    v['purpose_of_filing'] = [lab for lab in ['New Drill', 'Recompletion', 'Reclass', 'Field Transfer', 'Re-Enter', 'Amended'] if re.search(r'X\s+' + re.escape(lab), purpose_line)]
    profile_line = grab(r'7\. Wellbore Profile.*?:\s*(.*)$', re.M) or ''
    v['wellbore_profile'] = [lab for lab in ['Vertical', 'Horizontal', 'Directional', 'Sidetrack'] if re.search(r'X\s+' + re.escape(lab), profile_line)]
    v['rule_36_h2s'] = _rule36(txt)
    # field table rows: district, field no, name, well type, completion depth, distance, wells
    fields = []
    for m in re.finditer(r'^\s*(\S+)\s+(\d{8})\s+(.+?)\s{2,}(Oil Well|Gas Well|Oil or Gas Well|Injection|Disposal|Other)\s+(\d+)\s+([\d.]+)\s+(\d+)\s*$', txt, re.M):
        fields.append({'district': m.group(1), 'field_number': m.group(2), 'field_name': m.group(3).strip(), 'well_type': m.group(4),
                       'completion_depth': m.group(5), 'distance_to_nearest_well': m.group(6), 'wells_on_lease': m.group(7)})
    v['fields'] = fields
    lines = txt.split('\n')
    idx = next((i for i, l in enumerate(lines) if 'Name of filer' in l), None)
    v['filer_name'], v['date_submitted'] = (None, None)
    if idx and idx >= 1:
        toks = re.split(r'\s{3,}', lines[idx - 1].strip())
        if len(toks) >= 2:
            name, v['date_submitted'] = toks[-2].strip(), toks[-1].strip()
            # a wrapped name continues on the line above, in the right-hand column (col >= 120), never the remarks column
            prev = lines[idx - 2] if idx >= 2 else ''
            mprev = re.match(r'^\s{120,}(\S.*?)\s*$', prev)
            if mprev and 'best of my knowledge' not in mprev.group(1):
                name = mprev.group(1).strip() + ' ' + name
            v['filer_name'] = name
    v['data_validation_timestamp'] = grab(r'Data Validation Time Stamp:\s+(.+?)\(')

    ANCHOR = {'api_number': ('API', 'No.'), 'permit_number': ('Drilling', 'Permit', '#'), 'permit_status': ('Permit', 'Status:'),
              'operator_number': ('1.', 'RRC', 'Operator'), 'operator_name': ('2.', "Operator's", 'Name'), 'lease_name': ('4.', 'Lease', 'Name'),
              'well_number': ('5.', 'Well', 'No.'), 'total_depth': ('8.', 'Total', 'Depth'), 'district': ('11.', 'RRC', 'District'),
              'county': ('12.', 'County'), 'miles_from_town': ('14.', 'This', 'well'), 'direction_from_town': ('miles', 'in', 'a'),
              'nearest_town': ('direction', 'from'), 'abstract_number': ('18.', 'Abstract', 'No.'), 'contiguous_acres': ('unitized', 'tract:'),
              'lease_perpendiculars': ('21.', 'Lease', 'Perpendiculars:'), 'survey_perpendiculars': ('22.', 'Survey', 'Perpendiculars:'),
              'filer_name': ('Certificate:',), 'date_submitted': ('Certificate:',)}
    boxes = {}
    for k, val in v.items():
        if isinstance(val, str):
            b = find_box(val, ANCHOR.get(k))
            if b:
                boxes[k] = {'page': 1, 'bbox': b}
        elif isinstance(val, dict):
            # perpendiculars read left to right: feet_1, direction_1, feet_2, direction_2; each search starts after the previous hit
            anchor = ANCHOR.get(k)
            for kk in ['feet_1', 'direction_1', 'feet_2', 'direction_2']:
                vv = val.get(kk)
                if isinstance(vv, str):
                    b = find_box(vv, anchor)
                    if b:
                        boxes[f"{k}.{kk}"] = {'page': 1, 'bbox': b}
                        anchor = (vv,) if not anchor else tuple(anchor) + (vv,) if False else None
                        # after the first hit, continue from that value's own position by anchoring on it
                        anchor = (vv,)
    return {'values': v, 'citation_truth': boxes, 'page_size_pt': [W, H]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zipdir', required=True)
    ap.add_argument('--ascii', required=True)
    ap.add_argument('--manual', required=True)
    ap.add_argument('--zipname', default='subscriptions_2026-09-03.zip')
    ap.add_argument('--asciidate', default='2026-09-04')
    ap.add_argument('--permits', nargs='+', required=True)
    ap.add_argument('--no-scan', action='store_true')
    a = ap.parse_args()

    from pypdf import PdfReader, PdfWriter
    counties = county_table(pathlib.Path(a.manual))
    ascii_all = parse_ascii(pathlib.Path(a.ascii), counties)
    zipdir = pathlib.Path(a.zipdir)
    allfiles = sorted(zipdir.rglob('*.pdf'))

    for d in ['corpus/raw', 'corpus/packets/clean', 'corpus/packets/scan', 'truth/ascii', 'truth/w1', 'truth/split', 'truth/classify']:
        (HERE / d).mkdir(parents=True, exist_ok=True)

    manifest = {'built': date.today().isoformat(), 'sources': [
        {'name': a.zipname, 'url': RRC_W1_URL, 'licence': LICENCE, 'fetched': a.asciidate},
        {'name': 'daf420.dat (Drilling Permit Master and Trailer - Daily File)', 'url': RRC_ASCII_URL, 'licence': LICENCE, 'fetched': a.asciidate},
        {'name': 'OGA049M record layout manual', 'url': RRC_MANUAL_URL, 'licence': LICENCE, 'fetched': a.asciidate}],
        'documents': [], 'packets': []}
    joined = 0
    for permit in a.permits:
        files = [f for f in allfiles if re.search(rf'/{permit}_(W1|Plat)_', str(f))]
        if not files:
            print(f"{permit}: no files in zip", file=sys.stderr); continue
        w1 = [f for f in files if f'{permit}_W1_' in str(f)]
        plats = [f for f in files if f'{permit}_Plat_' in str(f)]
        raw = HERE / 'corpus/raw' / permit
        raw.mkdir(exist_ok=True)
        ordered = w1 + plats
        writer = PdfWriter()
        page_map = []  # (class, start, end) 1-indexed in the packet
        cursor = 1
        for f in ordered:
            dst = raw / f.name
            if f.resolve() != dst.resolve():
                shutil.copy2(f, dst)
            n = len(PdfReader(str(dst)).pages)
            cls = 'w1_permit' if f in w1 else 'plat'
            manifest['documents'].append({'permit': permit, 'file': str(dst.relative_to(HERE)), 'sha256': sha256(dst), 'pages': n, 'class': cls, 'source_zip': a.zipname})
            for p in PdfReader(str(dst)).pages:
                writer.add_page(p)
            page_map.append({'class': cls, 'file': f.name, 'pages': list(range(cursor, cursor + n))})
            cursor += n
            (HERE / 'truth/classify' / f'{permit}__{f.stem}.json').write_text(json.dumps({'file': f.name, 'class': cls, 'grade': 'OBSERVED', 'basis': 'RRC file naming (W1 vs Plat)'}, indent=1))
        clean = HERE / 'corpus/packets/clean' / f'{permit}.pdf'
        with open(clean, 'wb') as fh:
            writer.write(fh)
        total_pages = cursor - 1
        splits = {}
        for pm in page_map:
            splits.setdefault(pm['class'], []).extend(pm['pages'])
        (HERE / 'truth/split' / f'{permit}.json').write_text(json.dumps({'permit': permit, 'total_pages': total_pages, 'splits': splits, 'documents': page_map, 'grade': 'OBSERVED', 'basis': 'packet assembled from separately published RRC files'}, indent=1))

        scan = HERE / 'corpus/packets/scan' / f'{permit}.pdf'
        if not a.no_scan:
            # 150 dpi gray, 0.6 degree skew, mild noise, JPEG-in-PDF: a plausible mailroom scan.
            subprocess.run(['magick', '-density', '150', str(clean), '-colorspace', 'Gray', '-rotate', '0.6', '+noise', 'Gaussian', '-attenuate', '0.15',
                            '-quality', '75', '-compress', 'JPEG', str(scan)], check=True)

        asc = ascii_all.get(permit.zfill(7))
        if asc:
            joined += 1
            asc['grade'] = 'SYSTEM-EXTRACTED'; asc['basis'] = f'RRC daf420.dat {a.asciidate}, OGA049M positions'
            (HERE / 'truth/ascii' / f'{permit}.json').write_text(json.dumps(asc, indent=1))
        t = w1_text_truth(w1[0])
        t.update({'permit': permit, 'grade': 'SYSTEM-EXTRACTED', 'basis': 'RRC W-1 facsimile text layer (pdftotext -layout / -bbox-layout); boxes normalized to page'})
        (HERE / 'truth/w1' / f'{permit}.json').write_text(json.dumps(t, indent=1))
        manifest['packets'].append({'permit': permit, 'clean': str(clean.relative_to(HERE)), 'clean_sha256': sha256(clean),
                                    'scan': str(scan.relative_to(HERE)) if scan.exists() else None, 'scan_sha256': sha256(scan) if scan.exists() else None,
                                    'pages': total_pages, 'ascii_truth': bool(asc), 'w1_truth': f'truth/w1/{permit}.json', 'split_truth': f'truth/split/{permit}.json'})
        print(f"{permit}: {len(w1)} W-1 + {len(plats)} plat(s), {total_pages} pages, ascii={'yes' if asc else 'NO'}")
    manifest['join'] = {'permits_requested': len(a.permits), 'permits_with_ascii_truth': joined, 'note': 'join key = permit (status) number; same-morning daily file'}
    (HERE / 'corpus/manifest.json').write_text(json.dumps(manifest, indent=1))
    print(f"manifest: {len(manifest['documents'])} documents, {len(manifest['packets'])} packets, ascii join {joined}/{len(a.permits)}")


if __name__ == '__main__':
    main()
