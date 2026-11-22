"""Εγχειρίδια (0.19.0): οδηγίες χρήσης (/manual), ερωτήσεις-απαντήσεις (/manual/faq), βάση δεδομένων (/manual/db), διάγραμμα συστήματος (/manual/system).
Κάθε εγχειρίδιο είναι αρχείο Markdown στο app/ και αποδίδεται με τον εμπλουτισμένο renderer (mdrich): πλαίσια, καρτέλες, λίστες εργασιών, badges, Mermaid."""
import html, pathlib
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from .main_auth import auth
from .review import page
from . import mdrich

router = APIRouter()
APP = pathlib.Path(__file__).parent
PATH = APP / 'manual.md'
MANUALS = {'manual': ('manual.md', 'Οδηγίες χρήσης', '/manual', 'thilek-manual.md'), 'faq': ('manual_faq.md', 'Ερωτήσεις-απαντήσεις', '/manual/faq', 'thilek-faq.md'),
           'db': ('manual_db.md', 'Βάση δεδομένων', '/manual/db', 'thilek-manual-vasi.md'), 'system': ('manual_system.md', 'Διάγραμμα συστήματος', '/manual/system', 'thilek-system.md'),
           'reveal': ('manual_reveal.md', 'Βοήθεια Reveal', '/manual/reveal', 'thilek-reveal-help.md')}

CSS = ("<style>.man{display:grid;grid-template-columns:230px 1fr;gap:1.2rem;align-items:start}.mantoc{position:sticky;top:calc(var(--hh,3rem) + .6rem);max-height:calc(92vh - var(--hh,3rem));overflow:auto;font-size:.92rem;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);padding:.6rem .8rem}"
       ".mantoc a{display:block;padding:.15rem 0;text-decoration:none}.manbody{max-width:900px;line-height:1.55}.manbody h2{margin-top:1.8rem;border-bottom:1px solid var(--border);padding-bottom:.2rem}.manbody pre{background:var(--card);border:1px solid var(--border);padding:.6rem;overflow:auto;border-radius:var(--radius);max-height:none}"
       ".manbody code{background:var(--card);padding:0 .25rem;border-radius:3px}.manbody pre code{padding:0}.manbody blockquote{border-left:3px solid var(--accent);margin-left:0;padding-left:.8rem}.manbody table{border-collapse:collapse;margin:.6rem 0}.manbody td,.manbody th{border:1px solid var(--border);padding:.3rem .6rem;vertical-align:top}"
       ".manbar{margin:.2rem 0 .8rem}.faqbar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:.4rem 0 .8rem}.faqbar input{min-width:18rem}"
       "@media(max-width:900px){.man{grid-template-columns:1fr}.mantoc{position:static}}</style>")


def render(text, mermaid='svg', ck_prefix='m'):
    """Συμβατότητα με 0.18: (html, toc)."""
    body, toc, _ = mdrich.render(text, mermaid, ck_prefix); return body, toc


def build(slug):
    from . import settings
    fn, title, url, _ = MANUALS[slug]; mode = settings.get('diagram_mode')
    body, toc, env = mdrich.render((APP / fn).read_text(encoding='utf-8'), mode, slug)
    nav = ''.join(f"<a href='#{html.escape(s)}'>{html.escape(t)}</a>" for s, t in toc)
    bar = '<div class="tabs manbar">' + ''.join(f"<a class='tab{' on' if k == slug else ''}' href='{u}'>{html.escape(t)}</a>" for k, (_, t, u, _) in MANUALS.items()) + '</div>'
    faq = ("<div class=faqbar><input type=search class=r-txt data-filter='details.adm[data-faq]' data-count=faqn placeholder='Αναζήτηση στις ερωτήσεις…' aria-label='Αναζήτηση'><span id=faqn></span>"
           "<button type=button data-open-all=1>Άνοιγμα όλων</button><button type=button data-open-all=0>Κλείσιμο όλων</button></div>") if slug == 'faq' else ''
    js = "<script src='/static/vendor/mermaid/mermaid.min.js'></script>" if env.get('mermaid_local') else ''
    return page(title, f"{CSS}{bar}<div class=man><nav class=mantoc><b>Περιεχόμενα</b>{nav}<hr><a href='{url}.md' download>⬇ Λήψη .md</a></nav><div class=manbody>{faq}{body}</div></div>{js}")


@router.get('/manual', response_class=HTMLResponse, dependencies=[Depends(auth)])
def manual(): return build('manual')


@router.get('/manual.md', dependencies=[Depends(auth)])
def manual_md(): return _md('manual')


@router.get('/manual/{slug}.md', dependencies=[Depends(auth)])
def manual_other_md(slug: str): return _md(slug)


@router.get('/manual/{slug}', response_class=HTMLResponse, dependencies=[Depends(auth)])
def manual_other(slug: str):
    if slug not in MANUALS: raise HTTPException(404)
    return build(slug)


def _md(slug):
    if slug not in MANUALS: raise HTTPException(404)
    fn, _, _, dl = MANUALS[slug]
    return Response((APP / fn).read_text(encoding='utf-8'), media_type='text/markdown; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{dl}"'})
