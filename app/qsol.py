"""Λύσεις εκπαιδευτικού: parser των αρχείων <ID>.<θέμα>-<υπ>.md (schema 2) και σάρωση φακέλων -> πίνακας qsolution.
Καθαρό module (χωρίς FastAPI)· το χρησιμοποιούν η εφαρμογή και το tools/rebuild.py. Κακό αρχείο: ποτέ exception, μόνο προειδοποιήσεις."""
import hashlib, json, pathlib, re
import yaml
from .textnorm import norm
from .mdmath import fences, IMG

FNAME = re.compile(r'^(\d+)\.(\d+(?:-\d+)+)\.md$')
DIRS = ('05_LYSEIS', '04_TRAPEZA/orig')          # με αυτή τη σειρά: τα του orig/ υπερισχύουν
SECTIONS = (('statement', 'εκφωνηση', 'Εκφώνηση'), ('iep', 'ενδεικτικη λυση', 'Ενδεικτική λύση ΙΕΠ'),
            ('teacher', 'λυση εκπαιδευτικου', 'Λύση εκπαιδευτικού'), ('refs', 'παραπομπες', 'Παραπομπές'))
TITLES = {k: t for k, _, t in SECTIONS}
QTYPES = {'mcq': 'Πολλαπλής επιλογής', 'true_false': 'Σωστό/Λάθος', 'short': 'Σύντομη απάντηση', 'numeric': 'Αριθμητική', 'fill': 'Συμπλήρωση κενών', 'matching': 'Αντιστοίχιση'}
FM_REQ = ('id', 'iep_id', 'sub', 'course', 'points', 'qtype', 'status', 'schema')
STATUS = ('draft', 'reviewed')

def name_key(name):
    """'17771.2-1.md' -> ('17771', '2.1')· αλλιώς None."""
    m = FNAME.match(name)
    return (m.group(1), m.group(2).replace('-', '.')) if m else None

def sort_key(item_id, qcode):
    return (int(item_id) if str(item_id).isdigit() else 0, [int(x) if x.isdigit() else 0 for x in str(qcode).split('.')])

def _num(v):
    if isinstance(v, bool): return None
    if isinstance(v, (int, float)): return v
    try: return float(str(v).replace(',', '.'))
    except (TypeError, ValueError): return None

def split_front(text):
    t = (text or '').lstrip('﻿').replace('\r\n', '\n')
    if not t.startswith('---\n'): return None, t
    m = re.search(r'^---[ \t]*$', t[4:], re.M)
    if not m: return None, t
    return t[4:4 + m.start()], t[4 + m.end():]

def split_sections(body, warn):
    """Ενότητες «## Τίτλος» (οι γραμμές «---» είναι διαχωριστικά)· αγνοεί ό,τι είναι μέσα σε fenced code."""
    secs, cur, buf, stray = {}, None, [], []
    def close():
        if cur is None: return
        k = cur[0]
        if k in secs: warn.append(f'διπλή ενότητα «{cur[1]}»'); secs[k] += '\n\n' + '\n'.join(buf).strip()
        else: secs[k] = '\n'.join(buf).strip()
    for seg, code in fences(body):
        if code:
            (buf if cur else stray).append(seg); continue
        for line in seg.split('\n'):
            if re.match(r'^---[ \t]*$', line): continue
            m = re.match(r'^##[ \t]+(.+?)[ \t#]*$', line)
            if m:
                close(); title = m.group(1); n = norm(title)
                key = next((k for k, pre, _ in SECTIONS if n.startswith(norm(pre))), None)
                if not key: warn.append(f'άγνωστη ενότητα «{title}»'); key = 'x:' + title
                cur, buf = (key, title), []
                continue
            (buf if cur else stray).append(line)
    close()
    if '\n'.join(stray).strip(): warn.append('κείμενο εκτός ενότητας (πριν το πρώτο «## »)')
    return secs

def teacher_split(text):
    """Λύση εκπαιδευτικού -> (μέρη [{title, body}], κείμενα yaml του Quiz). Νέο μέρος σε κάθε «### » και σε κάθε γραμμή «--»."""
    parts, cur, buf, yamls, quiz = [], '', [], [], False
    def close():
        b = '\n'.join(buf).strip()
        if b and not quiz: parts.append({'title': cur, 'body': b})
    for seg, code in fences(text or ''):
        if code:
            if quiz:
                lines = seg.split('\n'); info = lines[0].strip().lstrip('`~').strip().lower()
                if info in ('yaml', 'yml'): yamls.append('\n'.join(lines[1:-1] if len(lines) > 1 and re.match(r'^\s*(`{3,}|~{3,})\s*$', lines[-1]) else lines[1:]))
            else: buf.append(seg)
            continue
        for line in seg.split('\n'):
            m = re.match(r'^###[ \t]+(.+?)[ \t#]*$', line)
            if m: close(); cur, buf = m.group(1), []; quiz = norm(cur).startswith('quiz'); continue
            if line.strip() == '--': close(); buf = []; continue
            buf.append(line)
    close()
    return parts, yamls

def check_item(d, n):
    """Έλεγχος/κανονικοποίηση ενός στοιχείου quiz. Επιστρέφει dict με λίστα 'err' (κενή = έγκυρο)."""
    err = []
    if not isinstance(d, dict): return {'n': n, 'type': '', 'stem': '', 'err': ['το στοιχείο δεν είναι λεξικό YAML']}
    t = str(d.get('type') or '').strip()
    it = {'n': n, 'type': t, 'stem': str(d.get('stem') or '').strip(), 'feedback': str(d.get('feedback') or '').strip(), 'err': []}
    if t not in QTYPES: err.append(f'άκυρος τύπος «{t}» (επιτρέπονται: {", ".join(QTYPES)})')
    if not it['stem']: err.append('λείπει το stem')
    pts = _num(d.get('points', 1)); it['points'] = pts if pts is not None and pts >= 0 else 1
    if d.get('points') is not None and (pts is None or pts < 0): err.append('άκυρο points')
    img = d.get('image')
    if img:
        if isinstance(img, str) and IMG.match(img) and '..' not in img: it['image'] = img
        else: err.append(f'μη ασφαλές όνομα εικόνας «{img}» (images/<ascii>.png|jpg|svg)')
    a = d.get('answer')
    if t == 'mcq':
        opts = d.get('options')
        if not isinstance(opts, list) or len(opts) < 2: err.append('το mcq θέλει options (λίστα με ≥2)'); opts = opts if isinstance(opts, list) else []
        it['options'] = [str(o) for o in opts]
        if isinstance(a, bool) or not (isinstance(a, int) or (isinstance(a, str) and a.strip().isdigit())): err.append('το answer του mcq πρέπει να είναι δείκτης 0-based')
        else:
            a = int(a)
            if not 0 <= a < len(opts): err.append(f'answer {a} εκτός ορίων (0..{len(opts) - 1})')
            it['answer'] = a
    elif t == 'true_false':
        if isinstance(a, str): a = {'true': True, 'false': False, 'σωστο': True, 'λαθος': False, 'σ': True, 'λ': False}.get(norm(a.strip()), a)
        if not isinstance(a, bool): err.append('το answer του true_false πρέπει να είναι true/false')
        else: it['answer'] = a
    elif t == 'numeric':
        v = _num(a)
        if v is None: err.append('το answer του numeric πρέπει να είναι αριθμός')
        else: it['answer'] = v
        tol = _num(d.get('tolerance', 0))
        if tol is None or tol < 0: err.append('άκυρο tolerance'); tol = 0
        it['tolerance'] = tol; it['unit'] = str(d.get('unit') or '').strip()
    elif t in ('short', 'fill'):
        vals = a if isinstance(a, list) else [a]
        vals = [str(x).strip() for x in vals if x is not None and str(x).strip()]
        if not vals: err.append(f'λείπει το answer του {t}')
        it['answer'] = vals
        if t == 'fill' and '___' not in it['stem']: it['warn'] = 'χωρίς «___» στο stem: στο Moodle θα γίνει σύντομη απάντηση'
    elif t == 'matching':
        pairs = d.get('pairs')
        ok = isinstance(pairs, list) and len(pairs) >= 2 and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in pairs)
        if not ok: err.append('το matching θέλει pairs: λίστα ≥2 ζευγών [αριστερό, δεξί]')
        it['pairs'] = [[str(p[0]), str(p[1])] for p in pairs] if ok else []
    it['err'] = err
    return it

def parse(text, filename=''):
    """Κείμενο αρχείου -> {item_id, qcode, fm, sections, quiz, warnings, status}. Δεν σηκώνει exception για κακό περιεχόμενο."""
    warn = []; key = name_key(pathlib.Path(filename).name) if filename else None
    raw_fm, body = split_front(text)
    fm = {}
    if raw_fm is None: warn.append('λείπει το front matter YAML (--- … --- στην αρχή)')
    else:
        try:
            fm = yaml.safe_load(raw_fm) or {}
            if not isinstance(fm, dict): warn.append('το front matter δεν είναι λεξικό YAML'); fm = {}
        except yaml.YAMLError as ex:
            warn.append('σφάλμα YAML στο front matter: ' + ' '.join(str(ex).split())[:160])
    for k in FM_REQ:
        if k not in fm: warn.append(f'λείπει το πεδίο «{k}» στο front matter')
    item_id, qcode = key or (str(fm.get('iep_id') or ''), str(fm.get('sub') or ''))
    if key:
        stem = pathlib.Path(filename).name[:-3]
        if 'id' in fm and str(fm['id']) != stem: warn.append(f'id «{fm["id"]}» ≠ όνομα αρχείου «{stem}»')
        if 'sub' in fm and str(fm['sub']) != qcode: warn.append(f'sub «{fm["sub"]}» ≠ ερώτημα από το όνομα «{qcode}»')
        if 'iep_id' in fm and str(fm['iep_id']) != item_id: warn.append(f'iep_id «{fm["iep_id"]}» ≠ θέμα από το όνομα «{item_id}»')
    elif filename: warn.append('όνομα αρχείου εκτός μορφής <ID>.<θέμα>-<υπ>.md')
    if 'schema' in fm and fm.get('schema') != 2: warn.append(f'schema {fm.get("schema")} (αναμένεται 2)')
    if 'points' in fm and _num(fm.get('points')) is None: warn.append('το points δεν είναι αριθμός')
    st = str(fm.get('status') or 'draft')
    if st not in STATUS: warn.append(f'άγνωστο status «{st}» (draft|reviewed)'); st = 'draft'
    secs = split_sections(body, warn)
    for k, _, title in SECTIONS:
        if not secs.get(k): warn.append(f'λείπει ή είναι κενή η ενότητα «{title}»')
    parts, yamls = teacher_split(secs.get('teacher', ''))
    quiz = []
    for y in yamls:
        try: docs = [d for d in yaml.safe_load_all(y) if d is not None]
        except yaml.YAMLError as ex:
            quiz.append({'n': len(quiz) + 1, 'type': '', 'stem': '', 'err': ['σφάλμα YAML: ' + ' '.join(str(ex).split())[:120]]}); continue
        for d in docs:
            for x in (d if isinstance(d, list) else [d]): quiz.append(check_item(x, len(quiz) + 1))
    if norm(secs.get('teacher', '')).find('### quiz') >= 0 and not quiz: warn.append('η υποενότητα Quiz δεν έχει μπλοκ ```yaml')
    for q in quiz:
        for e in q['err']: warn.append(f'Quiz στοιχείο {q["n"]}: {e}')
        if q.get('warn'): warn.append(f'Quiz στοιχείο {q["n"]}: {q["warn"]}')
    sections = {k: secs.get(k, '') for k in TITLES}; sections['teacher_parts'] = parts
    if not (sections['statement'] or sections['iep'] or sections['teacher']): st = 'error'
    return {'item_id': item_id, 'qcode': qcode, 'fm': fm, 'sections': sections, 'quiz': quiz, 'warnings': warn, 'status': st}

# ---------- σάρωση ----------
def course_dirs(root, course=None):
    root = pathlib.Path(root)
    if not root.is_dir(): return []
    names = [course] if course else sorted(p.name for p in root.iterdir() if p.is_dir())
    return [root / n for n in names if any((root / n / d).is_dir() for d in DIRS)]

def find_files(cdir, warn):
    found = {}
    for d in DIRS:
        for p in sorted((cdir / d).glob('*.md')) if (cdir / d).is_dir() else []:
            k = name_key(p.name)
            if not k:
                if p.name[:1].isdigit(): warn.append(f'{cdir.name}/{d}/{p.name}: όνομα εκτός μορφής <ID>.<θέμα>-<υπ>.md (αγνοήθηκε)')
                continue
            if k in found: warn.append(f'{cdir.name}/{d}/{p.name}: υπάρχει και στο {DIRS[0]}· χρησιμοποιείται αυτό')
            found[k] = p
    return found

def scan(c, data_root, course=None):
    """Σαρώνει <μάθημα>/04_TRAPEZA/orig/ (και 05_LYSEIS/) και ξαναγράφει τον πίνακα qsolution για τα μαθήματα αυτά.
    Επιστρέφει σύνοψη {files, linked, orphans, errors, warnings: ['διαδρομή: μήνυμα', ...]}."""
    root = pathlib.Path(data_root); res = {'files': 0, 'linked': 0, 'orphans': 0, 'errors': 0, 'warnings': []}
    dirs = course_dirs(root, course)
    if course: c.execute("DELETE FROM qsolution WHERE relpath LIKE ? ESCAPE '\\'", (course.replace('_', '\\_').replace('%', '\\%') + '/%',))
    else: c.execute('DELETE FROM qsolution')
    for cdir in dirs:
        for (item_id, qcode), p in sorted(find_files(cdir, res['warnings']).items(), key=lambda kv: sort_key(*kv[0])):
            rel = p.relative_to(root).as_posix()
            try: data = p.read_bytes(); text = data.decode('utf-8-sig')
            except (OSError, UnicodeDecodeError) as ex:
                res['warnings'].append(f'{rel}: δεν διαβάζεται ως UTF-8 ({type(ex).__name__})'); res['errors'] += 1; continue
            r = parse(text, p.name); w = list(r['warnings'])
            if r['fm'].get('course') and str(r['fm']['course']) != cdir.name: w.append(f'course «{r["fm"]["course"]}» ≠ φάκελος μαθήματος «{cdir.name}»')
            q = c.execute('SELECT id FROM question WHERE item_id=? AND code=?', (item_id, qcode)).fetchone()
            if q: res['linked'] += 1
            else: w.append(f'δεν υπάρχει ερώτημα {qcode} του θέματος {item_id} στη βάση (ορφανό αρχείο)'); res['orphans'] += 1
            res['errors'] += r['status'] == 'error'; res['files'] += 1
            c.execute('INSERT OR REPLACE INTO qsolution(item_id,qcode,question_id,iep_id,sub,relpath,fm,sections,quiz,status,warn,mtime,sha) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (item_id, qcode, q[0] if q else None, str(r['fm'].get('iep_id') or item_id), str(r['fm'].get('sub') or qcode), rel,
                       json.dumps(r['fm'], ensure_ascii=False, default=str), json.dumps(r['sections'], ensure_ascii=False), json.dumps(r['quiz'], ensure_ascii=False),
                       r['status'], json.dumps(w, ensure_ascii=False), p.stat().st_mtime, hashlib.sha256(data).hexdigest()))
            res['warnings'] += [f'{rel}: {x}' for x in w]
    return res

def summary(res):
    return f"λύσεις εκπαιδευτικού: {res['files']} αρχεία, {res['linked']} συνδέθηκαν, {res['orphans']} ορφανά, {res['errors']} άχρηστα, {len(res['warnings'])} προειδοποιήσεις"

# ---------- ανάγνωση ----------
def row_dict(r):
    d = dict(r)
    for k, dflt in (('fm', {}), ('sections', {}), ('quiz', []), ('warn', [])):
        try: d[k] = json.loads(d.get(k) or 'null') or dflt
        except ValueError: d[k] = dflt
    d['base'] = d['relpath'].rsplit('/', 1)[0] if '/' in d['relpath'] else ''
    d['course'] = d['relpath'].split('/', 1)[0]
    return d

def get(c, item_id, qcode):
    r = c.execute('SELECT * FROM qsolution WHERE item_id=? AND qcode=?', (item_id, qcode)).fetchone()
    return row_dict(r) if r else None

def resolver(c, course=''):
    """thilek://statement|solution/<ID>#p=N, thilek://item/<ID>, thilek://book/<σελ> -> πραγματικοί σύνδεσμοι της εφαρμογής."""
    def f(href):
        m = re.match(r'^thilek://(statement|solution|item|book)/([^#?/]+)(?:#p=(\d+))?$', href)
        if not m: return None
        kind, ref, pg = m.groups()
        if kind == 'item': return f'/review/{ref}' if ref.isdigit() else None
        if kind == 'book':
            if not ref.isdigit(): return None
            b = c.execute('SELECT id FROM book WHERE course_code=? ORDER BY id LIMIT 1', (course,)).fetchone() or c.execute('SELECT id FROM book ORDER BY id LIMIT 1').fetchone()
            return f'/book/{b[0]}/{ref}' if b else None
        it = c.execute(f"SELECT {'statement_path' if kind == 'statement' else 'solution_path'} FROM item WHERE id=?", (ref,)).fetchone()
        return f"/files/{it[0]}" + (f'#page={pg}' if pg else '') if it and it[0] else None
    return f
