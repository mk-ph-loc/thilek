"""File browser (0.18.0): προβολή, λήψη, upload, νέος φάκελος, μετονομασία, διαγραφή με κάδο στον φάκελο δεδομένων (data_root).
Αρχή σχεδιασμού: ό,τι μπορεί να χαλάσει το σύστημα ΜΠΛΟΚΑΡΕΤΑΙ με αναλυτική εξήγηση· ό,τι έχει ρίσκο θέλει ρητή επιβεβαίωση·
κάθε διαγραφή και αντικατάσταση πάει στον κάδο (`_kados`) και φαίνεται στο ιστορικό."""
import datetime, mimetypes, os, pathlib, re, shutil, tempfile, zipfile
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from . import config
from .main_auth import auth
from .review import db, page, html, same_origin, fld

router = APIRouter()
TRASH = '_kados'
MAX_UPLOAD = 100 * 1024 * 1024          # ανά αρχείο
MAX_ZIP = 300 * 1024 * 1024             # συνολικά σε λήψη zip
RESERVE = 200 * 1024 * 1024             # ελεύθερος χώρος που πρέπει να μένει στον δίσκο
ALLOWED_EXT = {'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv', 'md', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'json', 'yaml', 'yml', 'pptx', 'odt', 'zip'}
TEXT_EXT = {'md', 'txt', 'csv', 'json', 'yaml', 'yml'}
STD_DIRS = {'02_VIVLIA', '03_YLI', '04_TRAPEZA', '05_LYSEIS', '07_EXAGOGES', 'orig', 'images'}
BADNAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
IEP_FILE = re.compile(r'^\d+(_SOLUTION)?\.(pdf|docx|doc)$', re.I)
SOL_MD = re.compile(r'^(\d+)\.[\d-]+\.md$')
E = html.escape
def box(cls, txt): return f"<div class='note {cls}'>{txt}</div>" if txt else ''

def root() -> str: return os.path.realpath(config.load()['data_root'])

def deny(title, reasons, status=403):
    """Σελίδα άρνησης με αναλυτική εξήγηση (τίποτα δεν έχει αλλάξει)."""
    li = ''.join(f'<li>{r}</li>' for r in reasons)
    body = (f"<h2>⛔ {E(title)}</h2><div class='note bad'><b>Δεν έγινε καμία αλλαγή.</b> Το σύστημα σταμάτησε την ενέργεια για τους παρακάτω λόγους:<ul>{li}</ul></div>"
            "<p><a class=btn href='/fb' data-back>← Πίσω</a></p>")
    r = page(title, body); r.status_code = status; return r

class Refuse(Exception):
    def __init__(self, title, reasons, status=403): self.title, self.reasons, self.status = title, reasons, status

def clean_rel(rel: str) -> str:
    rel = (rel or '').replace('\\', '/').strip('/')
    if '\x00' in rel: raise Refuse('Μη έγκυρη διαδρομή', ['Η διαδρομή περιέχει μη επιτρεπτούς χαρακτήρες.'], 400)
    parts = [x for x in rel.split('/') if x not in ('', '.')]
    if any(x == '..' for x in parts): raise Refuse('Μη έγκυρη διαδρομή', ['Η διαδρομή περιέχει «..». Ο file browser δεν επιτρέπεται να βγει έξω από τον φάκελο δεδομένων του συστήματος, γιατί εκεί βρίσκονται η βάση, ο κώδικας και τα αρχεία του λειτουργικού.'], 400)
    return '/'.join(parts)

def resolve(rel: str, must_exist=True):
    """Επιστρέφει (απόλυτη διαδρομή, καθαρή σχετική). Μπλοκάρει έξοδο από τον data_root, ακόμη και μέσω συμβολικών συνδέσμων."""
    rel = clean_rel(rel); r = root(); p = os.path.realpath(os.path.join(r, rel))
    if p != r and not p.startswith(r + os.sep):
        raise Refuse('Η διαδρομή βγαίνει από τον φάκελο δεδομένων', ['Το στοιχείο οδηγεί (π.χ. μέσω συμβολικού συνδέσμου) έξω από τον φάκελο δεδομένων. Για λόγους ασφάλειας ο file browser δουλεύει μόνο μέσα στον data_root.'], 400)
    if must_exist and not os.path.exists(p): raise Refuse('Δεν βρέθηκε', [f'Η διαδρομή «{E(rel)}» δεν υπάρχει.'], 404)
    return p, rel

def depth(rel): return len([x for x in rel.split('/') if x])
def in_trash(rel): return rel == TRASH or rel.startswith(TRASH + '/')

def human(n):
    n = float(n or 0)
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB': return f'{int(n)} {u}' if u == 'B' else f'{n:.1f} {u}'
        n /= 1024

def log(c, op, path, detail=''):
    c.execute('INSERT INTO fileops(ts,op,path,detail) VALUES(?,?,?,?)', (datetime.datetime.now().isoformat(timespec='seconds'), op, path, detail[:300]))

def classify(rel, isdir):
    """Ρόλος αρχείου και κανόνες προστασίας. Επιστρέφει dict: role, icon, level ('ok'|'warn'|'block'), why (εξήγηση)."""
    name = rel.rsplit('/', 1)[-1]; parts = rel.split('/'); parent = parts[-2] if len(parts) > 1 else ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if in_trash(rel): return dict(role='Κάδος αρχείων', icon='🗑', level='block', why='Ο κάδος διαχειρίζεται μόνο από τη σελίδα «Κάδος»: εκεί επαναφέρεις ή αδειάζεις συνειδητά. Δεν επιτρέπονται άμεσες αλλαγές μέσα του.')
    if isdir:
        if depth(rel) == 1: return dict(role='Φάκελος μαθήματος', icon='📁', level='block', why='Είναι ο φάκελος ενός μαθήματος (π.χ. B-ILEKTROTECHNIA). Το όνομά του είναι ο κωδικός μαθήματος στη βάση· αν αλλάξει ή χαθεί, χάνεται όλη η σύνδεση θεμάτων, βιβλίου και λύσεων.')
        if name in STD_DIRS: return dict(role='Φάκελος συστήματος', icon='📁', level='block', why=f'Ο φάκελος «{name}» έχει σταθερή θέση στη δομή του συστήματος: το rebuild, η σάρωση λύσεων και οι εξαγωγές τον βρίσκουν με αυτό ακριβώς το όνομα.')
        return dict(role='Φάκελος', icon='📁', level='ok', why='')
    if name.startswith('.') or ext in ('db', 'sqlite', 'sqlite3', 'wal', 'shm', 'journal'):
        return dict(role='Βάση / κρυφό αρχείο συστήματος', icon='🛡', level='block', why='Είναι αρχείο της βάσης SQLite ή κρυφό αρχείο συστήματος. Αλλαγή ή διαγραφή του ενώ τρέχει η εφαρμογή μπορεί να καταστρέψει ολόκληρη τη βάση (ερωτήματα, quiz, διαγωνίσματα, έγγραφα).')
    if parent == 'orig' and IEP_FILE.match(name):
        k = 'Λύση ΙΕΠ' if '_SOLUTION' in name.upper() else 'Εκφώνηση ΙΕΠ'
        return dict(role=f'{k} ({ext.upper()})', icon='📕' if ext == 'pdf' else '📘', level='block', why='Πρωτότυπο αρχείο του ΙΕΠ. Το όνομά του (<ID>.pdf / <ID>_SOLUTION.pdf) είναι το κλειδί του θέματος στη βάση και τα ερωτήματα, οι εικόνες ερωτημάτων και οι θέσεις (bbox) προκύπτουν από το περιεχόμενό του. Αν αλλάξει, μετονομαστεί ή διαγραφεί, το rebuild θα χάσει το θέμα ή θα το διαβάσει λάθος.')
    if parent in ('orig', '05_LYSEIS') and SOL_MD.match(name): return dict(role='Λύση εκπαιδευτικού (Markdown)', icon='✍', level='warn', why='Είναι δική σου λύση. Το όνομα <ID>.<θέμα>-<υπ>.md πρέπει να ταιριάζει με το πεδίο id μέσα στο αρχείο και με υπάρχον ερώτημα· αν αλλάξει ή λείπει, η σελίδα Λύσεις θα δείχνει προειδοποίηση και τα Reveal/Moodle/HTML της εξαγωγής θα το παραλείπουν μέχρι την επόμενη σάρωση.')
    if parent == 'images' and parts[-3:-1] in (['orig', 'images'], ['05_LYSEIS', 'images']): return dict(role='Εικόνα λύσης', icon='🖼', level='warn', why='Οι εικόνες αυτές αναφέρονται μέσα στα αρχεία λύσεων με σχετική διαδρομή (images/…). Αν λείψει ή αλλάξει όνομα, η αντίστοιχη λύση θα εμφανίζει σπασμένη εικόνα και στις εξαγωγές.')
    if parent in ('02_VIVLIA',): return dict(role='Σχολικό βιβλίο', icon='📚', level='block', why='Από αυτό το PDF χτίζεται το ευρετήριο σελίδων του βιβλίου, η αναζήτηση και οι σύνδεσμοι ερωτημάτων–υποενοτήτων. Αλλαγή ή διαγραφή θα χαλάσει τις σελίδες (και τις συνδέσεις) μέχρι νέο rebuild, που μπορεί να μην αναπαραχθεί αν λείπει το αρχείο.')
    if parent == '03_YLI': return dict(role='Ύλη / ενότητες βιβλίου', icon='📑', level='block', why='Το book_sections.csv ορίζει τις ενότητες και τις σελίδες τους· είναι πηγή αλήθειας για τη βάση. Λάθος περιεχόμενο ή διαγραφή αλλάζει όλες τις συνδέσεις υλικού.')
    if parent == '04_TRAPEZA' and re.match(r'^iep_index_.*\.xlsx$', name, re.I): return dict(role='Ευρετήριο ΙΕΠ', icon='📊', level='block', why='Το ευρετήριο περιέχει τους κωδικούς θεμάτων και τους συνδέσμους λήψης. Χωρίς αυτό το rebuild δεν ξέρει ποια θέματα να φορτώσει.')
    if parent == '04_TRAPEZA' and name in ('solution_warnings.txt', 'ingest_warnings.txt', 'word_log.csv'): return dict(role='Αρχείο αναφοράς / log', icon='🧾', level='ok', why='')
    if '07_EXAGOGES' in parts: return dict(role='Αποθηκευμένη εξαγωγή', icon='📤', level='ok', why='')
    return dict(role='Αρχείο', icon={'pdf': '📕', 'png': '🖼', 'jpg': '🖼', 'jpeg': '🖼', 'xlsx': '📊', 'docx': '📘', 'md': '📝'}.get(ext, '📄'), level='ok', why='')

def protected_inside(p, rel, limit=20000):
    """Προστατευμένα/επικίνδυνα στοιχεία μέσα σε φάκελο (για διαγραφή ή μετονομασία φακέλου)."""
    blocks, warns, n = [], [], 0
    for dp, dn, fn in os.walk(p):
        for nm in dn + fn:
            n += 1
            if n > limit: return blocks, warns, True
            full = os.path.join(dp, nm); sub = os.path.relpath(full, root()).replace(os.sep, '/')
            cl = classify(sub, os.path.isdir(full))
            if cl['level'] == 'block' and not os.path.isdir(full) or (cl['level'] == 'block' and os.path.isdir(full)): blocks.append((sub, cl))
            elif cl['level'] == 'warn': warns.append((sub, cl))
    return blocks, warns, False

def assess(rel, op):
    """Αξιολόγηση ενέργειας (delete|rename|overwrite) σε στοιχείο: (level, [λόγοι])."""
    p, rel = resolve(rel); isdir = os.path.isdir(p); cl = classify(rel, isdir); why = []
    verb = {'delete': 'διαγραφή', 'rename': 'μετονομασία ή μετακίνηση', 'overwrite': 'αντικατάσταση'}[op]
    if cl['level'] == 'block': return 'block', [f'<b>{E(rel)}</b> ({cl["role"]}): δεν επιτρέπεται {verb}. {cl["why"]}']
    level = 'ok'
    if cl['level'] == 'warn': level = 'warn'; why.append(f'<b>{E(rel)}</b> ({cl["role"]}): {cl["why"]}')
    if isdir:
        bl, wl, cut = protected_inside(p, rel)
        if bl:
            ex = ', '.join(E(b[0]) for b in bl[:5])
            return 'block', [f'Ο φάκελος <b>{E(rel)}</b> περιέχει προστατευμένα στοιχεία ({len(bl)}{"+" if cut else ""}), π.χ. {ex}. Δεν επιτρέπεται {verb} ολόκληρου του φακέλου· ' + ('άνοιξέ τον και διάλεξε μεμονωμένα ό,τι επιτρέπεται.' if op == 'delete' else 'η μετακίνησή τους θα έσπαγε τις διαδρομές που βασίζεται το σύστημα.')]
        if wl: level = 'warn'; why.append(f'Ο φάκελος <b>{E(rel)}</b> περιέχει {len(wl)} στοιχεία με εξάρτηση από το σύστημα (λύσεις ή εικόνες λύσεων), π.χ. {E(wl[0][0])}.')
    return level, why

def trash_move(c, rel, reason):
    """Μεταφέρει στοιχείο στον κάδο και το καταγράφει. Επιστρέφει trash_rel."""
    p, rel = resolve(rel); r = root(); ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    base = os.path.join(r, TRASH, ts); n = 0
    while os.path.exists(os.path.join(base + (f'-{n}' if n else ''), os.path.basename(p))): n += 1
    d = base + (f'-{n}' if n else ''); os.makedirs(d, exist_ok=True); dst = os.path.join(d, os.path.basename(p))
    size = tree_size(p); isdir = os.path.isdir(p); shutil.move(p, dst); trel = os.path.relpath(dst, r).replace(os.sep, '/')
    c.execute('INSERT INTO trash(orig_rel,trash_rel,kind,size,deleted,reason) VALUES(?,?,?,?,?,?)', (rel, trel, 'dir' if isdir else 'file', size, datetime.datetime.now().isoformat(timespec='seconds'), reason))
    return trel

def tree_size(p):
    if os.path.isfile(p): return os.path.getsize(p)
    t = 0
    for dp, dn, fn in os.walk(p):
        for f in fn:
            try: t += os.path.getsize(os.path.join(dp, f))
            except OSError: pass
    return t

def valid_name(name):
    if not name or name != os.path.basename(name) or BADNAME.search(name): return 'Το όνομα περιέχει διαχωριστικά διαδρομής ή μη επιτρεπτούς χαρακτήρες (\\ / : * ? " < > |).'
    if name.startswith('.'): return 'Ονόματα που αρχίζουν με τελεία είναι κρυφά αρχεία συστήματος· δεν δημιουργούνται από τον file browser.'
    if name in ('.', '..') or name.endswith((' ', '.')): return 'Το όνομα δεν μπορεί να τελειώνει σε κενό ή τελεία (προβλήματα με Windows και το Google Drive).'
    if len(name) > 120: return 'Το όνομα είναι πολύ μεγάλο (όριο 120 χαρακτήρες).'
    if name.upper() == TRASH.upper(): return f'Το όνομα «{TRASH}» είναι δεσμευμένο για τον κάδο.'
    return ''

def db_hints(c):
    ids = {r[0] for r in c.execute('SELECT id FROM item')}
    try: sols = {os.path.basename(r[0]) for r in c.execute('SELECT relpath FROM qsolution')}
    except Exception: sols = set()
    return ids, sols

def db_note(rel, isdir, ids, sols):
    if isdir: return ''
    name = rel.rsplit('/', 1)[-1]; m = re.match(r'^(\d+)(_SOLUTION)?\.(pdf|docx|doc)$', name, re.I)
    if m: return ('✔ θέμα ' + m.group(1) + ' στη βάση') if m.group(1) in ids else '⚠ δεν υπάρχει θέμα στη βάση (χρειάζεται rebuild)'
    if SOL_MD.match(name): return '✔ στον πίνακα λύσεων' if name in sols else '⚠ δεν έχει σαρωθεί (πάτα «Σάρωση φακέλου» στις Λύσεις)'
    return ''

# ---------- σελίδες ----------
def crumbs(rel):
    out = ["<a href='/fb'>📂 data_root</a>"]; acc = []
    for x in [x for x in rel.split('/') if x]:
        acc.append(x); out.append(f"<a href='/fb?p={E('/'.join(acc))}'>{E(x)}</a>")
    return ' / '.join(out)

CSS = ("<style>.note{border-left:5px solid var(--accent);background:var(--code);padding:.5rem .8rem;border-radius:var(--radius);margin:.5rem 0}.note.bad{border-color:#d33;background:rgba(220,50,50,.08)}.note.warn{border-color:#e69500;background:rgba(230,150,0,.1)}.note.good{border-color:#2e9d57;background:rgba(46,157,87,.1)}"
       ".fbpath{font-family:Consolas,monospace;font-size:.85rem;color:var(--muted)}.lv-block{color:#d33}.lv-warn{color:#c47f00}.fbrole{font-size:.85rem}.fb-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:.6rem}</style>")

def listing(rel='', msg='', warn=''):
    p, rel = resolve(rel)
    if not os.path.isdir(p): raise Refuse('Δεν είναι φάκελος', [f'Η διαδρομή «{E(rel)}» είναι αρχείο· χρησιμοποίησε την προβολή.'], 400)
    if in_trash(rel): return RedirectResponse('/fb/trash', status_code=303)
    c = db(); ids, sols = db_hints(c); ents = []
    for nm in sorted(os.listdir(p), key=lambda s: (not os.path.isdir(os.path.join(p, s)), s.lower())):
        if rel == '' and nm == TRASH: continue
        full = os.path.join(p, nm); r2 = (rel + '/' + nm) if rel else nm; isd = os.path.isdir(full)
        if os.path.islink(full): continue
        ents.append((nm, r2, isd, classify(r2, isd), os.stat(full)))
    log_rows = c.execute('SELECT ts,op,path,detail FROM fileops ORDER BY id DESC LIMIT 12').fetchall(); ntr = c.execute('SELECT count(*) FROM trash').fetchone()[0]; c.close()
    trs = []
    for nm, r2, isd, cl, st in ents:
        lvl = {'block': '<span class=lv-block title="Προστατευμένο: δεν διαγράφεται και δεν μετονομάζεται">🔒</span> ', 'warn': '<span class=lv-warn title="Εξαρτάται από το σύστημα: θέλει επιβεβαίωση">⚠</span> ', 'ok': ''}[cl['level']]
        link = f"<a href='/fb?p={E(r2)}'>{cl['icon']} {E(nm)}</a>" if isd else f"<a href='/fb/view?p={E(r2)}'>{cl['icon']} {E(nm)}</a>"
        acts = ('' if isd else f"<a href='/fb/raw?p={E(r2)}&dl=1' title='Κατεβάζει το αρχείο στον υπολογιστή σου'>⬇</a> ") + f"<a href='/fb/rename?p={E(r2)}' title='Μετονομασία (με έλεγχο ασφάλειας)'>✎</a>"
        trs.append(f"<tr><td><input type=checkbox name=sel value='{E(r2)}' class=selbox></td><td>{lvl}{link}</td><td class=fbrole>{E(cl['role'])}</td><td>{'' if isd else human(st.st_size)}</td>"
                   f"<td>{datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')}</td><td class=fbrole>{E(db_note(r2, isd, ids, sols))}</td><td>{acts}</td></tr>")
    free = shutil.disk_usage(root()).free
    up = ("<form method=post action='/fb/upload' enctype='multipart/form-data' class=filters><input type=hidden name=p value='%s'>" % E(rel)
          + fld('Upload αρχείων (έως 100 MB το καθένα)', "<input type=file name=files multiple required>") + "<label class='f chk'><input type=checkbox name=confirm value=1> επιτρέπω αντικατάσταση (το παλιό πάει στον κάδο)</label><button class=primary title='Ανεβάζει τα αρχεία στον τρέχοντα φάκελο, μετά από έλεγχο ονόματος, τύπου, μεγέθους και χώρου'>⬆ Upload</button></form>")
    mk = ("<form method=post action='/fb/mkdir' class=filters><input type=hidden name=p value='%s'>" % E(rel) + fld('Νέος φάκελος', "<input name=name size=24 required>") + "<button title='Δημιουργεί υποφάκελο στον τρέχοντα φάκελο'>Δημιουργία</button></form>")
    bulk = ("<div class=bar><button type=button data-selall='sel' title='Επιλέγει όλα τα στοιχεία της λίστας'>☑ Όλα</button> <button type=button data-selnone='sel' title='Αφαιρεί κάθε επιλογή'>☐ Κανένα</button> "
            "<button formaction='/fb/zip' title='Κατεβάζει τα επιλεγμένα (και τα περιεχόμενα φακέλων) ως ένα αρχείο zip, έως 300 MB'>⬇ Λήψη zip</button> "
            "<button formaction='/fb/delete' class=danger title='Μεταφέρει τα επιλεγμένα στον κάδο (δεν σβήνονται οριστικά)· τα προστατευμένα μπλοκάρονται με εξήγηση'>🗑 Στον κάδο</button> <span>επιλεγμένα: <b id=count>0</b></span></div>")
    nolog = ''.join(f"<tr><td>{E(r['ts'])}</td><td>{E(r['op'])}</td><td>{E(r['path'])}</td><td>{E(r['detail'] or '')}</td></tr>" for r in log_rows)
    info = (f"<div class=note><b>Πού βρίσκεσαι στον server:</b> <span class=fbpath>{E(os.path.join(root(), rel))}</span><br>Ελεύθερος χώρος δίσκου: <b>{human(free)}</b> · "
            f"<a href='/fb/trash'>🗑 Κάδος ({ntr})</a> · Η βάση SQLite είναι ξεχωριστό αρχείο εκτός αυτής της λίστας.</div>")
    help_ = ("<details class=help><summary>Τι προστατεύει το σύστημα</summary><ul><li>🔒 <b>Μπλοκάρεται</b> η διαγραφή/μετονομασία των PDF και Word του ΙΕΠ, του βιβλίου, της ύλης, του ευρετηρίου, των φακέλων συστήματος και της βάσης.</li>"
             "<li>⚠ <b>Θέλει επιβεβαίωση</b> η αλλαγή σε λύσεις εκπαιδευτικού (.md) και στις εικόνες τους.</li><li>Κάθε διαγραφή ή αντικατάσταση πηγαίνει στον <b>κάδο</b> και μπορεί να επανέλθει.</li>"
             "<li>Δεν επιτρέπονται εκτελέσιμα/ενεργά αρχεία (.html, .js, .py, .sh, .exe…) και διαδρομές εκτός του φακέλου δεδομένων.</li><li>Μετά από αλλαγές στο <code>orig/</code> τρέξε «Σάρωση φακέλου» (Λύσεις) ή <code>thilek-rebuild</code> (νέα PDF).</li></ul></details>")
    body = (CSS + f"<h2>File browser</h2><div class=fbcrumb>{crumbs(rel)}</div>{box('good', E(msg))}{box('warn', E(warn))}{info}{__import__('app.syncui', fromlist=['x']).drive_bar()}{help_}"
            f"<div class=fb-grid>{up}{mk}</div><form method=post action='/fb/delete'><input type=hidden name=back value='{E(rel)}'>{bulk}"
            f"<table><tr><th></th><th>Όνομα</th><th>Χρήση στο σύστημα</th><th>Μέγεθος</th><th>Τροποποίηση</th><th>Στη βάση</th><th>Ενέργειες</th></tr>{''.join(trs) or '<tr><td colspan=7>Άδειος φάκελος.</td></tr>'}</table></form>"
            f"<details><summary>Τελευταίες ενέργειες αρχείων</summary><table><tr><th>Ώρα</th><th>Ενέργεια</th><th>Διαδρομή</th><th>Λεπτομέρειες</th></tr>{nolog}</table></details>")
    return page('File browser', body)

def handle(fn):
    """Αποκωδικοποιεί Refuse σε σελίδα άρνησης."""
    import functools
    @functools.wraps(fn)
    async def w(*a, **k):
        try:
            r = fn(*a, **k)
            if hasattr(r, '__await__'): r = await r
            return r
        except Refuse as x: return deny(x.title, x.reasons, x.status)
    return w

@router.get('/fb', response_class=HTMLResponse, dependencies=[Depends(auth)])
@handle
def fb_list(p: str = '', msg: str = '', warn: str = ''): return listing(p, msg, warn)

def textual(name): return name.rsplit('.', 1)[-1].lower() in TEXT_EXT

@router.get('/fb/view', response_class=HTMLResponse, dependencies=[Depends(auth)])
@handle
def fb_view(p: str):
    ap, rel = resolve(p)
    if not os.path.isfile(ap): raise Refuse('Δεν είναι αρχείο', ['Η διαδρομή είναι φάκελος.'], 400)
    if in_trash(rel): raise Refuse('Αρχείο στον κάδο', ['Τα αρχεία του κάδου προβάλλονται από τη σελίδα «Κάδος».'])
    cl = classify(rel, False); ext = rel.rsplit('.', 1)[-1].lower() if '.' in rel else ''; st = os.stat(ap); c = db(); ids, sols = db_hints(c); c.close()
    meta = (f"<table><tr><th>Διαδρομή στον server</th><td class=fbpath>{E(ap)}</td></tr><tr><th>Σχετική</th><td>{E(rel)}</td></tr><tr><th>Χρήση</th><td>{cl['icon']} {E(cl['role'])}{' · προστατευμένο 🔒' if cl['level'] == 'block' else (' · θέλει επιβεβαίωση ⚠' if cl['level'] == 'warn' else '')}</td></tr>"
            f"<tr><th>Μέγεθος</th><td>{human(st.st_size)}</td></tr><tr><th>Τροποποίηση</th><td>{datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}</td></tr><tr><th>Στη βάση</th><td>{E(db_note(rel, False, ids, sols)) or '—'}</td></tr></table>")
    if cl['why']: meta += f"<div class='note {'bad' if cl['level'] == 'block' else 'warn'}'>{E(cl['why'])}</div>"
    if ext in TEXT_EXT:
        raw = open(ap, 'rb').read(300 * 1024 + 1); cut = len(raw) > 300 * 1024; txt = raw[:300 * 1024].decode('utf-8', 'replace')
        view = f"<pre style='max-height:70vh'>{E(txt)}</pre>" + ('<p><b>Εμφανίζονται τα πρώτα 300 KB.</b></p>' if cut else '')
    elif ext in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'): view = f"<img src='/fb/raw?p={E(rel)}' alt='{E(rel)}' style='max-width:100%;border:1px solid var(--border);background:#fff'>"
    elif ext == 'pdf': view = f"<iframe src='/fb/raw?p={E(rel)}' title='PDF'></iframe>"
    else: view = "<div class=note>Αυτός ο τύπος αρχείου δεν προβάλλεται στον browser (π.χ. Word/Excel)· κατέβασέ το και άνοιξέ το στο πρόγραμμά του.</div>"
    parent = rel.rsplit('/', 1)[0] if '/' in rel else ''
    body = (CSS + f"<h2>{cl['icon']} {E(rel.rsplit('/', 1)[-1])}</h2><div class=fbcrumb>{crumbs(parent)}</div>{meta}<p><a class=btn href='/fb/raw?p={E(rel)}&dl=1'>⬇ Λήψη</a> <a class=btn href='/fb/rename?p={E(rel)}'>✎ Μετονομασία</a> <a class=btn href='/fb?p={E(parent)}'>← Φάκελος</a></p>{view}")
    return page('Προβολή αρχείου', body)

@router.get('/fb/raw', dependencies=[Depends(auth)])
def fb_raw(p: str, dl: int = 0):
    try: ap, rel = resolve(p)
    except Refuse as x: raise HTTPException(x.status, '; '.join(re.sub('<[^>]+>', '', r) for r in x.reasons))
    if not os.path.isfile(ap): raise HTTPException(404)
    if in_trash(rel): raise HTTPException(403, 'Τα αρχεία του κάδου δεν προβάλλονται απευθείας.')
    ext = rel.rsplit('.', 1)[-1].lower() if '.' in rel else ''; mt = mimetypes.guess_type(ap)[0] or 'application/octet-stream'
    inline = (not dl) and ext in ('pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'txt', 'md', 'csv', 'json', 'yaml', 'yml')
    if ext in TEXT_EXT: mt = 'text/plain; charset=utf-8'
    r = FileResponse(ap, media_type=mt, filename=None if inline else os.path.basename(ap), content_disposition_type='inline' if inline else 'attachment')
    r.headers['X-Content-Type-Options'] = 'nosniff'; r.headers['Content-Security-Policy'] = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
    return r

@router.post('/fb/mkdir', dependencies=[Depends(auth)])
@handle
def fb_mkdir(request: Request, p: str = Form(''), name: str = Form('')):
    same_origin(request); ap, rel = resolve(p); name = name.strip(); why = valid_name(name)
    if why: raise Refuse('Μη έγκυρο όνομα φακέλου', [why], 422)
    if depth(rel) < 1 or in_trash(rel): raise Refuse('Εδώ δεν δημιουργούνται φάκελοι', ['Νέοι φάκελοι δημιουργούνται μόνο μέσα σε φάκελο μαθήματος. Οι φάκελοι μαθημάτων δημιουργούνται από τον installer/provision και όχι από την εφαρμογή.'])
    t = os.path.join(ap, name)
    if os.path.exists(t): raise Refuse('Υπάρχει ήδη', [f'Στο «{E(rel)}» υπάρχει ήδη στοιχείο με όνομα «{E(name)}».'], 409)
    os.mkdir(t); c = db(); log(c, 'mkdir', (rel + '/' if rel else '') + name); c.commit(); c.close()
    return RedirectResponse('/fb?' + _q(p=rel, msg=f'Δημιουργήθηκε ο φάκελος «{name}».'), status_code=303)

def _q(**kw):
    from urllib.parse import urlencode
    return urlencode(kw)

@router.post('/fb/upload', dependencies=[Depends(auth)])
@handle
async def fb_upload(request: Request, p: str = Form(''), confirm: str = Form(''), files: list[UploadFile] = File(...)):
    same_origin(request); ap, rel = resolve(p)
    if depth(rel) < 1 or in_trash(rel): raise Refuse('Εδώ δεν γίνεται upload', ['Το upload επιτρέπεται μόνο μέσα σε φάκελο μαθήματος (όχι στη ρίζα και όχι στον κάδο), ώστε να μην μπλεχτούν αρχεία με τη δομή του συστήματος.'])
    free = shutil.disk_usage(root()).free; refuse, warns, done, c = [], [], [], db(); staged = []
    try:
        for f in files:
            name = os.path.basename((f.filename or '').replace('\\', '/')); ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
            why = valid_name(name)
            if why: refuse.append(f'«{E(name or "(χωρίς όνομα)")}»: {why}'); continue
            if ext not in ALLOWED_EXT:
                refuse.append(f'«{E(name)}»: ο τύπος <b>.{E(ext) or "(χωρίς επέκταση)"}</b> δεν επιτρέπεται. Αρχεία όπως .html, .js, .py, .sh, .exe μπορούν να εκτελέσουν κώδικα όταν ανοιχτούν από τον server ή να τον απειλήσουν· επιτρέπονται μόνο έγγραφα, εικόνες και δεδομένα ({", ".join(sorted(ALLOWED_EXT))}).'); continue
            tgt = os.path.join(ap, name); trel = (rel + '/' if rel else '') + name
            if os.path.exists(tgt):
                lv, why2 = assess(trel, 'overwrite')
                if lv == 'block': refuse.append(f'Αντικατάσταση της «{E(trel)}» όχι: ' + ' '.join(why2)); continue
                if not confirm: warns.append(f'Υπάρχει ήδη η «{E(trel)}». Για να την αντικαταστήσεις τσέκαρε «επιτρέπω αντικατάσταση» (το παλιό αρχείο θα πάει στον κάδο).' + (' ' + ' '.join(why2) if why2 else '')); continue
            fd, tmp = tempfile.mkstemp(prefix='.upload-', dir=ap); size = 0
            with os.fdopen(fd, 'wb') as out:
                while True:
                    ch = await f.read(1 << 20)
                    if not ch: break
                    size += len(ch)
                    if size > MAX_UPLOAD: break
                    out.write(ch)
            if size > MAX_UPLOAD: os.unlink(tmp); refuse.append(f'«{E(name)}»: ξεπερνά το όριο {human(MAX_UPLOAD)}.'); continue
            if size == 0: os.unlink(tmp); refuse.append(f'«{E(name)}»: το αρχείο είναι άδειο.'); continue
            if size + RESERVE > free: os.unlink(tmp); refuse.append(f'«{E(name)}»: ο ελεύθερος χώρος του δίσκου ({human(free)}) δεν αρκεί· το σύστημα κρατά πάντα {human(RESERVE)} εφεδρικά για τη βάση και τα backup.'); continue
            free -= size; staged.append((tmp, tgt, trel, name, size))
        if refuse or warns:
            for t in staged: os.unlink(t[0])
            if refuse: raise Refuse('Το upload σταμάτησε', refuse + warns, 422)
            return deny('Το upload θέλει επιβεβαίωση', warns, 409)
        for tmp, tgt, trel, name, size in staged:
            if os.path.exists(tgt): trash_move(c, trel, 'αντικατάσταση από upload')
            os.replace(tmp, tgt); log(c, 'upload', trel, human(size)); done.append(name)
        c.commit()
    except BaseException:
        for t in staged:
            if os.path.exists(t[0]): os.unlink(t[0])
        raise
    finally: c.close()
    note = f'Ανέβηκαν {len(done)} αρχεία: ' + ', '.join(done) + '.'
    warn = 'Σε φάκελο <code>orig</code>: για νέα PDF τρέξε <code>thilek-rebuild</code>· για νέες λύσεις .md πάτα «Σάρωση φακέλου» στις Λύσεις.' if rel.endswith('orig') or rel.endswith('05_LYSEIS') else ''
    return RedirectResponse('/fb?' + _q(p=rel, msg=note, warn=re.sub('<[^>]+>', '', warn)), status_code=303)

@router.get('/fb/rename', response_class=HTMLResponse, dependencies=[Depends(auth)])
@handle
def fb_rename_form(p: str):
    ap, rel = resolve(p); lv, why = assess(rel, 'rename'); name = rel.rsplit('/', 1)[-1]
    if lv == 'block': raise Refuse('Η μετονομασία δεν επιτρέπεται', why)
    note = (f"<div class='note warn'>{'<br>'.join(why)}</div>" if why else '')
    body = (CSS + f"<h2>Μετονομασία</h2><p class=fbpath>{E(ap)}</p>{note}<form method=post action='/fb/rename' class=filters><input type=hidden name=p value='{E(rel)}'>" + fld('Νέο όνομα', f"<input name=name value='{E(name)}' size=40 required>")
            + (("<label class='f chk'><input type=checkbox name=confirm value=1> καταλαβαίνω τον κίνδυνο</label>") if lv == 'warn' else '') + "<button class=primary>Μετονομασία</button> <a class=btn href='/fb' data-back>Άκυρο</a></form>")
    return page('Μετονομασία', body)

@router.post('/fb/rename', dependencies=[Depends(auth)])
@handle
def fb_rename(request: Request, p: str = Form(...), name: str = Form(...), confirm: str = Form('')):
    same_origin(request); ap, rel = resolve(p); name = name.strip(); lv, why = assess(rel, 'rename')
    if lv == 'block': raise Refuse('Η μετονομασία δεν επιτρέπεται', why)
    if lv == 'warn' and not confirm: raise Refuse('Η μετονομασία θέλει επιβεβαίωση', why + ['Τσέκαρε «καταλαβαίνω τον κίνδυνο» στη φόρμα μετονομασίας.'], 409)
    bad = valid_name(name)
    if bad: raise Refuse('Μη έγκυρο όνομα', [bad], 422)
    isdir = os.path.isdir(ap); old_ext = rel.rsplit('.', 1)[-1].lower() if '.' in rel and not isdir else ''; new_ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if not isdir and new_ext not in ALLOWED_EXT: raise Refuse('Μη επιτρεπτή επέκταση', [f'Η νέα επέκταση «.{E(new_ext)}» δεν επιτρέπεται (βλ. λίστα επιτρεπτών τύπων στο upload).'], 422)
    parent = rel.rsplit('/', 1)[0] if '/' in rel else ''; new_rel = (parent + '/' if parent else '') + name; tgt = os.path.join(os.path.dirname(ap), name)
    if os.path.exists(tgt): raise Refuse('Υπάρχει ήδη', [f'Υπάρχει ήδη στοιχείο «{E(name)}» στον ίδιο φάκελο· δεν γίνεται αντικατάσταση με μετονομασία.'], 409)
    cn = classify(new_rel, isdir)
    if cn['level'] == 'block' and not isdir: raise Refuse('Το νέο όνομα συγκρούεται με το σύστημα', [f'Το όνομα «{E(name)}» ταιριάζει σε προστατευμένη κατηγορία ({E(cn["role"])}). {E(cn["why"])}'], 422)
    os.rename(ap, tgt); c = db(); log(c, 'rename', rel, '→ ' + new_rel); c.commit(); c.close()
    return RedirectResponse('/fb?' + _q(p=parent, msg=f'Μετονομάστηκε σε «{name}».'), status_code=303)

@router.post('/fb/delete', dependencies=[Depends(auth)])
@handle
def fb_delete(request: Request, sel: list[str] = Form([]), back: str = Form(''), confirm: str = Form('')):
    same_origin(request)
    if not sel: raise Refuse('Δεν επιλέχθηκε τίποτα', ['Διάλεξε τουλάχιστον ένα στοιχείο με το τετράγωνο.'], 422)
    blocks, warns, items = [], [], []
    for s in sel:
        lv, why = assess(s, 'delete')
        if lv == 'block': blocks += why
        elif lv == 'warn': warns += why; items.append(s)
        else: items.append(s)
    if blocks: raise Refuse('Η διαγραφή μπλοκαρίστηκε', blocks + (['Δεν διαγράφηκε <b>κανένα</b> από τα επιλεγμένα (η ενέργεια ακυρώνεται συνολικά για να μη μείνει μισή).'] if len(sel) > 1 else []))
    if warns and not confirm:
        hid = ''.join(f"<input type=hidden name=sel value='{E(s)}'>" for s in sel)
        body = (CSS + "<h2>⚠ Χρειάζεται επιβεβαίωση</h2><div class='note warn'><ul>" + ''.join(f'<li>{w}</li>' for w in warns) + "</ul><p>Τα στοιχεία θα μπουν στον <b>κάδο</b> και μπορείς να τα επαναφέρεις, αλλά το σύστημα δεν θα τα βλέπει μέχρι τότε.</p></div>"
                f"<form method=post action='/fb/delete'>{hid}<input type=hidden name=back value='{E(back)}'><label><input type=checkbox name=confirm value=1 required> καταλαβαίνω, μετάβαση στον κάδο</label> <button class=danger>🗑 Στον κάδο</button> <a class=btn href='/fb?p={E(back)}'>Άκυρο</a></form>")
        return page('Επιβεβαίωση', body)
    c = db()
    for s in items: trash_move(c, s, 'διαγραφή από file browser'); log(c, 'trash', s)
    c.commit(); c.close()
    return RedirectResponse('/fb?' + _q(p=back, msg=f'Μεταφέρθηκαν στον κάδο: {len(items)} στοιχεία. Μπορείς να τα επαναφέρεις από τον Κάδο.'), status_code=303)

@router.post('/fb/zip', dependencies=[Depends(auth)])
@handle
def fb_zip(request: Request, sel: list[str] = Form([])):
    same_origin(request)
    if not sel: raise Refuse('Δεν επιλέχθηκε τίποτα', ['Διάλεξε στοιχεία για λήψη.'], 422)
    files, total = [], 0
    for s in sel:
        ap, rel = resolve(s)
        if in_trash(rel): raise Refuse('Στοιχείο του κάδου', ['Ο κάδος δεν κατεβαίνει από εδώ.'])
        if os.path.isfile(ap): files.append((ap, rel)); total += os.path.getsize(ap)
        else:
            for dp, dn, fn in os.walk(ap):
                for f in fn:
                    fp = os.path.join(dp, f)
                    if os.path.islink(fp): continue
                    files.append((fp, os.path.relpath(fp, root()).replace(os.sep, '/'))); total += os.path.getsize(fp)
        if total > MAX_ZIP: raise Refuse('Η λήψη είναι πολύ μεγάλη', [f'Το σύνολο ξεπερνά τα {human(MAX_ZIP)}. Κατέβασε μικρότερες επιλογές ή αντίγραψε τον φάκελο κατευθείαν από το Google Drive / Proxmox.'], 413)
    tmp = tempfile.NamedTemporaryFile(prefix='thilek-zip-', suffix='.zip', delete=False); tmp.close()
    with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as z:
        for fp, rel in files: z.write(fp, rel)
    c = db(); log(c, 'zip', f'{len(sel)} στοιχεία', f'{len(files)} αρχεία, {human(total)}'); c.commit(); c.close()
    from starlette.background import BackgroundTask
    return FileResponse(tmp.name, media_type='application/zip', filename='thilek-files.zip', background=BackgroundTask(os.unlink, tmp.name))

# ---------- κάδος ----------
@router.get('/fb/trash', response_class=HTMLResponse, dependencies=[Depends(auth)])
def fb_trash(msg: str = ''):
    c = db(); rows = c.execute('SELECT * FROM trash ORDER BY id DESC').fetchall(); c.close()
    trs = ''.join(f"<tr><td><input type=checkbox name=ids value={r['id']} class=selbox></td><td>{E(r['orig_rel'])}</td><td>{'📁' if r['kind'] == 'dir' else ('📝' if r['kind'] == 'mdoc' else '📄')} {E(r['kind'])}</td><td>{human(r['size'])}</td><td>{E((r['deleted'] or '').replace('T', ' '))}</td><td>{E('έγγραφο MD' if r['kind'] == 'mdoc' else (r['reason'] or ''))}</td></tr>" for r in rows)
    tot = sum(r['size'] or 0 for r in rows)
    body = (CSS + f"<h2>🗑 Κάδος αρχείων</h2>{box('good', E(msg))}<div class=note>Εδώ μένουν τα αρχεία που «διέγραψες» ή αντικατέστησες (φυσικά στον φάκελο <span class=fbpath>{E(os.path.join(root(), TRASH))}</span>). Σύνολο: <b>{human(tot)}</b> σε {len(rows)} στοιχεία. "
            "Η επαναφορά τα βάζει στην αρχική θέση· αν εκεί υπάρχει ήδη κάτι, δεν αντικαθίσταται. Η οριστική διαγραφή <b>δεν αναιρείται</b>.</div>"
            "<form method=post action='/fb/restore'><div class=bar><button type=button data-selall='ids'>☑ Όλα</button> <button type=button data-selnone='ids'>☐ Κανένα</button> <button class=primary formaction='/fb/restore' title='Επαναφέρει τα επιλεγμένα στην αρχική τους θέση'>↩ Επαναφορά</button> "
            "<button class=danger formaction='/fb/purge' title='Σβήνει οριστικά τα επιλεγμένα· πρέπει να γράψεις τη λέξη ΔΙΑΓΡΑΦΗ'>🔥 Οριστική διαγραφή</button> <input name=phrase placeholder='γράψε ΔΙΑΓΡΑΦΗ' size=14 title='Απαιτείται για οριστική διαγραφή'> <span>επιλεγμένα: <b id=count>0</b></span></div>"
            f"<table><tr><th></th><th>Αρχική θέση</th><th>Είδος</th><th>Μέγεθος</th><th>Διαγράφηκε</th><th>Αιτία</th></tr>{trs or '<tr><td colspan=6>Ο κάδος είναι άδειος.</td></tr>'}</table></form><p><a href='/fb'>← File browser</a></p>")
    return page('Κάδος', body)

@router.post('/fb/restore', dependencies=[Depends(auth)])
@handle
def fb_restore(request: Request, ids: list[int] = Form([])):
    same_origin(request)
    if not ids: raise Refuse('Δεν επιλέχθηκε τίποτα', ['Διάλεξε στοιχεία του κάδου.'], 422)
    c = db(); bad, ok = [], 0
    for i in ids:
        r = c.execute('SELECT * FROM trash WHERE id=?', (i,)).fetchone()
        if not r: continue
        if r['kind'] == 'mdoc':                       # έγγραφο MD που διαγράφηκε από τη βάση: επανεισαγωγή ως νέο έγγραφο
            try: src, _ = resolve(r['trash_rel'])
            except Refuse as x: bad.append(f'{E(r["orig_rel"])}: ' + ' '.join(x.reasons)); continue
            import json as _j
            meta = {}
            try: meta = _j.loads(r['reason'] or '{}')
            except ValueError: pass
            now = datetime.datetime.now().isoformat(timespec='seconds'); c.execute('INSERT INTO mdoc(name,markdown,source,created,updated) VALUES(?,?,?,?,?)', (meta.get('name') or 'Έγγραφο', open(src, encoding='utf-8').read(), (meta.get('source') or '') + ' (επαναφορά)', now, now))
            os.unlink(src); c.execute('DELETE FROM trash WHERE id=?', (i,)); log(c, 'restore', r['orig_rel'], 'νέο έγγραφο MD'); ok += 1; continue
        try: src, _ = resolve(r['trash_rel']); dst, orel = resolve(r['orig_rel'], must_exist=False)
        except Refuse as x: bad.append(f'{E(r["orig_rel"])}: ' + ' '.join(x.reasons)); continue
        if os.path.exists(dst): bad.append(f'Η «{E(r["orig_rel"])}» δεν επαναφέρθηκε: στη θέση της υπάρχει ήδη άλλο στοιχείο. Μετονόμασέ το ή διέγραψέ το πρώτα, για να μη χαθεί κάτι.'); continue
        if not os.path.exists(src): bad.append(f'«{E(r["orig_rel"])}»: το αντίγραφο στον κάδο δεν βρέθηκε στον δίσκο.'); continue
        os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.move(src, dst); c.execute('DELETE FROM trash WHERE id=?', (i,)); log(c, 'restore', orel); ok += 1
    c.commit(); c.close()
    if bad: raise Refuse(f'Επαναφέρθηκαν {ok}, αλλά υπήρξαν προβλήματα', bad, 409)
    return RedirectResponse('/fb/trash?' + _q(msg=f'Επαναφέρθηκαν {ok} στοιχεία.'), status_code=303)

@router.post('/fb/purge', dependencies=[Depends(auth)])
@handle
def fb_purge(request: Request, ids: list[int] = Form([]), phrase: str = Form('')):
    same_origin(request)
    if not ids: raise Refuse('Δεν επιλέχθηκε τίποτα', ['Διάλεξε στοιχεία του κάδου.'], 422)
    if phrase.strip() != 'ΔΙΑΓΡΑΦΗ': raise Refuse('Η οριστική διαγραφή θέλει επιβεβαίωση', ['Η οριστική διαγραφή δεν αναιρείται. Γράψε ακριβώς τη λέξη <b>ΔΙΑΓΡΑΦΗ</b> στο πεδίο δίπλα στο κουμπί.'], 409)
    c = db(); n = 0
    for i in ids:
        r = c.execute('SELECT * FROM trash WHERE id=?', (i,)).fetchone()
        if not r: continue
        try: src, _ = resolve(r['trash_rel'], must_exist=False)
        except Refuse: continue
        if os.path.isdir(src): shutil.rmtree(src)
        elif os.path.exists(src): os.unlink(src)
        d = os.path.dirname(src)
        try: os.rmdir(d)                      # άδειος φάκελος ημερομηνίας
        except OSError: pass
        c.execute('DELETE FROM trash WHERE id=?', (i,)); log(c, 'purge', r['orig_rel']); n += 1
    c.commit(); c.close()
    return RedirectResponse('/fb/trash?' + _q(msg=f'Διαγράφηκαν οριστικά {n} στοιχεία.'), status_code=303)
