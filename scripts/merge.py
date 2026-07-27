#!/usr/bin/env python3
"""Merge out/chunk*.json into papers.json and report problems.

Usage: cd /home/claude/work && python3 merge.py
"""
import json, glob, os, sys

papers = []
files = sorted(glob.glob("out/chunk*.json"))
if not files:
    sys.exit("no out/chunk*.json found")
for f in files:
    try:
        papers += json.load(open(f))
    except Exception as e:
        print("BAD_JSON", f, e)

seen, uniq = set(), []
for p in papers:
    if p.get("id") in seen:
        continue
    seen.add(p["id"])
    uniq.append(p)
uniq.sort(key=lambda p: p["id"])

problems = 0
for p in uniq:
    miss = [k for k in ("title", "authors", "categories", "abstract", "abstract_ko")
            if not p.get(k)]
    if miss:
        print("MISSING", p["id"], miss); problems += 1
    elif len(p["abstract_ko"]) < 0.4 * len(p["abstract"]):
        print("SHORT_KO", p["id"], len(p["abstract"]), "->", len(p["abstract_ko"])); problems += 1

json.dump(uniq, open("papers.json", "w"), ensure_ascii=False, indent=1)
print(f"merged {len(files)} chunks -> papers.json : {len(uniq)} papers, {problems} problems")
