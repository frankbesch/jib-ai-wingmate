"""Frozen controls K1, K2, K3 for held-out run 2 (plan 06-control-test-plan.md, section 3). Pure functions.

No model calls, no network, no corpus manifest, no truth file. The only file this module reads is
`demo/reconcile.py`, and only as source text: the REQUIRED literal is parsed with `ast`, never imported or run.

Inputs are what one Pulse run folder holds, already loaded by the caller:
  month  = runs/<id>/month.json as a dict.
  units  = row-8 unit records. Either raw cascade records from `calls.jsonl` (`kind`, `node`, `subject`,
           `score.final`, `score.abstain`) or flat dicts carrying `final` and `abstain` at top level.
           `subject` is `<doc_id>.<field>`.
  texts  = {doc_id: the Pulse text of that document, the same text the arms receive}.
Every K function returns the sorted list of flagged unit subjects.
"""
import ast
import pathlib

RECONCILE = pathlib.Path(__file__).resolve().parent.parent / 'reconcile.py'
AFE_CLASSES = ('afe', 'afe_cover')
MIN_SOURCE = 3          # a source shorter than this after norm() is no source
# K3 sources in reference/doi.json (inspected in synth-heldout/reference/doi.json, 2026-10-02):
# {"property_number": str, "well_name": str, "owners": [{"owner_name", "owner_number", ...}], ...}.
# A path step '*' walks every element of a list.
K3_KEYS = {
    'well_name': ('well_name',),
    'owner_name': ('owners', '*', 'owner_name'),
    'owner_number': ('owners', '*', 'owner_number'),
    'property_number': ('property_number',),
}


def required(path=RECONCILE):
    """REQUIRED {class: [field, ...]} parsed from the reconcile.py source with ast (not imported, not run)."""
    for node in ast.parse(pathlib.Path(path).read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REQUIRED' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f'{path}: no REQUIRED assignment')


def doc_class(month):
    """{doc_id: class as Pulse assigned it}, from month['classify'][i]['predicted'].

    month['documents'][doc]['class'] is NOT used: pipeline.py writes it from the corpus manifest
    (`doc = {'class': d['class'], ...}` with d a manifest document), so it is the generator's class.
    `predicted` is Pulse /classify's own output. A record without doc_id is skipped."""
    return {c['doc_id']: c.get('predicted') for c in month.get('classify', []) if c.get('doc_id')}


def norm(s):
    """Strip, collapse internal whitespace to one space, casefold. Nothing else."""
    return ' '.join(str(s).split()).casefold()


def bounded_in(needle, hay):
    """norm(needle) occurs in norm(hay) with a non-alphanumeric character or the text edge on both sides."""
    n, h = norm(needle), norm(hay)
    if not n:
        return False
    i = h.find(n)
    while i >= 0:
        j = i + len(n)
        if (i == 0 or not h[i - 1].isalnum()) and (j == len(h) or not h[j].isalnum()):
            return True
        i = h.find(n, i + 1)
    return False


def _valid(v):
    return isinstance(v, str) and len(norm(v)) >= MIN_SOURCE


def _kept_false(u):
    """(doc_id, field) when the unit is a kept 'not printed' (final is False, not abstained), else None."""
    if u.get('kind', 'unit') != 'unit' or u.get('node', 'row8') != 'row8':
        return None
    s = u.get('score', u)
    if s.get('final') is not False or s.get('abstain'):
        return None
    doc, _, field = u['subject'].partition('.')
    return doc, field


def k1_flags(units, month, req=None):
    """K1: a kept 'not printed' on a field in REQUIRED[Pulse class of the document]."""
    req = required() if req is None else req
    cls = doc_class(month)
    out = []
    for u in units:
        k = _kept_false(u)
        if k and k[1] in req.get(cls.get(k[0]), ()):
            out.append(u['subject'])
    return sorted(out)


def k2_sources(month, drop_source=None):
    """{doc_id: afe_number} from documents.<doc>.values.afe_number of every document Pulse classified as afe
    or afe_cover. Invalid sources (None, empty, under MIN_SOURCE after norm) are left out."""
    cls, docs = doc_class(month), month.get('documents', {})
    out = {}
    for d, c in cls.items():
        if c in AFE_CLASSES and d != drop_source:
            v = ((docs.get(d) or {}).get('values') or {}).get('afe_number')
            if _valid(v):
                out[d] = v
    return out


def _match_flags(units, fields, sources, texts):
    out = []
    for u in units:
        k = _kept_false(u)
        if k and k[1] in fields and any(bounded_in(s, texts.get(k[0], '')) for s in sources):
            out.append(u['subject'])
    return sorted(out)


def k2_flags(units, month, texts, drop_source=None):
    """K2: a kept 'not printed' on afe_number when any K2 source occurs, bounded, in that document's text."""
    return _match_flags(units, ('afe_number',), list(k2_sources(month, drop_source).values()), texts)


def _walk(obj, path):
    if not path:
        return [obj]
    if path[0] == '*':
        return [v for x in (obj if isinstance(obj, list) else []) for v in _walk(x, path[1:])]
    return _walk(obj[path[0]], path[1:]) if isinstance(obj, dict) and path[0] in obj else []


def k3_flags(units, reference_doi, texts):
    """K3: K2's match for the K3_KEYS fields, sources from reference/doi.json.
    Returns (flags, skipped): skipped = sorted fields whose key path yields no valid source."""
    flags, skipped = [], []
    for field, path in K3_KEYS.items():
        src = [v for v in _walk(reference_doi, path) if _valid(v)]
        if not src:
            skipped.append(field)
            continue
        flags += _match_flags(units, (field,), src, texts)
    return sorted(flags), sorted(skipped)
