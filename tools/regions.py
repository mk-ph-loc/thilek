"""Θέση κάθε ερωτήματος μέσα στο PDF (σελίδα, y, x σε σημεία PDF), ώστε να κόβονται εικόνες ερωτημάτων για τα διαγωνίσματα."""
import re, subprocess, xml.etree.ElementTree as ET
from classify import norm

NUM = re.compile(r'^(\d\.\d(?:\.\d+)?\.?|\d\))$')     # 2.1  2.1.  2.2.1  1)
TOP, BOTTOM = 50.0, 50.0                              # περιθώρια σελίδας (pt) για ερώτημα που συνεχίζεται σε άλλη σελίδα

def pdf_lines(pdf):
    """[(page_no, page_w, page_h, [ {x0,y0,x1,y1,words:[(text,x0,y0,x1,y1)]} ])]"""
    xml = subprocess.run(['pdftotext', '-bbox-layout', str(pdf), '-'], capture_output=True, text=True, timeout=120).stdout
    root = ET.fromstring(xml.split('<!DOCTYPE', 1)[0] + xml.split('>', 1)[1] if xml.startswith('<?xml') else re.sub(r'<!DOCTYPE[^>]*>', '', xml, count=1))
    ns = '{http://www.w3.org/1999/xhtml}'; out = []
    for n, pg in enumerate(root.iter(ns + 'page'), 1):
        lines = []
        for ln in pg.iter(ns + 'line'):
            ws = [(w.text or '', float(w.get('xMin')), float(w.get('yMin')), float(w.get('xMax')), float(w.get('yMax'))) for w in ln.iter(ns + 'word')]
            if ws: lines.append({'x0': float(ln.get('xMin')), 'y0': float(ln.get('yMin')), 'x1': float(ln.get('xMax')), 'y1': float(ln.get('yMax')), 'words': ws})
        out.append((n, float(pg.get('width')), float(pg.get('height')), lines))
    return out

def _key(text):
    for ln in (text or '').splitlines():
        t = [norm(x) for x in ln.split()]
        if t: return t[:3]
    return []

def compute(pdf, qs):
    """Επιστρέφει λίστα (ίδιου μήκους με qs) με {'regions': [...], 'mask': [p,x0,y0,x1,y1]|None} ή None όπου δεν βρέθηκε η αρχή του ερωτήματος."""
    pages = pdf_lines(pdf)
    if not pages or not qs: return [None] * len(qs)
    flat = [(pi, li) for pi, p in enumerate(pages) for li in range(len(p[3]))]
    starts, cur = [], 0
    for q in qs:
        k = _key(q['text']); found = None
        for j in range(cur, len(flat)):
            pi, li = flat[j]; toks = [norm(w[0]) for w in pages[pi][3][li]['words']][:len(k)]
            if k and toks == k: found = j; break
        starts.append(found)
        if found is not None: cur = found + 1
    allx0 = min(l['x0'] for p in pages for l in p[3]) - 6; allx1 = max(l['x1'] for p in pages for l in p[3]) + 6
    res = []
    for k, q in enumerate(qs):
        s = starts[k]
        if s is None: res.append(None); continue
        pi, li = flat[s]; ln = pages[pi][3][li]; y_start = ln['y0'] - 3
        nxt = next((starts[m] for m in range(k + 1, len(qs)) if starts[m] is not None), None)
        if nxt is not None: pj, lj = flat[nxt]; y_end = pages[pj][3][lj]['y0'] - 3
        else: pj = len(pages) - 1; y_end = min(pages[pj][2] - BOTTOM, max((l['y1'] for l in pages[pj][3]), default=0) + 8)
        regs = []
        for p in range(pi, pj + 1):
            w, h = pages[p][1], pages[p][2]
            a = y_start if p == pi else TOP; b = y_end if p == pj else h - BOTTOM
            if b - a > 4: regs.append({'p': pages[p][0], 'x0': max(0.0, allx0), 'x1': min(w, allx1), 'y0': max(0.0, a), 'y1': min(h, b)})
        first = ln['words'][0]
        mask = [pages[pi][0], first[1] - 1.5, first[2] - 1.5, first[3] + 1.5, first[4] + 1.5] if NUM.match(first[0]) else None
        res.append({'regions': regs, 'mask': mask} if regs else None)
    return res
