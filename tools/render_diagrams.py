#!/usr/bin/env python3
"""Προ-αποδίδει τα διαγράμματα Mermaid των εγχειριδίων (app/manual*.md) σε SVG στο app/diagrams/<hash>.svg.
Χρήση (στον υπολογιστή ανάπτυξης, χρειάζεται Chrome/Chromium):  python tools/render_diagrams.py
Ο server σε λειτουργία «Έτοιμο SVG» (/settings) τα εμφανίζει χωρίς JavaScript· όπου λείπει SVG πέφτει στο τοπικό Mermaid.
Μετά από αλλαγή στο κείμενο ενός διαγράμματος ξανατρέξε το script (το όνομα του αρχείου είναι hash του κειμένου)."""
import html, json, os, pathlib, re, shutil, subprocess, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import mdrich

def chrome():
    for n in (os.environ.get('THILEK_CHROME'), 'google-chrome', 'chromium', 'chromium-browser', 'chrome'):
        if n and shutil.which(n): return shutil.which(n)
    sys.exit('Δεν βρέθηκε Chrome/Chromium (όρισε THILEK_CHROME).')

def main():
    srcs = {}
    for f in sorted((ROOT / 'app').glob('manual*.md')):
        for s in mdrich.diagram_sources(f.read_text(encoding='utf-8')): srcs[mdrich.diagram_hash(s)] = s.strip()
    if not srcs: print('Κανένα διάγραμμα.'); return
    mjs = (ROOT / 'app' / 'static' / 'vendor' / 'mermaid' / 'mermaid.min.js').resolve()
    page = ("<!doctype html><meta charset=utf-8><body><script src='file://%s'></script><script>"
            "mermaid.initialize({startOnLoad:false,theme:'default',securityLevel:'strict',flowchart:{htmlLabels:false},sequence:{useMaxWidth:true}});"
            "var S=%s;(async function(){for(const h of Object.keys(S)){var t=document.createElement('textarea');t.id='o'+h;"
            "try{const r=await mermaid.render('m'+h,S[h]);t.textContent=r.svg}catch(e){t.textContent='ERR '+e}document.body.appendChild(t)}document.title='done'})();</script>") % (mjs, json.dumps(srcs))
    out = ROOT / 'app' / 'diagrams'; out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        hp = pathlib.Path(td) / 'h.html'; hp.write_text(page, encoding='utf-8')
        r = subprocess.run([chrome(), '--headless=new', '--no-sandbox', '--disable-gpu', '--virtual-time-budget=60000', '--allow-file-access-from-files', '--dump-dom', f'file://{hp}'], capture_output=True, text=True, timeout=180)
    ok = 0; keep = set()
    for h in srcs:
        m = re.search(r'<textarea id="o%s"[^>]*>(.*?)</textarea>' % h, r.stdout, re.S)
        svg = html.unescape(m.group(1)) if m else ''
        if not svg.startswith('<svg'): print('ΑΠΟΤΥΧΙΑ', h, svg[:200] or '(χωρίς έξοδο)'); continue
        (out / f'{h}.svg').write_text(svg, encoding='utf-8'); keep.add(f'{h}.svg'); ok += 1
    for f in out.glob('*.svg'):
        if f.name not in keep and f.stem in srcs: continue
        if f.stem not in srcs: f.unlink(); print('διαγράφηκε παλιό', f.name)
    print(f'{ok}/{len(srcs)} διαγράμματα → {out}')
    if ok != len(srcs): sys.exit(1)

if __name__ == '__main__': main()
