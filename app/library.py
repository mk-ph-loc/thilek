"""Επιλογή ερωτημάτων/θεμάτων: φίλτρα, ύλη μέχρι σελίδα, ετικέτες, και κοινές ενέργειες (διαγώνισμα, ετικέτα, αποθήκευση, έγγραφο, συγχώνευση)."""
import json, re
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from .main_auth import auth
from .review import db, page, html, same_origin, TYPES, TYPE_OPTS, fld, chk
from .exams import add_questions, LETTERS, MAX_GROUPS
from . import tools_merge
from .textnorm import norm

router = APIRouter()
LIMIT = 500

def norm_tag(t): return ' '.join((t or '').split()).lower()[:40]
def split_tags(s): return [t for t in dict.fromkeys(norm_tag(x) for x in re.split(r'[,;\n]', s or '')) if t]
def safe_back(b): return b if b and re.match(r'^/[A-Za-z0-9/_?=&%.,+-]*$', b) and not b.startswith('//') else ''

# ---------- επιλογή ----------
def coverage(c, upto, frm=0, mode='full', cap=8):
    """qids που καλύπτονται: όλες οι υποενότητες των συνδέσεών τους (αλλιώς η ενότητα) ανήκουν στο [frm, upto] (τυπωμένες σελίδες)."""
    by = {}
    for r in c.execute("SELECT qs.question_id qid,s.level,s.page_from a,s.page_to b FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE qs.origin!='rejected'"):
        by.setdefault(r['qid'], {2: [], 3: []}).setdefault(r['level'], []).append((r['a'], r['b'] or r['a']))
    ok = set()
    for qid, lv in by.items():
        secs = lv.get(3) or lv.get(2)
        if not secs: continue
        def good(a, b):
            end = min(b, a + cap - 1) if cap else b
            return a >= frm and (end <= upto if mode == 'full' else a <= upto)
        if all(good(a, b) for a, b in secs): ok.add(qid)
    return ok

SRC = (('', '— όλες —'), ('TTDD', 'Τράπεζα ΙΕΠ'), ('PAN', 'Πανελλήνιες'), ('OWN', 'Δικά μου'))
SRC_KEYS = ('TTDD', 'PAN', 'OWN')
WORD = (('', '— όλα —'), ('1', 'με Word'), ('0', 'χωρίς Word'))
def word_opts(cur): return ''.join(f"<option value='{v}'{' selected' if cur == v else ''}>{t}</option>" for v, t in WORD)
def src_opts(cur): return ''.join(f"<option value='{v}'{' selected' if cur == v else ''}>{t}</option>" for v, t in SRC)

def active_course(c):
    """Κωδικός ενεργού μαθήματος (ρύθμιση course_active)· '' = όλα. Αγνοείται αν δεν υπάρχει πια στη βάση."""
    try:
        r = c.execute("SELECT v FROM setting WHERE k='course_active'").fetchone()
        if r and r[0] and c.execute('SELECT 1 FROM course WHERE code=?', (r[0],)).fetchone(): return r[0]
    except Exception: pass
    return ''

def select_questions(c, f, limit=LIMIT):
    w, a = [], []
    qt = [t for t in f.get('qtype', []) if t in TYPES]
    if qt: w.append('q.qtype IN (%s)' % ','.join('?' * len(qt))); a += qt
    if f.get('image') in ('0', '1'): w.append('q.has_image=?'); a.append(int(f['image']))
    if f.get('yli'): w.append('i.iep_yli LIKE ?'); a.append(f['yli'] + '%')
    if str(f.get('position', '')).isdigit(): w.append('i.position=?'); a.append(int(f['position']))
    if f.get('section'): w.append("q.id IN (SELECT qs.question_id FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE s.code LIKE ? AND qs.origin!='rejected')"); a.append(f['section'] + '%')
    if f.get('fav') == '1': w.append('EXISTS (SELECT 1 FROM question_fav v WHERE v.item_id=q.item_id AND v.qcode=q.code)')
    if f.get('lsol') in ('0', '1'): w.append(('' if f['lsol'] == '1' else 'NOT ') + 'EXISTS (SELECT 1 FROM qsolution s WHERE s.item_id=q.item_id AND s.qcode=q.code)')
    if str(f.get('chapter', '')).isdigit(): w.append("q.id IN (SELECT qs.question_id FROM question_section qs JOIN section s ON s.id=qs.section_id WHERE s.code LIKE ? AND qs.origin!='rejected')"); a.append(f['chapter'] + '.%')
    if f.get('word') in ('0', '1'): w.append(('' if f['word'] == '1' else 'NOT ') + "EXISTS (SELECT 1 FROM wordsrc ws WHERE ws.item_id=q.item_id AND ws.kind='statement')")
    if f.get('src') in SRC_KEYS: w.append('i.source=?'); a.append(f['src'])
    ac = active_course(c)
    if ac: w.append('i.course_code=?'); a.append(ac)
    tags = split_tags(f.get('tag', ''))
    if tags and f.get('tagmode') == 'all':
        for t in tags: w.append('EXISTS (SELECT 1 FROM question_tag t WHERE t.item_id=q.item_id AND t.qcode=q.code AND t.tag=?)'); a.append(t)
    elif tags:
        w.append('EXISTS (SELECT 1 FROM question_tag t WHERE t.item_id=q.item_id AND t.qcode=q.code AND t.tag IN (%s))' % ','.join('?' * len(tags))); a += tags
    rows = c.execute("""SELECT q.id qid,q.item_id,q.code,q.points,q.qtype,q.has_image,q.text,q.geo IS NOT NULL has_geo,i.iep_yli,i.position,i.course_code,
        (SELECT group_concat(tag,', ') FROM question_tag t WHERE t.item_id=q.item_id AND t.qcode=q.code) tags,
        EXISTS (SELECT 1 FROM question_fav v WHERE v.item_id=q.item_id AND v.qcode=q.code) fav,
        EXISTS (SELECT 1 FROM qsolution s WHERE s.item_id=q.item_id AND s.qcode=q.code) has_sol,
        (SELECT status FROM wordsrc ws WHERE ws.item_id=q.item_id AND ws.kind='statement') word_st
        FROM question q JOIN item i ON i.id=q.item_id %s ORDER BY CAST(q.item_id AS INTEGER),q.id""" % ('WHERE ' + ' AND '.join(w) if w else ''), a).fetchall()
    rows = [dict(r) for r in rows]
    words = [norm(x) for x in (f.get('q') or '').split()]
    if words: rows = [r for r in rows if all(x in norm(r['text']) for x in words)]
    if f.get('upto'):
        ok = coverage(c, int(f['upto']), int(f.get('frm') or 0), f.get('mode', 'full'), int(f.get('cap', 8)))
        rows = [r for r in rows if r['qid'] in ok]
    return rows[:limit] if limit else rows

def thumb(r, dpi=70): return f"<img loading=lazy src='/crop/{r['qid']}.jpg?dpi={dpi}' style='max-width:380px'>" if r['has_geo'] else '<i>χωρίς εικόνα</i>'

def star(qid, on):
    return f"<button type=button class='star{' on' if on else ''}' data-fav='{qid}' title='αγαπημένο'>{'★' if on else '☆'}</button>"

def chapter_opts(c, cur=''):
    chs = sorted({r[0].split('.')[0] for r in c.execute('SELECT code FROM section') if r[0] and r[0].split('.')[0].isdigit()}, key=int)
    return "<option value=''>— όλα —</option>" + ''.join(f"<option value={n}{' selected' if str(cur) == n else ''}>Κεφάλαιο {n}</option>" for n in chs)

FILTER_KEYS = ('qtype', 'image', 'yli', 'section', 'chapter', 'position', 'tag', 'tagmode', 'q', 'fav', 'lsol', 'src', 'word')   # lsol: λύση εκπαιδευτικού 1/0 (το «sol» είναι ήδη η εικόνα λύσης στο /q)
LSOL = (('', '— όλα —'), ('1', 'με λύση'), ('0', 'χωρίς λύση'))
def lsol_opts(cur): return ''.join(f"<option value='{v}'{' selected' if cur == v else ''}>{t}</option>" for v, t in LSOL)
def word_link(r):
    st = r.get('word_st')
    return f"<a href='/word/{html.escape(r['item_id'])}' title='Word ΙΕΠ'>{'⚠' if st == 'warn' else ('✖' if st == 'error' else 'W')}</a>" if st else ''

def sol_link(r): return f"<a href='/lysi/{html.escape(r['item_id'])}/{html.escape(r['code'])}' title='λύση εκπαιδευτικού'>✎</a>" if r.get('has_sol') else ''

def qtable(rows, thumbs=False):
    out = ["<table><tr><th><input type=checkbox data-all='qids' title='όλα'></th><th title='αγαπημένα'>★</th><th>Θέμα</th><th>Ερώτημα</th><th>Μον.</th><th>Τύπος</th><th>Εικόνα</th><th>Ενότητα ΙΕΠ</th><th>Ετικέτες</th><th title='λύση εκπαιδευτικού'>Λύση ✎</th><th title='υπάρχει Word του ΙΕΠ'>W</th><th>" + ('Προεπισκόπηση' if thumbs else 'Κείμενο') + "</th></tr>"]
    for r in rows:
        cell = thumb(r) if thumbs else html.escape(' '.join((r['text'] or '').split())[:160])
        tg = ' '.join(f"<a href='/browse?{urlencode({'tag': t.strip()})}'>{html.escape(t.strip())}</a>" for t in (r['tags'] or '').split(',') if t.strip())
        out.append(f"<tr><td><input type=checkbox name=qids value={r['qid']}></td><td data-v='{int(bool(r.get('fav')))}'>{star(r['qid'], r.get('fav'))}</td><td><a href='/review/{html.escape(r['item_id'])}'>{html.escape(r['item_id'])}</a></td><td>{html.escape(r['code'])}</td><td>{r['points'] if r['points'] is not None else ''}</td>"
                   f"<td>{html.escape(TYPES.get(r['qtype'], '') or '')}</td><td>{'ναι' if r['has_image'] else ''}</td><td>{html.escape(r['iep_yli'] or '')}</td><td>{tg}</td><td>{sol_link(r)}</td><td>{word_link(r)}</td><td>{cell}</td></tr>")
    out.append('</table>'); return ''.join(out)

def action_bar(c, criteria=None, back='', pre_exam=''):
    exams = ''.join(f"<option value={e['id']}{' selected' if str(e['id']) == str(pre_exam) else ''}>#{e['id']} {html.escape(e['title'])}</option>" for e in c.execute('SELECT id,title FROM exam ORDER BY id DESC'))
    quizzes = ''.join(f"<option value={z['id']}>#{z['id']} {html.escape(z['name'])}</option>" for z in c.execute('SELECT id,name FROM quiz ORDER BY id DESC'))
    gopt = ''.join(f"<option value={n}>Θέμα {LETTERS[n - 1]}</option>" for n in range(1, MAX_GROUPS + 1))
    alltags = ''.join(f"<option value='{html.escape(t[0])}'>" for t in c.execute('SELECT DISTINCT tag FROM question_tag ORDER BY tag'))
    crit = html.escape(json.dumps(criteria or {}, ensure_ascii=False))
    return f"""<fieldset class=bar2><legend>Ενέργειες στα επιλεγμένα (<span id=count>0</span>)</legend>
<input type=hidden name=criteria value='{crit}'><input type=hidden name=back value='{html.escape(back)}'>
<div>Διαγώνισμα: <select name=exam_id><option value=''>—</option>{exams}</select> <select name=grp>{gopt}</select> <button name=act value=exam>Προσθήκη σε διαγώνισμα</button></div>
<div>Ετικέτα: <input name=tag list=taglist size=16 placeholder='π.χ. επανάληψη, νόμος ohm'><datalist id=taglist>{alltags}</datalist> <button name=act value=tag>Προσθήκη</button> <button name=act value=untag>Αφαίρεση</button></div>
<div>Αποθήκευση ως συλλογή: <input name=name size=22 placeholder='όνομα'> <button name=act value=save>Αποθήκευση επιλογής + κριτηρίων</button></div>
<div>Έγγραφο: τίτλος <input name=title size=22 value='Σύνθετο έγγραφο ασκήσεων'> αρίθμηση <select name=numbering><option value=new>νέα (1,2,3)</option><option value=source>πηγή (θέμα/ερώτημα)</option></select>
 ομαδοποίηση <select name=group><option value=''>καμία</option><option value=unit>ανά ενότητα ΙΕΠ</option></select> <label><input type=checkbox name=solutions value=1> απαντήσεις στο τέλος</label>
 <button name=act value=doc formtarget=_blank>Προβολή/εκτύπωση</button></div>
<div>Markdown: <select name=mdmode><option value=image>εικόνες</option><option value=text>κείμενο</option><option value=both>και τα δύο</option></select> <button name=act value=md>Μετατροπή σε Markdown έγγραφο</button></div>
<div>Quiz: <select name=quiz_id><option value=''>— νέο quiz —</option>{quizzes}</select> <input name=quiz_name size=16 placeholder='όνομα νέου'> <button name=act value=quiz>Δημιουργία στοιχείων quiz</button></div>
<div>Λύσεις εκπαιδευτικού (μόνο τα επιλεγμένα που έχουν λύση): {sol_controls()}</div>
<div>Συγχώνευση PDF των θεμάτων: <label><input type=checkbox name=sol value=1> λύσεις</label> <label><input type=checkbox name=book value=1> βιβλίο</label> <button name=act value=merge>Συγχώνευση</button></div>
</fieldset>"""

SOLCTL_CSS = ("<style>.solctl .solord{list-style:none;margin:.3rem 0;padding:0}.solctl .solord li{display:flex;align-items:center;gap:.4rem;margin:.15rem 0;padding:.1rem .5rem;border:1px solid #9994;border-radius:6px;max-width:26rem}"
              ".solctl .solord li label{flex:1}.solctl .solord li button{padding:0 .45rem;line-height:1.3}.solctl .solrow{margin:.3rem 0}.solctl .solbtn{margin:.4rem 0}</style>")

def sol_controls(style='kids'):
    """Επιλογές εξαγωγής λύσεων εκπαιδευτικού (κοινές για μπάρα ενεργειών και σελίδα /lysi): ενότητες με σειρά (↑↓ και έτοιμες διατάξεις), στυλ, κουμπιά εξαγωγής.
    Η σειρά είναι η σειρά των στοιχείων στη φόρμα (ο browser στέλνει τα τσεκαρισμένα sx με τη σειρά του DOM)."""
    from .solstyle import UNITS, PRESETS, STYLES
    items = ''.join(f"<li data-k={k}><label><input type=checkbox name=sx value={k} checked> {ic} {html.escape(t)}</label> <button type=button class=up title='πάνω'>↑</button><button type=button class=dn title='κάτω'>↓</button></li>" for k, t, ic in UNITS)
    pre = ''.join(f"<option value='{','.join(o)}'>{html.escape(t)}</option>" for _, t, o in PRESETS)
    sty = ''.join(f"<option value={k}{' selected' if k == (style if style in STYLES else 'kids') else ''}>{html.escape(v['label'])}</option>" for k, v in STYLES.items())
    return (f"{SOLCTL_CSS}<div class=solctl><div class=solrow>Ενότητες και σειρά: <select class=solpre><option value=''>— έτοιμη διάταξη —</option>{pre}</select> <small>ή τσεκάρισμα και ↑↓</small></div><ul class=solord>{items}</ul>"
            f"<div class=solrow>τίτλος <input name=sol_title size=22 value='Λύσεις εκπαιδευτικού'> στυλ <select name=sstyle>{sty}</select> <label><input type=checkbox name=hide value=1 checked> κρυφές λύσεις με κλικ (HTML μαθητή)</label> <label><input type=checkbox name=frag value=1> bullets ένα-ένα (Reveal, PowerPoint)</label> <a href='/manual/reveal'>βοήθεια Reveal</a> <a href='/manual/pandoc'>βοήθεια Pandoc</a></div>"
            "<div class=solbtn><button name=act value=reveal>Reveal.js</button> <button name=act value=html>HTML μαθητή</button> <button name=act value=solmd>Markdown/Word</button> <button name=act value=moodle>Moodle XML</button> <button name=act value=pptx title='Χρειάζεται Pandoc στον server'>PowerPoint (.pptx)</button></div></div>"
            "<script src='/static/solctl.js' defer></script>")

def expand(c, ids, qids):
    """Λίστα (item_id, qcode) από θέματα (ids) και ερωτήματα (qids), χωρίς διπλά."""
    out = []; seen = set()
    for i in ids:
        for r in c.execute('SELECT item_id,code FROM question WHERE item_id=? ORDER BY id', (i,)):
            if (r[0], r[1]) not in seen: seen.add((r[0], r[1])); out.append((r[0], r[1]))
    for qid in qids:
        r = c.execute('SELECT item_id,code FROM question WHERE id=?', (qid,)).fetchone()
        if r and (r[0], r[1]) not in seen: seen.add((r[0], r[1])); out.append((r[0], r[1]))
    return out

# ---------- σελίδες ----------
@router.get('/browse', response_class=HTMLResponse, dependencies=[Depends(auth)])
def browse(request: Request, qtype: str = '', image: str = '', yli: str = '', section: str = '', position: str = '', tag: str = '', tagmode: str = 'any', q: str = '', fav: str = '', chapter: str = '', thumbs: int = 0, exam: str = '', none: str = '', lsol: str = '', src: str = '', word: str = ''):
    c = db(); f = {'qtype': [qtype] if qtype else [], 'image': image, 'yli': yli.strip(), 'section': section.strip(), 'position': position, 'tag': tag, 'tagmode': tagmode, 'q': q, 'fav': fav, 'chapter': chapter, 'lsol': lsol, 'src': src, 'word': word}
    rows = select_questions(c, f)
    sel = "<option value=''>— όλοι —</option>" + TYPE_OPTS(qtype)
    img = ''.join(f"<option value='{v}'{' selected' if image == v else ''}>{t}</option>" for v, t in (('', '— όλα —'), ('1', 'με εικόνα'), ('0', 'χωρίς εικόνα')))
    pos = ''.join(f"<option value='{v}'{' selected' if position == v else ''}>{t}</option>" for v, t in (('', '— όλα —'), ('2', 'Θέμα 2'), ('4', 'Θέμα 4')))
    E = html.escape
    tm = "<select name=tagmode><option value=any%s>οποιαδήποτε</option><option value=all%s>όλες</option></select>" % ('' if tagmode == 'all' else ' selected', ' selected' if tagmode == 'all' else '')
    flt = ("<form method='get' class=filters>" + fld('Λέξεις-κλειδιά', f"<input name=q value='{E(q)}' size=18>") + fld('Τύπος', f"<select name=qtype>{sel}</select>") + fld('Εικόνα', f"<select name=image>{img}</select>")
           + fld('Θέμα', f"<select name=position>{pos}</select>") + fld('Κεφάλαιο', f"<select name=chapter>{chapter_opts(c, chapter)}</select>") + fld('Αγαπημένα', "<select name=fav><option value=''>— όλα —</option><option value=1%s>μόνο αγαπημένα</option></select>" % (' selected' if fav == '1' else '')) + fld('Λύση εκπαιδευτικού', f"<select name=lsol>{lsol_opts(lsol)}</select>") + fld('Ενότητα ΙΕΠ', f"<input name=yli value='{E(yli)}' size=5>") + fld('Υποενότητα βιβλίου', f"<input name=section value='{E(section)}' size=6>")
           + fld('Πηγή', f"<select name=src>{src_opts(src)}</select>") + fld('Word ΙΕΠ', f"<select name=word>{word_opts(word)}</select>")
           + fld('Ετικέτες', f"<input name=tag value='{E(tag)}' size=16>") + fld('Λογική ετικετών', tm) + chk('μικρογραφίες', f"<input type=checkbox name=thumbs value=1{' checked' if thumbs else ''}>") + "<button>Φίλτρο</button> <button formaction='/q/start' class=primary title='ένα-ένα με επόμενο/προηγούμενο, με τα ίδια φίλτρα'>Περιήγηση ένα-ένα →</button></form>")
    back = '/browse?' + request.url.query
    exam_note = f"<p>Διαγώνισμα #{E(exam)}: διάλεξε ερωτήματα και «Προσθήκη σε διαγώνισμα». <a href='/exams/{E(exam)}'>πίσω</a></p>" if exam.isdigit() else ''
    body = (f"<h2>Ερωτήματα</h2>{'<p><b>Κανένα ερώτημα με αυτά τα φίλτρα.</b></p>' if none else ''}{flt}{exam_note}<form method='post' action='/select/act'>{action_bar(c, {'type': 'browse', 'filters': f}, back, exam)}<p>{len(rows)} ερωτήματα (έως {LIMIT})</p>{qtable(rows, bool(thumbs))}</form>")
    return page('Ερωτήματα', body)

@router.get('/coverage', response_class=HTMLResponse, dependencies=[Depends(auth)])
def coverage_page(request: Request, upto: str = '', frm: str = '', mode: str = 'full', cap: str = '8', qtype: str = '', position: str = '', tag: str = '', thumbs: int = 0):
    c = db(); E = html.escape
    mode_sel = "<select name=mode><option value=full%s>έχει τελειώσει πριν τη σελίδα</option><option value=started%s>έχει αρχίσει</option></select>" % ('' if mode == 'started' else ' selected', ' selected' if mode == 'started' else '')
    pos_sel = "<select name=position><option value=''>—</option><option value=2%s>2</option><option value=4%s>4</option></select>" % (' selected' if position == '2' else '', ' selected' if position == '4' else '')
    form = ("<form method='get' class=filters>" + fld('Ύλη μέχρι τη σελίδα (τυπωμένη)', f"<input name=upto value='{E(upto)}' size=6 required>") + fld('από σελίδα', f"<input name=frm value='{E(frm)}' size=6>")
            + fld('Υποενότητα καλυμμένη όταν', mode_sel) + fld('Όριο μήκους υποενότητας (σελ., 0 = όπως στο ευρετήριο)', f"<input name=cap value='{E(cap)}' size=4>")
            + fld('Τύπος', f"<select name=qtype><option value=''>—</option>{TYPE_OPTS(qtype)}</select>") + fld('Θέμα', pos_sel) + fld('Ετικέτες', f"<input name=tag value='{E(tag)}' size=14>")
            + chk('μικρογραφίες', f"<input type=checkbox name=thumbs value=1{' checked' if thumbs else ''}>") + "<button>Εμφάνιση δυνατοτήτων</button></form>"
            "<p class=meta><small>Το τέλος κάθε ενότητας στο ευρετήριο περιλαμβάνει και τις ασκήσεις, γι' αυτό υπάρχει όριο μήκους υποενότητας.</small></p>")
    if not upto.isdigit(): return page('Ύλη μέχρι σελίδα', f'<h2>Τι ασκήσεις έχω μέχρι τη σελίδα…</h2>{form}')
    f = {'qtype': [qtype] if qtype else [], 'position': position, 'tag': tag, 'upto': upto, 'frm': frm or '0', 'mode': mode, 'cap': cap if cap.isdigit() else '8'}
    rows = select_questions(c, f, limit=0)
    items = {}
    for r in rows: items.setdefault(r['item_id'], {'cov': 0, 'yli': r['iep_yli'], 'pos': r['position']})['cov'] += 1
    totals = {r[0]: r[1] for r in c.execute('SELECT item_id,count(*) FROM question GROUP BY item_id')}
    full = [i for i, v in items.items() if v['cov'] == totals.get(i)]
    bypos, byunit = {}, {}
    for r in rows:
        bypos[r['position']] = bypos.get(r['position'], 0) + 1; u = '.'.join((r['iep_yli'] or '—').split()[0].split('.')[:2]) if r['iep_yli'] else '—'; byunit.setdefault(u, [0, set()]); byunit[u][0] += 1; byunit[u][1].add(r['item_id'])
    summ = (f"<p><b>Μέχρι τη σελ. {E(upto)}</b>: {len(full)} θέματα καλύπτονται πλήρως (όλα τα ερωτήματά τους) και {len(rows)} ερωτήματα από {len(items)} θέματα. "
            + ', '.join(f"Θέμα {k or '—'}: {v} ερωτήματα" for k, v in sorted(bypos.items(), key=lambda x: str(x[0]))) + '.</p>')
    utab = "<table><tr><th>Ενότητα ΙΕΠ</th><th>Ερωτήματα</th><th>Θέματα</th></tr>" + ''.join(f"<tr><td>{E(u)}</td><td>{v[0]}</td><td>{len(v[1])}</td></tr>" for u, v in sorted(byunit.items())) + '</table>'
    itab = "<h3>Θέματα που καλύπτονται πλήρως</h3><table><tr><th><input type=checkbox data-all='ids'></th><th>ID</th><th>Θέμα</th><th>Ενότητα ΙΕΠ</th><th>Ερωτήματα</th></tr>" + ''.join(
        f"<tr><td><input type=checkbox name=ids value='{i}'></td><td><a href='/review/{i}'>{i}</a></td><td>{items[i]['pos'] or ''}</td><td>{E(items[i]['yli'] or '')}</td><td>{items[i]['cov']}</td></tr>" for i in sorted(full, key=int)) + '</table>'
    partial = [i for i in items if i not in full]
    ptxt = f"<p><small>Μερικώς καλυμμένα θέματα (μόνο μερικά ερωτήματα μέσα στην ύλη): {len(partial)}. Δες τα ερωτήματά τους παρακάτω.</small></p>" if partial else ''
    back = '/coverage?' + request.url.query
    body = (f"<h2>Τι ασκήσεις έχω μέχρι τη σελίδα {E(upto)}</h2>{form}{summ}{utab}<form method='post' action='/select/act'>{action_bar(c, {'type': 'coverage', 'filters': f}, back)}{itab}{ptxt}<h3>Ερωτήματα που καλύπτονται ({len(rows)})</h3>{qtable(rows[:LIMIT], bool(thumbs))}</form>")
    return page('Ύλη μέχρι σελίδα', body)

@router.get('/tags', response_class=HTMLResponse, dependencies=[Depends(auth)])
def tags_page():
    c = db()
    rows = c.execute('SELECT tag,count(*) n,count(DISTINCT item_id) ni FROM question_tag GROUP BY tag ORDER BY tag').fetchall()
    trs = ''.join(f"<tr><td><a href='/browse?{urlencode({'tag': r['tag']})}'>{html.escape(r['tag'])}</a></td><td>{r['n']}</td><td>{r['ni']}</td><td><form method='post' action='/tags/delete' data-confirm='Διαγραφή ετικέτας από όλα;'><input type=hidden name=tag value='{html.escape(r['tag'])}'><button>✖ διαγραφή</button></form></td></tr>" for r in rows)
    return page('Ετικέτες', f"<h2>Ετικέτες</h2><p>Βάζεις ετικέτες από τη σελίδα <a href='/browse'>Ερωτήματα</a> (επιλογή + «Ετικέτα») ή από τη σελίδα ελέγχου κάθε θέματος. Η αναζήτηση με λέξεις-κλειδιά βρίσκει ερωτήματα για μαζική ετικέτα.</p><table><tr><th>Ετικέτα</th><th>Ερωτήματα</th><th>Θέματα</th><th></th></tr>{trs}</table>")

@router.post('/tags/delete', dependencies=[Depends(auth)])
def tags_delete(request: Request, tag: str = Form(...)):
    same_origin(request); c = db(); c.execute('DELETE FROM question_tag WHERE tag=?', (norm_tag(tag),)); c.commit(); c.close(); return RedirectResponse('/tags', status_code=303)

@router.post('/select/act', dependencies=[Depends(auth)])
def act(request: Request, act: str = Form(...), ids: list[str] = Form([]), qids: list[int] = Form([]), exam_id: str = Form(''), grp: int = Form(1), tag: str = Form(''), name: str = Form(''),
        title: str = Form('Σύνθετο έγγραφο ασκήσεων'), numbering: str = Form('new'), group: str = Form(''), solutions: str = Form(''), sol: str = Form(''), book: str = Form(''),
        criteria: str = Form('{}'), back: str = Form(''), quiz_id: str = Form(''), quiz_name: str = Form(''), mdmode: str = Form('image'),
        sx: list[str] = Form([]), sol_title: str = Form(''), rtheme: str = Form(''), sstyle: str = Form(''), hide: str = Form(''), frag: str = Form('')):
    same_origin(request); c = db(); ids = [i for i in dict.fromkeys(ids) if i.isdigit()]
    members = expand(c, ids, qids); back = safe_back(back)
    def done():
        c.commit(); c.close(); return RedirectResponse(back or '/browse', status_code=303)
    if not members: c.close(); raise HTTPException(422, 'Δεν επιλέχθηκε τίποτα.')
    if act == 'exam':
        if not exam_id.isdigit() or not c.execute('SELECT 1 FROM exam WHERE id=?', (int(exam_id),)).fetchone(): c.close(); raise HTTPException(422, 'Διάλεξε διαγώνισμα.')
        q = [c.execute('SELECT id FROM question WHERE item_id=? AND code=?', m).fetchone()[0] for m in members]
        add_questions(c, int(exam_id), q, grp); c.commit(); c.close(); return RedirectResponse(f'/exams/{exam_id}', status_code=303)
    if act in ('tag', 'untag'):
        tags = split_tags(tag)
        if not tags: c.close(); raise HTTPException(422, 'Γράψε ετικέτα.')
        for it, code in members:
            for t in tags:
                if act == 'tag': c.execute('INSERT OR IGNORE INTO question_tag(item_id,qcode,tag) VALUES(?,?,?)', (it, code, t))
                else: c.execute('DELETE FROM question_tag WHERE item_id=? AND qcode=? AND tag=?', (it, code, t))
        return done()
    if act == 'md':
        from . import mdgen
        from .mddoc import new_doc
        did = new_doc(c, title or 'Έγγραφο', mdgen.members_md(c, members, title or 'Έγγραφο', mdmode if mdmode in ('image', 'text', 'both') else 'image', numbering), f'επιλογή ({len(members)} ερωτήματα)'); c.commit(); c.close()
        return RedirectResponse(f'/docs/{did}', status_code=303)
    if act == 'quiz':
        from .quizzes import add_from_questions
        if quiz_id.isdigit() and c.execute('SELECT 1 FROM quiz WHERE id=?', (int(quiz_id),)).fetchone(): zid = int(quiz_id)
        else: zid = c.execute('INSERT INTO quiz(name,created) VALUES(?,?)', ((quiz_name.strip() or 'Νέο quiz')[:200], __import__('datetime').datetime.now().isoformat(timespec='seconds'))).lastrowid
        add_from_questions(c, zid, members); c.commit(); c.close(); return RedirectResponse(f'/quizzes/{zid}', status_code=303)
    if act == 'save':
        from .collections import create_collection
        cid = create_collection(c, name or 'Συλλογή', members, criteria, {'title': title, 'numbering': numbering, 'group': group, 'solutions': bool(solutions)}); c.commit(); c.close()
        return RedirectResponse(f'/collections/{cid}', status_code=303)
    if act == 'doc':
        from .collections import compose
        r = compose(c, members, {'title': title, 'numbering': numbering, 'group': group, 'solutions': bool(solutions)}); c.close(); return r
    if act in ('reveal', 'html', 'solmd', 'moodle', 'pptx'):                 # λύσεις εκπαιδευτικού (μόνο όσα επιλεγμένα έχουν αρχείο λύσης)
        from .solexport import export
        try: return export(c, act, members, sx, sol_title, sstyle or rtheme, bool(hide), bool(frag))
        finally: c.close()
    if act == 'merge':
        items = sorted({m[0] for m in members}, key=int)
        try: data, n = tools_merge.build(c, items, bool(sol), bool(book), 'by_item', 8, [], True)
        finally: c.close()
        return Response(data, media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="thilek-merge.pdf"', 'X-Pages': str(n)})
    c.close(); raise HTTPException(422, 'Άγνωστη ενέργεια')

def filter_card(c, f, action, hidden=None, thumbs=0, button='Εμφάνιση'):
    """Κοινή φόρμα φίλτρων ερωτημάτων (GET). f: dict φίλτρων όπως στο select_questions· hidden: επιπλέον κρυφά πεδία."""
    E = html.escape; qt = f.get('qtype') or ''; qt = qt[0] if isinstance(qt, list) and qt else (qt if isinstance(qt, str) else '')
    sel = "<option value=''>— όλοι —</option>" + TYPE_OPTS(qt)
    img = ''.join(f"<option value='{v}'{' selected' if f.get('image') == v else ''}>{t}</option>" for v, t in (('', '— όλα —'), ('1', 'με εικόνα'), ('0', 'χωρίς εικόνα')))
    pos = ''.join(f"<option value='{v}'{' selected' if str(f.get('position', '')) == v else ''}>{t}</option>" for v, t in (('', '— όλα —'), ('2', 'Θέμα 2'), ('4', 'Θέμα 4')))
    favo = "<option value=''>— όλα —</option><option value=1%s>μόνο αγαπημένα</option>" % (' selected' if f.get('fav') == '1' else '')
    tm = "<select name=tagmode><option value=any%s>οποιαδήποτε</option><option value=all%s>όλες</option></select>" % ('' if f.get('tagmode') == 'all' else ' selected', ' selected' if f.get('tagmode') == 'all' else '')
    hid = ''.join(f"<input type=hidden name={E(k)} value='{E(str(v))}'>" for k, v in (hidden or {}).items())
    return (f"<form method=get action='{E(action)}' class=filters>{hid}" + fld('Λέξεις-κλειδιά', f"<input name=q value='{E(f.get('q', ''))}' size=16>") + fld('Τύπος', f"<select name=qtype>{sel}</select>")
            + fld('Κεφάλαιο', f"<select name=chapter>{chapter_opts(c, f.get('chapter', ''))}</select>") + fld('Εικόνα', f"<select name=image>{img}</select>") + fld('Θέμα', f"<select name=position>{pos}</select>")
            + fld('Αγαπημένα', f"<select name=fav>{favo}</select>") + fld('Πηγή', f"<select name=src>{src_opts(f.get('src', ''))}</select>") + fld('Word ΙΕΠ', f"<select name=word>{word_opts(f.get('word', ''))}</select>") + fld('Ενότητα ΙΕΠ', f"<input name=yli value='{E(f.get('yli', ''))}' size=5>") + fld('Υποενότητα', f"<input name=section value='{E(f.get('section', ''))}' size=6>")
            + fld('Ετικέτες', f"<input name=tag value='{E(f.get('tag', ''))}' size=14>") + fld('Λογική ετικετών', tm)
            + chk('μικρογραφίες', f"<input type=checkbox name=thumbs value=1{' checked' if thumbs else ''}>") + f"<button>{E(button)}</button></form>")

def filters_of(params):
    """Φίλτρα από query params (FILTER_KEYS) -> dict για select_questions."""
    f = {k: (params.get(k) or '').strip() for k in FILTER_KEYS}
    f['qtype'] = [f['qtype']] if f['qtype'] else []; f['tagmode'] = f['tagmode'] or 'any'; return f
