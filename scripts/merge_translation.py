#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge Translations into Twine Extract JSON
=========================================

Inputs
------
1. Extract JSON: Output of `twine_extract_recursive.py`.
   Structure: {PassageName: {meta:{...}, segments:[...]}}
2. Translation skeleton JSON: Output of `skeleton_from_extract.py`, *edited* by translators.
   Structure: {PassageName: {"segid.field": "Translated text", ...}, ...}

What gets merged
----------------
We update the extract structure in-place (copy) with translated values for these cases:

  - seg.type == "text"  & key: "<segid>.src"     -> seg["src"] = translated
  - seg.type == "link"  & key: "<segid>.label"   -> seg["label"] = translated
  - seg.type == "macro" & key: "<segid>.args"    -> replace *first string literal* in seg["args"]
       Applies to macro names in the translatable set:
           click, link, link-repeat, link-reveal,
           hover, hover-tooltip,
           tooltip,
           alert,
           print

NOTE: We do **not** edit seg["src"] for macro segments; we preserve original macro syntax.
      Only the first quoted string literal inside seg["args"] is replaced.
      If the macro had no string literal originally, no translation can be applied.

Safety & Validation
-------------------
* If translation key refers to non-existent passage/segment/field -> warning.
* If segment type/field mismatch (e.g., trying to write label to a text seg) -> warning, ignore.
* If we cannot find a string literal in macro args when translation provided -> warning, ignore.
* If translation contains the quote char used in macro args, we escape it with backslash.

CLI Usage
---------
    python merge_translation.py extract.json skeleton.json -o merged.json

    # Preview only (dry run, no output file):
    python merge_translation.py extract.json skeleton.json --dry-run

    # Strict mode (error if missing keys, etc.):
    python merge_translation.py extract.json skeleton.json -o merged.json --strict

    # Keep untranslated keys (warn only):
    python merge_translation.py extract.json skeleton.json -o merged.json

Exit Codes
----------
0 = success
1 = strict errors encountered

"""

from __future__ import annotations
import argparse, json, sys, re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple, Set

# ----------------------------------------------------------------------
# Config: macro names whose args first string literal is translatable
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# String literal parsing & replacement
# ----------------------------------------------------------------------
def find_first_string_literal_span(arg_text: str) -> Optional[Tuple[int, int, str]]:
    """
    Locate the first string literal in arg_text.
    Return (start_index_of_delim, end_index_of_delim_exclusive, quote_char)
    where substring[arg_start:arg_end] includes delimiters (quotes).
    If none found, return None.
    """
    i = 0
    n = len(arg_text)
    while i < n:
        ch = arg_text[i]
        if ch in ('"', "'"):
            quote = ch
            j = i + 1
            while j < n:
                c = arg_text[j]
                if c == "\\" and j + 1 < n:  # escape next char
                    j += 2
                    continue
                if c == quote:
                    return i, j + 1, quote
                j += 1
            # unmatched -> treat to end
            return i, n, quote
        i += 1
    return None


def unescape_string_literal(lit: str, quote: str) -> str:
    """
    Given a literal including delimiters? Actually we pass inner substring
    without delimiters when calling; but here we ensure we unescape \\" and \'.
    """
    # naive: turn backslash escapes into literal char (\" -> ", \\ -> \ etc.)
    out = []
    i = 0
    n = len(lit)
    while i < n:
        c = lit[i]
        if c == "\\" and i + 1 < n:
            out.append(lit[i + 1])
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def escape_for_quote(text: str, quote: str) -> str:
    """Escape occurrences of quote char and backslash for embedding in literal."""
    # we escape backslash first to avoid double-escaping
    text = text.replace("\\", "\\\\")
    if quote == '"':
        text = text.replace('"', '\\"')
    else:
        text = text.replace("'", "\\'")
    return text


def replace_first_string_literal(arg_text: str, new_value: str) -> Tuple[str, bool]:
    """
    Replace the content of the first string literal in arg_text with new_value.
    Preserve original quote char. Escape appropriately.
    Return (new_arg_text, replaced_flag).
    """
    span = find_first_string_literal_span(arg_text)
    if span is None:
        return arg_text, False
    start, end, quote = span
    inner = arg_text[start + 1 : end - 1]  # raw literal content (escaped)
    # decode not strictly needed; we just re-escape new text
    new_inner = escape_for_quote(new_value, quote)
    new_arg_text = arg_text[:start + 1] + new_inner + arg_text[end - 1 :]
    return new_arg_text, True


# ----------------------------------------------------------------------
# Walk extract structure and index segments by id
# ----------------------------------------------------------------------
def index_segments(passages: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Build index: {PassageName: {segid: seg_dict}}
    Includes *all* segments recursively (macro hook children, bare hook children).
    """
    index: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for pname, prec in passages.items():
        seg_idx: Dict[str, Dict[str, Any]] = {}
        segs = prec.get("segments", [])
        for seg in segs:
            _index_segment_recursive(seg, seg_idx)
        index[pname] = seg_idx
    return index


def _index_segment_recursive(seg: Dict[str, Any], seg_idx: Dict[str, Dict[str, Any]]):
    sid = seg.get("id")
    if sid:
        seg_idx[sid] = seg
    stype = seg.get("type")

    if stype == "macro" and "hook" in seg and isinstance(seg["hook"], dict):
        for child in seg["hook"].get("segments", []):
            _index_segment_recursive(child, seg_idx)

    elif stype == "hook" and "segments" in seg:
        for child in seg["segments"]:
            _index_segment_recursive(child, seg_idx)

    # others have no children


# ----------------------------------------------------------------------
# Merge logic
# ----------------------------------------------------------------------
def merge_translation(
    extract_data: Dict[str, Any],
    skeleton_data: Dict[str, Any],
    strict: bool = False,
    apply_empty: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """
    Merge skeleton translations into extract structure.
    Returns (merged_data, num_warnings_or_errors).
    If strict=True, missing/mismatch increments error count; caller decides exit code.
    """
    merged = deepcopy(extract_data)
    passage_index = index_segments(merged)

    problems = 0

    for pname, trans_map in skeleton_data.items():
        if pname not in merged:
            _warn(f"Translation provided for unknown passage '{pname}'.")
            if strict:
                problems += 1
            continue

        seg_index = passage_index[pname]
        for key, new_text in trans_map.items():
            # parse segid.field
            if "." not in key:
                _warn(f"Bad translation key '{key}' in passage '{pname}' (missing .field).")
                if strict:
                    problems += 1
                continue
            segid, field = key.rsplit(".", 1)

            seg = seg_index.get(segid)
            if seg is None:
                _warn(f"Translation key '{key}' refers to unknown segment id in passage '{pname}'.")
                if strict:
                    problems += 1
                continue

            if not apply_empty and (new_text is None or str(new_text).strip() == ""):
                # skip empty translation (treat as untranslated)
                continue

            stype = seg.get("type")

            # case 1: text.src
            if stype == "text" and field == "src":
                seg["src"] = str(new_text)
                continue

            # case 2: link.label
            if stype == "link" and field == "label":
                seg["label"] = str(new_text)
                # we do NOT touch seg["src"] because rebuild will regenerate from fields
                continue

            # case 3: macro.args
            if stype == "macro" and field == "args":
                name = (seg.get("name") or "").strip().lower()
                if name in TRANSLATABLE_MACRO_NAMES:
                    arg_text = seg.get("args", "")
                    new_arg_text, ok = replace_first_string_literal(arg_text, str(new_text))
                    if ok:
                        seg["args"] = new_arg_text
                        # NOTE: seg["src"] = macro literal only; we do *not* auto-update src because
                        # we rebuild macros from name+args; if you rely on src for raw reproduction,
                        # you'll need a later render step.
                    else:
                        _warn(f"No string literal in macro args for '{key}' (name={name}); translation ignored.")
                        if strict:
                            problems += 1
                else:
                    _warn(f"Macro '{name}' not in translatable set; key '{key}' ignored.")
                    if strict:
                        problems += 1
                continue

            # fallback: mismatch
            _warn(f"Translation key '{key}' does not match segment type/field (stype={stype}).")
            if strict:
                problems += 1

    return merged, problems


def _warn(msg: str):
    print(f"[WARN] {msg}", file=sys.stderr)


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def cli():
    ap = argparse.ArgumentParser(
        description="Merge translation skeleton JSON into Twine extract JSON."
    )
    ap.add_argument("extract_json", help="Input extract JSON from twine_extract_recursive.py")
    ap.add_argument("skeleton_json", help="Translation skeleton JSON (edited by translators)")
    ap.add_argument("-o", "--out", help="Output merged JSON (default: stdout)")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as errors (nonzero exit).")
    ap.add_argument(
        "--apply-empty",
        action="store_true",
        help="Apply even empty translation strings (default: skip empties).",
    )
    ap.add_argument(
        "--indent", type=int, default=2, help="JSON indent (default 2; 0=minified)"
    )
    args = ap.parse_args()

    extract_data = json.load(open(args.extract_json, "r", encoding="utf-8"))
    skeleton_data = json.load(open(args.skeleton_json, "r", encoding="utf-8"))

    merged, problems = merge_translation(
        extract_data,
        skeleton_data,
        strict=args.strict,
        apply_empty=args.apply_empty,
    )

    js = json.dumps(merged, ensure_ascii=False, indent=args.indent if args.indent > 0 else None)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(js)
    else:
        print(js)

    if args.strict and problems:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    cli()
