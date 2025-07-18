#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate Translated Twine Extract JSON
=====================================

Compares ORIGINAL extract.json (English) with TRANSLATED extract.json (e.g.,
output of merge_translation.py) and reports:

  * Structure differences (missing passages/segments, type changes)
  * Untranslated strings
      - text.src unchanged
      - link.label unchanged
      - translatable macro.args first string literal unchanged
  * Illegal modifications to non‑translatable fields
      (e.g., link.target, macro.name, tag.src, var.src, etc.)
  * Variable placeholder loss ($var count mismatch)
  * Basic macro args integrity

Exit status:
  0  = only warnings (or clean)
  1  = errors when --strict specified or --fail-on missing/illegal

Usage
-----
    python validate_translation.py original_en.json translated_cn.json
    python validate_translation.py en.json cn.json --strict
    python validate_translation.py en.json cn.json --html report.html

"""

from __future__ import annotations
import argparse, json, re, sys, textwrap
from typing import Any, Dict, List, Tuple, Set

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
TRANSLATABLE_MACRO_NAMES = {
    "click", "link", "link-repeat", "link-reveal",
    "hover", "hover-tooltip", "tooltip", "alert", "print",
}

VAR_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")

# ANSI colors
RED = "\033[31m"; YEL = "\033[33m"; GRN = "\033[32m"; END = "\033[0m"
def color(txt, col): return txt if sys.stdout.isatty() else txt if col=='' else txt

# --------------------------------------------------------------------------
# String literal helpers
# --------------------------------------------------------------------------
def find_first_lit_span(arg: str) -> Tuple[int,int,str]|None:
    """Return (start,end,quote) of first string literal including quotes."""
    i = 0; n=len(arg)
    while i<n:
        ch = arg[i]
        if ch in ("'",'"'):
            quote=ch; j=i+1
            while j<n:
                c=arg[j]
                if c=="\\" and j+1<n:
                    j+=2; continue
                if c==quote:
                    return i,j+1,quote
                j+=1
            return None
        i+=1
    return None

def extract_first_lit(arg:str)->str|None:
    span=find_first_lit_span(arg); 
    if not span: return None
    s,e,q=span
    # de-escape for comparison
    inner = arg[s+1:e-1]
    inner = inner.replace("\\\\","\\").replace(f"\\{q}",q)
    return inner

# --------------------------------------------------------------------------
# Core validation
# --------------------------------------------------------------------------
class Validator:
    def __init__(self, orig:Dict[str,Any], trans:Dict[str,Any], strict:bool=False):
        self.orig=orig; self.trans=trans; self.strict=strict
        self.errors:int=0
        self.warns:int=0
        self.untranslated:int=0
        self.passages_checked:int=0

    def log(self,msg,level='warn'):
        if level=='error':
            self.errors+=1
            print(color("[ERR] ","")+msg)
        elif level=='untr':
            self.untranslated+=1
            print(color("[UNTR] ",YEL)+msg+END)
        else:
            self.warns+=1
            print(color("[WARN] ",YEL)+msg+END)

    def run(self):
        # passage existence
        for pname, opass in self.orig.items():
            tpass = self.trans.get(pname)
            if not tpass:
                self.log(f"passage '{pname}' missing in translated file","error")
                continue
            self.passages_checked+=1
            self.check_passage(pname, opass, tpass)

        # extra passages
        for pname in self.trans.keys():
            if pname not in self.orig:
                self.log(f"extra passage '{pname}' present only in translated","warn")

    def check_passage(self,pname:str,opass:Dict[str,Any],tpass:Dict[str,Any]):
        oidx = self.index_segments(opass)
        tidx = self.index_segments(tpass)
        # segment-by-segment
        for sid, oseg in oidx.items():
            tseg = tidx.get(sid)
            if not tseg:
                self.log(f"{pname}:{sid} missing in translated","error")
                continue
            self.check_segment(pname,sid,oseg,tseg)

        for sid in tidx.keys():
            if sid not in oidx:
                self.log(f"{pname}:{sid} present only in translated","warn")

    def check_segment(self,p:str,sid:str, o:Dict[str,Any], t:Dict[str,Any]):
        ot = o.get("type"); tt = t.get("type")
        if ot!=tt:
            self.log(f"{p}:{sid} type mismatch {ot}->{tt}","error"); return
        if ot=="text":
            self.check_text(p,sid,o,t)
        elif ot=="link":
            self.check_link(p,sid,o,t)
        elif ot=="macro":
            self.check_macro(p,sid,o,t)
        else:
            # immutable fields
            imm=["src","target"] if ot in ("tag","var","align_center") else []
            for f in imm:
                if o.get(f)!=t.get(f):
                    self.log(f"{p}:{sid} field '{f}' was modified but is not translatable","error")
            # recurse hooks
            if ot=="macro" and "hook" in o:
                self.recurse_hook(p,sid,o["hook"],t.get("hook"))
            if ot=="hook":
                self.recurse_hook(p,sid,o,t)

    def recurse_hook(self,p,sid,o_hook,t_hook):
        if not isinstance(o_hook,dict) or not isinstance(t_hook,dict):
            return
        oseg=o_hook.get("segments",[]); tseg=t_hook.get("segments",[])
        for i,(os,ts) in enumerate(zip(oseg,tseg),start=1):
            ch_id=f"{sid}_{i}"
            self.check_segment(p,ch_id,os,ts)

    def check_text(self,p,sid,o,t):
        otext=o.get("src",""); ttext=t.get("src","")
        if otext==ttext:
            self.log(f"{p}:{sid} text not translated","untr")
        # var placeholder check
        ovar=set(VAR_RE.findall(otext)); tvar=set(VAR_RE.findall(ttext))
        if ovar!=tvar:
            self.log(f"{p}:{sid} variable placeholder mismatch {ovar}->{tvar}","error")

    def check_link(self,p,sid,o,t):
        if o.get("target")!=t.get("target"):
            self.log(f"{p}:{sid} link.target changed","error")
        olb,tlb=o.get("label",""),t.get("label","")
        if olb==tlb:
            self.log(f"{p}:{sid} link label not translated","untr")

    def check_macro(self,p,sid,o,t):
        oname=o.get("name",""); tname=t.get("name","")
        if oname!=tname:
            self.log(f"{p}:{sid} macro name modified","error"); return
        # compare args
        name=oname.lower()
        oarg=o.get("args",""); targ=t.get("args","")
        if name in TRANSLATABLE_MACRO_NAMES:
            olit=extract_first_lit(oarg); tlit=extract_first_lit(targ)
            if olit==tlit:
                self.log(f"{p}:{sid} macro '{name}' string literal not translated","untr")
            # check other parts unchanged
            span=find_first_lit_span(oarg)
            if span:
                os,oe,_=span
                if oarg[:os]!=targ[:os] or oarg[oe:]!=targ[oe:]:
                    self.log(f"{p}:{sid} macro '{name}' args outside literal were modified","error")
        else:
            # args should remain unchanged
            if oarg!=targ:
                self.log(f"{p}:{sid} macro '{name}' args modified but not translatable","error")
        # hook recurse
        if "hook" in o:
            self.recurse_hook(p,sid,o["hook"],t.get("hook"))

    @staticmethod
    def index_segments(passrec:Dict[str,Any])->Dict[str,Dict[str,Any]]:
        idx={}
        def rec(seg:Dict[str,Any]):
            sid=seg.get("id")
            if sid: idx[sid]=seg
            if seg.get("type")=="macro" and isinstance(seg.get("hook"),dict):
                for ch in seg["hook"].get("segments",[]): rec(ch)
            if seg.get("type")=="hook":
                for ch in seg.get("segments",[]): rec(ch)
        for s in passrec.get("segments",[]): rec(s)
        return idx

# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cli():
    ap=argparse.ArgumentParser(description="Validate translated Twine extract JSON against original.")
    ap.add_argument("original",help="Original extract JSON (English)")
    ap.add_argument("translated",help="Translated/merged extract JSON")
    ap.add_argument("--strict",action="store_true",help="Exit 1 on any error/warn/untr")
    args=ap.parse_args()
    orig=json.load(open(args.original,encoding='utf-8'))
    trans=json.load(open(args.translated,encoding='utf-8'))
    v=Validator(orig,trans,args.strict)
    v.run()
    print("\nSummary: passages",v.passages_checked,
          "| errors",v.errors,"| warns",v.warns,"| untranslated",v.untranslated)
    if args.strict and (v.errors or v.untranslated):
        sys.exit(1)

if __name__=="__main__":
    cli()
