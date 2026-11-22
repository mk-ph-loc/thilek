"""0.32: παρουσιάσεις (πίνακες deck / deck_slide). CRUD, ενδείξεις «η λύση άλλαξε» (⚠) και «την άλλαξες εσύ» (✎), και οι builders των συνταγών.
Δεν έχει FastAPI. Οι διαφάνειες από λύσεις είναι ΑΝΤΙΓΡΑΦΟ (το επεξεργάζεσαι)· η αναφορά στην πηγή (item_id+qcode) κρατιέται, ώστε να φαίνεται αν η λύση άλλαξε.
Δεδομένα χρήστη: επιβιώνουν του rebuild. Χωρίς ξένα κλειδιά, οπότε η διαγραφή deck σβήνει ρητά τις διαφάνειές του."""
import datetime, hashlib, json
import yaml
from . import decktpl as T, qsol, solexport as X
from .solstyle import LABEL, PRESETS, include_of, style_of

SLIDE_COLS = ('layout', 'title', 'body', 'notes', 'opts', 'down', 'hidden', 'src_item', 'src_qcode', 'src_unit', 'src_part', 'src_sha', 'gen_sha', 'linked')
GRP = 'ΑΒΓΔΕΖΗΘΙΚ'


def now(): return datetime.datetime.now().isoformat(timespec='seconds')


def sha(title, body): return hashlib.sha256(((title or '') + '\x00' + (body or '')).encode('utf-8')).hexdigest()[:16]


def _row(r, deck=True):
    d = dict(r)
    if deck:
        try: d['state'] = json.loads(d.get('state') or '{}')
        except ValueError: d['state'] = {}
        if not isinstance(d['state'], dict): d['state'] = {}
        d['opts'] = T.load_opts(d.get('opts'))
    else: d['opts'] = T.load_opts(d.get('opts'), deck=False)
    return d


# ---------- CRUD ----------
def get(c, deck_id):
    r = c.execute('SELECT * FROM deck WHERE id=?', (deck_id,)).fetchone()
    return _row(r) if r else None


def slides(c, deck_id): return [_row(r, False) for r in c.execute('SELECT * FROM deck_slide WHERE deck_id=? ORDER BY pos,id', (deck_id,))]


def get_slide(c, deck_id, sid):
    r = c.execute('SELECT * FROM deck_slide WHERE id=? AND deck_id=?', (sid, deck_id)).fetchone()
    return _row(r, False) if r else None


def create(c, name, recipe='free', title='', subtitle='', style='calm', opts=None, state=None, kind=0, course=''):
    recipe = recipe if recipe in T.RECIPE_KEYS else 'free'
    return c.execute('INSERT INTO deck(name,title,subtitle,recipe,state,style,opts,kind,course_code,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                     ((name or 'Νέα παρουσίαση').strip()[:T.LIMITS['name']] or 'Νέα παρουσίαση', (title or '')[:T.LIMITS['title']], (subtitle or '')[:T.LIMITS['title']], recipe,
                      json.dumps(state or {}, ensure_ascii=False), style_of(style), T.dump_opts(opts or {}), 1 if kind == 1 else (2 if kind == 2 else 0), course or '', now(), now())).lastrowid


def save_deck(c, deck_id, **kw):
    """Ενημέρωση πεδίων deck (μόνο γνωστά): name, title, subtitle, style, opts, state, note."""
    sets, args = [], []
    for k, v in kw.items():
        if k in ('name', 'title', 'subtitle', 'note'): sets.append(f'{k}=?'); args.append((v or '')[:T.LIMITS['title'] if k != 'name' else T.LIMITS['name']] or ('Νέα παρουσίαση' if k == 'name' else ''))
        elif k == 'style': sets.append('style=?'); args.append(style_of(v))
        elif k == 'opts': sets.append('opts=?'); args.append(T.dump_opts(v))
        elif k == 'state': sets.append('state=?'); args.append(json.dumps(v, ensure_ascii=False))
    if sets: c.execute(f"UPDATE deck SET {','.join(sets)},updated=? WHERE id=?", args + [now(), deck_id])


def count(c, deck_id): return c.execute('SELECT count(*) FROM deck_slide WHERE deck_id=?', (deck_id,)).fetchone()[0]


def renumber(c, deck_id):
    for n, (sid,) in enumerate(c.execute('SELECT id FROM deck_slide WHERE deck_id=? ORDER BY pos,id', (deck_id,)).fetchall(), 1): c.execute('UPDATE deck_slide SET pos=? WHERE id=?', (n, sid))


def _insert(c, deck_id, pos, s, gen=False):
    if count(c, deck_id) >= T.LIMITS['slides']: raise ValueError(f"Πάνω από {T.LIMITS['slides']} διαφάνειες.")
    title = (s.get('title') or '')[:T.LIMITS['title']]; body = (s.get('body') or '')[:T.LIMITS['body']]
    return c.execute('INSERT INTO deck_slide(deck_id,pos,layout,title,body,notes,opts,down,hidden,src_item,src_qcode,src_unit,src_part,src_sha,gen_sha,linked,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (deck_id, pos, T.layout_ok(s.get('layout')), title, body, (s.get('notes') or '')[:T.LIMITS['notes']], T.dump_opts(s.get('opts') or {}, False), 1 if s.get('down') else 0, 1 if s.get('hidden') else 0,
                      s.get('src_item'), s.get('src_qcode'), s.get('src_unit'), s.get('src_part'), s.get('src_sha'), (sha(title, body) if gen else s.get('gen_sha')), 1 if s.get('linked') else 0, now())).lastrowid


def add_slide(c, deck_id, layout='content', after=None):
    """Νέα διαφάνεια από πρότυπο μετά από την `after` (id) ή στο τέλος. Επιστρέφει το id."""
    layout = T.layout_ok(layout); title, body, opts = T.skeleton(layout)
    pos = count(c, deck_id) + 1
    if after:
        r = c.execute('SELECT pos FROM deck_slide WHERE id=? AND deck_id=?', (after, deck_id)).fetchone()
        if r: pos = r[0] + 1; c.execute('UPDATE deck_slide SET pos=pos+1 WHERE deck_id=? AND pos>=?', (deck_id, pos))
    sid = _insert(c, deck_id, pos, {'layout': layout, 'title': title, 'body': body, 'opts': opts}); renumber(c, deck_id); touch(c, deck_id); return sid


def touch(c, deck_id): c.execute('UPDATE deck SET updated=? WHERE id=?', (now(), deck_id))


def update_slide(c, deck_id, sid, layout=None, title=None, body=None, notes=None, opts=None, down=None, hidden=None):
    s = get_slide(c, deck_id, sid)
    if not s: return False
    c.execute('UPDATE deck_slide SET layout=?,title=?,body=?,notes=?,opts=?,down=?,hidden=?,updated=? WHERE id=?',
              (T.layout_ok(layout if layout is not None else s['layout']), (title if title is not None else s['title'] or '')[:T.LIMITS['title']], (body if body is not None else s['body'])[:T.LIMITS['body']],
               (notes if notes is not None else s['notes'])[:T.LIMITS['notes']], T.dump_opts(opts if opts is not None else s['opts'], False), int(bool(s['down'] if down is None else down)),
               int(bool(s['hidden'] if hidden is None else hidden)), now(), sid))
    touch(c, deck_id); return True


def move(c, deck_id, sid, delta):
    ss = [r[0] for r in c.execute('SELECT id FROM deck_slide WHERE deck_id=? ORDER BY pos,id', (deck_id,))]
    if sid not in ss: return False
    i = ss.index(sid); j = i + (1 if delta > 0 else -1)
    if 0 <= j < len(ss): ss[i], ss[j] = ss[j], ss[i]
    for n, x in enumerate(ss, 1): c.execute('UPDATE deck_slide SET pos=? WHERE id=?', (n, x))
    touch(c, deck_id); return True


def copy_slide(c, deck_id, sid):
    s = get_slide(c, deck_id, sid)
    if not s: return None
    c.execute('UPDATE deck_slide SET pos=pos+1 WHERE deck_id=? AND pos>?', (deck_id, s['pos']))
    n = _insert(c, deck_id, s['pos'] + 1, s); touch(c, deck_id); return n


def delete_slide(c, deck_id, sid):
    c.execute('DELETE FROM deck_slide WHERE id=? AND deck_id=?', (sid, deck_id)); renumber(c, deck_id); touch(c, deck_id)


def delete_deck(c, deck_id):
    c.execute('DELETE FROM deck_slide WHERE deck_id=?', (deck_id,)); c.execute('DELETE FROM deck WHERE id=?', (deck_id,))


def copy_deck(c, deck_id, name=None, kind=0):
    d = get(c, deck_id)
    if not d: return None
    n = create(c, name or (d['name'][:100] + ' (αντίγραφο)'), d['recipe'], d['title'], d['subtitle'], d['style'], d['opts'], d['state'], kind, d['course_code'])
    for s in slides(c, deck_id): _insert(c, n, s['pos'], s)
    return n


def replace_slides(c, deck_id, items):
    """Αντικατάσταση όλων των διαφανειών (εισαγωγή deck.md)."""
    c.execute('DELETE FROM deck_slide WHERE deck_id=?', (deck_id,))
    for n, s in enumerate(items, 1): _insert(c, deck_id, n, s)
    touch(c, deck_id)


# ---------- ενδείξεις ----------
def edited(s): return bool(s.get('gen_sha')) and sha(s.get('title'), s.get('body')) != s['gen_sha']


def stale(c, sl):
    """{id διαφάνειας: 'changed' | 'missing'} για διαφάνειες με πηγή· η λύση έχει άλλο sha ή δεν υπάρχει πια."""
    out = {}; cache = {}
    for s in sl:
        if not s.get('src_item') or not s.get('src_sha'): continue
        k = (s['src_item'], s['src_qcode'])
        if k not in cache:
            r = c.execute('SELECT sha FROM qsolution WHERE item_id=? AND qcode=?', k).fetchone(); cache[k] = r[0] if r else None
        if cache[k] is None: out[s['id']] = 'missing'
        elif cache[k] != s['src_sha']: out[s['id']] = 'changed'
    return out


# ---------- builders ----------
def _sl(layout, title, body='', **kw):
    d = {'layout': layout, 'title': title, 'body': body}; d.update(kw); return d


def _quiz_yaml(q):
    d = {'type': q['type'], 'stem': q['stem']}
    for k in ('options', 'answer', 'pairs', 'tolerance', 'unit', 'feedback', 'image', 'part'):
        if q.get(k) not in (None, '', []) and not (k == 'tolerance' and not q[k]): d[k] = q[k]
    if q.get('points', 1) != 1: d['points'] = q['points']
    return yaml.safe_dump(d, allow_unicode=True, sort_keys=False, default_flow_style=None, width=1000).strip()


def _solution_slides(c, r, include, ans_inline=True, base_slides=True):
    """Διαφάνειες ενός ερωτήματος με λύση: ενότητα, και μετά (κάθετη στοίβα) εκφώνηση, βήματα, quiz. -> λίστα dict με src_*."""
    out = []; src = dict(src_item=r['item_id'], src_qcode=r['qcode'], src_sha=r.get('sha'))
    out.append(_sl('section', X.label(r), '', **dict(src, src_unit='section')))
    for k, kind, d in X.unit_items(r, include):
        if kind == 'md':
            out.append(_sl('statement' if k == 'statement' else 'content', LABEL[k] if k != 'statement' else X.label(r), X.fix_md(d, r['base'], 2), down=1, **dict(src, src_unit=k)))
        elif kind == 'parts':
            for i, b in enumerate(d, 1): out.append(_sl('solution-step', LABEL[k] + (f' ({i}/{len(d)})' if len(d) > 1 else ''), X.fix_md(b, r['base'], 2), down=1, **dict(src, src_unit=k, src_part=i)))
        else:
            for q in d:
                out.append(_sl('quiz', f"Quiz {q['n']}", f"::: quiz\n{_quiz_yaml(q)}\n:::", down=1, opts={'base': r['base'], 'ans': None if ans_inline else False}, **dict(src, src_unit='quiz', src_part=q['n'])))
    return out


def _include(st): return include_of(st.get('sx')) if st.get('sx') else list(PRESETS[0][2])


def _b_solutions(c, deck):
    rows = X.load(c, [tuple(m) for m in deck['state'].get('members', [])]); have = {(r['item_id'], r['qcode']) for r in rows}
    miss = [f'{m[0]}/{m[1]}' for m in deck['state'].get('members', []) if tuple(m) not in have]; out = []
    for r in rows: out += _solution_slides(c, r, _include(deck['state']))
    return out, miss


def _b_quiz(c, deck):
    rows = X.load(c, [tuple(m) for m in deck['state'].get('members', [])]); have = {(r['item_id'], r['qcode']) for r in rows}
    miss = [f'{m[0]}/{m[1]}' for m in deck['state'].get('members', []) if tuple(m) not in have]
    inline = deck['opts']['answers'] == 'inline'; out = [_sl('content', 'Quiz', 'Απαντήστε στις ερωτήσεις. ' + ('Η απάντηση εμφανίζεται με το επόμενο βήμα.' if inline else 'Οι απαντήσεις είναι στο τέλος.'))]; ans = []; n = 0
    for r in rows:
        for q in [q for q in r['quiz'] if not q['err']]:
            n += 1; src = dict(src_item=r['item_id'], src_qcode=r['qcode'], src_sha=r.get('sha'), src_unit='quiz', src_part=q['n'])
            out.append(_sl('quiz', f'Quiz {n}', f"::: quiz\n{_quiz_yaml(q)}\n:::", opts={'base': r['base'], 'ans': None if inline else False}, **src)); ans.append(f"{n}. {X.answer_text(q) or '—'}")
    if not inline and ans: out.append(_sl('summary', 'Απαντήσεις', '\n'.join(ans)))
    return (out if n else []), miss + ([] if n else ['κανένα έγκυρο στοιχείο quiz'])


def _b_review(c, deck):
    mem = [tuple(m) for m in deck['state'].get('members', [])]; groups = {}; order = []
    for it, qc in mem:
        r = c.execute("SELECT s.code,s.title_el FROM question q JOIN question_section qs ON qs.question_id=q.id AND qs.origin!='rejected' JOIN section s ON s.id=qs.section_id AND s.level=3 "
                      "WHERE q.item_id=? AND q.code=? ORDER BY s.page_from LIMIT 1", (it, qc)).fetchone()
        k = (r[0], r[1]) if r else ('', 'Άλλα ερωτήματα')
        if k not in groups: groups[k] = []; order.append(k)
        groups[k].append((it, qc))
    order.sort(key=lambda k: (k[0] == '', k[0])); out = []
    if len(order) > 1: out.append(_sl('bullets', 'Τι θα δούμε', '\n'.join(f"- {k[0]} {k[1]}".strip() for k in order), opts={'frag': True}))
    skipped = []
    for k in order:
        out.append(_sl('section', f"{k[0]} {k[1]}".strip()))
        out.append(_sl('bullets', 'Βασικά σημεία', '- …\n- …\n- …', opts={'frag': True}))
        rows = X.load(c, groups[k]); have = {(r['item_id'], r['qcode']) for r in rows}; skipped += [f'{a}/{b}' for a, b in groups[k] if (a, b) not in have]
        for r in rows[:2]:
            st = (r['sections'] or {}).get('statement') or ''
            if st: out.append(_sl('statement', X.label(r), X.fix_md(st, r['base'], 2), src_item=r['item_id'], src_qcode=r['qcode'], src_unit='statement', src_sha=r.get('sha')))
        for r in rows:
            for q in [q for q in r['quiz'] if not q['err']][:1]:
                out.append(_sl('quiz', f"Quiz · {k[0]}".strip(' ·'), f"::: quiz\n{_quiz_yaml(q)}\n:::", opts={'base': r['base']}, src_item=r['item_id'], src_qcode=r['qcode'], src_unit='quiz', src_part=q['n'], src_sha=r.get('sha')))
    out.append(_sl('summary', 'Ανακεφαλαίωση', '1. …\n2. …'))
    return (out if mem else []), skipped


def _b_exam(c, deck):
    eid = deck['state'].get('exam_id')
    rows = c.execute('SELECT grp,item_id,qcode FROM exam_question WHERE exam_id=? ORDER BY grp,pos', (eid,)).fetchall() if isinstance(eid, int) else []
    out, miss, last = [], [], None
    for g, it, qc in rows:
        if g != last: out.append(_sl('section', 'ΘΕΜΑ ' + (GRP[g - 1] if 1 <= g <= len(GRP) else str(g)))); last = g
        r = qsol.get(c, it, qc); q = c.execute('SELECT text FROM question WHERE item_id=? AND code=?', (it, qc)).fetchone(); src = dict(src_item=it, src_qcode=qc)
        if r: src['src_sha'] = r.get('sha')
        st = X.fix_md(((r or {}).get('sections') or {}).get('statement') or '', (r or {}).get('base', ''), 2) if r else ''
        out.append(_sl('statement', f'Θέμα {it} · {qc}', st or (q[0] if q else ''), **dict(src, src_unit='statement')))
        if not r: miss.append(f'{it}/{qc}'); continue
        for k, kind, d in X.unit_items(r, ['full', 'iep']):
            if kind == 'parts':
                for i, b in enumerate(d, 1): out.append(_sl('solution-step', 'Λύση' + (f' ({i}/{len(d)})' if len(d) > 1 else ''), X.fix_md(b, r['base'], 2), down=1, **dict(src, src_unit=k, src_part=i)))
                break
            if kind == 'md': out.append(_sl('content', LABEL[k], X.fix_md(d, r['base'], 2), down=1, **dict(src, src_unit=k))); break
    return out, miss


def _b_lesson(c, deck):
    out = []
    for lay in ('title', 'bullets', 'content', 'two-col', 'math', 'summary', 'quiz'):
        t, b, o = T.skeleton(lay)
        out.append(_sl(lay, deck['title'] if lay == 'title' and deck.get('title') else (('Στόχοι' if lay == 'bullets' else t)), b, opts=o))
    return out, []


def _b_free(c, deck):
    t, b, o = T.skeleton('title'); t2, b2, o2 = T.skeleton('content')
    return [_sl('title', deck.get('title') or t, b), _sl('content', t2, b2)], []


BUILDERS = {'free': _b_free, 'lesson': _b_lesson, 'solutions': _b_solutions, 'review': _b_review, 'quiz': _b_quiz, 'exam': _b_exam}


def gen_key(s):
    """Σταθερό κλειδί διαφάνειας της συνταγής (για το «Ξαναχτίσιμο»)."""
    if s.get('src_item'): return (s['src_item'], s['src_qcode'], s.get('src_unit') or '', s.get('src_part') or 0)
    return ('', '', s.get('layout') or '', s.get('title') or '')


def build(c, deck_id, rebuild=False):
    """Δημιουργεί (ή ξαναχτίζει) τις διαφάνειες από τη συνταγή. Στο ξαναχτίσιμο: όσες επεξεργάστηκες με το χέρι (gen_sha ≠ τρέχον) κρατιούνται· οι χειροκίνητες (χωρίς gen_sha) μένουν
    στη θέση τους (μετά την ίδια διαφάνεια της συνταγής)· οι ανέγγιχτες ξαναπαράγονται. Επιστρέφει {'created', 'kept': [τίτλοι], 'missing': [..]}."""
    deck = get(c, deck_id)
    if not deck: raise ValueError('Δεν υπάρχει η παρουσίαση.')
    gen, missing = BUILDERS[deck['recipe']](c, deck)
    for g in gen: g['opts'] = g.get('opts') or {}
    old = slides(c, deck_id) if rebuild else []; kept = {}; manual = {}; anchor = None; first_manual = []
    for s in old:
        if s.get('gen_sha'):
            anchor = gen_key(s)
            if edited(s): kept[anchor] = s
        else: (manual.setdefault(anchor, []) if anchor is not None else first_manual).append(s)
    final, used = [], set()
    for s in first_manual: final.append((s, False))
    for g in gen:
        k = gen_key(g)
        if k in kept: final.append((kept[k], False)); used.add(k)
        else: final.append((g, True))
        for m in manual.pop(k, []): final.append((m, False))
    for k, s in kept.items():                           # επεξεργασμένη διαφάνεια που δεν παράγεται πια: μένει στο τέλος
        if k not in used: final.append((s, False))
    for ms in manual.values():
        for m in ms: final.append((m, False))
    c.execute('DELETE FROM deck_slide WHERE deck_id=?', (deck_id,))
    for n, (s, is_gen) in enumerate(final, 1): _insert(c, deck_id, n, s, gen=is_gen)
    touch(c, deck_id)
    return {'created': sum(1 for _, g in final if g), 'kept': [s['title'] for s, g in final if not g and s.get('gen_sha') and edited(s)], 'missing': missing}


def refresh_from_source(c, deck_id, sid):
    """Ξαναπαράγει μία διαφάνεια από την τρέχουσα λύση (ανανέωση μετά από αλλαγή). True αν βρέθηκε."""
    s = get_slide(c, deck_id, sid)
    if not s or not s.get('src_item'): return False
    r = qsol.get(c, s['src_item'], s['src_qcode'])
    if not r: return False
    for g in _solution_slides(c, r, list(X.KEYS)):
        if gen_key(g) == gen_key(s):
            title, body = g['title'], g['body']
            c.execute('UPDATE deck_slide SET title=?,body=?,src_sha=?,gen_sha=?,updated=? WHERE id=?', (title, body[:T.LIMITS['body']], r.get('sha'), sha(title, body[:T.LIMITS['body']]), now(), sid)); touch(c, deck_id); return True
    return False
