"""Οθόνη ελέγχου συνδέσεων ερώτημα ↔ υποενότητα βιβλίου. Απλό HTML χωρίς εξωτερικά αρχεία (CSP: μόνο 'self')."""
import html as _html, sqlite3, pathlib, re
from urllib.parse import urlparse, urlencode, parse_qsl
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from . import config, migrations, __version__
from .main_auth import auth

router = APIRouter()
TYPES = {'mcq': 'Πολλαπλής επιλογής', 'true_false': 'Σωστό/Λάθος', 'matching': 'Αντιστοίχισης', 'fill': 'Συμπλήρωσης κενών',
         'problem': 'Προβλήματος (υπολογισμοί)', 'development': 'Ανάπτυξης'}   # ίδιο με tools/classify.py
TYPE_OPTS = lambda cur: ''.join(f"<option value='{k}'{' selected' if k == cur else ''}>{v}</option>" for k, v in TYPES.items())
class html:                       # html.escape ανεκτικό σε None
    @staticmethod
    def escape(v): return _html.escape('' if v is None else str(v))

CSS = """
:root{--bg:#fff;--fg:#222;--muted:#666;--head:#1f3a5f;--headfg:#fff;--card:#fff;--border:#ccc;--th:#eef;--rowalt:#fafafa;--hover:#f0f5ff;--accent:#1f3a5f;--btn:#f3f3f3;--btnfg:#222;--code:#f6f6f6;--radius:4px;--shadow:none;--font:system-ui,sans-serif;--pad:.25rem .5rem;
 --t-iep:#e8eef7;--t-auto:#fff3cd;--t-manual:#d4edda;--t-ai:#e2d9f3}
[data-theme=dark]{--bg:#14181f;--fg:#e4e8ee;--muted:#9aa4b2;--head:#0b0e13;--headfg:#e4e8ee;--card:#1b212b;--border:#303845;--th:#232b38;--rowalt:#171c25;--hover:#222c3b;--accent:#5aa2ff;--btn:#263041;--btnfg:#e4e8ee;--code:#10141a;--radius:6px;
 --t-iep:#243247;--t-auto:#4a4222;--t-manual:#1f4130;--t-ai:#38304d;color-scheme:dark}
[data-theme=soft]{--bg:#f3f6f3;--fg:#233028;--muted:#6a7a6f;--head:#2f6b4f;--headfg:#fff;--card:#fff;--border:#dce4de;--th:#e5efe8;--rowalt:#f8fbf8;--hover:#eef6f0;--accent:#2f6b4f;--btn:#e8f1eb;--btnfg:#1f3a2c;--code:#f0f5f1;--radius:10px;--pad:.4rem .65rem;
 --shadow:0 1px 3px rgba(0,0,0,.07),0 6px 16px rgba(0,0,0,.05);--font:'Segoe UI',system-ui,sans-serif;--t-iep:#e0eaf4;--t-auto:#fbf0c9;--t-manual:#d3ecdb;--t-ai:#e6ddf4}
*{scrollbar-width:thin;scrollbar-color:var(--accent) var(--th)}::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-track{background:var(--th)}::-webkit-scrollbar-thumb{background:var(--accent);border-radius:6px;border:2px solid var(--th)}
body{font:15px/1.45 var(--font);margin:0;color:var(--fg);background:var(--bg)}a{color:var(--accent)}
header{background:var(--head);color:var(--headfg);padding:.55rem 1rem;display:flex;flex-wrap:wrap;align-items:center;gap:.2rem 1rem;box-shadow:var(--shadow)}header a{color:var(--headfg);text-decoration:none;opacity:.9}header a:hover{opacity:1;text-decoration:underline}header .sp{flex:1}header label{font-size:.85rem}
main{padding:1rem}h2{margin:.2rem 0 .8rem}h3{margin:1rem 0 .4rem}
form{display:inline}.filters{display:flex;flex-wrap:wrap;gap:.6rem 1rem;align-items:end;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.6rem .8rem;margin:.4rem 0 .8rem;box-shadow:var(--shadow)}
.f{display:flex;flex-direction:column;font-size:.78rem;color:var(--muted);gap:.15rem}.f.chk{flex-direction:row;align-items:center;gap:.35rem;font-size:.9rem;color:var(--fg)}.f small{font-size:.8rem}
input,select,button{font:inherit;color:var(--fg)}input[type=text],input:not([type]),input[type=number],select{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.28rem .4rem;color:var(--fg)}
button{background:var(--btn);color:var(--btnfg);border:1px solid var(--border);border-radius:var(--radius);padding:.28rem .7rem;cursor:pointer}button:hover{border-color:var(--accent)}.filters button,button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
fieldset{border:1px solid var(--border);border-radius:var(--radius);background:var(--card);box-shadow:var(--shadow);margin:.5rem 0;padding:.5rem .8rem}legend{padding:0 .4rem;color:var(--muted)}.bar2{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:.5rem 1.2rem}.bar2 div{padding:.35rem .5rem;border:1px solid var(--border);border-radius:var(--radius)}.bar2 legend{grid-column:1/-1}.q form{display:block;margin:.35rem 0}.q select{max-width:100%}
.scroll{overflow:auto;max-height:68vh;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);box-shadow:var(--shadow);margin:.4rem 0}
table{border-collapse:separate;border-spacing:0;width:100%}td,th{border-bottom:1px solid var(--border);padding:var(--pad);text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--th);z-index:1;white-space:nowrap}th.sortable{cursor:pointer;user-select:none}th.sortable:hover{color:var(--accent)}tr:nth-child(even) td{background:var(--rowalt)}tr:hover td{background:var(--hover)}
.q{border:1px solid var(--border);border-radius:var(--radius);padding:.6rem;margin:.6rem 0;background:var(--card);box-shadow:var(--shadow)}pre{white-space:pre-wrap;background:var(--code);padding:.4rem;max-height:14rem;overflow:auto;border-radius:var(--radius)}
.tag{display:inline-block;border-radius:999px;padding:0 .55rem;font-size:.85em;color:var(--fg)}.iep{background:var(--t-iep)}.auto{background:var(--t-auto)}.manual{background:var(--t-manual)}.ai{background:var(--t-ai)}
.cols{display:grid;gap:1rem}.pane{max-height:82vh;overflow:auto;padding-right:.3rem}iframe{width:100%;height:80vh;border:1px solid var(--border);border-radius:var(--radius);background:#fff}
.star{background:none;border:0;font-size:1.25rem;cursor:pointer;color:var(--muted,#888);padding:0 .2rem}.star.on{color:#e6a700}.qv img{max-width:100%;border:1px solid var(--border);background:#fff}.btn{display:inline-block;padding:.4rem .8rem;border:1px solid var(--accent);border-radius:var(--radius);text-decoration:none}.tabs{display:flex;gap:.2rem;border-bottom:2px solid var(--border);margin:.4rem 0 .8rem}.tab{padding:.45rem .9rem;border:1px solid var(--border);border-bottom:0;border-radius:var(--radius) var(--radius) 0 0;background:var(--card);text-decoration:none}.tab.on{font-weight:bold;background:var(--accent);color:#fff}.pqlist{list-style:none;padding:0;max-width:900px}.pq{border:1px solid var(--border);background:var(--card);border-radius:var(--radius);padding:.4rem .6rem;margin:.5rem 0}.pq img{max-width:100%;background:#fff;border:1px solid var(--border)}.pqn{font-weight:bold;font-size:1.1rem}.foot,footer{margin:2rem 1rem 1rem;padding-top:.5rem;border-top:1px solid var(--border);font-size:.85rem;color:var(--muted,#777)}.mdbar{margin:.3rem 0;display:flex;flex-wrap:wrap;gap:.3rem;align-items:center}#pv{position:fixed;z-index:50;display:none;border:2px solid var(--accent);background:#fff;box-shadow:0 6px 24px rgba(0,0,0,.35);pointer-events:none}#pv img{display:block;width:340px}.preview table{border-collapse:collapse}.preview td,.preview th{border:1px solid var(--border)}
.bar{margin:.3rem 0 .6rem;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:.4rem .7rem}.bar a,.bar b{margin-right:.8rem}.on{font-weight:bold}img{max-width:100%}
"""

from .uikit_css import UI_CSS
from .mdrich import RICH_CSS
from . import docsui
JS = (pathlib.Path(__file__).parent / 'static' / 'app.js').read_text(encoding='utf-8')
THEME_JS = (pathlib.Path(__file__).parent / 'static' / 'theme.js').read_text(encoding='utf-8')
@router.get('/static/app.js', include_in_schema=False)
def app_js(): return Response(JS, media_type='application/javascript')
@router.get('/static/theme.js', include_in_schema=False)
def theme_js(): return Response(THEME_JS, media_type='application/javascript')
def fld(label, ctrl, cls=''): return f"<label class='f {cls}'><span>{label}</span>{ctrl}</label>"
def chk(ctrl_label, ctrl): return f"<label class='f chk'>{ctrl}{ctrl_label}</label>"

CTX_KEYS = ('yli', 'todo', 'view', 'bp')
def ctx_of(raw):
    """Κρατά μόνο τις γνωστές παραμέτρους πλοήγησης (φίλτρο, πάνελ, σελίδα βιβλίου)."""
    d = {k: v for k, v in parse_qsl(raw or '') if k in CTX_KEYS and v and len(v) < 40}
    if 'bp' in d and not d['bp'].isdigit(): del d['bp']
    if 'view' in d: d['view'] = ','.join(x for x in d['view'].split(',') if x in ('sol', 'book'))
    return {k: v for k, v in d.items() if v}
def url(iid, d): return f'/review/{iid}' + ('?' + urlencode(d) if d else '')
def ordered_ids(c, yli='', todo=0):
    w, a = [], []
    if yli: w.append('i.iep_yli LIKE ?'); a.append(yli + '%')
    rows = c.execute(f"""SELECT i.id,(SELECT count(*) FROM question q WHERE q.item_id=i.id) nq,
        (SELECT count(*) FROM question q JOIN question_section s ON s.question_id=q.id WHERE q.item_id=i.id AND s.origin IN ('manual','ai')) nconf
        FROM item i {'WHERE ' + ' AND '.join(w) if w else ''} ORDER BY CAST(i.id AS INTEGER)""", a).fetchall()
    return [r['id'] for r in rows if not (todo and r['nq'] and r['nconf'] >= r['nq'])]

_MIGRATED = set()                 # διαδρομές βάσης που ελέγχθηκαν ήδη (migrations μία φορά ανά διαδρομή)
def db():
    path = config.load()['db']; c = sqlite3.connect(path); c.row_factory = sqlite3.Row
    if path not in _MIGRATED:
        _MIGRATED.add(path)
        try: migrations.migrate(c)
        except Exception as ex: print('migrations:', type(ex).__name__, ex)     # λάθος-ασφαλές: η σελίδα ανοίγει ούτως ή άλλως
    return c

def page(title, body):
    body = re.sub(r'<table>.*?</table>', lambda m: '<div class=scroll>' + m.group(0) + '</div>', body, flags=re.S)       # κύλιση + σταθερή επικεφαλίδα
    st = docsui.settings_now()
    h = HTMLResponse(f"<!doctype html><html lang='el'{docsui.html_attrs(st)}><meta charset='utf-8'><meta name=viewport content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><script src='/static/theme.js'></script><style>{CSS}{UI_CSS}{RICH_CSS}</style>"
                     f"<header><a href='/search'>Αναζήτηση</a><a href='/review'>Θέματα</a><a href='/browse'>Ερωτήματα</a><a href='/browse?fav=1'>★ Αγαπημένα</a><a href='/coverage'>Ύλη/σελίδα</a><a href='/tags'>Ετικέτες</a><a href='/saved'>Αποθηκευμένα</a><a href='/tools/merge'>Συγχώνευση PDF</a><a href='/tools/html'>Εξαγωγή HTML</a><a href='/exams'>Διαγωνίσματα</a><a href='/quizzes'>Quiz</a><a href='/wizard'>Wizard</a><a href='/decks' title='Παρουσιάσεις: διαφάνειες από λύσεις, Reveal, PDF, PowerPoint'>Παρουσιάσεις</a><a href='/sites' title='Site μαθήματος: σελίδες, μενού, quiz και παρουσιάσεις, zip'>Site</a><a href='/word' title='Word του ΙΕΠ: ανάγνωση και σύγκριση με PDF'>Word</a><a href='/courses' title='Μάθημα και πηγές θεμάτων'>Μαθήματα</a><a href='/own' title='Δικά μου θέματα και πανελλήνιες'>Δικά μου</a><a href='/compare' title='Σύγκριση απαντήσεων με το ΙΕΠ'>Σύγκριση ΙΕΠ</a><a href='/publish' title='Δημοσιευμένες σελίδες για μαθητές'>Δημοσιεύσεις</a><a href='/lyseis'>Λύσεις</a><a href='/docs'>Έγγραφα MD</a><a href='/fb'>Αρχεία</a><a href='/fileops' title='Χωρισμός, συγχώνευση και μετονομασία αρχείων'>Εργαλεία αρχείων</a><a href='/manual'>Οδηγίες</a><a href='/sync' title='Συγχρονισμός Drive και εντολές'>⟳ Συγχρονισμός</a><a href='/settings' title='Ρυθμίσεις'>⚙ Ρυθμίσεις</a><span class=sp></span><label>Εμφάνιση <select id=theme><option value=classic>Κλασική</option><option value=dark>Σκοτεινή</option><option value=soft>Απαλή</option></select></label><b>TH-ILEK</b></header><main>{docsui.help_html(None, st)}{body}</main><footer>TH-ILEK v{__version__} · <a href='/manual'>Οδηγίες</a> · <a href='/health'>health</a><span class=legend><span><i style='background:var(--c-sel)'></i>επιλογή γραμμών</span><span><i style='background:var(--c-opt)'></i>ρυθμίσεις ναι/όχι</span><span><i style='background:var(--c-list)'></i>λίστες</span><span><i style='background:var(--c-txt)'></i>πεδία κειμένου</span><span><i style='background:var(--c-file)'></i>αρχεία</span><span><i style='background:var(--c-danger)'></i>κίνδυνος</span></span></footer><script src='/static/app.js'></script><script src='/static/ui.js'></script><script src='/static/docs.js'></script></html>")
    h.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-src 'self'; img-src 'self'"
    return h

def same_origin(req: Request):
    src = req.headers.get('origin') or req.headers.get('referer')
    if not src or urlparse(src).netloc != req.headers.get('host'): raise HTTPException(403, 'cross-site request')

@router.get('/', include_in_schema=False)
def root():
    from . import settings
    return RedirectResponse(settings.get('start_page') or '/review')

@router.get('/review', response_class=HTMLResponse, dependencies=[Depends(auth)])
def review_list(yli: str = '', todo: int = 0):
    c = db(); w, a = [], []
    if yli: w.append('i.iep_yli LIKE ?'); a.append(yli + '%')
    from .library import active_course
    ac = active_course(c)
    if ac: w.append('i.course_code=?'); a.append(ac)
    rows = c.execute(f"""SELECT i.id,i.position,i.iep_yli,i.solution_status,(SELECT group_concat(kind||':'||status) FROM wordsrc ws WHERE ws.item_id=i.id) wst,
        (SELECT count(*) FROM question q WHERE q.item_id=i.id) nq,
        (SELECT count(*) FROM question q JOIN question_section s ON s.question_id=q.id WHERE q.item_id=i.id AND s.origin IN ('manual','ai')) nconf,
        (SELECT count(*) FROM question q JOIN question_section s ON s.question_id=q.id WHERE q.item_id=i.id AND s.origin='auto') nauto
        FROM item i {'WHERE ' + ' AND '.join(w) if w else ''} ORDER BY CAST(i.id AS INTEGER)""", a).fetchall()
    out = ["<form method='get' class=filters>" + fld('Ενότητα ΙΕΠ', "<input name=yli value='%s' size=6>" % html.escape(yli)) + chk('μόνο όσα δεν έχω επιβεβαιώσει', "<input type=checkbox name=todo value=1 %s>" % ('checked' if todo else '')) + "<button>Φίλτρο</button></form>",
           "<table><tr><th>ID</th><th>Θέμα</th><th>Ενότητα ΙΕΠ</th><th>Ερωτήματα</th><th>Επιβεβαιωμένα</th><th>Προτάσεις</th><th>Λύση</th><th title='Word ΙΕΠ'>W</th></tr>"]
    for r in rows:
        if todo and r['nq'] and r['nconf'] >= r['nq']: continue
        out.append(f"<tr><td><a href='{url(r['id'], ctx_of(urlencode({'yli': yli, 'todo': todo or ''})))}'>{r['id']}</a></td><td>{r['position'] or ''}</td><td>{html.escape(r['iep_yli'] or '')}</td><td>{r['nq']}</td><td>{r['nconf']}</td><td>{r['nauto']}</td><td>{html.escape(r['solution_status'] or '')}</td><td>{'' if not r['wst'] else ('<a href=/word/' + str(r['id']) + '>' + ('⚠' if 'warn' in r['wst'] else ('✖' if 'error' in r['wst'] else 'W')) + '</a>')}</td></tr>")
    out.append('</table>'); return page('Θέματα', ''.join(out))

@router.get('/review/{iid}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def review_item(iid: str, request: Request):
    ctx = ctx_of(request.url.query); views = set(ctx.get('view', '').split(',')) - {''}
    c = db(); it = c.execute('SELECT * FROM item WHERE id=?', (iid,)).fetchone()
    if not it: raise HTTPException(404)
    book = c.execute('SELECT * FROM book WHERE course_code=?', (it['course_code'],)).fetchone()
    secs = c.execute('SELECT s.id,s.code,s.title_el,s.page_from,s.page_to FROM section s WHERE s.book_id=? AND s.level=3 ORDER BY s.id', (book['id'],)).fetchall() if book else []
    opts = ''.join(f"<option value='{s['id']}'>{html.escape(s['code'])} {html.escape(s['title_el'] or '')} (σελ. {s['page_from']}–{s['page_to'] or s['page_from']})</option>" for s in secs)
    left = f"<iframe src='/files/{html.escape(it['statement_path'])}'></iframe>" if it['statement_path'] else '<p>Δεν υπάρχει αρχείο εκφώνησης.</p>'
    sol = f" · <a href='/files/{html.escape(it['solution_path'])}' target='_blank'>λύση ({html.escape(it['solution_status'] or '')})</a>" if it['solution_path'] else ''
    qs = []
    for q in c.execute('SELECT * FROM question WHERE item_id=? ORDER BY id', (iid,)):
        links = c.execute("""SELECT s.id sid,s.code,s.title_el,s.page_from,s.page_to,qs.origin,qs.score FROM question_section qs JOIN section s ON s.id=qs.section_id
                             WHERE qs.question_id=? AND qs.origin!='rejected' ORDER BY s.level DESC,s.id""", (q['id'],)).fetchall()
        li = []
        for l in links:
            pg = f"σελ. {l['page_from']}–{l['page_to'] or l['page_from']}"
            if book:
                pane = url(iid, {**ctx, 'view': ','.join(sorted(views | {'book'})), 'bp': l['page_from'] + book['pdf_offset']})
                pg = f"<a href='{html.escape(pane)}' title='άνοιγμα στο πάνελ βιβλίου'>{pg}</a> <a target='_blank' title='νέα καρτέλα' href='/files/{html.escape(book['relpath'])}#page={l['page_from'] + book['pdf_offset']}'>↗</a>"
            sc = f" {l['score']:.2f}" if l['score'] is not None else ''
            btn = ''
            if l['origin'] == 'auto':
                btn += f"<button name=action value=confirm:{l['sid']}>✔ επιβεβαίωση</button> "
            btn += f"<button name=action value=remove:{l['sid']}>✖ αφαίρεση</button>"
            li.append(f"<div><span class='tag {l['origin']}'>{l['origin']}{sc}</span> <b>{html.escape(l['code'])}</b> {html.escape(l['title_el'] or '')} ({pg}) {btn}</div>")
        tg = [r[0] for r in c.execute('SELECT tag FROM question_tag WHERE item_id=? AND qcode=? ORDER BY tag', (iid, q['code']))]
        tagform = (f"<form method='post' action='/select/act'><input type=hidden name=qids value={q['id']}><input type=hidden name=back value='{html.escape(url(iid, ctx))}'>"
                   f"Ετικέτες: {' '.join('<span class=tag iep>' + html.escape(t) + '</span>' for t in tg) or '—'} <input name=tag size=12 placeholder='νέα ετικέτα'><button name=act value=tag>+</button>"
                   + (f"<button name=act value=untag title='αφαίρεση της ετικέτας που γράφεις'>−</button>" if tg else '') + "</form>")
        meta = f"""<form method='post' action='/review/{html.escape(iid)}/meta'><input type=hidden name=ctx value='{html.escape(urlencode(ctx))}'><input type=hidden name=question_id value={q['id']}>
            <select name=qtype>{TYPE_OPTS(q['qtype'])}</select> <label><input type=checkbox name=has_image value=1 {'checked' if q['has_image'] else ''}> εικόνα/σχήμα</label>
            <span class='tag {'manual' if q['qtype_origin'] == 'manual' else 'auto'}'>{'χειροκίνητο' if q['qtype_origin'] == 'manual' else 'πρόταση'}</span> <button>Αποθήκευση</button></form>"""
        qs.append(f"""<div class='q'><b>{html.escape(q['code'])}</b> · {q['points'] if q['points'] is not None else '?'} μον. {meta}{tagform}<pre>{html.escape(q['text'] or '')}</pre>
            <form method='post' action='/review/{html.escape(iid)}/link'><input type=hidden name=ctx value='{html.escape(urlencode(ctx))}'><input type=hidden name=question_id value={q['id']}>{''.join(li) or '<i>χωρίς σύνδεση</i>'}
            <div>Προσθήκη: <select name=section_id><option value=''>— υποενότητα —</option>{opts}</select> <button name=action value=add>Ορισμός</button></div></form></div>""")
    ids = ordered_ids(c, ctx.get('yli', ''), int(ctx.get('todo', 0) or 0)); pos = ids.index(iid) if iid in ids else None
    nav_ctx = {k: v for k, v in ctx.items()}
    prev_a = f"<a rel=prev href='{html.escape(url(ids[pos - 1], nav_ctx))}'>◀ προηγούμενο ({ids[pos - 1]})</a>" if pos else '<span>◀</span>'
    next_a = f"<a rel=next href='{html.escape(url(ids[pos + 1], nav_ctx))}'>επόμενο ({ids[pos + 1]}) ▶</a>" if pos is not None and pos + 1 < len(ids) else '<span>▶</span>'
    where = f"{pos + 1}/{len(ids)}" if pos is not None else 'εκτός φίλτρου'
    def toggle(name, label, available=True):
        if not available: return f"<span title='δεν υπάρχει'>{label} (—)</span>"
        v = views ^ {name}
        return f"<a class='{'on' if name in views else ''}' href='{html.escape(url(iid, {**{k: x for k, x in ctx.items() if k != 'view'}, **({'view': ','.join(sorted(v))} if v else {})}))}'>{'☑' if name in views else '☐'} {label}</a>"
    bar = f"<div class=bar>{prev_a} <b>{where}</b> {next_a} · Πάνελ: {toggle('sol', 'λύση', bool(it['solution_path']))} {toggle('book', 'βιβλίο', bool(book))} · <small>πλήκτρα ← →</small></div>"
    panes = [f"<div><h4>Εκφώνηση</h4>{left}</div>"]
    if 'sol' in views and it['solution_path']: panes.append(f"<div><h4>Λύση ({html.escape(it['solution_status'] or '')})</h4><iframe src='/files/{html.escape(it['solution_path'])}'></iframe></div>")
    if 'book' in views and book:
        first = c.execute("SELECT s.page_from FROM question_section qs JOIN section s ON s.id=qs.section_id JOIN question q ON q.id=qs.question_id WHERE q.item_id=? AND qs.origin!='rejected' ORDER BY qs.question_id, s.level DESC LIMIT 1", (iid,)).fetchone()
        bp = int(ctx['bp']) if ctx.get('bp') else (first['page_from'] + book['pdf_offset'] if first else 1 + book['pdf_offset'])
        panes.append(f"<div><h4>Βιβλίο (σελ. PDF {bp}, τυπωμένη {bp - book['pdf_offset']})</h4><iframe src='/files/{html.escape(book['relpath'])}#page={bp}'></iframe></div>")
    panes.append(f"<div class=pane><h4>Ερωτήματα</h4>{''.join(qs) or '<p>Δεν βρέθηκαν ερωτήματα.</p>'}</div>")
    body = f"<h2>Θέμα {html.escape(iid)} <small>({html.escape(it['iep_yli'] or 'χωρίς ενότητα')}){sol}</small></h2>{bar}<div class=cols style='grid-template-columns:repeat({len(panes)},minmax(380px,1fr))'>{''.join(panes)}</div>"
    return page(f'Θέμα {iid}', body)

@router.post('/review/{iid}/link', dependencies=[Depends(auth)])
def review_link(iid: str, request: Request, question_id: int = Form(...), action: str = Form(...), section_id: str = Form(''), ctx: str = Form('')):
    same_origin(request)
    c = db(); q = c.execute('SELECT id FROM question WHERE id=? AND item_id=?', (question_id, iid)).fetchone()
    if not q: raise HTTPException(404)
    kind, _, sid = action.partition(':'); sid = sid or section_id
    if not sid.isdigit(): return RedirectResponse(url(iid, ctx_of(ctx)), status_code=303)
    sid = int(sid)
    if kind == 'confirm': c.execute("UPDATE question_section SET origin='manual' WHERE question_id=? AND section_id=? AND origin='auto'", (question_id, sid))
    elif kind == 'add':
        c.execute("INSERT OR REPLACE INTO question_section(question_id,section_id,origin,score) VALUES(?,?,'manual',NULL)", (question_id, sid))
        c.execute("UPDATE question_section SET origin='rejected' WHERE question_id=? AND origin='auto' AND section_id!=?", (question_id, sid))
    elif kind == 'remove':
        c.execute("UPDATE question_section SET origin='rejected' WHERE question_id=? AND section_id=? AND origin IN ('auto','iep')", (question_id, sid))
        c.execute("DELETE FROM question_section WHERE question_id=? AND section_id=? AND origin IN ('manual','ai')", (question_id, sid))
    c.commit(); c.close()
    return RedirectResponse(url(iid, ctx_of(ctx)), status_code=303)

@router.post('/review/{iid}/meta', dependencies=[Depends(auth)])
def review_meta(iid: str, request: Request, question_id: int = Form(...), qtype: str = Form(...), has_image: str = Form(''), ctx: str = Form('')):
    same_origin(request)
    if qtype not in TYPES: raise HTTPException(422, 'άγνωστος τύπος')
    c = db(); q = c.execute('SELECT qtype,has_image FROM question WHERE id=? AND item_id=?', (question_id, iid)).fetchone()
    if not q: raise HTTPException(404)
    img = 1 if has_image else 0
    if q['qtype'] != qtype: c.execute("UPDATE question SET qtype=?,qtype_origin='manual' WHERE id=?", (qtype, question_id))
    if q['has_image'] != img: c.execute("UPDATE question SET has_image=?,image_origin='manual' WHERE id=?", (img, question_id))
    c.commit(); c.close()
    return RedirectResponse(url(iid, ctx_of(ctx)), status_code=303)

