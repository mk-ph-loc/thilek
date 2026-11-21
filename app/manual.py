"""Εγχειρίδιο χρήσης: το αρχείο app/manual.md εμφανίζεται ως σελίδα (/manual) με περιεχόμενα· και ως ωμό Markdown (/manual.md)."""
import html, pathlib, re
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from markdown_it import MarkdownIt
from .main_auth import auth
from .review import page

router = APIRouter()
PATH = pathlib.Path(__file__).parent / 'manual.md'

def slug(t):
    s = re.sub(r'[^\w\- ]', '', t.lower(), flags=re.U).strip().replace(' ', '-')
    return s or 'x'

def render(text):
    md = MarkdownIt('commonmark', {'html': False}).enable('table'); toks = md.parse(text); toc = []; used = set()
    for i, t in enumerate(toks):
        if t.type == 'heading_open' and t.tag in ('h2', 'h3'):
            title = toks[i + 1].content; sid = base = slug(title); n = 2
            while sid in used: sid = f'{base}-{n}'; n += 1
            used.add(sid); t.attrSet('id', sid)
            if t.tag == 'h2': toc.append((sid, title))
    return md.renderer.render(toks, md.options, {}), toc

CSS = ("<style>.man{display:grid;grid-template-columns:230px 1fr;gap:1.2rem;align-items:start}.mantoc{position:sticky;top:calc(var(--hh,3rem) + .6rem);max-height:calc(92vh - var(--hh,3rem));overflow:auto;font-size:.92rem;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);padding:.6rem .8rem}"
       ".mantoc a{display:block;padding:.15rem 0;text-decoration:none}.manbody{max-width:860px;line-height:1.55}.manbody h2{margin-top:1.8rem;border-bottom:1px solid var(--border);padding-bottom:.2rem}.manbody pre{background:var(--card);border:1px solid var(--border);padding:.6rem;overflow:auto;border-radius:var(--radius)}"
       ".manbody code{background:var(--card);padding:0 .25rem;border-radius:3px}.manbody pre code{padding:0}.manbody blockquote{border-left:3px solid var(--accent);margin-left:0;padding-left:.8rem}.manbody table{border-collapse:collapse;margin:.6rem 0}.manbody td,.manbody th{border:1px solid var(--border);padding:.3rem .6rem;vertical-align:top}"
       "@media(max-width:900px){.man{grid-template-columns:1fr}.mantoc{position:static}}</style>")

@router.get('/manual', response_class=HTMLResponse, dependencies=[Depends(auth)])
def manual():
    body, toc = render(PATH.read_text(encoding='utf-8'))
    nav = ''.join(f"<a href='#{html.escape(s)}'>{html.escape(t)}</a>" for s, t in toc)
    return page('Οδηγίες χρήσης', f"{CSS}<div class=man><nav class=mantoc><b>Περιεχόμενα</b>{nav}<hr><a href='/manual.md'>⬇ Λήψη .md</a></nav><div class=manbody>{body}</div></div>")

@router.get('/manual.md', dependencies=[Depends(auth)])
def manual_md():
    return Response(PATH.read_text(encoding='utf-8'), media_type='text/markdown; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="thilek-manual.md"'})
