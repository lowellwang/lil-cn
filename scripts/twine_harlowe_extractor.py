#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twine Harlowe Passage Extractor (Recursive + Strict Macro)
==========================================================

Extracts Twine (Harlowe 3.x) story passages from an exported HTML file,
tokenizes each passage into translation-safe segments, and outputs a JSON
structure suitable for building translation skeletons and later reconstruction.

Key Features
------------
* Parses <tw-storydata> and all <tw-passagedata>.
* html.unescape() on both attributes and passage inner text.
* Recursive tokenizer priority:
    0. alignment marker  =><=           -> align_center segment
    1. [[link]] / [[label->target]]     -> link segment
    2. (macroName: args) [hook ...]?    -> macro segment, optional hook children (recursive)
       (only recognized if a colon ':' appears at top level inside parens,
        and macroName matches [A-Za-z_][A-Za-z0-9_-]*)
    3. <HTML tag ...>                   -> tag segment
    4. bare [hook ...]                  -> hook segment with child segments (recursive)
    5. $var                             -> var segment
    6. remaining text                   -> text segment
* Hierarchical segment IDs:
    s0001, s0002, ...
    s0001_1 (child #1 of s0001), s0001_2_1 (grandchild), etc.
* --name filter to extract subset of passages for debugging.
* JSON pretty-printing via --indent.

Intended Workflow
-----------------
1. Run this extractor to get structured JSON.
2. Run skeleton generator to collect only translatable fields.
3. Translate skeleton.
4. Merge translations back into structured JSON.
5. Render localized Twine or runtime inject with userscript.

Usage
-----
    python twine_extract_recursive_strictmacro.py story.html out.json
    python twine_extract_recursive_strictmacro.py story.html --name "Startup"
    python twine_extract_recursive_strictmacro.py story.html --name "Startup,Wake"
    python twine_extract_recursive_strictmacro.py --demo part.txt --name "Wake"

"""

from __future__ import annotations
import argparse
import hashlib
import html
import json
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


# =============================================================================
# Utilities
# =============================================================================
def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


# =============================================================================
# Attribute parsing
# =============================================================================
ATTR_RE = re.compile(r'(\w+)\s*=\s*"(.*?)"')

def parse_attrs(attr_text: str) -> Dict[str, str]:
    """Parse attributes of <tw-passagedata>; html.unescape() values."""
    attrs: Dict[str, str] = {}
    for k, v in ATTR_RE.findall(attr_text):
        attrs[k] = html.unescape(v)
    return attrs


# =============================================================================
# Balanced scanners
# =============================================================================
def scan_balanced(src: str, start: int, open_ch: str, close_ch: str) -> Tuple[int, str]:
    """
    Scan from start (at open_ch) to matching close_ch (balanced).
    Return (new_index_after_segment, substring_including_delims).
    If unbalanced, consume to end-of-string.
    """
    depth = 0
    i = start
    n = len(src)
    while i < n:
        c = src[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1, src[start:i + 1]
        i += 1
    # unmatched: take rest
    return n, src[start:]


# =============================================================================
# Specific scanners
# =============================================================================

# 0) Alignment marker
ALIGN_CENTER = "=><="

def scan_align_center(src: str, start: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    """Detect Harlowe center-align markup '=><='."""
    if src.startswith(ALIGN_CENTER, start):
        return start + len(ALIGN_CENTER), {"type": "align_center", "src": ALIGN_CENTER}
    return start + 1, None


# 1) [[link]] / [[label->target]]
def scan_link(src: str, start: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    if not src.startswith("[[", start):
        return start + 1, None
    i = start + 2
    n = len(src)
    while i < n and not src.startswith("]]", i):
        i += 1
    if i >= n:
        return n, None  # unmatched
    inner = src[start + 2 : i]
    i += 2
    if "->" in inner:
        label_part, target_part = inner.split("->", 1)
        label = html.unescape(label_part.strip())
        target = html.unescape(target_part.strip())
    else:
        label = html.unescape(inner.strip())
        target = html.unescape(inner.strip())
    seg = {
        "type": "link",
        "src": src[start:i],
        "label": label,
        "target": target,
        "hash": sha1(label),
    }
    return i, seg


# --- Macro head detection ---------------------------------------------------
_MACRO_NAME_TOKEN = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')

def _skip_quoted(src: str, start: int) -> Optional[int]:
    """Skip over a quoted string starting at index start. Return new index after closing quote."""
    quote = src[start]
    i = start + 1
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    return None  # unmatched


def looks_like_macro_head(src: str, start: int) -> bool:
    """
    Heuristic check: does the paren group at `start` look like a Harlowe macro?
    Requirements:
      * start char must be '('
      * at top level depth==1 before closing ')', we encounter ':' once
      * substring before that ':' matches macro name token regex
    Strings and nested parens are skipped structurally.
    """
    if start >= len(src) or src[start] != "(":
        return False

    depth = 1
    i = start + 1
    n = len(src)
    token_buf = []

    while i < n:
        c = src[i]

        # string literal skip
        if c in ('"', "'"):
            nxt = _skip_quoted(src, i)
            if nxt is None:
                return False
            i = nxt
            continue

        if c == "(":
            depth += 1
            i += 1
            continue

        if c == ")":
            depth -= 1
            if depth == 0:
                # closed without colon
                return False
            i += 1
            continue

        if depth == 1 and c == ":":
            candidate = "".join(token_buf).strip()
            return bool(_MACRO_NAME_TOKEN.match(candidate))
        if depth == 1:
            token_buf.append(c)
        i += 1

    # ran out before matching ')'
    return False


# 2) (macroName: args) [hook...]?
def scan_macro_recursive(src: str, start: int) -> Tuple[int, Optional[Dict[str, Any]], Optional[str]]:
    """
    Parse a macro ONLY if looks_like_macro_head() is True.
    Returns (new_index, macro_seg, hook_src_or_None).
    macro_seg['src'] = '(name: args)' (macro only; hook separate)
    """
    if not looks_like_macro_head(src, start):
        return start + 1, None, None

    end_macro, macro_raw = scan_balanced(src, start, "(", ")")
    inner = macro_raw[1:-1]
    # split on first ':' (safe, we know one exists at top level)
    colon_pos = inner.find(":")
    if colon_pos >= 0:
        name = inner[:colon_pos].strip()
        args = inner[colon_pos + 1 :].strip()
    else:
        name = inner.strip()
        args = ""

    i = end_macro
    hook_src = None
    if i < len(src) and src[i] == "[":
        end_hook, hook_raw = scan_balanced(src, i, "[", "]")
        hook_src = hook_raw
        i = end_hook

    seg = {
        "type": "macro",
        "name": name,
        "args": args,
        "src": macro_raw,
    }
    return i, seg, hook_src


# 3) <HTML ...>
HTML_TAG_RE = re.compile(r"<[^>]+>")

def scan_html_tag(src: str, start: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    if src[start] != "<":
        return start + 1, None
    m = HTML_TAG_RE.match(src, start)
    if not m:
        return start + 1, None
    raw = m.group(0)
    return m.end(), {"type": "tag", "src": raw}


# 4) bare [hook ...]
def scan_hook_recursive(src: str, start: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    if src[start] != "[" or src.startswith("[[", start):
        return start + 1, None
    end, raw = scan_balanced(src, start, "[", "]")
    inner = raw[1:-1]
    child_segments = tokenize_recursive(inner)
    seg = {
        "type": "hook",
        "src": raw,
        "segments": child_segments,
    }
    return end, seg


# 5) $var
VAR_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")

def scan_var(src: str, start: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    m = VAR_RE.match(src, start)
    if not m:
        return start + 1, None
    raw = m.group(0)
    return m.end(), {"type": "var", "src": raw, "hash": sha1(raw)}


# =============================================================================
# Recursive tokenizer
# =============================================================================
def tokenize_recursive(src: str) -> List[Dict[str, Any]]:
    """
    Recursive tokenizer that produces a tree-aware segment list.
    Argument `src` must be *unescaped* passage source text.
    """
    segs: List[Dict[str, Any]] = []
    buf: List[str] = []
    i = 0
    n = len(src)

    def flush_text():
        nonlocal buf
        if buf:
            s = "".join(buf)
            segs.append({"type": "text", "src": s, "hash": sha1(s)})
            buf = []

    while i < n:
        ch = src[i]

        # 0. align =><=
        if src.startswith(ALIGN_CENTER, i):
            flush_text()
            i, seg = scan_align_center(src, i)
            if seg:
                segs.append(seg)
                continue

        # 1. link [[...]]
        if ch == "[" and i + 1 < n and src[i + 1] == "[":
            flush_text()
            i2, link_seg = scan_link(src, i)
            if link_seg:
                segs.append(link_seg)
                i = i2
                continue

        # 2. macro (name: ...)
        if ch == "(" and looks_like_macro_head(src, i):
            flush_text()
            i2, macro_seg, hook_src = scan_macro_recursive(src, i)
            if macro_seg:
                if hook_src is not None:
                    inner = hook_src[1:-1]
                    macro_seg["hook"] = {
                        "src": hook_src,
                        "segments": tokenize_recursive(inner),
                    }
                segs.append(macro_seg)
                i = i2
                continue
            # fallthrough if somehow failed (shouldn't)

        # 3. HTML tag
        if ch == "<":
            flush_text()
            i2, tag_seg = scan_html_tag(src, i)
            if tag_seg:
                segs.append(tag_seg)
                i = i2
                continue

        # 4. bare hook [ ... ]
        if ch == "[":
            flush_text()
            i2, hook_seg = scan_hook_recursive(src, i)
            if hook_seg:
                segs.append(hook_seg)
                i = i2
                continue

        # 5. var $foo
        if ch == "$":
            flush_text()
            i2, var_seg = scan_var(src, i)
            if var_seg:
                segs.append(var_seg)
                i = i2
                continue

        # 6. default text
        buf.append(ch)
        i += 1

    flush_text()
    return segs


# =============================================================================
# ID assignment (hierarchical)
# =============================================================================
def assign_ids_top_level(segs: List[Dict[str, Any]], prefix: str = "s") -> None:
    """
    Assign IDs to segments in-place.
    Top-level: s0001, s0002, ...
    Descendants: parentID_1, parentID_2, ...
    """
    for idx, seg in enumerate(segs, start=1):
        seg_id = f"{prefix}{idx:04d}"
        seg["id"] = seg_id
        _assign_ids_children(seg, seg_id)


def _assign_ids_children(seg: Dict[str, Any], parent_id: str) -> None:
    # macro with hook children
    if seg.get("type") == "macro" and "hook" in seg and isinstance(seg["hook"], dict):
        kids = seg["hook"].get("segments", [])
        for j, child in enumerate(kids, start=1):
            cid = f"{parent_id}_{j}"
            child["id"] = cid
            _assign_ids_children(child, cid)

    # bare hook children
    if seg.get("type") == "hook" and "segments" in seg:
        kids = seg["segments"]
        for j, child in enumerate(kids, start=1):
            cid = f"{parent_id}_{j}"
            child["id"] = cid
            _assign_ids_children(child, cid)


# =============================================================================
# Passage extraction
# =============================================================================
PASSAGE_RE = re.compile(
    r"<tw-passagedata(?P<attrs>[^>]*)>(?P<body>.*?)</tw-passagedata>",
    re.DOTALL | re.IGNORECASE,
)

def extract_passages(html_text: str) -> Dict[str, Dict[str, Any]]:
    """
    Extract and tokenize all <tw-passagedata> blocks (within <tw-storydata> if present).
    Returns dict keyed by passage name.
    """
    out: Dict[str, Dict[str, Any]] = {}

    # Restrict to story element if present
    story_match = re.search(
        r"<tw-storydata[^>]*>(?P<story>.*)</tw-storydata>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    story_text = story_match.group("story") if story_match else html_text

    for m in PASSAGE_RE.finditer(story_text):
        attrs_raw = m.group("attrs")
        body_raw = m.group("body")

        attrs = parse_attrs(attrs_raw)
        body = html.unescape(body_raw)  # CRITICAL: decode Twine-escaped content

        name = attrs.get("name") or f"pid_{attrs.get('pid','?')}"
        pid = int(attrs.get("pid", "0") or 0)
        tags = attrs.get("tags", "")
        position = attrs.get("position")
        size = attrs.get("size")

        segs = tokenize_recursive(body)
        assign_ids_top_level(segs)

        out[name] = {
            "meta": {
                "pid": pid,
                "tags": tags,
                "position": position,
                "size": size,
                "hash": sha1(body),  # hash of full unescaped passage
            },
            "segments": segs,
        }

    return out


# =============================================================================
# Filtering support (--name)
# =============================================================================
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


def filter_passages(all_passages: Dict[str, Dict[str, Any]], wanted: Optional[Set[str]]) -> Dict[str, Dict[str, Any]]:
    if wanted is None:
        return all_passages
    return {k: v for k, v in all_passages.items() if k in wanted}


# =============================================================================
# CLI
# =============================================================================
def cli():
    ap = argparse.ArgumentParser(
        description="Extract Twine Harlowe passages into structured JSON (recursive, strict macro)."
    )
    ap.add_argument("html", nargs="?", help="Input Twine story HTML")
    ap.add_argument("out", nargs="?", help="Output JSON (default: stdout)")
    ap.add_argument("--demo", help="Use this HTML snippet file instead of positional path")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default 2; 0=minified)")
    ap.add_argument(
        "--name",
        action="append",
        help="Limit output to one or more passage names. Repeatable or comma-separated.",
    )
    args = ap.parse_args()

    if args.demo:
        html_text = open(args.demo, "r", encoding="utf-8").read()
    else:
        if not args.html:
            ap.error("Must supply story HTML path or use --demo FILE.")
        html_text = open(args.html, "r", encoding="utf-8").read()

    data = extract_passages(html_text)

    wanted = normalize_name_filters(args.name)
    if wanted is not None:
        filtered = filter_passages(data, wanted)
        missing = wanted.difference(filtered.keys())
        if missing:
            print(f"[WARN] Passage(s) not found: {', '.join(sorted(missing))}", file=sys.stderr)
        data = filtered

    js = json.dumps(data, ensure_ascii=False, indent=args.indent if args.indent > 0 else None)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(js)
    else:
        print(js)


# =============================================================================
# Main
# =============================================================================
if __name__ == "__main__":
    cli()
