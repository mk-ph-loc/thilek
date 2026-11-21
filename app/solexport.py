"""Εξαγωγές λύσεων εκπαιδευτικού (μόνο από επιλογή): Reveal.js (αυτόνομο HTML, offline), σύνθετο Markdown/Word (νέο έγγραφο /docs), Moodle XML.
Moodle XML: ΔΕΝ έχει δοκιμαστεί σε πραγματικό Moodle· βγαίνει μόνο από τα quiz blocks των αρχείων λύσεων (όχι από τα quiz της εφαρμογής)."""
import base64, datetime, functools, html, pathlib, re
from fastapi import HTTPException
from fastapi.responses import RedirectResponse, Response
from . import config, qsol
from .mdmath import render_md, md_text, moodle_text, outside_fences, img_data, IMG, normalize_math_md
from .solstyle import UNITS, KEYS, LABEL, ICON, TEACHER, STYLES, include_of, teacher_units, style_of, reveal_css

E = html.escape
VENDOR = pathlib.Path(__file__).parent / 'static' / 'vendor'
LET = 'αβγδεζηθικλμ'

def unit_items(r, include):
    """Ενότητες μιας λύσης με τη σειρά του include: [(κλειδί, 'md'|'parts'|'quiz', περιεχόμενο)] (μόνο όσες έχουν περιεχόμενο)."""
    s = r['sections']; tu = teacher_units(s.get('teacher_parts') or []); qs = [q for q in r['quiz'] if not q['err']]; out = []
    for k in include:
        if k in ('statement', 'iep'):
            if s.get(k): out.append((k, 'md', s[k]))
        elif k in TEACHER:
            if tu.get(k): out.append((k, 'parts', tu[k]))
        elif k == 'quiz' and qs: out.append((k, 'quiz', qs))
    return out

def load(c, keys):
    """keys: [(item_id, qcode)] με τη σειρά επιλογής -> γραμμές qsolution (μόνο όσες υπάρχουν, χωρίς διπλά)."""
    out, seen = [], set()
    for k in keys:
        if k in seen: continue
        seen.add(k); r = qsol.get(c, *k)
        if r: out.append(r)
    return out

def label(r): return f"Θέμα {r['item_id']} · ερώτημα {r['qcode']}"

def answer_text(q):
    t = q.get('type')
    if 'answer' not in q and t != 'matching': return ''
    if t == 'mcq': i = q['answer']; o = q.get('options') or []; return f"{LET[i] if i < len(LET) else i + 1}. {o[i]}" if 0 <= i < len(o) else ''
    if t == 'true_false': return 'Σωστό' if q['answer'] else 'Λάθος'
    if t == 'numeric': return f"{q['answer']:g}" + (f" ± {q['tolerance']:g}" if q.get('tolerance') else '') + (f" {q['unit']}" if q.get('unit') else '')
    if t in ('short', 'fill'): return ' / '.join(q['answer'])
    if t == 'matching': return '; '.join(f'{a} → {b}' for a, b in q.get('pairs') or [])
    return ''

# ---------- Reveal.js ----------
def _no_close(s, tag): return re.sub(f'</({tag})', r'<\\/\1', s, flags=re.I)

@functools.lru_cache(maxsize=1)
def assets():
    rd = lambda p: (VENDOR / p).read_text(encoding='utf-8')
    strip = lambda css: re.sub(r'@font-face\s*\{[^}]*\}', '', css)          # τα θέματα έχουν ~575KB base64 γραμματοσειρές: έξω, γραμματοσειρά συστήματος
    def font(m):
        p = VENDOR / 'katex' / 'fonts' / m.group(1)
        return f"url(data:font/woff2;base64,{base64.b64encode(p.read_bytes()).decode()}) format(\"woff2\")" if p.is_file() else 'local("none")'
    kcss = re.sub(r'url\(fonts/([A-Za-z0-9_-]+\.woff2)\)\s*format\("woff2"\)', font, rd('katex/katex.min.css'))
    return {'reveal_css': rd('reveal/reveal.css'), 'white': strip(rd('reveal/white.css')), 'black': strip(rd('reveal/black.css')), 'reveal_js': rd('reveal/reveal.js'),
            'katex_css': kcss, 'katex_js': rd('katex/katex.min.js'), 'auto_js': rd('katex/auto-render.min.js')}

def quiz_slide(r, q, root):
    t = q['type']; body = [f"<div class=hd><h2>Quiz {q['n']} <small>({E(qsol.QTYPES.get(t, t))}, {q.get('points', 1):g} μον.)</small></h2></div><div class=stem>{md_text(q['stem'])}</div>"]
    if q.get('image'):
        u = img_data(root, f"{r['base']}/{q['image']}")
        if u: body.append(f"<img src='{E(u)}' alt=''>")
    if t == 'mcq': body.append('<ol class=opts>' + ''.join(f"<li>{LET[i] if i < len(LET) else i + 1}. {md_text(o)}</li>" for i, o in enumerate(q.get('options') or [])) + '</ol>')
    elif t == 'true_false': body.append('<p>Σωστό ή Λάθος;</p>')
    if t == 'matching':
        rows = ''.join(f"<tr><td>{md_text(a)}</td><td class=fragment>{md_text(b)}</td></tr>" for a, b in q.get('pairs') or [])
        body.append(f"<table><tr><th>Α</th><th>Β</th></tr>{rows}</table>")
    else: body.append(f"<p class='fragment ans'>Απάντηση: <b>{md_text(answer_text(q))}</b></p>")
    if q.get('feedback'): body.append(f"<p class='fragment fb'>{md_text(q['feedback'])}</p>")
    return f"<section class='u u-quiz'>{''.join(body)}</section>"

def hd(r, k, style, extra=''):
    badge = f"<span class=badge>{ICON[k]}</span>" if STYLES[style]['icons'] else ''
    return f"<div class=hd>{badge}<h2>{E(LABEL[k])}{extra}</h2><span class=who>{E(label(r))}</span></div>"

def reveal_html(rows, title, include, style='calm', root=''):
    a = assets(); style = style_of(style); theme = STYLES[style]['base']
    sl = [f"<section class=u-title><h1>{E(title)}</h1><p>{len(rows)} λύσεις · TH-ILEK · {datetime.date.today().isoformat()}</p><ul class=toc>" + ''.join(f"<li>{E(label(r))}</li>" for r in rows) + '</ul></section>']
    for r in rows:
        md = lambda t: render_md(t, r['base'], embed_root=root)
        for k, kind, d in unit_items(r, include):
            if kind == 'md': sl.append(f"<section class='u u-{k}'>{hd(r, k, style)}{md(d)}</section>")
            elif kind == 'parts':                                                          # κάθετη στοίβα: ένα slide ανά βήμα (γραμμή «--»)
                vs = [f"<section class='u u-{k}'>{hd(r, k, style, f' <small>({i}/{len(d)})</small>' if len(d) > 1 else '')}{md(b)}</section>" for i, b in enumerate(d, 1)]
                sl.append('<section>' + ''.join(vs) + '</section>')
            else:
                intro = f"<section class='u u-quiz'>{hd(r, 'quiz', style)}<p>{len(d)} ερωτήσεις· ↓ για να τις δεις, η απάντηση εμφανίζεται με το επόμενο βήμα.</p></section>"
                sl.append('<section>' + intro + ''.join(quiz_slide(r, q, root) for q in d) + '</section>')
    init = ("(function(){var d=[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false},{left:'\\\\(',right:'\\\\)',display:false},{left:'\\\\[',right:'\\\\]',display:true}];"
            "try{renderMathInElement(document.querySelector('.slides'),{delimiters:d,throwOnError:false});}catch(e){}"
            "Reveal.initialize({hash:true,width:1280,height:800,margin:0.04,center:false,slideNumber:'c/t',transition:'slide',plugins:[]});})();")
    st = lambda s: '<style>' + _no_close(s, 'style') + '</style>'
    sc = lambda s: '<script>' + _no_close(s, 'script') + '</script>'
    return (f"<!doctype html><html lang='el'><head><meta charset='utf-8'><meta name=viewport content='width=device-width,initial-scale=1'><title>{E(title)}</title>"
            f"{st(a['reveal_css'])}{st(a[theme])}{st(a['katex_css'])}{st(reveal_css(style))}</head><body><div class=reveal><div class=slides>{''.join(sl)}</div></div>"
            f"{sc(a['katex_js'])}{sc(a['auto_js'])}{sc(a['reveal_js'])}{sc(init)}</body></html>")

# ---------- σύνθετο Markdown ----------
def fix_md(text, base, demote=2):
    """Εικόνες images/x -> /files/<base>/images/x, επικεφαλίδες κατεβαίνουν επίπεδα, χωρίς γραμμές «--» (διαχωριστικά διαφανειών)."""
    def line(l):
        if l.strip() == '--': return None
        m = re.match(r'^(#{1,6})([ \t].*)$', l)
        if m: l = '#' * min(6, len(m.group(1)) + demote) + m.group(2)
        return re.sub(r'(!\[[^\]]*\]\()(images/[A-Za-z0-9_.-]+\.(?:png|jpe?g|svg))(\))', lambda x: f'{x.group(1)}/files/{base}/{x.group(2)}{x.group(3)}', l, flags=re.I)
    return outside_fences(text, line)

def quiz_md(r, qs):
    out = []
    for q in qs:
        out.append(f"{q['n']}. *({qsol.QTYPES.get(q['type'], q['type'])}, {q.get('points', 1):g} μον.)* {' '.join(q['stem'].split())}")
        if q.get('image') and IMG.match(q['image']): out.append(f"\n   ![](/files/{r['base']}/{q['image']})\n")
        for i, o in enumerate(q.get('options') or []): out.append(f"   - {LET[i] if i < len(LET) else i + 1}. {o}")
        out.append(f"\n   **Απάντηση:** {answer_text(q)}" + (f" — {' '.join(q['feedback'].split())}" if q.get('feedback') else ''))
        out.append('')
    return '\n'.join(out)

def sol_markdown(rows, title, include, style=''):
    """style (αν δοθεί) γράφει αόρατο ορισμό «[thilek-style]: #στυλ» που διαβάζει η εξαγωγή Word για τα χρώματα των επικεφαλίδων· στο στυλ «Μαθητικό» οι επικεφαλίδες παίρνουν εικονίδια."""
    icons = bool(style) and STYLES[style_of(style)]['icons'] and style_of(style) == 'kids'
    out = [f'# {title}', '']
    for k, r in enumerate(rows):
        pts = r['fm'].get('points')
        out += [f"## {label(r)}" + (f' ({pts} μον.)' if pts not in (None, '') else ''), '']
        for key, kind, d in unit_items(r, include):
            h = f"### {ICON[key] + ' ' if icons else ''}{LABEL[key]}"
            if kind == 'md': out += [h, '', fix_md(d, r['base']), '']
            elif kind == 'parts': out += [h, ''] + [x for b in d for x in (fix_md(b, r['base']), '')]
            else: out += [h, '', quiz_md(r, d), '']
        if k < len(rows) - 1: out += ['\\newpage', '']
    if style: out += ['', f'[thilek-style]: #{style_of(style)}', '']
    return normalize_math_md('\n'.join(out))

# ---------- Moodle XML ----------
def cdata(s): return '<![CDATA[' + (s or '').replace(']]>', ']]]]><![CDATA[>') + ']]>'
def xtext(s): return E(s or '', quote=False)
def cloze_esc(s): return re.sub(r'([}#~/"\\])', r'\\\1', s)
def num(v): return f'{v:g}' if isinstance(v, (int, float)) else str(v)

def moodle_xml(rows, title, root='', cat='single', tags=False):
    """-> (xml, παραλείψεις [κείμενο], πλήθος). Κάθε στοιχείο quiz χωρίς σφάλμα γίνεται μία ερώτηση.
    cat: 'single' (μία κατηγορία = τίτλος) | 'item' (υποκατηγορία «Θέμα <ID>») | 'qtype' (υποκατηγορία ανά τύπο στοιχείου). tags: ετικέτες Moodle (θέμα, ερώτημα, τύπος, ετικέτες της λύσης)."""
    base_cat = (title or 'TH-ILEK').replace('/', '-'); blocks = []
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<quiz>', '<!-- TH-ILEK: εξαγωγή από τα quiz blocks των λύσεων εκπαιδευτικού. ΔΕΝ έχει δοκιμαστεί σε πραγματικό Moodle. -->',
           ]
    skipped, notes, n = [], [], 0
    for r in rows:
        for q in r['quiz']:
            name = f"{r['item_id']}.{r['qcode'].replace('.', '-')} · στοιχείο {q['n']}"
            if q['err']: skipped.append(f"{name}: {'; '.join(q['err'])}"); continue
            t = q['type']; stem = q['stem']; files = ''
            if t == 'numeric' and q.get('unit'): stem += f"\n(σε {q['unit']})"
            if t == 'fill' and '___' not in stem: notes.append(f'{name}: fill χωρίς «___», έγινε σύντομη απάντηση'); t = 'short'
            if t == 'fill':
                blanks = len(re.findall(r'_{3,}', stem)); ans = q['answer']
                if blanks > 1 and len(ans) != blanks and len(ans) != 1: skipped.append(f'{name}: {blanks} κενά αλλά {len(ans)} απαντήσεις'); continue
                parts = re.split(r'_{3,}', stem); qt = moodle_text(parts[0])
                for k, p in enumerate(parts[1:]):
                    alts = [ans[k]] if blanks > 1 and len(ans) == blanks else ans
                    qt += '{1:SHORTANSWER:' + '~'.join('=' + cloze_esc(a) for a in alts) + '}' + moodle_text(p)
            else: qt = moodle_text(stem)
            if q.get('image'):
                u = img_data(root, f"{r['base']}/{q['image']}"); fn = q['image'].split('/')[-1]
                if u:
                    files = f'<file name="{xtext(fn)}" path="/" encoding="base64">{u.split(",", 1)[1]}</file>'; qt += f'<br><img src="@@PLUGINFILE@@/{E(fn)}" alt="">'
                else: notes.append(f"{name}: λείπει η εικόνα {q['image']} (η ερώτηση βγήκε χωρίς αυτήν)")
            mtype = {'true_false': 'truefalse', 'mcq': 'multichoice', 'short': 'shortanswer', 'numeric': 'numerical', 'fill': 'cloze', 'matching': 'matching'}[t]
            x = [f'<question type="{mtype}">', f'<name><text>{xtext(name)}</text></name>', f'<questiontext format="html"><text>{cdata(qt)}</text>{files}</questiontext>',
                 f'<generalfeedback format="html"><text>{cdata(moodle_text(q.get("feedback", "")))}</text></generalfeedback>']
            if t != 'fill': x.append(f'<defaultgrade>{num(q.get("points", 1))}</defaultgrade>')
            x += ['<penalty>0.3333333</penalty>', '<hidden>0</hidden>']
            if t == 'true_false':
                x += [f'<answer fraction="{100 if q["answer"] else 0}" format="moodle_auto_format"><text>true</text><feedback format="html"><text></text></feedback></answer>',
                      f'<answer fraction="{0 if q["answer"] else 100}" format="moodle_auto_format"><text>false</text><feedback format="html"><text></text></feedback></answer>']
            elif t == 'mcq':
                x += ['<single>true</single>', '<shuffleanswers>true</shuffleanswers>', '<answernumbering>abc</answernumbering>']
                x += [f'<answer fraction="{100 if i == q["answer"] else 0}" format="html"><text>{cdata(moodle_text(o))}</text><feedback format="html"><text></text></feedback></answer>' for i, o in enumerate(q['options'])]
            elif t == 'short':
                x.append('<usecase>0</usecase>'); x += [f'<answer fraction="100" format="moodle_auto_format"><text>{xtext(a)}</text><feedback format="html"><text></text></feedback></answer>' for a in q['answer']]
            elif t == 'numeric':
                x.append(f'<answer fraction="100" format="moodle_auto_format"><text>{num(q["answer"])}</text><tolerance>{num(q.get("tolerance", 0))}</tolerance><feedback format="html"><text></text></feedback></answer>')
            elif t == 'matching':
                x.append('<shuffleanswers>true</shuffleanswers>')
                x += [f'<subquestion format="html"><text>{cdata(moodle_text(a))}</text><answer><text>{cdata(moodle_text(b))}</text></answer></subquestion>' for a, b in q['pairs']]
            if tags:
                tg = [f"θέμα-{r['item_id']}", f"ερώτημα-{r['qcode']}", t] + [str(z) for z in (r.get('fm') or {}).get('tags') or []]
                seen_t = []
                for z in tg:
                    z = z.replace(',', ' ').strip()
                    if z and z not in seen_t: seen_t.append(z)
                x.append('<tags>' + ''.join(f'<tag><text>{xtext(z)}</text></tag>' for z in seen_t) + '</tags>')
            x.append('</question>')
            ck = '' if cat == 'single' else (f"Θέμα {r['item_id']}" if cat == 'item' else {'true_false': 'Σωστό-Λάθος', 'mcq': 'Πολλαπλής επιλογής', 'short': 'Σύντομη απάντηση', 'numeric': 'Αριθμητική', 'fill': 'Συμπλήρωση', 'matching': 'Αντιστοίχιση'}[t])
            blocks.append((ck, '\n'.join(x))); n += 1
    if cat == 'qtype': blocks.sort(key=lambda b: b[0])                   # ταξινόμηση ανά τύπο (σταθερή)
    last = None
    for ck, xml in blocks:
        if last is None or ck != last:
            path = '$course$/top/' + base_cat + (('/' + ck.replace('/', '-')) if ck else '')
            out.append(f'<question type="category"><category><text>{xtext(path)}</text></category></question>'); last = ck
        out.append(xml)
    if not blocks: out.append(f'<question type="category"><category><text>{xtext("$course$/top/" + base_cat)}</text></category></question>')
    for s in skipped: out.append('<!-- παραλείφθηκε: ' + s.replace('--', '- -') + ' -->')
    for s in notes: out.append('<!-- σημείωση: ' + s.replace('--', '- -') + ' -->')
    out.append('</quiz>')
    return '\n'.join(out) + '\n', skipped, n

# ---------- κοινή είσοδος (μπάρα ενεργειών /select/act και σελίδα /lysi) ----------
def export(c, act, keys, sx=None, title='', theme='', hide=True):
    rows = load(c, keys)
    if not rows: raise HTTPException(422, 'Κανένα από τα επιλεγμένα ερωτήματα δεν έχει λύση εκπαιδευτικού (αρχείο .md). Δες τη σελίδα «Λύσεις».')
    inc = include_of(sx); style = style_of(theme); title = (title or '').strip()[:200] or 'Λύσεις εκπαιδευτικού'; root = config.load()['data_root']
    if act == 'reveal':
        return Response(reveal_html(rows, title, inc, style, root), media_type='text/html; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="thilek-reveal.html"'})
    if act == 'html':
        from .solhtml import student_html
        return Response(student_html(rows, title, inc, style, root, bool(hide)), media_type='text/html; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="thilek-mathitis.html"'})
    if act == 'solmd':
        from .mddoc import new_doc
        did = new_doc(c, title, sol_markdown(rows, title, inc, style if theme else ''), f'λύσεις εκπαιδευτικού ({len(rows)})'); c.commit()
        return RedirectResponse(f'/docs/{did}', status_code=303)
    if act == 'moodle':
        xml, skipped, n = moodle_xml(rows, title, root)
        if not n: raise HTTPException(422, 'Οι επιλεγμένες λύσεις δεν έχουν έγκυρα στοιχεία quiz για Moodle.' + (f' Παραλείφθηκαν: {len(skipped)}.' if skipped else ''))
        return Response(xml, media_type='application/xml; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="thilek-moodle.xml"', 'X-Skipped': str(len(skipped)), 'X-Questions': str(n)})
    raise HTTPException(422, 'Άγνωστη ενέργεια')
