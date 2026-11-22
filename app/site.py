"""0.34: site builder, μέρος 1 (πίνακες site / site_page). Σελίδες σε ιεραρχία (μενού), σώμα σελίδας = Markdown + οδηγίες `:::` (ίδιος αναλυτής με τις παρουσιάσεις, deckmd.parse με δικό του σύνολο οδηγιών),
απόδοση σε αυτόνομες σελίδες HTML (inline CSS/JS, KaTeX μόνο όπου υπάρχουν τύποι) και εξαγωγή zip. Quiz και παρουσιάσεις μπαίνουν ΩΣ ΣΤΙΓΜΙΟΤΥΠΟ (snapshot) τη στιγμή της απόδοσης/εξαγωγής.
Δεν έχει FastAPI. Δεδομένα χρήστη: επιβιώνουν του rebuild. Χωρίς ξένα κλειδιά (parent_id 0 = ρίζα), οπότε οι διαγραφές σβήνουν ρητά.
Δεν υπάρχει δημοσίευση στο /p/ ούτε αναζήτηση (0.35)· τα ονόματα αρχείων της εξαγωγής είναι επίπεδα (χωρίς φακέλους) ώστε να μπορούν να περάσουν αργότερα από το publish.save_site."""
import datetime, html, io, json, pathlib, re, zipfile
from . import config, deck as D, deckexport as DX, deckmd, embed as EM, solexport as X
from .mdmath import md_text, render_md

E = html.escape
DIRS = ('cols', 'quiz', 'embed', 'quiz-ref', 'deck-ref', 'file', 'callout')
KINDS = (('page', 'Σελίδα'), ('section', 'Ενότητα (μόνο μενού και κάρτες)'))
KIND_KEYS = tuple(k for k, _ in KINDS)
LIM = {'name': 100, 'title': 200, 'body': 200_000, 'footer': 300}
MAX_PAGES, MAX_DEPTH = 200, 3
MAX_FILE, MAX_TOTAL = 10_000_000, 60_000_000
RESERVED = {'index', 'data', 'readme', 'search', 'meta'}
FILE_EXT = {'.pdf', '.png', '.jpg', '.jpeg', '.svg', '.txt', '.json'}
CALLOUTS = {'note': ('Σημείωση', '#3b6ea5'), 'tip': ('Συμβουλή', '#2e9e5b'), 'warning': ('Προσοχή', '#b45309'), 'danger': ('Κίνδυνος', '#c0392b')}
THEMES = {
    'calm': ('Ήρεμο φωτεινό', dict(bg='#f4f6f9', fg='#243040', card='#ffffff', head='#2b4a6f', accent='#3b6ea5', line='#d5dce6')),
    'paper': ('Χαρτί (εκτύπωση)', dict(bg='#ffffff', fg='#111111', card='#ffffff', head='#111111', accent='#1d4ed8', line='#bbbbbb')),
    'dark': ('Σκοτεινό', dict(bg='#12161d', fg='#e6e9ef', card='#1b212b', head='#9fc4ff', accent='#6ea8ff', line='#2c3542')),
}
GR = dict(zip('αβγδεζηθικλμνξοπρστυφχψω', ['a', 'v', 'g', 'd', 'e', 'z', 'i', 'th', 'i', 'k', 'l', 'm', 'n', 'x', 'o', 'p', 'r', 's', 't', 'y', 'f', 'ch', 'ps', 'o']))
GR['ς'] = 's'


def now(): return datetime.datetime.now().isoformat(timespec='seconds')


# ---------- ρυθμίσεις ----------
def load_opts(raw):
    try: d = json.loads(raw or '{}')
    except ValueError: d = {}
    d = d if isinstance(d, dict) else {}
    return {'footer': d['footer'][:LIM['footer']] if isinstance(d.get('footer'), str) else '', 'home': d['home'] if isinstance(d.get('home'), int) and not isinstance(d.get('home'), bool) else 0}


def theme_of(t): return t if t in THEMES else 'calm'


def slugify(s):
    """Ελληνικά/λατινικά -> [a-z0-9-]. Κενό αποτέλεσμα -> 'selida'. Δεν είναι δεσμευμένο όνομα."""
    t = ''.join(GR.get(ch, ch) for ch in (s or '').lower().replace('ά', 'α').replace('έ', 'ε').replace('ή', 'η').replace('ί', 'ι').replace('ϊ', 'ι').replace('ΐ', 'ι').replace('ό', 'ο').replace('ύ', 'υ').replace('ϋ', 'υ').replace('ΰ', 'υ').replace('ώ', 'ω'))
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')[:40]
    return clean_slug(t or 'selida')


def clean_slug(t):
    t = re.sub(r'[^a-z0-9-]+', '-', (t or '').lower()).strip('-')[:50]
    if not t: return ''
    if t in RESERVED or t.startswith(('deck-', 'file-')): t = 'p-' + t
    return t


def uniq_slug(c, site_id, want, exclude=0):
    base = clean_slug(want) or 'selida'; s, n = base, 2
    while c.execute('SELECT 1 FROM site_page WHERE site_id=? AND slug=? AND id<>?', (site_id, s, exclude)).fetchone(): s = f'{base[:46]}-{n}'; n += 1
    return s


# ---------- CRUD ----------
def get(c, sid):
    r = c.execute('SELECT * FROM site WHERE id=?', (sid,)).fetchone()
    if not r: return None
    d = dict(r); d['opts'] = load_opts(d.get('opts')); d['theme'] = theme_of(d.get('theme')); return d


def create(c, name, title='', theme='calm', course=''):
    name = (name or 'Νέο site').strip()[:LIM['name']] or 'Νέο site'
    sid = c.execute('INSERT INTO site(name,title,theme,opts,course_code,created,updated) VALUES(?,?,?,?,?,?,?)', (name, (title or name)[:LIM['title']], theme_of(theme), '{}', course or '', now(), now())).lastrowid
    add_page(c, sid, 'Αρχική', body='Καλώς ήρθες! Γράψε εδώ το κείμενο της αρχικής σελίδας.')
    return sid


def save_site(c, sid, name=None, title=None, theme=None, footer=None, home=None):
    s = get(c, sid)
    if not s: return
    o = dict(s['opts'])
    if footer is not None: o['footer'] = footer[:LIM['footer']]
    if home is not None: o['home'] = home if c.execute('SELECT 1 FROM site_page WHERE id=? AND site_id=?', (home, sid)).fetchone() else 0
    c.execute('UPDATE site SET name=?,title=?,theme=?,opts=?,updated=? WHERE id=?', ((name if name else s['name'])[:LIM['name']] or s['name'], (title if title is not None else s['title'] or '')[:LIM['title']],
                                                                                    theme_of(theme if theme else s['theme']), json.dumps(o, ensure_ascii=False), now(), sid))


def delete_site(c, sid):
    c.execute('DELETE FROM site_page WHERE site_id=?', (sid,)); c.execute('DELETE FROM site WHERE id=?', (sid,))


def copy_site(c, sid, name=None):
    s = get(c, sid)
    if not s: return None
    n = c.execute('INSERT INTO site(name,title,theme,opts,course_code,note,created,updated) VALUES(?,?,?,?,?,?,?,?)', ((name or s['name'] + ' (αντίγραφο)')[:LIM['name']], s['title'], s['theme'], '{}', s['course_code'], s['note'], now(), now())).lastrowid
    ids = {0: 0}
    for p in pages(c, sid):                              # οι γονείς προηγούνται (ταξινόμηση tree)
        ids[p['id']] = c.execute('INSERT INTO site_page(site_id,parent_id,pos,slug,title,kind,body,opts,hidden,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                 (n, ids.get(p['parent_id'], 0), p['pos'], p['slug'], p['title'], p['kind'], p['body'], p['opts'], p['hidden'], now())).lastrowid
    h = s['opts']['home']
    if h in ids: c.execute('UPDATE site SET opts=? WHERE id=?', (json.dumps({'footer': s['opts']['footer'], 'home': ids[h]}, ensure_ascii=False), n))
    return n


def rows(c, sid): return [dict(r) for r in c.execute('SELECT * FROM site_page WHERE site_id=? ORDER BY parent_id,pos,id', (sid,))]


def order(rs):
    """Λίστα [(page, depth)] κατά σειρά μενού (γονέας και μετά τα παιδιά του). Ορφανά (άγνωστος γονέας) θεωρούνται ρίζα· προστασία από κύκλους."""
    ids = {r['id'] for r in rs}; kids = {}
    for r in rs: kids.setdefault(r['parent_id'] if r['parent_id'] in ids and r['parent_id'] != r['id'] else 0, []).append(r)
    out, seen = [], set()

    def walk(pid, depth):
        for r in sorted(kids.get(pid, []), key=lambda x: (x['pos'], x['id'])):
            if r['id'] in seen: continue
            seen.add(r['id']); out.append((r, depth)); walk(r['id'], depth + 1)
    walk(0, 0)
    return out


def pages(c, sid): return [p for p, _ in order(rows(c, sid))]
def depth_of(rs, pid):
    by = {r['id']: r for r in rs}; d, n = 0, pid
    while n in by and by[n]['parent_id'] and d <= MAX_DEPTH + 2: n = by[n]['parent_id']; d += 1
    return d


def get_page(c, sid, pid):
    r = c.execute('SELECT * FROM site_page WHERE id=? AND site_id=?', (pid, sid)).fetchone()
    return dict(r) if r else None


def _renumber(c, sid, parent):
    for i, r in enumerate(c.execute('SELECT id FROM site_page WHERE site_id=? AND parent_id=? ORDER BY pos,id', (sid, parent)).fetchall(), 1): c.execute('UPDATE site_page SET pos=? WHERE id=?', (i, r[0]))


def add_page(c, sid, title='Νέα σελίδα', kind='page', parent=0, body='', after=None):
    """-> id ή None (όριο σελίδων/βάθους/άγνωστος γονέας)."""
    rs = rows(c, sid)
    if len(rs) >= MAX_PAGES: return None
    if parent and (parent not in {r['id'] for r in rs} or depth_of(rs, parent) + 1 >= MAX_DEPTH): return None
    title = (title or 'Νέα σελίδα').strip()[:LIM['title']] or 'Νέα σελίδα'
    pos = (c.execute('SELECT max(pos) FROM site_page WHERE site_id=? AND parent_id=?', (sid, parent)).fetchone()[0] or 0) + 1
    pid = c.execute('INSERT INTO site_page(site_id,parent_id,pos,slug,title,kind,body,opts,hidden,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (sid, parent, pos, uniq_slug(c, sid, slugify(title)), title, kind if kind in KIND_KEYS else 'page', (body or '')[:LIM['body']], '{}', 0, now())).lastrowid
    if after:
        a = get_page(c, sid, after)
        if a and a['parent_id'] == parent:
            c.execute('UPDATE site_page SET pos=pos+1 WHERE site_id=? AND parent_id=? AND pos>? AND id<>?', (sid, parent, a['pos'], pid)); c.execute('UPDATE site_page SET pos=? WHERE id=?', (a['pos'] + 1, pid))
    _renumber(c, sid, parent); touch(c, sid); return pid


def touch(c, sid): c.execute('UPDATE site SET updated=? WHERE id=?', (now(), sid))


def update_page(c, sid, pid, title=None, slug=None, kind=None, body=None, hidden=None):
    p = get_page(c, sid, pid)
    if not p: return False
    t = (title if title is not None else p['title'] or '').strip()[:LIM['title']] or p['title'] or 'Σελίδα'
    s = uniq_slug(c, sid, slug, pid) if slug and clean_slug(slug) else p['slug']
    c.execute('UPDATE site_page SET title=?,slug=?,kind=?,body=?,hidden=?,updated=? WHERE id=?',
              (t, s, kind if kind in KIND_KEYS else p['kind'], (body if body is not None else p['body'])[:LIM['body']], p['hidden'] if hidden is None else (1 if hidden else 0), now(), pid))
    touch(c, sid); return True


def descendants(rs, pid):
    out, todo = [], [pid]
    while todo:
        x = todo.pop()
        for r in rs:
            if r['parent_id'] == x and r['id'] not in out and r['id'] != pid: out.append(r['id']); todo.append(r['id'])
    return out


def delete_page(c, sid, pid):
    """Διαγράφει τη σελίδα ΚΑΙ τις υποσελίδες της. -> πλήθος."""
    rs = rows(c, sid); p = next((r for r in rs if r['id'] == pid), None)
    if not p: return 0
    ids = [pid] + descendants(rs, pid)
    for i in ids: c.execute('DELETE FROM site_page WHERE id=?', (i,))
    _renumber(c, sid, p['parent_id'])
    s = get(c, sid)
    if s and s['opts']['home'] in ids: save_site(c, sid, home=0)
    touch(c, sid); return len(ids)


def move(c, sid, pid, act):
    """act: up | down (ανάμεσα στα αδέλφια) · in (γίνεται παιδί του προηγούμενου αδελφού) · out (βγαίνει ένα επίπεδο έξω, μετά τον γονέα)."""
    p = get_page(c, sid, pid)
    if not p: return False
    par = p['parent_id']; sib = [r['id'] for r in c.execute('SELECT id FROM site_page WHERE site_id=? AND parent_id=? ORDER BY pos,id', (sid, par))]; i = sib.index(pid)
    if act in ('up', 'down'):
        j = i - 1 if act == 'up' else i + 1
        if not 0 <= j < len(sib): return False
        sib[i], sib[j] = sib[j], sib[i]
        for k, x in enumerate(sib, 1): c.execute('UPDATE site_page SET pos=? WHERE id=?', (k, x))
    elif act == 'in':
        if i == 0: return False
        np_ = sib[i - 1]; rs = rows(c, sid)
        if depth_of(rs, np_) + 1 + max([0] + [depth_of(rs, d) - depth_of(rs, pid) for d in descendants(rs, pid)]) + 1 > MAX_DEPTH: return False
        c.execute('UPDATE site_page SET parent_id=?,pos=? WHERE id=?', (np_, (c.execute('SELECT max(pos) FROM site_page WHERE parent_id=? AND site_id=?', (np_, sid)).fetchone()[0] or 0) + 1, pid)); _renumber(c, sid, par)
    elif act == 'out':
        if not par: return False
        g = get_page(c, sid, par); gp = g['parent_id'] if g else 0
        c.execute('UPDATE site_page SET pos=pos+1 WHERE site_id=? AND parent_id=? AND pos>?', (sid, gp, g['pos'] if g else 0)); c.execute('UPDATE site_page SET parent_id=?,pos=? WHERE id=?', (gp, (g['pos'] if g else 0) + 1, pid))
        _renumber(c, sid, par); _renumber(c, sid, gp)
    else: return False
    touch(c, sid); return True


# ---------- ασφαλή αρχεία (μπλοκ file) ----------
def safe_file(root, rel):
    """rel σχετικό μέσα στο data_root -> (Path, '') ή (None, λόγος). Όχι symlink/κρυφά/..., γνωστές καταλήξεις, ≤10 MB."""
    rel = (rel or '').strip().replace('\\', '/').lstrip('/')
    if rel.startswith('files/'): rel = rel[6:]
    if not rel or '..' in rel.split('/') or any(x.startswith('.') or x.startswith('_') for x in rel.split('/')): return None, 'μη επιτρεπτή διαδρομή'
    p = pathlib.Path(root) / rel
    if p.suffix.lower() not in FILE_EXT: return None, 'μη επιτρεπτός τύπος αρχείου (pdf, png, jpg, svg, txt, json)'
    try:
        if p.is_symlink() or not p.is_file(): return None, 'το αρχείο δεν υπάρχει'
        if not p.resolve().is_relative_to(pathlib.Path(root).resolve()): return None, 'εκτός data_root'
        if p.stat().st_size > MAX_FILE: return None, 'πολύ μεγάλο αρχείο (όριο 10 MB)'
    except OSError: return None, 'το αρχείο δεν διαβάζεται'
    return p, ''


def flat_name(rel, taken):
    stem = re.sub(r'[^A-Za-z0-9._-]+', '-', pathlib.PurePosixPath(rel).stem).strip('-')[:40] or 'arxeio'; ext = pathlib.PurePosixPath(rel).suffix.lower(); n, nm = 1, f'file-{stem}{ext}'
    while nm in taken and taken[nm] != rel: n += 1; nm = f'file-{stem}-{n}{ext}'
    return nm


# ---------- απόδοση ----------
class Ctx:
    """Κοινή κατάσταση απόδοσης. mode='export': σύνδεσμοι σε αρχεία zip· mode='preview': σύνδεσμοι στις διαδρομές /sites/<id>/…"""
    def __init__(self, c, site, root, domains, mode='export'):
        self.c, self.site, self.root, self.domains, self.mode = c, site, root, domains, mode
        self.rs = rows(c, site['id']); self.ord = order(self.rs); self.vis = [(p, d) for p, d in self.ord if not p['hidden'] and self._shown(p)]
        self.slug_of = {p['slug']: p for p, _ in self.vis}; self.files, self.decks, self.warn = {}, {}, []

    def _shown(self, p):
        by = {r['id']: r for r in self.rs}; n = p['parent_id']; k = 0
        while n and n in by and k < 10:
            if by[n]['hidden']: return False
            n = by[n]['parent_id']; k += 1
        return True

    def href(self, p):
        return p['slug'] + '.html' if self.mode == 'export' else f"/sites/{self.site['id']}/view/{p['slug']}"

    def deck_href(self, did): return f'deck-{did}.html' if self.mode == 'export' else f"/sites/{self.site['id']}/deck/{did}"
    def file_href(self, rel, name): return name if self.mode == 'export' else f"/sites/{self.site['id']}/file?p={html.escape(rel, quote=True)}"

    def link(self, href):
        m = re.match(r'^thilek://page/([a-z0-9-]{1,50})$', href)
        p = self.slug_of.get(m.group(1)) if m else None
        return self.href(p) if p else None

    def home(self):
        h = self.site['opts']['home']; vp = [p for p, _ in self.vis]
        return next((p for p in vp if p['id'] == h), None) or next((p for p in vp if p['kind'] == 'page'), None) or (vp[0] if vp else None)


def _md(ctx, text): return render_md(text, '', links=ctx.link, embed_root=ctx.root)


def quiz_card(c, qid, ctx, w):
    z = c.execute('SELECT * FROM quiz WHERE id=?', (qid,)).fetchone()
    if not z: w.append(f'quiz-ref: δεν υπάρχει quiz με αριθμό {qid}'); return f"<p class=warn>⚠ Δεν υπάρχει quiz με αριθμό {qid}.</p>"
    its = c.execute('SELECT * FROM quiz_item WHERE quiz_id=? ORDER BY pos', (qid,)).fetchall()
    if not its: w.append(f'quiz-ref: το quiz «{z["name"]}» είναι κενό'); return f"<p class=warn>⚠ Το quiz «{E(z['name'])}» είναι κενό.</p>"
    from .quizzes import LET, ans_text, opts_of
    out = []
    for n, r in enumerate(its, 1):
        if r['use_image']: w.append(f'quiz-ref {qid}: το στοιχείο {n} χρησιμοποιεί εικόνα από το PDF — η εικόνα ΔΕΝ περιλαμβάνεται στο στιγμιότυπο')
        head = f"<div><span class=num>{n}.</span> <b>{md_text(r['stem'])}</b> <small>({r['points']:g} μον.)</small></div>"
        if r['kind'] == 'tf': body = f"<div class=opts><label><input type=radio name=q{r['id']} value='Σωστό'> Σωστό</label> <label><input type=radio name=q{r['id']} value='Λάθος'> Λάθος</label></div>"
        elif r['kind'] == 'mcq': body = "<div class=opts>" + ''.join(f"<div><label><input type=radio name=q{r['id']} value='{i}'> {LET[i] if i < len(LET) else i + 1}. {md_text(o)}</label></div>" for i, o in enumerate(opts_of(r))) + '</div>'
        else: body = f"<details><summary>Απάντηση</summary><div>{md_text(r['answer'])}</div></details>"
        fb = (f"<div class=fb hidden>Σωστή απάντηση: <b>{md_text(ans_text(r))}</b>{' — ' + md_text(r['feedback']) if r['feedback'] else ''}</div>" if r['kind'] != 'free' else (f"<div class=fb hidden>{md_text(r['feedback'])}</div>" if r['feedback'] else ''))
        out.append(f"<div class='q qi' data-kind='{E(r['kind'])}' data-answer='{E(r['answer'] or '', quote=True)}' data-points='{r['points']:g}'>{head}{body}{fb}</div>")
    ctx.has_quiz = True
    return (f"<section class=sqw><h3>{E(z['name'])}</h3>" + (f"<p>{E(z['description'])}</p>" if z['description'] else '') + ''.join(out)
            + "<div class=bar><button type=button class=sq-check>Έλεγχος απαντήσεων</button> <button type=button class=sq-reset>Καθαρισμός</button> <b class=sq-score></b></div></section>")


SQ_JS = ("(function(){var ws=document.querySelectorAll('.sqw');Array.prototype.forEach.call(ws,function(w){var items=function(){return Array.prototype.slice.call(w.querySelectorAll('.qi'))};"
         "var sc=w.querySelector('.sq-score');w.querySelector('.sq-check').addEventListener('click',function(){var got=0,total=0,done=0;items().forEach(function(it){var k=it.dataset.kind,a=it.dataset.answer,p=parseFloat(it.dataset.points)||0;"
         "it.classList.remove('ok','bad');var fb=it.querySelector('.fb');if(fb)fb.hidden=false;if(k==='free'){var d=it.querySelector('details');if(d)d.open=true;return;}total+=p;"
         "var s=it.querySelector('input[type=radio]:checked');if(!s){it.classList.add('bad');return;}done++;if(s.value===a){got+=p;it.classList.add('ok');}else it.classList.add('bad');});"
         "sc.textContent='Βαθμολογήσιμα: '+got+' / '+total+' μονάδες ('+done+' απαντημένα)';});"
         "w.querySelector('.sq-reset').addEventListener('click',function(){items().forEach(function(it){it.classList.remove('ok','bad');it.querySelectorAll('input[type=radio]').forEach(function(r){r.checked=false});"
         "var fb=it.querySelector('.fb');if(fb)fb.hidden=true;var d=it.querySelector('details');if(d)d.open=false;});sc.textContent='';});});})();")


def body_html(ctx, p, body=None):
    """Σώμα σελίδας -> (HTML, προειδοποιήσεις)."""
    text = p['body'] if body is None else body; bl, w = deckmd.parse(text or '', DIRS); out = []
    if len(text or '') > LIM['body']: w.append('το σώμα ξεπερνά το όριο μεγέθους')
    for b in bl:
        t = b['t']
        if t == 'md': out.append(_md(ctx, b['text']))
        elif t == 'cols': out.append("<div class=cols>" + ''.join(f"<div class=col>{_md(ctx, x)}</div>" for x in b['cols']) + '</div>')
        elif t == 'quiz':
            it, err = deckmd.quiz_item(b['yaml'])
            if err: w.append('quiz: ' + err); out.append(f"<p class=warn>⚠ quiz: {E(err)}</p>")
            else:
                ans = X.answer_text(it); opts = ''
                if it['type'] == 'mcq': opts = '<ol class=opts>' + ''.join(f"<li>{X.LET[i] if i < len(X.LET) else i + 1}. {md_text(o)}</li>" for i, o in enumerate(it.get('options') or [])) + '</ol>'
                elif it['type'] == 'matching': opts = '<ul>' + ''.join(f"<li>{md_text(a)}</li>" for a, _ in it.get('pairs') or []) + '</ul>'
                out.append(f"<div class='q'><div><b>{md_text(it['stem'])}</b> <small>({it.get('points', 1):g} μον.)</small></div>{opts}<details><summary>Απάντηση</summary><div>{md_text(ans)}"
                           + (f"<br><small>{md_text(it['feedback'])}</small>" if it.get('feedback') else '') + '</div></details></div>')
        elif t == 'embed':
            url, params = b['url'], b.get('params')
            if not deckmd.RE_URL.match(url): w.append(f"embed: μη επιτρεπτός σύνδεσμος «{url[:60]}» (μόνο https)")
            else:
                ok, _, why = EM.check(EM.to_src(url, params, ctx.domains), ctx.domains)
                if not ok: w.append('embed: ' + why + ' — θα εμφανιστεί ως σύνδεσμος')
            ctx.has_embed = True; out.append(EM.render(url, b['caption'], params, ctx.domains, 'click'))
        elif t == 'quiz-ref':
            if not b['arg'].isdigit(): w.append('quiz-ref: χρειάζεται αριθμός quiz (::: quiz-ref 3)'); out.append("<p class=warn>⚠ quiz-ref: λείπει ο αριθμός του quiz.</p>")
            else: out.append(quiz_card(ctx.c, int(b['arg']), ctx, w))
        elif t == 'deck-ref':
            toks = b['arg'].split(None, 1)
            if not toks or not toks[0].isdigit(): w.append('deck-ref: χρειάζεται αριθμός παρουσίασης (::: deck-ref 5)'); out.append("<p class=warn>⚠ deck-ref: λείπει ο αριθμός της παρουσίασης.</p>"); continue
            did = int(toks[0]); d = D.get(ctx.c, did); cap = (toks[1] if len(toks) > 1 else '') or (b['text'].strip().split('\n')[0] if b['text'].strip() else '')
            if not d: w.append(f'deck-ref: δεν υπάρχει παρουσίαση με αριθμό {did}'); out.append(f"<p class=warn>⚠ Δεν υπάρχει παρουσίαση με αριθμό {did}.</p>"); continue
            n = D.count(ctx.c, did)
            if not [s for s in D.slides(ctx.c, did) if not s['hidden']]: w.append(f'deck-ref {did}: η παρουσίαση δεν έχει εμφανίσιμες διαφάνειες'); out.append(f"<p class=warn>⚠ Η παρουσίαση «{E(d['name'])}» δεν έχει εμφανίσιμες διαφάνειες.</p>"); continue
            ctx.decks[did] = d
            out.append(f"<a class=card href='{E(ctx.deck_href(did), quote=True)}' target=_blank rel='noopener'><b>▶ {E(cap or d.get('title') or d['name'])}</b><small>Παρουσίαση · {n} διαφάνειες (στιγμιότυπο· ανοίγει σε νέα καρτέλα)</small></a>")
        elif t == 'file':
            toks = b['arg'].split(None, 1); rel = toks[0] if toks else ''; cap = (toks[1] if len(toks) > 1 else '') or (b['text'].strip().split('\n')[0] if b['text'].strip() else '')
            fp, why = safe_file(ctx.root, rel)
            if not fp: w.append(f'file: «{rel[:60]}»: {why}'); out.append(f"<p class=warn>⚠ file: {E(why)} ({E(rel[:60])})</p>"); continue
            rel = fp.resolve().relative_to(pathlib.Path(ctx.root).resolve()).as_posix(); nm = flat_name(rel, {k: v[0] for k, v in ctx.files.items()}); ctx.files[nm] = (rel, fp)
            ext = fp.suffix.lower()
            if ext in ('.png', '.jpg', '.jpeg', '.svg'):
                from .mdmath import img_data
                u = img_data(ctx.root, rel); out.append(f"<figure><img src='{E(u or '', quote=True)}' alt='{E(cap, quote=True)}' style='max-width:100%'>" + (f"<figcaption>{E(cap)}</figcaption>" if cap else '') + '</figure>')
            else: out.append(f"<a class=card href='{ctx.file_href(rel, nm)}' target=_blank rel='noopener'><b>📎 {E(cap or fp.name)}</b><small>{E(fp.suffix[1:].upper())} · {fp.stat().st_size // 1024} KB</small></a>")
        elif t == 'callout':
            toks = b['arg'].split(None, 1); k = toks[0].lower() if toks and toks[0].lower() in CALLOUTS else 'note'; title = toks[1] if toks and toks[0].lower() in CALLOUTS and len(toks) > 1 else (toks[0] if toks and toks[0].lower() not in CALLOUTS else CALLOUTS[k][0])
            if toks and toks[0].lower() not in CALLOUTS: w.append(f'callout: άγνωστο είδος «{toks[0][:20]}» (note, tip, warning, danger) — χρησιμοποιήθηκε «note»'); title = b['arg']
            out.append(f"<aside class='callout co-{k}'><b>{E(title)}</b>{_md(ctx, b['text'])}</aside>")
    return ''.join(out), w


CSS = ("*{box-sizing:border-box}body{margin:0;font:17px/1.6 system-ui,'Segoe UI',sans-serif;background:var(--bg);color:var(--fg)}a{color:var(--accent)}.layout{display:grid;grid-template-columns:minmax(200px,260px) 1fr;min-height:100vh}"
       "nav.menu{background:var(--card);border-right:1px solid var(--line);padding:1rem .8rem;position:sticky;top:0;align-self:start;max-height:100vh;overflow:auto}nav.menu .st{font-weight:700;color:var(--head);display:block;margin-bottom:.6rem;text-decoration:none;font-size:1.1em}"
       "nav.menu ul{list-style:none;margin:0;padding:0}nav.menu li a{display:block;padding:.25rem .5rem;border-radius:6px;text-decoration:none;color:var(--fg)}nav.menu li a:hover{background:var(--line)}nav.menu li a.cur{background:var(--accent);color:#fff}"
       "nav.menu li.sec>span{display:block;padding:.35rem .5rem 0;font-weight:700;font-size:.85em;text-transform:uppercase;letter-spacing:.03em;opacity:.75}nav.menu ul ul{margin-left:.8rem}"
       "main{padding:1.5rem 2rem;max-width:56rem}h1,h2,h3{color:var(--head);line-height:1.25}.crumb{font-size:.85em;opacity:.75;margin-bottom:.4rem}.cols{display:flex;gap:1.2rem;flex-wrap:wrap}.col{flex:1;min-width:14rem}"
       "img{max-width:100%}table{border-collapse:collapse}td,th{border:1px solid var(--line);padding:.3rem .6rem}pre{background:var(--card);border:1px solid var(--line);padding:.6rem;overflow:auto;border-radius:8px}code{font-family:ui-monospace,Consolas,monospace}"
       ".card{display:block;border:1px solid var(--line);background:var(--card);border-radius:10px;padding:.7rem 1rem;margin:.6rem 0;text-decoration:none;color:var(--fg)}.card b{display:block;color:var(--head)}.card small{opacity:.75}"
       ".callout{border-left:5px solid var(--co);background:var(--card);border-radius:6px;padding:.5rem 1rem;margin:.8rem 0;border:1px solid var(--line);border-left:5px solid var(--co)}.callout>b{color:var(--co)}"
       ".co-note{--co:#3b6ea5}.co-tip{--co:#2e9e5b}.co-warning{--co:#b45309}.co-danger{--co:#c0392b}.q{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:.6rem .9rem;margin:.6rem 0}"
       ".qi.ok{outline:3px solid #2e9e5b}.qi.bad{outline:3px solid #d9534f}.fb{margin-top:.4rem;font-size:.92em}.opts label{cursor:pointer}.bar{margin:.6rem 0}button{font:inherit;padding:.3rem .8rem;cursor:pointer}"
       ".warn{color:#b45309}.emb{position:relative;width:100%;margin:.6rem 0;border:1px dashed var(--line);border-radius:8px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.3rem;padding:1rem;min-height:8rem}.emb iframe{border:0;width:100%;height:100%;min-height:22rem}"
       ".pn{display:flex;justify-content:space-between;gap:1rem;margin:2rem 0 1rem;font-size:.95em}footer.sf{padding:1rem 2rem;font-size:.85em;opacity:.7;border-top:1px solid var(--line)}"
       "@media(max-width:760px){.layout{grid-template-columns:1fr}nav.menu{position:static;max-height:none;border-right:0;border-bottom:1px solid var(--line)}main{padding:1rem}}@media print{nav.menu,.pn,.bar{display:none}.layout{display:block}}")


def menu_html(ctx, cur):
    def lvl(parent):
        items = []
        for p, d in ctx.vis:
            if (p['parent_id'] if p['parent_id'] in {x['id'] for x, _ in ctx.vis} else 0) != parent: continue
            sub = lvl(p['id'])
            if p['kind'] == 'section': items.append(f"<li class=sec><span>{E(p['title'])}</span>{sub}</li>")
            else: items.append(f"<li><a href='{E(ctx.href(p), quote=True)}'{' class=cur aria-current=page' if cur and p['id'] == cur['id'] else ''}>{E(p['title'])}</a>{sub}</li>")
        return f"<ul>{''.join(items)}</ul>" if items else ''
    return lvl(0)


def page_html(ctx, p, body=None, title=None, kind=None, note=''):
    """Πλήρης αυτόνομη σελίδα HTML της p (με μενού, ψιλά γράμματα, προηγούμενη/επόμενη). body/title/kind: αντικαθιστούν τα αποθηκευμένα (ζωντανή προεπισκόπηση). -> (html, warnings)."""
    ctx.has_quiz = ctx.has_embed = False; site = ctx.site; th = THEMES[site['theme']][1]
    p = dict(p, kind=kind or p['kind'], title=(title if title is not None else p['title']))
    inner, w = body_html(ctx, p, body); text = (body if body is not None else p['body']) or ''
    if p['kind'] == 'section' and not inner.strip():
        kids = [x for x, _ in ctx.vis if x['parent_id'] == p['id']]
        inner = ''.join(f"<a class=card href='{E(ctx.href(k), quote=True)}'><b>{E(k['title'])}</b></a>" for k in kids) or '<p><i>Η ενότητα δεν έχει σελίδες.</i></p>'
    math = bool(re.search(r'\$|\\\(|\\\[', inner)); a = X.assets() if math else None
    vp = [x for x, _ in ctx.vis if x['kind'] == 'page']; i = next((k for k, x in enumerate(vp) if x['id'] == p['id']), -1)
    pn = ''
    if i >= 0 and p['kind'] == 'page':
        pr = f"<a href='{E(ctx.href(vp[i - 1]), quote=True)}'>← {E(vp[i - 1]['title'])}</a>" if i > 0 else '<span></span>'; nx = f"<a href='{E(ctx.href(vp[i + 1]), quote=True)}'>{E(vp[i + 1]['title'])} →</a>" if i + 1 < len(vp) else '<span></span>'
        pn = f"<div class=pn>{pr}{nx}</div>"
    by = {x['id']: x for x, _ in ctx.vis}; trail = []; n = p['parent_id']
    while n in by and len(trail) < MAX_DEPTH: trail.insert(0, by[n]['title']); n = by[n]['parent_id']
    crumb = f"<div class=crumb>{' › '.join(E(t) for t in trail)}</div>" if trail else ''
    home = ctx.home(); st = f"<a class=st href='{E(ctx.href(home), quote=True)}'>{E(site['title'] or site['name'])}</a>" if home else f"<span class=st>{E(site['title'] or site['name'])}</span>"
    foot = f"<footer class=sf>{E(site['opts']['footer'])}</footer>" if site['opts']['footer'] else ''
    css = ':root{' + ''.join(f'--{k}:{v};' for k, v in th.items()) + '}' + CSS
    frames = EM.csp_frames(ctx.domains)
    csp = f"default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:; media-src data:; frame-src {frames}; base-uri 'none'; form-action 'none'"
    js = (SQ_JS if ctx.has_quiz else '') + (EM.CLICK_JS if ctx.has_embed else '')
    scripts = ''
    if math: scripts += '<script>' + a['katex_js'].replace('</script', '<\\/script') + '</script><script>' + a['auto_js'].replace('</script', '<\\/script') + "</script><script>try{renderMathInElement(document.querySelector('main'),{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false},{left:'\\\\(',right:'\\\\)',display:false},{left:'\\\\[',right:'\\\\]',display:true}],throwOnError:false});}catch(e){}</script>"
    if js: scripts += '<script>' + js + '</script>'
    banner = f"<div style=\"position:sticky;top:0;z-index:9;background:#fff3cd;color:#664d03;font:13px sans-serif;padding:4px 8px\">⚠ {E(note)[:600]}</div>" if note else ''
    h = (f"<!doctype html><html lang=el><head><meta charset=utf-8><meta http-equiv='Content-Security-Policy' content=\"{E(csp)}\"><meta name=viewport content='width=device-width,initial-scale=1'><title>{E(p['title'])} · {E(site['title'] or site['name'])}</title>"
         f"<style>{css}</style>" + ('<style>' + a['katex_css'].replace('</style', '<\\/style') + '</style>' if math else '') + f"</head><body>{banner}<div class=layout><nav class=menu aria-label='Μενού'>{st}{menu_html(ctx, p)}</nav><main>{crumb}<h1>{E(p['title'])}</h1>{inner}{pn}</main></div>{foot}{scripts}</body></html>")
    return h, w


# ---------- εξαγωγή ----------
def build_zip(c, sid, domains=()):
    """-> (zip bytes, όνομα, μοντέλο dict με warnings, files). ValueError αν δεν υπάρχουν εμφανίσιμες σελίδες ή το πακέτο είναι πολύ μεγάλο."""
    s = get(c, sid)
    if not s: raise ValueError('Δεν υπάρχει αυτό το site.')
    root = config.load()['data_root']; ctx = Ctx(c, s, root, list(domains), 'export')
    if not ctx.vis: raise ValueError('Το site δεν έχει εμφανίσιμες σελίδες.')
    files, warns, deck_ids = {}, [], {}
    for p, _ in ctx.vis:
        h, w = page_html(ctx, p); files[p['slug'] + '.html'] = h.encode('utf-8'); warns += [f"{p['title']}: {x}" for x in w]; deck_ids.update(ctx.decks)
        for nm, (rel, fp) in ctx.files.items():
            if fp.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.svg'): files.setdefault(nm, fp.read_bytes())
    home = ctx.home(); files['index.html'] = files[home['slug'] + '.html']
    for did, d in deck_ids.items():
        files[f'deck-{did}.html'] = DX.reveal(d, D.slides(c, did), root, publish=True, domains=list(domains)).encode('utf-8')
    if sum(len(v) for v in files.values()) > MAX_TOTAL: raise ValueError('Το πακέτο ξεπερνά το όριο μεγέθους (60 MB).')
    model = {'title': s['title'] or s['name'], 'theme': s['theme'], 'home': home['slug'] + '.html', 'exported': now(), 'warnings': warns,
             'pages': [{'slug': p['slug'], 'file': p['slug'] + '.html', 'title': p['title'], 'kind': p['kind'], 'depth': d, 'parent': next((x['slug'] for x, _ in ctx.vis if x['id'] == p['parent_id']), '')} for p, d in ctx.vis],
             'decks': [{'id': k, 'file': f'deck-{k}.html', 'title': v.get('title') or v['name']} for k, v in deck_ids.items()]}
    files['data.json'] = json.dumps(model, ensure_ascii=False, indent=1).encode('utf-8')
    readme = (f"{model['title']}\nΕξήχθη από το TH-ILEK: {model['exported']}\n\nΑνοίγεις το index.html σε οποιονδήποτε browser (και χωρίς δίκτυο). Οι σελίδες είναι αυτόνομα αρχεία· οι παρουσιάσεις και τα quiz είναι στιγμιότυπο της ώρας της εξαγωγής.\n"
              "Τα ενσωματωμένα βίντεο/προσομοιώσεις (embed) φορτώνουν από το διαδίκτυο μόνο αν πατήσεις «Φόρτωση».\n")
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items(): z.writestr(n, d)
        z.writestr('README.txt', readme)
    return b.getvalue(), DX.slug(model['title']) + '-site.zip', model
