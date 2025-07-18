#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Translation Skeleton JSON from Twine Extract
====================================================

Reads the JSON produced by `twine_extract_recursive.py` (the extractor), and
emits a *skeleton* JSON that contains ONLY the fields a translator should edit.

Included translation targets (in priority / grouping):
  1. segments where type == "text" -> src
  2. segments where type == "link" -> label
  3. segments where type == "macro" and name in this set -> args first string:
       click
       link, link-repeat, link-reveal
       hover, hover-tooltip
       tooltip
       alert
       print

We parse the *first* string literal in the macro's args. If no string literal,
the macro contributes nothing to the skeleton.

Output structure
----------------
{
  "<PassageName>": {
    "<segid>.src":   "<text to translate>",
    "<segid>.label": "<link label>",
    "<segid>.args":  "<macro string literal>",
    ...
  },
  ...
}

This JSON is meant for translators to edit in-place: replace each value with
Chinese (or other target language). Later, a merge tool will reinsert the
translations into the full segment tree.

Filtering
---------
--name PassageName    # repeatable or comma-separated
--nonempty-only       # (default) skip empty strings
--keep-empty          # include empty strings too

Usage
-----
    python skeleton_from_extract.py extract.json > skeleton.json
    python skeleton_from_extract.py extract.json --name Startup --name Wake -o sk.json
"""

from __future__ import annotations
import argparse, json, re, sys
from typing import Any, Dict, List, Optional, Set

# ======================================================================
# Config: which macro names should expose args for translation
# ======================================================================
TRANSLATABLE_MACRO_NAMES = {
    "click",
    "link",
    "link-repeat",
    "link-reveal",
    "hover",
    "hover-tooltip",
    "tooltip",
    "alert",
    "print",
}

# ======================================================================
# String literal extraction
# ======================================================================
# We want the *first* string literal, respecting escapes. Support both
# double-quoted "..." and single-quoted '...'.

def extract_first_string_literal(arg_text: str) -> Optional[str]:
    """
    Return the unescaped contents of the first quoted string literal in arg_text,
    or None if none found.
    Recognizes "..." and '...' with backslash escaping of same-quote char.
    """
    if not arg_text:
        return None

    i = 0
    n = len(arg_text)
    while i < n:
        ch = arg_text[i]
        if ch in ("'", '"'):
            quote = ch
            i += 1
            buf = []
            while i < n:
                c = arg_text[i]
                if c == "\\" and i + 1 < n:
                    buf.append(arg_text[i + 1])  # keep char literally
                    i += 2
                    continue
                if c == quote:
                    # done
                    return "".join(buf)
                buf.append(c)
                i += 1
            # unmatched quote -> take what we have
            return "".join(buf)
        i += 1
    return None


# ======================================================================
# Skeleton builder (recursive walk)
# ======================================================================
def build_skeleton_for_passage(passage: Dict[str, Any], nonempty_only: bool = True) -> Dict[str, str]:
    """
    Given a single passage record from extractor output, build the skeleton map.
    Returns dict mapping 'segid.field' -> text.
    """
    out: Dict[str, str] = {}
    segs = passage.get("segments", [])
    for seg in segs:
        _collect_segment(seg, out, nonempty_only=nonempty_only)
    return out


def _collect_segment(seg: Dict[str, Any], out: Dict[str, str], nonempty_only: bool = True):
    stype = seg.get("type")
    sid = seg.get("id")
    if not sid:
        return

    # 1. text -> src
    if stype == "text":
        txt = seg.get("src", "")
        if (not nonempty_only) or txt.strip():
            out[f"{sid}.src"] = txt
        # no children
        return

    # 2. link -> label
    if stype == "link":
        lbl = seg.get("label", "")
        if (not nonempty_only) or lbl.strip():
            out[f"{sid}.label"] = lbl
        return

    # 3. macro -> maybe args
    if stype == "macro":
        name = (seg.get("name") or "").strip().lower()
        if name in TRANSLATABLE_MACRO_NAMES:
            arg_text = seg.get("args", "")
            literal = extract_first_string_literal(arg_text)
            if literal is not None:
                if (not nonempty_only) or literal.strip():
                    out[f"{sid}.args"] = literal

        # recurse into macro hook children (if any)
        hook = seg.get("hook")
        if isinstance(hook, dict):
            for child in hook.get("segments", []):
                _collect_segment(child, out, nonempty_only=nonempty_only)
        return

    # 4. bare hook -> recurse
    if stype == "hook":
        for child in seg.get("segments", []):
            _collect_segment(child, out, nonempty_only=nonempty_only)
        return

    # 5. others (var, tag, align_center, etc.) -> no translation; no recursion
    return


# ======================================================================
# Passage filtering
# ======================================================================
def normalize_name_filters(name_args: Optional[List[str]]) -> Optional[Set[str]]:
    if not name_args:
        return None
    names: Set[str] = set()
    for chunk in name_args:
        for piece in chunk.split(","):
            piece = piece.strip()
            if piece:
                names.add(piece)
    return names or None


def filter_passages(all_passages: Dict[str, Any], wanted: Optional[Set[str]]) -> Dict[str, Any]:
    if wanted is None:
        return all_passages
    return {k: v for k, v in all_passages.items() if k in wanted}


# ======================================================================
# Main CLI
# ======================================================================
def cli():
    ap = argparse.ArgumentParser(
        description="Generate translation skeleton JSON from Twine extract JSON."
    )
    ap.add_argument("extract_json", help="Input: JSON produced by twine_extract_recursive.py")
    ap.add_argument("-o", "--out", help="Output skeleton JSON (default stdout)")
    ap.add_argument(
        "--name",
        action="append",
        help="Limit to passage name(s); repeatable or comma-separated."
    )
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--nonempty-only", action="store_true", default=True,
                     help="(default) Skip entries whose extracted text is empty/whitespace.")
    grp.add_argument("--keep-empty", dest="nonempty_only", action="store_false",
                     help="Include empty strings in skeleton.")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default 2; 0=minified)")
    args = ap.parse_args()

    data = json.load(open(args.extract_json, "r", encoding="utf-8"))

    wanted = normalize_name_filters(args.name)
    data = filter_passages(data, wanted)

    skeleton: Dict[str, Dict[str, str]] = {}
    for pname, prec in data.items():
        sk = build_skeleton_for_passage(prec, nonempty_only=args.nonempty_only)
        if sk:  # only include passages that actually have entries
            skeleton[pname] = sk

    js = json.dumps(skeleton, ensure_ascii=False, indent=args.indent if args.indent > 0 else None)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(js)
    else:
        print(js)


if __name__ == "__main__":
    cli()
