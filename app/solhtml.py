"""Αυτόνομο HTML μαθητή από λύσεις εκπαιδευτικού: μία σελίδα προς διανομή, offline (KaTeX και εικόνες ενσωματωμένα), με επιλεγμένο στυλ και σειρά ενοτήτων,
λύσεις κρυμμένες με κλικ και quiz που διορθώνεται στον browser. Οι σωστές απαντήσεις βρίσκονται μέσα στο αρχείο (ο μαθητής μπορεί να τις δει με «Προβολή πηγής»)."""
import datetime, html, json, random
from . import qsol
from .mdmath import render_md, md_text, protect, restore, math_to_text, img_data
from .solstyle import ICON, LABEL, STYLES, TEACHER, vars_css

E = html.escape
HIDE = ('iep', 'full')                                  # ενότητες που κρύβονται με κλικ όταν ζητηθεί

def plain(s):
    p, m = protect(s or ''); return restore(p, m, math_to_text)

def _qhtml(r, q, uid, root, X):
    t = q['type']; qid = f'q{uid}'
    out = [f"<div class=qhead><b>{q['n']}.</b> <small>({E(qsol.QTYPES.get(t, t))}, {q.get('points', 1):g} μον.)</small></div><div class=stem>{md_text(q['stem'])}</div>"]
    if q.get('image'):
        u = img_data(root, f"{r['base']}/{q['image']}")
        if u: out.append(f"<img src='{E(u)}' alt=''>")
    d = {'t': t, 'ans': md_text(X.answer_text(q)), 'fb': md_text(q['feedback']) if q.get('feedback') else ''}
    if t == 'mcq':
        d['a'] = q['answer']; out.append(''.join(f"<label class=opt><input type=radio name={qid} value={i}> <span>{X.LET[i] if i < len(X.LET) else i + 1}. {md_text(o)}</span></label>" for i, o in enumerate(q.get('options') or [])))
    elif t == 'true_false':
        d['a'] = 1 if q['answer'] else 0; out.append(f"<label class=opt><input type=radio name={qid} value=1> <span>Σωστό</span></label><label class=opt><input type=radio name={qid} value=0> <span>Λάθος</span></label>")
    elif t == 'numeric':
        d['a'] = q['answer']; d['tol'] = q.get('tolerance') or 0
        out.append(f"<input class=txt inputmode=decimal autocomplete=off placeholder='αριθμός'> {E(q.get('unit') or '')}")
    elif t == 'matching':
        pairs = q.get('pairs') or []; rights = [plain(b) for _, b in pairs]; d['pairs'] = rights
        sh = list(dict.fromkeys(rights)); random.Random(uid).shuffle(sh)
        opts = '<option value="">—</option>' + ''.join(f"<option value='{E(x, quote=True)}'>{E(x)}</option>" for x in sh)
        out.append(''.join(f"<div class=mrow><span>{md_text(a)}</span> <b>→</b> <select>{opts}</select></div>" for a, _ in pairs))
    else:
        d['a'] = list(q['answer']) if isinstance(q.get('answer'), (list, tuple)) else [str(q.get('answer', ''))]; out.append("<input class=txt autocomplete=off placeholder='απάντηση'>")
    out.append("<div class=qbtn><button type=button class=btn data-do=check>Έλεγχος</button> <button type=button class='btn alt' data-do=show>Δείξε την απάντηση</button></div><div class=res></div>")
    return f"<div class=q data-q={uid}>{''.join(out)}</div>", d

CSS = (".wrap{max-width:940px;margin:0 auto;padding:1rem 1.1rem 3rem}body{margin:0;background:var(--bg);color:var(--fg);font:calc(18px*var(--sz)) / 1.6 var(--font)}"
       "header.top{padding:1.2rem 0 .4rem}h1{margin:.2em 0;color:var(--head);font-size:1.9em}.meta{opacity:.75;margin:.2em 0}"
       "nav.toc{display:flex;flex-wrap:wrap;gap:.4rem;margin:.6rem 0}.chip{background:var(--card);color:var(--accent);border:2px solid var(--accent);border-radius:999px;padding:.15em .8em;text-decoration:none;font-size:.9em}"
       "article{background:var(--card);border-radius:var(--rad);box-shadow:0 2px 10px #0002;margin:1.4rem 0;padding:.8rem 1.3rem 1.1rem}article>h2{margin:.2em 0 .5em;color:var(--head);font-size:1.4em}"
       ".unit{border-left:7px solid var(--u);background:var(--ut);border-radius:var(--rad);padding:.55rem 1rem;margin:.9rem 0}.unit>h3,.unit>summary{margin:.1em 0 .4em;color:var(--u);font-size:1.1em;font-weight:700}"
       "details.unit>summary{cursor:pointer;margin:0}details.unit[open]>summary{margin-bottom:.4em}.badge{display:inline-block;margin-right:.35em}.unit p{margin:.45em 0}"
       "img{max-width:100%;height:auto;background:#fff}table{border-collapse:collapse;margin:.5em 0}td,th{border:1px solid currentColor;padding:.25em .6em}pre{overflow:auto;padding:.5em;background:#0001;border-radius:6px}"
       ".q{background:var(--card);border:2px solid var(--u);border-radius:var(--rad);padding:.6rem .9rem;margin:.7rem 0}.qhead small{opacity:.75}.opt{display:block;padding:.2em .3em;cursor:pointer}"
       ".txt,select{font:inherit;padding:.25em .5em;border:2px solid var(--accent);border-radius:8px;background:var(--card);color:var(--fg);max-width:100%}.mrow{margin:.35em 0}"
       ".btn{font:inherit;font-size:.9em;background:var(--accent);color:#fff;border:0;border-radius:999px;padding:.3em 1.1em;cursor:pointer}.btn.alt{background:transparent;color:var(--accent);border:2px solid var(--accent)}"
       ".qbtn{margin:.55em 0 .2em}.res{margin-top:.3em;font-weight:600}.res.ok{color:var(--ok)}.res.bad{color:var(--bad)}.res .fb{font-weight:400;color:var(--fg)}footer{opacity:.6;font-size:.85em;margin-top:2rem}"
       "@media print{body{background:#fff}.qbtn,nav.toc{display:none}article{box-shadow:none;border:1px solid #999;break-inside:auto}.unit{break-inside:avoid}}")

JS = r"""(function(){
var Q=JSON.parse(document.getElementById('qz').textContent);
function nz(s){return String(s==null?'':s).normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/ς/g,'σ').replace(/\s+/g,' ').trim();}
function num(s){s=String(s).replace(/\s/g,'').replace(',','.');var m=s.match(/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?/i);return m?parseFloat(m[0]):NaN;}
function show(el,ok,extra){var r=el.querySelector('.res'),q=Q[el.dataset.q];r.className='res '+(ok===null?'':ok?'ok':'bad');
 r.innerHTML=(ok===null?'':ok?'✔ Σωστά! ':'✖ Όχι ακριβώς. ')+(extra||'')+(q.fb&&ok!==null?'<div class=fb>'+q.fb+'</div>':'');
 if(window.renderMathInElement){try{renderMathInElement(r,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],throwOnError:false});}catch(e){}}}
function check(el){var q=Q[el.dataset.q],ok=false,c;
 if(q.t==='mcq'||q.t==='true_false'){c=el.querySelector('input:checked');if(!c)return show(el,null,'Διάλεξε μια απάντηση.');ok=String(q.a)===c.value;}
 else if(q.t==='numeric'){var v=num(el.querySelector('.txt').value);if(isNaN(v))return show(el,null,'Γράψε έναν αριθμό.');ok=Math.abs(v-q.a)<=Math.max(q.tol||0,Math.abs(q.a)*1e-9);}
 else if(q.t==='matching'){var s=el.querySelectorAll('select'),any=false;ok=true;s.forEach(function(x,i){if(x.value)any=true;if(nz(x.value)!==nz(q.pairs[i]))ok=false;});if(!any)return show(el,null,'Διάλεξε αντιστοιχίσεις.');}
 else{var t=nz(el.querySelector('.txt').value);if(!t)return show(el,null,'Γράψε μια απάντηση.');ok=q.a.some(function(a){return nz(a)===t;});}
 show(el,ok,ok?'':'');}
document.addEventListener('click',function(e){var b=e.target.closest('button[data-do]');if(!b)return;var el=b.closest('.q');
 if(b.dataset.do==='check')check(el);else{var q=Q[el.dataset.q],r=el.querySelector('.res');r.className='res';r.innerHTML='Απάντηση: <b>'+q.ans+'</b>'+(q.fb?'<div class=fb>'+q.fb+'</div>':'');
  if(window.renderMathInElement){try{renderMathInElement(r,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],throwOnError:false});}catch(e){}}}});
var op=[];window.addEventListener('beforeprint',function(){op=[].slice.call(document.querySelectorAll('details')).filter(function(d){return !d.open;});op.forEach(function(d){d.open=true;});});
window.addEventListener('afterprint',function(){op.forEach(function(d){d.open=false;});});
try{renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false},{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true}],throwOnError:false,ignoredTags:['script','style','textarea','pre','code']});}catch(e){}
})();"""

def student_html(rows, title, include, style, root, hide=True):
    from . import solexport as X
    s = STYLES[style]; a = X.assets(); data, arts = {}, []
    for n, r in enumerate(rows, 1):
        body = []; md = lambda t: render_md(t, r['base'], embed_root=root)
        for k, kind, d in X.unit_items(r, include):
            badge = f"<span class=badge>{ICON[k]}</span>" if s['icons'] else ''
            if kind == 'quiz':
                qh = []
                for q in d:
                    uid = f'{n}_{q["n"]}'; h, dd = _qhtml(r, q, uid, root, X); data[uid] = dd; qh.append(h)
                body.append(f"<section class='unit u-{k}'><h3>{badge}{E(LABEL[k])}</h3>{''.join(qh)}</section>")
                continue
            inner = md(d) if kind == 'md' else '\n'.join(md(b) for b in d)
            if hide and k in HIDE: body.append(f"<details class='unit u-{k}'><summary>{badge}{E(LABEL[k])} <small>(κλικ για εμφάνιση)</small></summary>{inner}</details>")
            else: body.append(f"<section class='unit u-{k}'><h3>{badge}{E(LABEL[k])}</h3>{inner}</section>")
        arts.append(f"<article id=s{n}><h2>{E(X.label(r))}</h2>{''.join(body)}</article>")
    chips = ''.join(f"<a class=chip href='#s{n}'>{E(r['qcode'])} · {E(r['item_id'])}</a>" for n, r in enumerate(rows, 1)) if len(rows) > 1 else ''
    js_data = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    css = f"{a['katex_css']}{vars_css(style)}:root{{--sz:{s['size']}}}{CSS}"
    return (f"<!doctype html><html lang='el'><head><meta charset='utf-8'><meta name=viewport content='width=device-width,initial-scale=1'><title>{E(title)}</title>"
            f"<style>{X._no_close(css, 'style')}</style></head><body><div class=wrap><header class=top><h1>{E(title)}</h1><p class=meta>{len(rows)} ερωτήματα · {datetime.date.today().isoformat()}</p>"
            f"<nav class=toc>{chips}</nav></header>{''.join(arts)}<footer>TH-ILEK · αυτόνομη σελίδα, λειτουργεί χωρίς σύνδεση στο διαδίκτυο</footer></div>"
            f"<script type='application/json' id=qz>{js_data}</script><script>{X._no_close(a['katex_js'], 'script')}</script><script>{X._no_close(a['auto_js'], 'script')}</script><script>{JS}</script></body></html>")
