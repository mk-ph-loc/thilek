"""Δημιουργία Markdown από διαγωνίσματα, quiz και επιλογές ερωτημάτων."""
import json, re
from .quizgen import LET, CODE, clean
from .exams import LETTERS, exam_rows

PARA = re.compile(r'^(στ|[α-ηθ])[.)]\s|^\d+[.)]\s')

def text_to_md(text):
    """Κείμενο εξαγόμενο από PDF -> παράγραφοι (οι αλλαγές γραμμής μέσα σε πρόταση ενώνονται· κάθε α./β./1. ξεκινά νέα παράγραφο)."""
    out, cur = [], []
    for ln in (text or '').splitlines():
        t = ' '.join(ln.split())
        if not t: 
            if cur: out.append(' '.join(cur)); cur = []
            continue
        if PARA.match(t) and cur: out.append(' '.join(cur)); cur = []
        cur.append(t)
    if cur: out.append(' '.join(cur))
    return '\n\n'.join(out)

def q_block(q, label, mode):
    parts = []
    if mode in ('image', 'both') and q['geo']: parts.append(f"![]({'/crop/%d.jpg' % q['qid']})")
    if mode in ('text', 'both') or not q['geo']: parts.append(text_to_md(CODE.sub('', q['text'] or '', count=1)))
    return f"**{label}**\n\n" + '\n\n'.join(p for p in parts if p)

def exam_md(c, eid, mode='image'):
    e = c.execute('SELECT * FROM exam WHERE id=?', (eid,)).fetchone()
    rows = exam_rows(c, eid)
    qs = {}
    for r in rows:
        x = c.execute('SELECT id qid,text,geo FROM question WHERE item_id=? AND code=?', (r['item_id'], r['qcode'])).fetchone()
        qs[(r['item_id'], r['qcode'])] = dict(x) if x else {'qid': 0, 'text': '', 'geo': None}
    total = sum(r['points'] or 0 for r in rows)
    out = [f"# {e['title']}"]
    if e['school']: out.append(e['school'])
    if e['subtitle']: out.append(e['subtitle'])
    out.append(f"Τάξη: {e['class_name'] or ''} · Ημερομηνία: {e['exam_date'] or ''} · Διάρκεια: {e['duration'] or ''} · Σύνολο: {total} μονάδες")
    if e['notes']: out.append(f"> {e['notes']}")
    out.append('Ονοματεπώνυμο: ______________________________  Βαθμός: ________')
    groups = {}
    for r in rows: groups.setdefault(r['grp'], []).append(r)
    for g in sorted(groups):
        out.append(f"## ΘΕΜΑ {LETTERS[g - 1]} ({sum(r['points'] or 0 for r in groups[g])} μονάδες)")
        for k, r in enumerate(groups[g], 1): out.append(q_block(qs[(r['item_id'], r['qcode'])], f"{LETTERS[g - 1]}{k}.", mode))
    return '\n\n'.join(out) + '\n'

def members_md(c, members, title='Σύνθετο έγγραφο ασκήσεων', mode='image', numbering='new'):
    out = [f"# {title}"]
    for n, (it, code) in enumerate(members, 1):
        q = c.execute('SELECT id qid,text,geo,points FROM question WHERE item_id=? AND code=?', (it, code)).fetchone()
        if not q: continue
        label = f"{n}." if numbering == 'new' else f"Θέμα {it}, ερ. {code}"
        out.append(q_block(dict(q), label, mode))
    return '\n\n'.join(out) + '\n'

def quiz_md(c, qid, key=True):
    z = c.execute('SELECT * FROM quiz WHERE id=?', (qid,)).fetchone()
    out = [f"# {z['name']}"]
    if z['description']: out.append(z['description'])
    for k, r in enumerate(c.execute('SELECT * FROM quiz_item WHERE quiz_id=? ORDER BY pos', (qid,)).fetchall(), 1):
        try: opts = json.loads(r['options'] or '[]')
        except ValueError: opts = []
        head = f"**{k}.** {r['stem']} *({r['points']:g} μον.)*"
        if r['kind'] == 'tf': block = [head, '☐ Σωστό  ☐ Λάθος']; ans = r['answer']
        elif r['kind'] == 'mcq':
            block = [head, '\n'.join(f"- {LET[i]}. {o}" for i, o in enumerate(opts))]; ans = f"{LET[int(r['answer'])]}. {opts[int(r['answer'])]}" if (r['answer'] or '').isdigit() and int(r['answer']) < len(opts) else ''
        else: block = [head]; ans = r['answer']
        if key and ans: block.append(f"> Σωστή απάντηση: {ans}" + (f" — {r['feedback']}" if r['feedback'] else ''))
        out.append('\n\n'.join(block))
    return '\n\n'.join(out) + '\n'
