#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render Localized Twine Passages from Extract JSON
=================================================

Given a *merged* extract JSON (after translations were merged), produce:

1. A mapping JSON: passage_name -> HTML-entity-escaped Harlowe source
   (default; ready to inject into <tw-passagedata>.textContent in userscript).
2. Optionally raw (unescaped) Harlowe source via --raw (--format rawjson).
3. Optional full HTML wrapper (experimental) via --format html (not default).

Rendering Rules
---------------
Segments are recursively rendered:

  text           -> seg["src"]
  link           -> [[{label}->{target}]] or [[{label}]]
  macro          -> (name: args) + rendered hook children if present
  hook           -> [ ...children... ]
  tag            -> seg["src"] (HTML tag literal)
  var            -> seg["src"]
  align_center   -> =><=
  other          -> seg.get("src","")

After concatenating the passage raw string, we HTML-escape it so it can safely
replace the contents of <tw-passagedata>. Twine exports entity-escaped story
data, so we mimic that encoding.

Escaping (order matters):
  & -> &amp;
  < -> &lt;
  > -> &gt;
  " -> &quot;
  ' -> &#39;

Usage
-----
    python render_translation.py extract_cn.json -o translations_escaped.json

    # Only for specific passage(s):
    python render_translation.py extract_cn.json --name Startup --name Wake

    # Produce raw (unescaped) Harlowe source mapping:
    python render_translation.py extract_cn.json --raw -o translations_raw.json

    # Produce an entire localized HTML (experimental):
    python render_translation.py extract_cn.json --base-html story.html --format html -o story_cn.html

"""

from __future__ import annotations
import argparse, json, sys
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Minimal HTML escaping (Twine-style)
# ---------------------------------------------------------------------------
def html_escape_for_passagedata(text: str) -> str:
    """Escape Harlowe source so it can be safely embedded in <tw-passagedata>."""
    # IMPORTANT: order matters: ampersand first
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&#39;")
    return text

# ---------------------------------------------------------------------------
# Rendering of segments (recursive)
# ---------------------------------------------------------------------------
def render_segment(seg: Dict[str, Any]) -> str:
    st = seg.get("type")
    if st == "text":
        return seg.get("src", "")

    if st == "link":
        label = seg.get("label", "")
        target = seg.get("target")
        if target is None or target == "":
            return f"[[{label}]]"
        return f"[[{label}->{target}]]"

    if st == "macro":
        name = seg.get("name", "")
        args = seg.get("args", "")
        head = f"({name}: {args})"
        if "hook" in seg and isinstance(seg["hook"], dict):
            return head + render_hook_obj(seg["hook"])
        return head

    if st == "hook":
        # bare hook segment
        return "[" + render_segments(seg.get("segments", [])) + "]"

    if st == "tag":
        # raw HTML as embedded literal
        return seg.get("src", "")

    if st == "var":
        return seg.get("src", "")

    if st == "align_center":
        return "=><="

    # unknown fallback
    return seg.get("src", "")

def render_hook_obj(hook: Dict[str, Any]) -> str:
    return "[" + render_segments(hook.get("segments", [])) + "]"

def render_segments(seglist: List[Dict[str, Any]]) -> str:
    return "".join(render_segment(s) for s in seglist)

# ---------------------------------------------------------------------------
# Passage rendering
# ---------------------------------------------------------------------------
def render_passage(passage: Dict[str, Any]) -> str:
    segs = passage.get("segments", [])
    return render_segments(segs)

# ---------------------------------------------------------------------------
# Passage filtering
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# HTML injection (optional full rebuild)
# ---------------------------------------------------------------------------
def inject_translations_into_html(base_html: str, translations_escaped: Dict[str, str]) -> str:
    """
    Experimental: given the *full* original story HTML text and a mapping of
    passage name -> escaped source, replace <tw-passagedata> inner text.

    NOTE: This is a naive regex-based replacement; if your story is huge and
    includes nested markup or identical names inside comments, consider using
    an HTML parser. For production, you'd likely do a DOM parse.

    We match <tw-passagedata ... name="...">...</tw-passagedata> and replace body.
    """
    import re, html as html_mod

    def repl(match):
        attrs_raw = match.group("attrs")
        body_raw = match.group("body")
        # parse minimal attrs to get name
        name = None
        for k, v in re.findall(r'(\w+)\s*=\s*"(.*?)"', attrs_raw):
            if k == "name":
                name = html_mod.unescape(v)
                break
        if name and name in translations_escaped:
            return f"<tw-passagedata{attrs_raw}>{translations_escaped[name]}</tw-passagedata>"
        else:
            return match.group(0)

    PASSAGE_RE = re.compile(
        r"<tw-passagedata(?P<attrs>[^>]*)>(?P<body>.*?)</tw-passagedata>",
        re.DOTALL | re.IGNORECASE,
    )
    return PASSAGE_RE.sub(repl, base_html)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cli():
    ap = argparse.ArgumentParser(
        description="Render localized Twine passages from merged extract JSON."
    )
    ap.add_argument("extract_json", help="Merged extract JSON (after translations).")
    ap.add_argument("-o", "--out", help="Output file (default stdout).")
    ap.add_argument(
        "--name",
        action="append",
        help="Limit to passage name(s); repeatable or comma-separated."
    )
    ap.add_argument(
        "--raw",
        action="store_true",
        help="Output raw (UNescaped) mapping JSON (passage_name -> raw Harlowe source)."
    )
    ap.add_argument(
        "--format",
        choices=["json", "rawjson", "html"],
        default="json",
        help="Output format: json (escaped mapping), rawjson (same as --raw), html (inject into --base-html)."
    )
    ap.add_argument(
        "--base-html",
        help="Required when --format html: original Twine HTML file to patch."
    )
    ap.add_argument(
        "--indent", type=int, default=2, help="JSON indent (default 2; 0=minified)"
    )
    args = ap.parse_args()

    # If user gave --raw, override format
    if args.raw:
        args.format = "rawjson"

    data = json.load(open(args.extract_json, "r", encoding="utf-8"))

    wanted = normalize_name_filters(args.name)
    data = filter_passages(data, wanted)

    # Render all passages
    raw_map: Dict[str, str] = {}
    esc_map: Dict[str, str] = {}
    for pname, prec in data.items():
        raw_src = render_passage(prec)
        raw_map[pname] = raw_src
        esc_map[pname] = html_escape_for_passagedata(raw_src)

    if args.format == "rawjson":
        out_obj = raw_map
        js = json.dumps(out_obj, ensure_ascii=False, indent=args.indent if args.indent > 0 else None)

    elif args.format == "html":
        if not args.base_html:
            print("--format html requires --base-html ORIGINAL_STORY.html", file=sys.stderr)
            sys.exit(1)
        base_html_text = open(args.base_html, "r", encoding="utf-8").read()
        patched = inject_translations_into_html(base_html_text, esc_map)
        js = patched  # not JSON; raw HTML output
    else:  # "json"
        out_obj = esc_map
        js = json.dumps(out_obj, ensure_ascii=False, indent=args.indent if args.indent > 0 else None)

    if args.out:
        mode = "w"
        enc = "utf-8"
        with open(args.out, mode, encoding=enc) as f:
            f.write(js)
    else:
        print(js)

if __name__ == "__main__":
    cli()
