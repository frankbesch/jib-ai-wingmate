#!/usr/bin/env python3
"""Freeze a truth dir as one sha256 (the recipe that reproduces the pilot's committed truth-a/truth-b values).

Recipe, equal to running from ROOT:  shasum -a 256 <label>/*.json | shasum -a 256
  - one line per *.json file in the dir (REPORT.md and other files are excluded), sorted by file name,
    "<sha256 of the file>  <label>/<file name>\\n" (shasum's two-space text format);
  - the frozen value is the sha256 of those lines concatenated;
  - <label> is the dir path relative to ROOT. ROOT is the layer-B root (`<corpus>/layerB`): the pilot hashed
    `../truth` (layer A) and `<set>/truth-b` (layer B) from `synth-pilot/layerB/`.
Default ROOT (no --root): the dir's grandparent, so `<corpus>/layerB/<set>/truth-b` gets label `<set>/truth-b`.

Usage: freeze_hashes.py --dir <truth dir> [--dir ...] [--root <dir>] [--out <sha file or existing dir>]
Prints one hash per --dir (in order); the label used goes to stderr. Read-only toward the truth dirs.
"""
import argparse, hashlib, os, pathlib, sys


def listing(d, label):
    files = sorted(p for p in pathlib.Path(d).glob('*.json') if p.is_file())
    if not files:
        raise SystemExit(f'{d}: no *.json files to hash')
    return ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {label}/{p.name}\n' for p in files)


def dir_hash(d, root=None):
    """(hash, label) for truth dir d; label = d relative to root (default: d's grandparent)."""
    d = pathlib.Path(d).resolve()
    root = pathlib.Path(root).resolve() if root else d.parent.parent
    label = os.path.relpath(d, root)
    return hashlib.sha256(listing(d, label).encode()).hexdigest(), label


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dir', action='append', required=True)
    ap.add_argument('--root', default=None, help='layer-B root the label is relative to; default the dir\'s grandparent')
    ap.add_argument('--out', default=None, help='file (one --dir) or existing dir (writes <dir name>.sha256 per --dir)')
    a = ap.parse_args()
    out = pathlib.Path(a.out) if a.out else None
    if out and not out.is_dir() and len(a.dir) > 1:
        raise SystemExit('--out must be an existing dir when --dir is given more than once')
    for d in a.dir:
        h, label = dir_hash(d, a.root)
        print(h)
        print(f'{d}: label {label}', file=sys.stderr)
        if out:
            target = out / f'{pathlib.Path(d).resolve().name}.sha256' if out.is_dir() else out
            target.write_text(h + '\n')
            print(f'wrote {target}', file=sys.stderr)


if __name__ == '__main__':
    main()
