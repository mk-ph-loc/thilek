"""0.31.0: wizard αρχείων — χωρισμός PDF, συγχώνευση PDF, μαζική μετονομασία με μοτίβο.
Αρχές: (1) πάντα προεπισκόπηση (dry-run) πριν την εφαρμογή· ο server ξαναϋπολογίζει το σχέδιο στην εφαρμογή (δεν εμπιστεύεται τη σελίδα προεπισκόπησης)·
(2) τα νέα αρχεία δεν αντικαθιστούν ποτέ υπάρχοντα· (3) τα πρωτότυπα (PDF/Word ΙΕΠ, βιβλίο κ.λπ.) διαβάζονται αλλά δεν αλλάζουν: το split/merge γράφει σε φάκελο `07_EXAGOGES`
και η μετονομασία «σε αντίγραφα» αντιγράφει εκεί· η μετονομασία επί τόπου υπακούει στις προστασίες του file browser· (4) όλα μέσα στον data_root, με καταγραφή στον πίνακα `fileops`."""
from urllib.parse import quote
import html, os, re, shutil
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from . import config
from .main_auth import auth
from .review import db, page, same_origin
from . import filebrowser as FB
from .filebrowser import Refuse, handle, resolve, clean_rel, classify, assess, valid_name, log, root, in_trash, human, E, TRASH, RESERVE, ALLOWED_EXT

router = APIRouter()
MAX_SRC = 300 * 1024 * 1024
MAX_PARTS = 200
MAX_PAGES = 5000
MAX_FILES = 400
OUT = '07_EXAGOGES'
TABS = (('split', 'Χωρισμός PDF'), ('merge', 'Συγχώνευση PDF'), ('rename', 'Μετονομασία με μοτίβο'))
TOKEN = re.compile(r'\{([a-z]+)(?::(0?\d{1,2})d)?\}')
SPLIT_KEYS = ('name', 'n', 'from', 'to')
RENAME_KEYS = ('name', 'n')


def natkey(s): return [int(x) if x.isdigit() else x.lower() for x in re.split(r'(\d+)', s)]


def check_pattern(pat, keys):
    """Επιτρέπονται μόνο {κλειδί} ή {κλειδί:02d} από τη λίστα keys· ό,τι άλλο στις αγκύλες απορρίπτεται (χωρίς attribute/index)."""
    if not pat or len(pat) > 120: raise ValueError('Το μοτίβο είναι κενό ή πολύ μεγάλο.')
    rest = TOKEN.sub('', pat)
    if '{' in rest or '}' in rest: raise ValueError('Μη έγκυρο μοτίβο: επιτρέπονται μόνο {name}, {n}, {n:03d}' + (', {from}, {to}' if 'from' in keys else '') + '.')
    for m in TOKEN.finditer(pat):
        if m.group(1) not in keys: raise ValueError(f'Άγνωστο πεδίο {{{m.group(1)}}} στο μοτίβο.')


def fill(pat, **kw):
    def one(m):
        v = kw[m.group(1)]
        w = m.group(2)
        return f'{int(v):0{int(w)}d}' if w else str(v)
    return TOKEN.sub(one, pat)


def parse_ranges(spec, n):
    """«1-3, 4-6; 8; 10-» ή «κάθε 5» / «every 5» -> [(από, έως)] (1-based, εντός 1..n)."""
    s = (spec or '').strip()
    if not s: raise ValueError('Δώσε περιοχές σελίδων, π.χ. 1-3, 4-6, 8 ή «κάθε 5».')
    m = re.fullmatch(r'(?:every|κάθε|καθε)\s*(\d{1,4})', s.lower())
    if m:
        k = int(m.group(1))
        if k < 1: raise ValueError('Το «κάθε N» θέλει N ≥ 1.')
        out = [(a, min(a + k - 1, n)) for a in range(1, n + 1, k)]
    else:
        out = []
        for tok in re.split(r'[,;\n]+', s):
            tok = tok.strip()
            if not tok: continue
            m = re.fullmatch(r'(\d{1,5})(?:\s*-\s*(\d{0,5}))?', tok)
            if not m: raise ValueError(f'Μη έγκυρη περιοχή «{tok}». Γράψε 3, 2-5 ή 7-.')
            a = int(m.group(1)); b = (int(m.group(2)) if m.group(2) else n) if '-' in tok else a
            if a < 1 or b < a or b > n: raise ValueError(f'Η περιοχή «{tok}» είναι εκτός του εύρους 1–{n}.')
            out.append((a, b))
    if not out: raise ValueError('Δεν βρέθηκε καμία περιοχή.')
    if len(out) > MAX_PARTS: raise ValueError(f'Πάνω από {MAX_PARTS} κομμάτια· χώρισε σε περισσότερα βήματα.')
    return out


def out_dir(rel, hint=''):
    """(απόλυτη, σχετική) διαδρομή φακέλου εξόδου: πρέπει να είναι μέσα σε φάκελο 07_EXAGOGES. Κενό -> <μάθημα>/07_EXAGOGES/files από το hint."""
    rel = clean_rel(rel)
    if not rel:
        h = clean_rel(hint).split('/')[0] if hint else ''
        if not h: raise Refuse('Λείπει φάκελος εξόδου', ['Δώσε φάκελο εξόδου μέσα σε <b>07_EXAGOGES</b>, π.χ. <code>B-ILEKTROTECHNIA/07_EXAGOGES/files</code>.'], 422)
        rel = f'{h}/{OUT}/files'
    if OUT not in rel.split('/') or in_trash(rel): raise Refuse('Μη επιτρεπτός φάκελος εξόδου', [f'Τα νέα αρχεία γράφονται μόνο μέσα σε φάκελο <b>{OUT}</b> (εκεί που αποθηκεύονται οι εξαγωγές), ώστε να μην ανακατεύονται με τα πρωτότυπα. Ζητήθηκε: <b>{E(rel)}</b>.'], 422)
    p, rel = resolve(rel, must_exist=False)
    if os.path.exists(p) and not os.path.isdir(p): raise Refuse('Μη έγκυρος φάκελος εξόδου', [f'Το «{E(rel)}» είναι αρχείο.'], 422)
    return p, rel


def pdf_info(rel):
    """(απόλυτη, σχετική, πλήθος σελίδων). Διαβάζει μόνο· αρνείται κρυπτογραφημένα/μεγάλα/μη PDF."""
    from pypdf import PdfReader
    p, rel = resolve(rel)
    if not os.path.isfile(p) or not rel.lower().endswith('.pdf') or in_trash(rel): raise Refuse('Μη έγκυρο PDF', [f'Το «{E(rel)}» δεν είναι αρχείο PDF του φακέλου δεδομένων.'], 422)
    if os.path.getsize(p) > MAX_SRC: raise Refuse('Πολύ μεγάλο PDF', [f'Το «{E(rel)}» ξεπερνά τα {human(MAX_SRC)}.'], 422)
    try:
        r = PdfReader(p, strict=False)
        if r.is_encrypted: raise Refuse('Κρυπτογραφημένο PDF', [f'Το «{E(rel)}» είναι κρυπτογραφημένο.'], 422)
        return p, rel, len(r.pages)
    except Refuse: raise
    except Exception: raise Refuse('Δεν διαβάζεται το PDF', [f'Το «{E(rel)}» δεν άνοιξε ως PDF.'], 422)


# ---------- σχέδια (dry-run) ----------
def _status(base, names, outp):
    """Έλεγχος ονόματος εξόδου: (κατάσταση, μήνυμα)."""
    bad = valid_name(base)
    if bad: return 'bad', bad
    if base.rsplit('.', 1)[-1].lower() not in ALLOWED_EXT: return 'bad', 'Μη επιτρεπτή επέκταση.'
    if base.lower() in names: return 'dup', 'Διπλό όνομα μέσα στο ίδιο σχέδιο.'
    if os.path.exists(os.path.join(outp, base)): return 'exists', 'Υπάρχει ήδη· δεν αντικαθίσταται.'
    return 'ok', ''


def split_plan(src, spec, pat, outdir):
    sp, srel, n = pdf_info(src); op, orel = out_dir(outdir, srel)
    try: check_pattern(pat, SPLIT_KEYS); parts = parse_ranges(spec, n)
    except ValueError as e: raise Refuse('Μη έγκυρες ρυθμίσεις', [E(str(e))], 422)
    stem = os.path.basename(srel)[:-4]; names = set(); items = []
    for i, (a, b) in enumerate(parts, 1):
        name = fill(pat, name=stem, n=i, **{'from': a, 'to': b}) + '.pdf'; st, msg = _status(name, names, op); names.add(name.lower())
        items.append(dict(name=name, rel=f'{orel}/{name}', a=a, b=b, status=st, msg=msg))
    return dict(kind='split', src=srel, pages=n, out=orel, outp=op, items=items)


def merge_plan(srcs, outname, outdir, order='list'):
    if not srcs: raise Refuse('Δεν επιλέχθηκαν αρχεία', ['Διάλεξε τουλάχιστον ένα PDF.'], 422)
    if len(srcs) > MAX_FILES: raise Refuse('Πάρα πολλά αρχεία', [f'Όριο {MAX_FILES} αρχεία.'], 422)
    infos = [pdf_info(s) for s in dict.fromkeys(srcs)]
    if order == 'name': infos.sort(key=lambda x: natkey(os.path.basename(x[1])))
    elif order == 'path': infos.sort(key=lambda x: natkey(x[1]))
    op, orel = out_dir(outdir, infos[0][1]); name = (outname or 'merged.pdf').strip()
    if not name.lower().endswith('.pdf'): name += '.pdf'
    st, msg = _status(name, set(), op); total = sum(i[2] for i in infos)
    if total > MAX_PAGES: st, msg = 'bad', f'Πάνω από {MAX_PAGES} σελίδες συνολικά ({total}).'
    return dict(kind='merge', srcs=[(i[1], i[2]) for i in infos], total=total, out=orel, outp=op, name=name, status=st, msg=msg, rel=f'{orel}/{name}')


def rename_plan(srcs, mode, find, repl, rx, tpl, start, width, outdir):
    if not srcs: raise Refuse('Δεν επιλέχθηκαν αρχεία', ['Διάλεξε τουλάχιστον ένα αρχείο.'], 422)
    if len(srcs) > MAX_FILES: raise Refuse('Πάρα πολλά αρχεία', [f'Όριο {MAX_FILES} αρχεία.'], 422)
    try:
        check_pattern(tpl or '{name}', RENAME_KEYS); start = int(start or 0); width = int(width or 0)
        if not (0 <= start <= 99999 and 0 <= width <= 6): raise ValueError('Μη έγκυρη αρίθμηση.')
        cre = None
        if find:
            if len(find) > 80: raise ValueError('Το «βρες» είναι πολύ μεγάλο.')
            cre = re.compile(find if rx else re.escape(find))
    except (ValueError, re.error) as e: raise Refuse('Μη έγκυρες ρυθμίσεις', [E(str(e))], 422)
    tpl = tpl or '{name}'; items = []; files = []
    for s in dict.fromkeys(srcs):
        p, rel = resolve(s)
        if not os.path.isfile(p) or in_trash(rel): raise Refuse('Μη έγκυρο αρχείο', [f'Το «{E(rel)}» δεν είναι αρχείο του φακέλου δεδομένων.'], 422)
        files.append((p, rel))
    files.sort(key=lambda x: natkey(os.path.basename(x[1])))
    copy = mode == 'copy'
    if copy: op, orel = out_dir(outdir, files[0][1])
    olds = {rel.lower() for _, rel in files}; names = {}; seen = set()
    for i, (p, rel) in enumerate(files):
        base = os.path.basename(rel); stem, dot, ext = base.rpartition('.')
        if not dot: stem, ext = base, ''
        try: stem2 = cre.sub(repl or '', stem) if cre else stem
        except (re.error, IndexError) as e: raise Refuse('Μη έγκυρη αντικατάσταση', [E(str(e))], 422)
        t = tpl.replace('{n}', f'{{n:0{width}d}}') if width else tpl
        new = fill(t, name=stem2, n=start + i)
        new = new + ('.' + ext if ext else '')
        folder = orel if copy else (rel.rsplit('/', 1)[0] if '/' in rel else ''); new_rel = (folder + '/' if folder else '') + new
        lvl, msg = 'ok', ''
        if new == base and not copy: lvl, msg = 'same', 'Χωρίς αλλαγή.'
        else:
            lvl, msg = _status(new, seen, op if copy else os.path.dirname(p)); seen.add(new.lower())
            if lvl == 'ok' and not copy and new_rel.lower() in olds: lvl, msg = 'exists', 'Το όνομα ταυτίζεται με άλλο αρχείο της επιλογής.'
            if lvl == 'ok' and not copy:
                if classify(new_rel, False)['level'] == 'block': lvl, msg = 'bad', 'Το νέο όνομα ταιριάζει σε προστατευμένη κατηγορία συστήματος.'
                else:
                    a, why = assess(rel, 'rename')
                    if a == 'block': lvl, msg = 'blocked', 'Προστατευμένο αρχείο (πρωτότυπο ΙΕΠ, βιβλίο, ύλη κ.λπ.): χρησιμοποίησε «σε αντίγραφα».'
                    elif a == 'warn': lvl, msg = 'warn', 'Αρχείο με εξάρτηση από το σύστημα (λύση ή εικόνα λύσης): θέλει επιβεβαίωση.'
        items.append(dict(rel=rel, name=new, new_rel=new_rel, status=lvl, msg=msg, p=p))
    return dict(kind='rename', mode='copy' if copy else 'inplace', out=orel if copy else '', outp=op if copy else '', items=items)


# ---------- εφαρμογή ----------
def _space(outp, est):
    d = outp
    while d and not os.path.exists(d): d = os.path.dirname(d)
    free = shutil.disk_usage(d or root()).free
    if est + RESERVE > free: raise Refuse('Δεν υπάρχει αρκετός χώρος', [f'Χρειάζονται ~{human(est)} και πρέπει να μένουν {human(RESERVE)} ελεύθερα.'], 507)


def apply_plan(plan, confirm=False):
    """-> (μήνυμα, πλήθος που έγιναν). Γράφει μόνο καινούργια αρχεία ('xb')· ό,τι δεν είναι 'ok' (ή 'warn' με επιβεβαίωση) παραλείπεται."""
    from pypdf import PdfReader, PdfWriter
    c = db(); done = 0; skipped = 0
    try:
        if plan['kind'] == 'split':
            ok = [i for i in plan['items'] if i['status'] == 'ok']
            if not ok: raise Refuse('Τίποτα για εκτέλεση', ['Κανένα κομμάτι δεν είναι έτοιμο (δες την προεπισκόπηση).'], 409)
            sp = resolve(plan['src'])[0]; _space(plan['outp'], os.path.getsize(sp) * sum(i['b'] - i['a'] + 1 for i in ok) // max(plan['pages'], 1) + 1)
            os.makedirs(plan['outp'], exist_ok=True); r = PdfReader(sp, strict=False)
            for i in ok:
                w = PdfWriter()
                for k in range(i['a'] - 1, i['b']): w.add_page(r.pages[k])
                with open(os.path.join(plan['outp'], i['name']), 'xb') as f: w.write(f)
                log(c, 'split', i['rel'], f"από {plan['src']} σελ. {i['a']}-{i['b']}"); done += 1
            skipped = len(plan['items']) - done; msg = f'Δημιουργήθηκαν {done} αρχεία PDF στο «{plan["out"]}».'
        elif plan['kind'] == 'merge':
            if plan['status'] != 'ok': raise Refuse('Η συγχώνευση δεν μπορεί να γίνει', [E(plan['msg'])], 409)
            _space(plan['outp'], sum(os.path.getsize(resolve(s)[0]) for s, _ in plan['srcs']) + 1)
            os.makedirs(plan['outp'], exist_ok=True); w = PdfWriter()
            for s, n in plan['srcs']:
                r = PdfReader(resolve(s)[0], strict=False); first = len(w.pages)
                for pg in r.pages: w.add_page(pg)
                w.add_outline_item(title=os.path.basename(s), page_number=first)
            with open(os.path.join(plan['outp'], plan['name']), 'xb') as f: w.write(f)
            log(c, 'merge', plan['rel'], f"{len(plan['srcs'])} αρχεία, {plan['total']} σελίδες"); done = 1
            msg = f'Δημιουργήθηκε το «{plan["rel"]}» ({plan["total"]} σελίδες).'
        else:
            ok = [i for i in plan['items'] if i['status'] == 'ok' or (i['status'] == 'warn' and confirm)]
            if not ok: raise Refuse('Τίποτα για εκτέλεση', ['Κανένα αρχείο δεν είναι έτοιμο (δες την προεπισκόπηση ή τσέκαρε την επιβεβαίωση).'], 409)
            if plan['mode'] == 'copy':
                _space(plan['outp'], sum(os.path.getsize(i['p']) for i in ok)); os.makedirs(plan['outp'], exist_ok=True)
                for i in ok:
                    dst = os.path.join(plan['outp'], i['name'])
                    with open(i['p'], 'rb') as a, open(dst, 'xb') as b: shutil.copyfileobj(a, b)
                    log(c, 'copy', i['new_rel'], 'αντίγραφο από ' + i['rel']); done += 1
                msg = f'Αντιγράφηκαν {done} αρχεία στο «{plan["out"]}» με τα νέα ονόματα (τα πρωτότυπα δεν άλλαξαν).'
            else:
                for i in ok:
                    dst = os.path.join(os.path.dirname(i['p']), i['name'])
                    if os.path.exists(dst): continue
                    os.rename(i['p'], dst); log(c, 'rename', i['rel'], '→ ' + i['new_rel']); done += 1
                msg = f'Μετονομάστηκαν {done} αρχεία.'
            skipped = len(plan['items']) - done
        c.commit()
    finally: c.close()
    return msg + (f' Παραλείφθηκαν {skipped}.' if skipped else ''), done


# ---------- σελίδες ----------
CSS = (FB.CSS + "<style>.fotabs{display:flex;gap:.4rem;margin:.4rem 0 .8rem}.fotabs a{padding:.3rem .7rem;border:1px solid var(--border);border-radius:var(--radius);text-decoration:none}.fotabs a.on{background:var(--accent);color:#fff}"
       ".fol{max-height:22rem;overflow:auto;border:1px solid var(--border);border-radius:var(--radius);padding:.3rem .6rem}.fol label{display:block}.st-ok{color:#2e9d57}.st-warn{color:#c47f00}.st-bad,.st-blocked,.st-exists,.st-dup{color:#d33}.st-same{color:var(--muted)}</style>")
ICON = {'ok': '✔', 'warn': '⚠', 'bad': '✖', 'blocked': '🔒', 'exists': '✖', 'dup': '✖', 'same': '–'}


def folders(limit=300):
    out = []
    r = root()
    for dp, dn, fn in os.walk(r):
        dn[:] = sorted((d for d in dn if not d.startswith('.') and d != TRASH and not d.startswith('_')), key=natkey)
        rel = os.path.relpath(dp, r).replace(os.sep, '/')
        if rel != '.' and rel.count('/') <= 3: out.append(rel)
        if len(out) >= limit: break
    return sorted(out, key=natkey)


def listing(d, pdf_only):
    p, rel = resolve(d)
    if not os.path.isdir(p): raise Refuse('Δεν είναι φάκελος', [E(rel)], 422)
    names = [n for n in os.listdir(p) if os.path.isfile(os.path.join(p, n)) and not n.startswith('.') and (not pdf_only or n.lower().endswith('.pdf'))]
    return rel, sorted(names, key=natkey)


def hidden(pairs): return ''.join(f"<input type=hidden name='{E(k)}' value='{E(v)}'>" for k, v in pairs)


def form_page(tab, d, msg=''):
    tabs = '<div class=fotabs>' + ''.join(f"<a class='{'on' if k == tab else ''}' href='/fileops?tab={k}'>{E(t)}</a>" for k, t in TABS) + '</div>'
    opts = ''.join(f"<option value='{E(f)}'{' selected' if f == d else ''}>{E(f)}</option>" for f in folders())
    pick = (f"<form method=get action='/fileops' class=filters><input type=hidden name=tab value='{tab}'><label class=f>Φάκελος <select class=r-list name=dir><option value=''>— διάλεξε —</option>{opts}</select></label>"
            "<button>Φόρτωση αρχείων</button></form>")
    head = f"<h2>Εργαλεία αρχείων</h2>{f'<div class=note>{E(msg)}</div>' if msg else ''}{tabs}{pick}"
    if not d: return page('Εργαλεία αρχείων', CSS + head + "<p><i>Διάλεξε φάκελο και πάτα «Φόρτωση αρχείων».</i></p>")
    rel, names = listing(d, tab != 'rename')
    if not names: return page('Εργαλεία αρχείων', CSS + head + '<p><i>Δεν υπάρχουν κατάλληλα αρχεία σε αυτόν τον φάκελο.</i></p>')
    kind = 'radio' if tab == 'split' else 'checkbox'
    boxes = ''.join(f"<label><input type={kind} {'class=r-opt ' if kind == 'checkbox' else ''}name=src value='{E((rel + '/' if rel else '') + n)}'> {E(n)}</label>" for n in names)
    allb = "<label><input type=checkbox data-all='src'> επιλογή όλων</label>" if kind == 'checkbox' else ''
    if tab == 'split':
        opt = ("<label class=f>Σελίδες <input class=r-txt name=spec size=30 placeholder='1-3, 4-6, 8  ή  κάθε 5'></label> <label class=f>Όνομα αρχείων <input class=r-txt name=pat size=34 value='{name}_{n:02d}_σελ{from}-{to}'></label>"
               "<p><small>Πεδία: {name} όνομα πηγής, {n} αύξων, {from} {to} σελίδες. Η πηγή δεν αλλάζει.</small></p>")
    elif tab == 'merge':
        opt = ("<label class=f>Όνομα εξόδου <input class=r-txt name=outname size=30 value='merged.pdf'></label> <label class=f>Σειρά <select class=r-list name=order><option value=name>αλφαβητικά (φυσική)</option><option value=list>όπως στη λίστα</option></select></label>"
               "<p><small>Σελιδοδείκτης ανά αρχείο. Τα πρωτότυπα δεν αλλάζουν.</small></p>")
    else:
        opt = ("<fieldset><legend>Πού</legend><label class='f chk'><input type=radio name=mode value=copy checked> σε αντίγραφα (στον φάκελο εξόδου· λειτουργεί και για πρωτότυπα)</label>"
               "<label class='f chk'><input type=radio name=mode value=inplace> επί τόπου (με τις προστασίες του file browser)</label></fieldset>"
               "<label class=f>Βρες <input class=r-txt name=find size=18></label> <label class=f>Αντικατάστησε με <input class=r-txt name=repl size=18></label> <label class='f chk'><input type=checkbox name=rx value=1> κανονική έκφραση</label>"
               "<label class=f>Μοτίβο <input class=r-txt name=tpl size=24 value='{name}'></label> <label class=f>Αρχή αρίθμησης <input class=r-txt name=start size=5 value='1'></label> <label class=f>Ψηφία <input class=r-txt name=width size=3 value='2'></label>"
               "<p><small>Μοτίβο: {name} (το όνομα μετά το «βρες/αντικατάστησε»), {n} αρίθμηση, π.χ. <code>θέμα_{n}_{name}</code>. Η επέκταση διατηρείται.</small></p>")
    outf = f"<label class=f>Φάκελος εξόδου (μέσα σε {OUT}) <input class=r-txt name=outdir size=40 placeholder='κενό = &lt;μάθημα&gt;/{OUT}/files'></label>"
    body = (head + f"<form method=post action='/fileops/preview'><input type=hidden name=tab value='{tab}'><input type=hidden name=dir value='{E(rel)}'>"
            f"<h3>Αρχεία στον φάκελο «{E(rel)}»</h3>{allb}<div class=fol>{boxes}</div>{opt}{outf}<p><button class=primary>Προεπισκόπηση (δεν αλλάζει τίποτα)</button></p></form>")
    return page('Εργαλεία αρχείων', CSS + body)


def get_plan(f):
    tab = f.get('tab'); g = lambda k, d='': str(f.get(k) or d); srcs = [str(x) for x in f.getlist('src')]
    if tab == 'split':
        if len(srcs) != 1: raise Refuse('Διάλεξε ένα PDF', ['Ο χωρισμός δουλεύει σε ένα PDF τη φορά.'], 422)
        return split_plan(srcs[0], g('spec'), g('pat', '{name}_{n:02d}'), g('outdir'))
    if tab == 'merge': return merge_plan(srcs, g('outname'), g('outdir'), g('order', 'name'))
    if tab == 'rename': return rename_plan(srcs, g('mode', 'copy'), g('find'), g('repl'), bool(g('rx')), g('tpl', '{name}'), g('start', '1'), g('width', '0'), g('outdir'))
    raise Refuse('Άγνωστη ενέργεια', [E(str(tab))], 422)


def preview_page(f, plan):
    keep = [(k, str(v)) for k, v in f.multi_items() if k not in ('confirm',)]
    if plan['kind'] == 'merge':
        rows = ''.join(f"<tr><td>{E(s)}</td><td>{n}</td></tr>" for s, n in plan['srcs'])
        tbl = (f"<p>Έξοδος: <b>{E(plan['rel'])}</b> · {plan['total']} σελίδες · <span class='st-{plan['status']}'>{ICON[plan['status']]} {E(plan['msg'] or 'έτοιμο')}</span></p>"
               f"<table><tr><th>Αρχείο (με τη σειρά συγχώνευσης)</th><th>Σελίδες</th></tr>{rows}</table>"); n_ok = 1 if plan['status'] == 'ok' else 0; warn = False
    else:
        if plan['kind'] == 'split':
            rows = ''.join(f"<tr><td>σελ. {i['a']}–{i['b']}</td><td>{E(i['rel'])}</td><td class='st-{i['status']}'>{ICON[i['status']]} {E(i['msg'] or 'έτοιμο')}</td></tr>" for i in plan['items'])
            tbl = f"<p>Πηγή: <b>{E(plan['src'])}</b> ({plan['pages']} σελίδες)</p><table><tr><th>Μέρος</th><th>Νέο αρχείο</th><th>Κατάσταση</th></tr>{rows}</table>"
        else:
            rows = ''.join(f"<tr><td>{E(i['rel'])}</td><td>{E(i['new_rel'])}</td><td class='st-{i['status']}'>{ICON[i['status']]} {E(i['msg'] or 'έτοιμο')}</td></tr>" for i in plan['items'])
            tbl = f"<p>Τρόπος: <b>{'σε αντίγραφα' if plan['mode'] == 'copy' else 'επί τόπου'}</b></p><table><tr><th>Τώρα</th><th>Μετά</th><th>Κατάσταση</th></tr>{rows}</table>"
        n_ok = sum(1 for i in plan['items'] if i['status'] == 'ok'); warn = any(i['status'] == 'warn' for i in plan['items'])
    conf = "<label class='f chk'><input type=checkbox name=confirm value=1> καταλαβαίνω τον κίνδυνο (αρχεία λύσεων/εικόνων που συνδέονται με το σύστημα)</label>" if warn else ''
    go = (f"<form method=post action='/fileops/apply'>{hidden(keep)}{conf}<button class=primary>Εφαρμογή ({n_ok}{'+' if warn else ''})</button> " if n_ok or warn else "<form><p><b>Τίποτα δεν είναι έτοιμο.</b></p>")
    back = f"<a class=btn href='/fileops?tab={quote(str(f.get('tab') or 'split'))}&dir={quote(str(f.get('dir') or ''))}' data-back>← Πίσω</a></form>"
    return page('Προεπισκόπηση αρχείων', CSS + f"<h2>Προεπισκόπηση</h2><div class='note'>Δεν έχει αλλάξει τίποτα ακόμη.</div>{tbl}{go}{back}")


@router.get('/fileops', response_class=HTMLResponse, dependencies=[Depends(auth)])
@handle
def fileops_page(tab: str = 'split', dir: str = '', msg: str = ''):
    return form_page(tab if tab in dict(TABS) else 'split', dir, msg)


@router.post('/fileops/preview', response_class=HTMLResponse, dependencies=[Depends(auth)])
@handle
async def fileops_preview(request: Request):
    same_origin(request); f = await request.form(); return preview_page(f, get_plan(f))


@router.post('/fileops/apply', dependencies=[Depends(auth)])
@handle
async def fileops_apply(request: Request):
    same_origin(request); f = await request.form(); plan = get_plan(f)
    msg, _ = apply_plan(plan, bool(f.get('confirm')))
    from urllib.parse import quote
    return RedirectResponse(f"/fileops?tab={quote(str(f.get('tab')))}&dir={quote(str(f.get('dir') or ''))}&msg={quote(msg)}", status_code=303)
