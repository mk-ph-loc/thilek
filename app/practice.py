"""Εξάσκηση μαθητή και flashcards από quiz (αυτόνομες σελίδες HTML), εξαγωγή Anki (TSV), δημοσίευση στα /p/. Δεν αποθηκεύεται τίποτα στον server."""
import json, re
from html import escape as E
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from .main_auth import auth
from .review import db, same_origin
from .quizzes import get_quiz, opts_of, ans_text, LET
from . import publish

router = APIRouter()
KINDS = {'practice': 'εξάσκηση', 'cards': 'flashcards'}
META = "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'\">"
HDR = {'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"}


def items_of(c, qid):
    out = []
    for r in c.execute('SELECT * FROM quiz_item WHERE quiz_id=? ORDER BY pos', (qid,)).fetchall():
        if not (r['stem'] or '').strip(): continue
        o = opts_of(r)[:len(LET)] if r['kind'] == 'mcq' else []
        out.append({'k': r['kind'], 'q': r['stem'].strip(), 'o': o, 'a': r['answer'] or '', 't': ans_text(r) if r['kind'] != 'free' else (r['answer'] or ''), 'f': (r['feedback'] or '').strip(), 'p': r['points'], 'src': r['src_item'] or ''})
    return out


def jdump(x): return json.dumps(x, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


CSS = ("body{font:17px/1.5 'Segoe UI',Arial,sans-serif;max-width:760px;margin:0 auto;padding:1rem;background:#f4f6fa;color:#1d2433}h1{font-size:1.3rem}button{font:inherit;padding:.55rem .9rem;margin:.25rem .25rem .25rem 0;border:1px solid #9aa7c0;border-radius:8px;background:#fff;cursor:pointer}"
       "button.primary{background:#1f3a68;color:#fff;border-color:#1f3a68}.card{background:#fff;border:1px solid #d3dae8;border-radius:12px;padding:1rem;margin:.8rem 0}.opt{display:block;width:100%;text-align:left}.ok{background:#dff3e6!important;border-color:#2e9e5b!important}"
       ".bad{background:#fbe3e1!important;border-color:#d9534f!important}.muted{color:#5b6679;font-size:.9em}.q{white-space:pre-wrap}.big{min-height:9rem;display:flex;align-items:center;justify-content:center;text-align:center;cursor:pointer;white-space:pre-wrap}")

PRACTICE_JS = r"""
(function(){var D=JSON.parse(document.getElementById('d').textContent),I=D.items,KEY='thilek-practice-'+D.id,L='ΑΒΓΔΕΖΗΘ';
var el=document.getElementById('app'),queue,again,first,cur,round=0,total=I.length,firstOk=0,answered=false;
function h(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function shuf(a){a=a.slice();for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=a[i];a[i]=a[j];a[j]=t}return a}
function best(){try{var v=JSON.parse(localStorage.getItem(KEY)||'null');return v}catch(e){return null}}
function save(p){try{var v=best()||{runs:0,best:0};v.runs++;v.best=Math.max(v.best,p);localStorage.setItem(KEY,JSON.stringify(v))}catch(e){}}
function start(){queue=shuf(I.map(function(_,i){return i}));again=[];first={};round=1;firstOk=0;next()}
function next(){answered=false;if(!queue.length){if(again.length){return between()}return done()}cur=queue.shift();show()}
function head(){var d=h('div','muted','Γύρος '+round+(round>1?' (επανάληψη λαθών)':'')+' · απομένουν '+(queue.length+1));return d}
function mark(ok){if(!(cur in first)){first[cur]=ok;if(ok)firstOk++}if(!ok&&again.indexOf(cur)<0)again.push(cur)}
function fin(ok,box,it){var fb=h('div','card');fb.appendChild(h('b','',ok?'✔ Σωστά!':'✘ Όχι ακριβώς.'));if(!ok&&it.k!=='free')fb.appendChild(h('div','','Σωστή απάντηση: '+it.t));if(it.f)fb.appendChild(h('div','muted',it.f));
 var b=h('button','primary','Επόμενο ▶');b.onclick=next;fb.appendChild(b);box.appendChild(fb);b.focus()}
function show(){var it=I[cur];el.textContent='';el.appendChild(head());var box=h('div','card');box.appendChild(h('div','q',it.q));
 if(it.k==='free'){var r=h('button','','Δες την απάντηση');r.onclick=function(){r.remove();box.appendChild(h('div','card',it.a||'—'));if(it.f)box.appendChild(h('div','muted',it.f));
   var y=h('button','primary','Το ήξερα');var n=h('button','','Να το ξαναδώ');y.onclick=function(){mark(true);next()};n.onclick=function(){mark(false);next()};box.appendChild(y);box.appendChild(n)};box.appendChild(r)}
 else{var ch=it.k==='tf'?[['Σωστό','Σωστό'],['Λάθος','Λάθος']]:it.o.map(function(o,i){return [String(i),L[i]+'. '+o]});var bs=[];
  ch.forEach(function(c){var b=h('button','opt',c[1]);b.onclick=function(){if(answered)return;answered=true;var ok=c[0]===it.a;mark(ok);bs.forEach(function(x){x[1].disabled=true;if(x[0]===it.a)x[1].classList.add('ok')});if(!ok)b.classList.add('bad');fin(ok,box,it)};bs.push([c[0],b]);box.appendChild(b)})}
 el.appendChild(box)}
function between(){el.textContent='';var b=h('div','card');b.appendChild(h('h1','','Τέλος γύρου '+round));b.appendChild(h('p','','Σωστά με την πρώτη: '+firstOk+' από '+total+'. Λάθη προς επανάληψη: '+again.length+'.'));
 var g=h('button','primary','Επανάληψη των λαθών ▶');g.onclick=function(){queue=shuf(again);again=[];round++;next()};b.appendChild(g);el.appendChild(b)}
function done(){var p=Math.round(100*firstOk/total);save(p);el.textContent='';var b=h('div','card');b.appendChild(h('h1','','Τελείωσες! 🎉'));b.appendChild(h('p','','Σωστά με την πρώτη φορά: '+firstOk+' από '+total+' ('+p+'%). Όλα απαντήθηκαν σωστά στο τέλος.'));
 var v=best();if(v)b.appendChild(h('p','muted','Σε αυτόν τον browser: '+v.runs+' ολοκληρώσεις, καλύτερο '+v.best+'%.'));var g=h('button','primary','Ξανά από την αρχή');g.onclick=start;b.appendChild(g);el.appendChild(b)}
var v=best(),intro=h('div','muted',total+' ερωτήσεις'+(v?' · καλύτερο αποτέλεσμα σε αυτόν τον browser: '+v.best+'%':''));document.getElementById('intro').appendChild(intro);
document.getElementById('go').onclick=function(){document.getElementById('intro').hidden=true;start()}})();
"""

CARDS_JS = r"""
(function(){var D=JSON.parse(document.getElementById('d').textContent),I=D.items,L='ΑΒΓΔΕΖΗΘ',deck=I.map(function(_,i){return i}),pos=0,back=false,known=0,el=document.getElementById('app');
function h(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e}
function front(it){var s=it.q;if(it.k==='mcq')s+='\n\n'+it.o.map(function(o,i){return L[i]+'. '+o}).join('\n');return s}
function bk(it){var s=it.t||'—';if(it.f)s+='\n\n'+it.f;return s}
function render(){el.textContent='';if(!deck.length){var b=h('div','card');b.appendChild(h('h1','','Τα ξέρεις όλα! 🎉'));var r=h('button','primary','Ξανά όλες');r.onclick=function(){deck=I.map(function(_,i){return i});pos=0;back=false;known=0;render()};b.appendChild(r);el.appendChild(b);return}
 if(pos>=deck.length)pos=0;var it=I[deck[pos]];el.appendChild(h('div','muted','Κάρτα '+(pos+1)+' από '+deck.length+' · τις ξέρω: '+known));
 var c=h('div','card big',back?bk(it):front(it));c.tabIndex=0;c.setAttribute('role','button');c.onclick=function(){back=!back;render()};c.onkeydown=function(e){if(e.key===' '||e.key==='Enter'){e.preventDefault();back=!back;render()}};el.appendChild(c);
 var bar=h('div');function btn(t,f,p){var b=h('button',p?'primary':'',t);b.onclick=f;bar.appendChild(b)}
 btn('◀',function(){pos=(pos-1+deck.length)%deck.length;back=false;render()});btn('Γύρνα την κάρτα',function(){back=!back;render()});btn('▶',function(){pos=(pos+1)%deck.length;back=false;render()});
 btn('Το ξέρω ✔',function(){deck.splice(pos,1);known++;back=false;render()},true);btn('Ανακάτεμα',function(){for(var i=deck.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=deck[i];deck[i]=deck[j];deck[j]=t}pos=0;back=false;render()});el.appendChild(bar);c.focus()}
render()})();
"""


def page_html(kind, qid, title, items):
    js = PRACTICE_JS if kind == 'practice' else CARDS_JS
    h1 = f"<h1>{E(title)}</h1>"
    body = f"{h1}{'<div id=intro class=card><div class=muted>Οι ερωτήσεις έρχονται με τυχαία σειρά. Όσες αποτύχεις επανέρχονται μέχρι να τις απαντήσεις σωστά. Δεν στέλνεται τίποτα πουθενά.</div><button class=primary id=go>Ξεκίνα</button></div>' if kind == 'practice' else ''}<div id=app></div>"
    return (f"<!doctype html><html lang='el'><meta charset='utf-8'><meta name=viewport content='width=device-width,initial-scale=1'>{META}<title>{E(title)}</title><style>{CSS}</style><body>{body}"
            f"<script id=d type='application/json'>{jdump({'id': qid, 'items': items})}</script><script>{js}</script></body></html>")


def build(c, qid, kind):
    z = get_quiz(c, qid); its = items_of(c, qid)
    if not its: raise HTTPException(404, 'Το quiz δεν έχει στοιχεία.')
    if kind == 'cards': its = [i for i in its if i['t'] or i['k'] == 'free']
    return z, page_html(kind, qid, f"{z['name']} — {KINDS[kind]}", its)


def anki_tsv(c, qid):
    z = get_quiz(c, qid); its = items_of(c, qid)
    def cell(s): return '"' + re.sub(r'\s*\n\s*', '<br>', E(s).replace('\t', ' ')).replace('"', '""') + '"'
    tag = lambda s: re.sub(r'[^\w-]+', '_', s.strip()).strip('_')[:40]
    out = ['#separator:tab', '#html:true', '#tags column:3']; n = skipped = 0
    for it in its:
        back = it['t'] or ''
        if not back: skipped += 1; continue
        fr = it['q'] + (('\n\n' + '\n'.join(f'{LET[i]}. {o}' for i, o in enumerate(it['o']))) if it['k'] == 'mcq' else '')
        if it['f']: back += '\n\n' + it['f']
        tags = ' '.join(t for t in (tag('thilek'), tag(z['name']), it['k'], ('ΙΕΠ_' + tag(it['src'])) if it['src'] else '') if t)
        out.append(f"{cell(fr)}\t{cell(back)}\t{tags}"); n += 1
    return '\n'.join(out) + '\n', n, skipped


@router.get('/quizzes/{qid}/practice', response_class=HTMLResponse, dependencies=[Depends(auth)])
def quiz_practice(qid: int):
    c = db(); z, h = build(c, qid, 'practice'); c.close(); return HTMLResponse(h, headers=HDR)


@router.get('/quizzes/{qid}/cards', response_class=HTMLResponse, dependencies=[Depends(auth)])
def quiz_cards(qid: int):
    c = db(); z, h = build(c, qid, 'cards'); c.close(); return HTMLResponse(h, headers=HDR)


@router.get('/quizzes/{qid}/anki.tsv', dependencies=[Depends(auth)])
def quiz_anki(qid: int):
    c = db(); txt, n, sk = anki_tsv(c, qid); c.close()
    return Response(txt, media_type='text/tab-separated-values; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="thilek-quiz-{qid}-anki.tsv"', 'X-Cards': str(n), 'X-Skipped': str(sk)})


@router.post('/quizzes/{qid}/publish', dependencies=[Depends(auth)])
async def quiz_publish(request: Request, qid: int):
    same_origin(request); f = await request.form(); kind = str(f.get('kind') or '')
    if kind not in KINDS: raise HTTPException(422, 'Άγνωστο είδος δημοσίευσης.')
    c = db(); z, h = build(c, qid, kind); c.close()
    publish.save_site(f"{z['name']} — {KINDS[kind]}", {'index.html': h.encode('utf-8')}, slug=f'quiz-{qid}-{kind}', source=f'Quiz {qid}')
    return RedirectResponse('/publish?ok=1', status_code=303)
