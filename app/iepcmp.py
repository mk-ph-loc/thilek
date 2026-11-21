"""0.25: σύγκριση των δικών σου απαντήσεων (στοιχεία quiz των λύσεων εκπαιδευτικού) με την τελική απάντηση της λύσης ΙΕΠ (κείμενο λύσης του ερωτήματος).
Συγκρίνονται: Σωστό/Λάθος (ανά γράμμα α, β…), πολλαπλής επιλογής (γράμμα) και αριθμητικές απαντήσεις. Τα υπόλοιπα είναι «δεν συγκρίνεται».
Αποτελέσματα και χειροκίνητες αλλαγές αποθηκεύονται στον πίνακα iepcmp (δεδομένα χρήστη, διατηρούνται στο rebuild)."""
import csv, datetime, html, io, re
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from . import qsol
from .main_auth import auth
from .quizgen import LET, tf_answers, mcq_answer
from .review import db, page, same_origin

router = APIRouter()
E = html.escape
STATUS = (('agrees', 'συμφωνεί'), ('differs', 'διαφέρει'), ('check', 'να ελεγχθεί'), ('na', 'δεν συγκρίνεται'))
SKEYS = tuple(k for k, _ in STATUS)
NUM = re.compile(r'(?<![\w.,])-?\d+(?:[.,]\d+)?')


def nums(text):
    out = []
    for m in NUM.finditer(text or ''):
        try: out.append((float(m.group(0).replace(',', '.')), m.start()))
        except ValueError: pass
    return out


def compare_row(r, sol_text):
    """r: γραμμή qsolution· sol_text: κείμενο λύσης ΙΕΠ του ερωτήματος. -> λίστα dict {qn, kind, mine, iep, auto, note} για κάθε έγκυρο στοιχείο quiz."""
    out = []; items = [q for q in r['quiz'] if not q['err']]; tfs = tf_answers(sol_text); tf_items = [q for q in items if q['type'] == 'true_false']
    letters = [l for l in LET if l in tfs]
    seq_ok = len(tf_items) == len(letters) and len(letters) > 0; ti = 0
    for q in items:
        t = q['type']; d = {'qn': q['n'], 'kind': t, 'mine': '', 'iep': '', 'auto': 'na', 'note': ''}
        if t == 'true_false':
            mine = 'Σωστό' if q['answer'] else 'Λάθος'; d['mine'] = mine; let = q.get('part') or (letters[ti] if seq_ok and ti < len(letters) else '')
            ti += 1
            if let and let in tfs: d['iep'] = f'{let}: {tfs[let]}'; d['auto'] = 'agrees' if tfs[let] == mine else 'differs'
            else: d['note'] = 'δεν βρέθηκε αντιστοίχιση με γράμμα της λύσης ΙΕΠ (πρόσθεσε part: "α" στο στοιχείο)' if not q.get('part') else f'το γράμμα {q.get("part")} δεν υπάρχει στη λύση ΙΕΠ'
        elif t == 'mcq':
            d['mine'] = f"{LET[q['answer']]}: {q['options'][q['answer']]}"[:80] if q['answer'] < len(LET) else str(q['answer'])
            ia = mcq_answer(sol_text, len(q['options']))
            if ia is None: d['note'] = 'δεν εντοπίστηκε ένα μόνο γράμμα απάντησης στη λύση ΙΕΠ'
            else: d['iep'] = LET[int(ia)]; d['auto'] = 'agrees' if int(ia) == q['answer'] else 'differs'
        elif t == 'numeric':
            v = float(q['answer']); d['mine'] = f"{v:g}" + (f" {q.get('unit')}" if q.get('unit') else ''); tol = max(float(q.get('tolerance') or 0), abs(v) * 0.005, 1e-9)
            found = [(x, p) for x, p in nums(sol_text) if abs(x - v) <= tol]; end = len(sol_text or '') - 200
            if not found: d['auto'] = 'check'; d['note'] = 'ο αριθμός δεν βρέθηκε στο κείμενο της λύσης ΙΕΠ (άλλη μορφή, μονάδα ή τύπος;)'
            elif any(p >= end for _, p in found): d['auto'] = 'agrees'; d['iep'] = f'{found[-1][0]:g} (στο τέλος της λύσης)'
            else: d['auto'] = 'check'; d['iep'] = f'{found[0][0]:g} (στη μέση της λύσης)'; d['note'] = 'ο αριθμός υπάρχει στη λύση ΙΕΠ αλλά όχι στο τέλος· δεν είναι βέβαιο ότι είναι η τελική απάντηση'
        else: d['note'] = 'ο τύπος δεν συγκρίνεται αυτόματα'; d['mine'] = str(q.get('answer') if not isinstance(q.get('answer'), list) else ' | '.join(map(str, q['answer'])))[:80]
        out.append(d)
    return out


def refresh(c, keys=None):
    """Υπολογίζει και αποθηκεύει τις συγκρίσεις (όλων των λύσεων ή των keys). Οι χειροκίνητες κατηγορίες/σημειώσεις διατηρούνται. -> (στοιχεία, νέα/αλλαγμένα)."""
    rows = [qsol.get(c, *k) for k in keys] if keys is not None else [qsol.row_dict(x) for x in c.execute('SELECT * FROM qsolution')]
    n = 0; seen = set(); now = datetime.datetime.now().isoformat(timespec='seconds')
    for r in rows:
        if not r: continue
        s = c.execute('SELECT sol_text FROM question WHERE item_id=? AND code=?', (r['item_id'], r['qcode'])).fetchone(); st = (s['sol_text'] if s else '') or ''
        for d in compare_row(r, st):
            k = (r['item_id'], r['qcode'], d['qn']); seen.add(k); n += 1
            old = c.execute('SELECT manual FROM iepcmp WHERE item_id=? AND qcode=? AND qn=?', k).fetchone()
            if old and old['manual']: c.execute('UPDATE iepcmp SET kind=?,mine=?,iep=?,auto=?,updated=? WHERE item_id=? AND qcode=? AND qn=?', (d['kind'], d['mine'], d['iep'], d['auto'], now) + k)
            else: c.execute('INSERT INTO iepcmp(item_id,qcode,qn,kind,mine,iep,auto,status,manual,note,updated) VALUES(?,?,?,?,?,?,?,?,0,?,?) ON CONFLICT(item_id,qcode,qn) DO UPDATE SET kind=excluded.kind,mine=excluded.mine,iep=excluded.iep,auto=excluded.auto,status=excluded.status,note=excluded.note,updated=excluded.updated',
                              k[:3] + (d['kind'], d['mine'], d['iep'], d['auto'], d['auto'], d['note'], now))
    if keys is None:                                                    # σβήσε συγκρίσεις στοιχείων που δεν υπάρχουν πια (χωρίς χειροκίνητη αλλαγή)
        for x in c.execute('SELECT item_id,qcode,qn,manual FROM iepcmp').fetchall():
            if (x['item_id'], x['qcode'], x['qn']) not in seen and not x['manual']: c.execute('DELETE FROM iepcmp WHERE item_id=? AND qcode=? AND qn=?', (x['item_id'], x['qcode'], x['qn']))
    c.commit(); return n


def for_entries(c, es):
    """Συγκρίσεις των ορατών ερωτημάτων του wizard (υπολογίζονται εκ νέου και αποθηκεύονται). -> [dict]"""
    keys = list(dict.fromkeys((e['item'], e['code']) for e in es if e['vis'] == 'show'))
    refresh(c, keys); out = []
    for k in keys: out += [dict(x) for x in c.execute('SELECT * FROM iepcmp WHERE item_id=? AND qcode=? ORDER BY qn', k)]
    return out


def warnings(rows):
    w = []; d = [x for x in rows if x['status'] == 'differs']; ck = [x for x in rows if x['status'] == 'check']
    lab = lambda xs: ', '.join(f"{x['item_id']}/{x['qcode']}#{x['qn']}" for x in xs[:8]) + ('…' if len(xs) > 8 else '')
    if d: w.append(f"Σύγκριση ΙΕΠ: {len(d)} στοιχεία quiz έχουν απάντηση που ΔΙΑΦΕΡΕΙ από τη λύση ΙΕΠ ({lab(d)}). Δες τη σελίδα «Σύγκριση ΙΕΠ».")
    if ck: w.append(f"Σύγκριση ΙΕΠ: {len(ck)} στοιχεία θέλουν έλεγχο ({lab(ck)}).")
    return w


def label(k): return dict(STATUS).get(k, k)


@router.get('/compare', response_class=HTMLResponse, dependencies=[Depends(auth)])
def compare_page(status: str = '', msg: str = ''):
    c = db(); cnt = {r[0]: r[1] for r in c.execute('SELECT status,count(*) FROM iepcmp GROUP BY status')}
    where = 'WHERE status=?' if status in SKEYS else ''; rows = c.execute(f'SELECT * FROM iepcmp {where} ORDER BY CAST(item_id AS INTEGER), qcode, qn', (status,) if where else ()).fetchall(); c.close()
    flt = ' · '.join(f"<a href='/compare?status={k}'>{E(v)} ({cnt.get(k, 0)})</a>" for k, v in STATUS) + " · <a href='/compare'>όλα</a>"
    tr = ''
    for x in rows:
        k = f"{x['item_id']}|{x['qcode']}|{x['qn']}"; opts = ''.join(f"<option value={s} {'selected' if x['status'] == s else ''}>{E(l)}</option>" for s, l in STATUS)
        tr += (f"<tr class='cmp-{x['status']}'><td><a href='/review/{E(x['item_id'])}'>{E(x['item_id'])}</a> · {E(x['qcode'])}#{x['qn']}</td><td>{E(x['kind'] or '')}</td><td>{E(x['mine'] or '')}</td><td>{E(x['iep'] or '')}</td><td>{E(label(x['auto'] or ''))}</td>"
               f"<td><input type=hidden name=k value='{E(k)}'><select class=r-list name='st_{E(k)}'>{opts}</select>{' ✎' if x['manual'] else ''}</td><td><input class=r-txt name='nt_{E(k)}' size=40 value='{E(x['note'] or '')}'></td></tr>")
    note = f"<div class='adm adm-success'><p class=adm-t>{E(msg)}</p></div>" if msg else ''
    body = (f"{note}<h2>Σύγκριση με τη λύση ΙΕΠ</h2><p>Συγκρίνει την απάντηση που έχεις στα στοιχεία quiz των λύσεών σου με την τελική απάντηση του ΙΕΠ (Σ/Λ ανά γράμμα, πολλαπλής επιλογής, αριθμοί). "
            "Είναι <b>ευρετική σύγκριση</b>· όπου δεν είναι βέβαιη, γράφει «να ελεγχθεί». Η τελική κρίση είναι δική σου: άλλαξε την κατάσταση και γράψε σημείωση.</p>"
            "<form method=post action=/compare/refresh><button class=primary>Υπολογισμός από όλες τις λύσεις</button></form>"
            f"<p>{flt} · <a href='/compare.csv'>⬇ CSV</a></p>"
            f"<form method=post action=/compare/save><div class=scroll><table><tr><th>Ερώτημα</th><th>Τύπος</th><th>Η απάντησή μου</th><th>ΙΕΠ</th><th>Αυτόματο</th><th>Κατάσταση</th><th>Σημείωση</th></tr>{tr or '<tr><td colspan=7>Καμία σύγκριση. Πάτα «Υπολογισμός».</td></tr>'}</table></div>"
            + ("<button class=primary>Αποθήκευση αλλαγών</button>" if rows else '') + "</form>")
    return page('Σύγκριση ΙΕΠ', body)


@router.post('/compare/refresh', dependencies=[Depends(auth)])
def compare_refresh(request: Request):
    same_origin(request); c = db(); n = refresh(c); c.close()
    from urllib.parse import quote
    return RedirectResponse('/compare?msg=' + quote(f'Υπολογίστηκαν {n} στοιχεία.'), status_code=303)


@router.post('/compare/save', dependencies=[Depends(auth)])
async def compare_save(request: Request):
    same_origin(request); f = await request.form(); c = db(); n = 0
    for k in f.getlist('k'):
        p = str(k).split('|')
        if len(p) != 3 or not p[2].isdigit(): continue
        s = str(f.get('st_' + k) or ''); nt = str(f.get('nt_' + k) or '').strip()[:300]
        x = c.execute('SELECT auto,status,note,manual FROM iepcmp WHERE item_id=? AND qcode=? AND qn=?', (p[0], p[1], int(p[2]))).fetchone()
        if not x or s not in SKEYS: continue
        man = 1 if (s != x['auto'] or (nt and (x['manual'] or nt != (x['note'] or '')))) else 0
        if s == x['status'] and nt == (x['note'] or '') and man == x['manual']: continue
        c.execute('UPDATE iepcmp SET status=?,note=?,manual=?,updated=? WHERE item_id=? AND qcode=? AND qn=?', (s, nt, man, datetime.datetime.now().isoformat(timespec='seconds'), p[0], p[1], int(p[2]))); n += 1
    c.commit(); c.close()
    from urllib.parse import quote
    return RedirectResponse('/compare?msg=' + quote(f'Αποθηκεύτηκαν {n} αλλαγές.'), status_code=303)


@router.get('/compare.csv', dependencies=[Depends(auth)])
def compare_csv():
    c = db(); rows = c.execute('SELECT * FROM iepcmp ORDER BY CAST(item_id AS INTEGER), qcode, qn').fetchall(); c.close()
    b = io.StringIO(); w = csv.writer(b); w.writerow(['θέμα', 'ερώτημα', 'στοιχείο', 'τύπος', 'η απάντησή μου', 'ΙΕΠ', 'αυτόματο', 'κατάσταση', 'χειροκίνητο', 'σημείωση'])
    for x in rows: w.writerow([x['item_id'], x['qcode'], x['qn'], x['kind'], x['mine'], x['iep'], label(x['auto']), label(x['status']), 'ναι' if x['manual'] else '', x['note'] or ''])
    return Response(('﻿' + b.getvalue()).encode('utf-8'), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="sygkrisi-iep.csv"'})
