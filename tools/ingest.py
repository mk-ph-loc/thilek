#!/usr/bin/env python3
"""Split IEP TTDD PDFs into questions. Reads <course>/04_TRAPEZA/orig/<ID>.pdf + <ID>_SOLUTION.pdf,
writes <course>/04_TRAPEZA/derived/<ID>/item.json and manifest.csv. Originals are never modified."""
import re, json, csv, hashlib, subprocess, pathlib, openpyxl, classify, regions

THEME = re.compile(r'[Θθ][έΕεΈ][Μμ][Αα]\s*(\d)')   # «ΘΕΜΑ 2» και «Θέμα 2ο»
H_DOT = re.compile(r'^[ \t]*(\d)\.(\d)(?:\.(\d+))?\.?(?:[ \t]+(?=\S)|[ \t]*$)', re.M)   # 2.1  2.1.  2.2.1
H_PAR = re.compile(r'^[ \t]*(\d)\)[ \t]+(?=\S)', re.M)                       # 1)  2)
PTS = re.compile(r'Μον(?:άδες|\.)\s*:?\s*(\d+)', re.I)                          # Μονάδες 5 / Μονάδες: 04
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def text(p): return subprocess.run(['pdftotext', '-layout', str(p), '-'], capture_output=True, text=True).stdout

THEME_POINTS = 25
def pts_values(body): return [int(x) for x in PTS.findall(body)]
def points_from(v):
    if not v: return None
    if len(v) >= 3 and v[-1] == sum(v[:-1]): return v[-1]      # τα μέρη ακολουθούνται από σύνολο
    return sum(v)

def split_questions(t):
    """Questions with points = sum of every 'Μονάδες N' inside the block. Handles 2.1 / 2.1. / 2.2.1 / 1) / no numbering."""
    tm = THEME.search(t); theme = tm.group(1) if tm else '0'
    heads = [(m.start(), f'{m.group(1)}.{m.group(2)}' + (f'.{m.group(3)}' if m.group(3) else '')) for m in H_DOT.finditer(t)]
    if tm: heads = [h for h in heads if h[1].split('.')[0] == theme]   # π.χ. γραμμή «5.5 V» μέσα στο Θέμα 2 δεν είναι ερώτημα
    if not heads: heads = [(m.start(), f'{theme}.{m.group(1)}') for m in H_PAR.finditer(t)]
    if not heads:
        return [{'code': f'{theme}.0', 'points': points_from(pts_values(t)), 'text': t.strip()}] if t.strip() else []
    out = []
    for i, (pos, code) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(t)
        body = t[pos:end].strip()
        out.append({'code': code, 'vals': pts_values(body), 'text': body})
    # γενικό «Μονάδες 25» στο τέλος του θέματος: δεν ανήκει στο τελευταίο ερώτημα
    if sum(points_from(q['vals']) or 0 for q in out) > THEME_POINTS and out[-1]['vals'] and out[-1]['vals'][-1] == THEME_POINTS and len(out) > 1:
        out[-1]['vals'] = out[-1]['vals'][:-1]
    for q in out: q['points'] = points_from(q.pop('vals'))
    seen = {}
    for q in out:
        n = seen.get(q['code'], 0); seen[q['code']] = n + 1
        if n: q['code'] += '_' + 'bcdefgh'[min(n - 1, 6)]; q['dup'] = True
    return out

def solution_status(e, s):
    if not s.exists(): return 'no_solution'
    if sha(s) == sha(e): return 'solution_identical_to_statement'
    ts = text(s).lower()
    if 'ενδεικτικ' not in ts and 'απαντ' not in ts: return 'solution_unrecognised'
    return 'ok'

def run(course_dir, xlsx):
    course = pathlib.Path(course_dir); tt = course / '04_TRAPEZA'; orig = tt / 'orig'; der = tt / 'derived'
    der.mkdir(parents=True, exist_ok=True)
    meta = {}
    for r in openpyxl.load_workbook(xlsx)['Θέματα'].iter_rows(min_row=5, values_only=True):
        if r[0]: meta[str(r[0])] = {'date': r[1].date().isoformat() if r[1] else None, 'theme': r[2], 'yli': r[8], 'chapter': r[9]}
    ids = sorted({re.match(r'(\d+)', f.name).group(1) for f in orig.glob('*.pdf')}, key=int)
    rows, warn = [], []
    for i in ids:
        e, s = orig / f'{i}.pdf', orig / f'{i}_SOLUTION.pdf'
        if not e.exists(): warn.append(f'{i}: λείπει η εκφώνηση'); continue
        te = text(e)
        if len(te.strip()) < 40: warn.append(f'{i}: χωρίς κείμενο στο PDF (σαρωμένο;) — χρειάζεται OCR'); qs = []
        else: qs = classify.annotate(split_questions(te), te, classify.image_pages(e))
        st = solution_status(e, s)
        try:
            for q, r in zip(qs, regions.compute(e, qs)): q['geo'] = r
            if qs and any(q.get('geo') is None for q in qs): warn.append(f'{i}: δεν βρέθηκε η θέση κάποιου ερωτήματος στο PDF (δεν θα κόβεται εικόνα)')
            if qs and st == 'ok':                                    # θέσεις και κείμενο στη λύση, μόνο αν υπάρχουν όλοι οι κωδικοί
                sqs = split_questions(text(s)); byc = {q['code']: g for q, g in zip(sqs, regions.compute(s, sqs))}; stx = {q['code']: q['text'] for q in sqs}
                if all(q['code'] in byc and byc[q['code']] for q in qs):
                    for q in qs: q['sol_geo'] = byc[q['code']]
                for q in qs:
                    if q['code'] in stx: q['sol_text'] = stx[q['code']]
        except Exception as ex: warn.append(f'{i}: αποτυχία υπολογισμού θέσεων ({type(ex).__name__})')
        total = sum(q['points'] or 0 for q in qs)
        if any(q.get('dup') for q in qs): warn.append(f'{i}: διπλός κωδικός ερωτήματος (μετονομάστηκε _b…) — έλεγξε χειροκίνητα')
        if qs and total != 25: warn.append(f'{i}: άθροισμα μονάδων {total} ≠ 25 ({[q["code"]+":"+str(q["points"]) for q in qs]})')
        if i not in meta: warn.append(f'{i}: δεν υπάρχει στο Excel του ΙΕΠ')
        m = meta.get(i, {}); d = der / i; d.mkdir(exist_ok=True)
        (d / 'item.json').write_text(json.dumps({'id': i, 'source': 'TTDD', 'course': course.name, **m, 'solution_status': st, 'questions': qs}, ensure_ascii=False, indent=1), encoding='utf-8')
        rows.append([i, m.get('theme'), m.get('yli'), m.get('chapter'), len(qs), total, st, sha(e), sha(s) if s.exists() else ''])
    for i in sorted(set(meta) - set(ids), key=int): warn.append(f'{i}: υπάρχει στο Excel αλλά όχι στο orig/')
    with open(tt / 'manifest.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['id', 'theme', 'yli', 'chapter', 'n_questions', 'points_total', 'solution_status', 'sha256_statement', 'sha256_solution']); w.writerows(rows)
    (tt / 'ingest_warnings.txt').write_text('\n'.join(warn), encoding='utf-8')
    return rows, warn

if __name__ == '__main__':
    import sys
    rows, warn = run(sys.argv[1], sys.argv[2]); print(len(rows), 'θέματα,', len(warn), 'προειδοποιήσεις'); print('\n'.join(warn[:40]))
