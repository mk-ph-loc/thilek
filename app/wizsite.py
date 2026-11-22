"""0.22: «ένα-ένα» εξαγωγή του wizard: μία σελίδα ανά θέμα ή ερώτημα + index + data.json + zip.
Διαχωρισμός: τα δεδομένα (data.json: ερωτήματα, μονάδες, αρχεία) φτιάχνονται ξεχωριστά από την παρουσίαση (σελίδες/index)."""
import io, json, re, zipfile
from html import escape as _E
from . import config, solexport as X
from . import wizmodel as M

GRAN = (('item', 'ένα αρχείο ανά θέμα'), ('question', 'ένα αρχείο ανά ερώτημα'))


def E(s): return _E(str(s))


def groups(es, gran):
    """Ορατά ερωτήματα ομαδοποιημένα: κλειδί -> [entries] (με τη σειρά εμφάνισης)."""
    out = {}
    for e in es:
        if e['vis'] != 'show': continue
        k = f"t{e['item']}" if gran != 'question' else f"q{e['item']}_{e['code']}"
        out.setdefault(re.sub(r'[^A-Za-z0-9_-]+', '-', k), []).append(e)
    return out


def data_model(c, st, es):
    """Καθαρά δεδομένα (χωρίς HTML): τίτλος, σύνολο, σελίδες με ερωτήματα και μονάδες, όσα δεν έχουν λύση."""
    gs = groups(es, st.get('gran', 'item')); pages, skipped = [], []
    for k, ents in gs.items():
        rows = X.load(c, [(e['item'], e['code']) for e in ents])
        have = {(r['item_id'], r['qcode']) for r in rows}
        miss = [f"{e['item']}/{e['code']}" for e in ents if (e['item'], e['code']) not in have]
        skipped += miss
        if not rows: continue
        qs = [{'item': e['item'], 'code': e['code'], 'points': e['pts']} for e in ents if (e['item'], e['code']) in have]
        first = rows[0]
        title = f"Θέμα {first['item_id']}" if st.get('gran', 'item') != 'question' else f"Θέμα {first['item_id']} · ερώτημα {first['qcode']}"
        pages.append({'file': k + '.html', 'title': title, 'points': sum(q['points'] for q in qs), 'questions': qs, 'keys': [(q['item'], q['code']) for q in qs]})
    return {'title': st['title'], 'total': sum(p['points'] for p in pages), 'format': st['format'], 'pages': pages, 'skipped': skipped}


def index_html(model):
    li = ''.join(f"<li><a href='{E(p['file'])}'>{E(p['title'])}</a> <span>{len(p['questions'])} ερωτήματα · {M.fmt_pts(p['points'])} μον.</span></li>" for p in model['pages'])
    sk = f"<p class=sk>Δεν περιλαμβάνονται (χωρίς λύση): {E(', '.join(model['skipped']))}</p>" if model['skipped'] else ''
    return ("<!doctype html><html lang=el><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{E(model['title'])}</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#1b2430}}"
            "h1{margin-bottom:.2rem}ol{padding-left:1.4rem}li{margin:.5rem 0}li span{color:#5b6877;font-size:.9em;margin-left:.5rem}a{color:#0b5cad;font-weight:600}.sk{color:#8a5a00}</style>"
            f"<h1>{E(model['title'])}</h1><p>Σύνολο μονάδων: <b>{M.fmt_pts(model['total'])}</b></p><ol>{li}</ol>{sk}</html>")


def build_site(c, st, es):
    """-> (αρχεία {όνομα: bytes}, μοντέλο). Μορφές: reveal (παρουσίαση ανά σελίδα) ή student (HTML μαθητή)."""
    fm = st['format']
    if fm not in ('reveal', 'student'): raise ValueError('format')
    model = data_model(c, st, es); root = config.load()['data_root']
    inc = X.include_of(st['sx']); style = X.style_of(st['style']); files = {}
    for p in model['pages']:
        rows = X.load(c, p['keys'])
        if fm == 'reveal': h = X.reveal_html(rows, p['title'], inc, style, root, bool(st.get('frag')))
        else:
            from .solhtml import student_html
            h = student_html(rows, p['title'], inc, style, root, bool(st['hide']))
        files[p['file']] = h.encode('utf-8')
    if not files: return {}, model
    pub = {k: v for k, v in model.items()}; pub['pages'] = [{k: v for k, v in p.items() if k != 'keys'} for p in model['pages']]
    files['index.html'] = index_html(model).encode('utf-8')
    files['data.json'] = json.dumps(pub, ensure_ascii=False, indent=1).encode('utf-8')
    return files, model


def zip_bytes(files, readme=''):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items(): z.writestr(n, d)
        if readme: z.writestr('README.txt', readme)
    return b.getvalue()
