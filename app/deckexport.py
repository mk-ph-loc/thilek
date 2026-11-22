"""0.32: εξαγωγές παρουσιάσεων: Reveal.js (αυτόνομο HTML), διάταξη εκτύπωσης για PDF από τον browser, PowerPoint μέσω Pandoc, deck.md, αποθήκευση/δημοσίευση.
Επαναχρησιμοποιεί solexport.reveal_page / pandoc_run / fragmentize και deckmd. Δεν υπάρχει PDF στον server (μόνο Ctrl+P → «Αποθήκευση ως PDF» από τον browser·
εναλλακτικές για πιο προχωρημένο PDF: LibreOffice headless πάνω στο .pptx ή Pandoc + XeLaTeX/Beamer, βλ. εγχειρίδιο)."""
import html, re
from fastapi import HTTPException
from . import config, decktpl as T, deckmd, embed as EM, settings, solexport as X
from .mdmath import img_data, normalize_math_md, outside_fences, render_md
from .solstyle import STYLES, style_of

E = html.escape
DECK_CSS = (".reveal .cols{display:flex;gap:1.2em;align-items:flex-start}.reveal .col{flex:1;min-width:0}.reveal .ctr{display:flex;flex-direction:column;justify-content:center;height:100%;text-align:center}"
            ".reveal .ctr h1{margin:.2em 0}.reveal .l-section h1{color:var(--accent);font-size:2.2em}.reveal .small{font-size:.8em}.reveal .center{text-align:center}.reveal .dim{opacity:.7}"
            ".reveal .warn{color:var(--bad)}.reveal .emb{position:relative;width:100%;max-width:100%;margin:.4em 0;background:#0001;border-radius:var(--rad);overflow:hidden;display:flex;flex-direction:column;align-items:center;justify-content:center}.reveal .emb iframe{position:absolute;inset:0;width:100%;height:100%;border:0}.reveal .embgo{font-size:.7em;padding:.4em .9em;cursor:pointer}.reveal .embed{padding:.4em .8em;border:1px solid currentColor;border-radius:var(--rad);display:inline-block}.reveal .qz .stem{margin:.3em 0}"
            ".reveal .hd{margin-bottom:.4em}.reveal .l-bullets li,.reveal .l-summary li{margin:.25em 0}")


def effective(deck, sl):
    """Διαφάνειες που εξάγονται: χωρίς τις κρυμμένες, με προαιρετική διαφάνεια τίτλου και περιεχομένων (opts.title_slide / opts.toc)."""
    vis = [s for s in sl if not s.get('hidden')]; o = deck['opts']; out = []
    if o['title_slide'] and not (vis and vis[0].get('layout') == 'title'): out.append({'layout': 'title', 'title': deck.get('title') or deck['name'], 'body': deck.get('subtitle') or '', 'notes': '', 'opts': {}, 'down': 0})
    if o['toc']:
        items = [s['title'] for s in vis if s.get('layout') == 'section' and s.get('title')]
        if items: out.append({'layout': 'bullets', 'title': 'Περιεχόμενα', 'body': '\n'.join('- ' + t for t in items), 'notes': '', 'opts': {'frag': False}, 'down': 0})
    return out + vis


def section_html(s, deck, root, links=None, domains=(), mode='reveal'):
    o = T.load_opts(s.get('opts'), deck=False); lay = T.layout_ok(s.get('layout'))
    cls = ['u', f"l-{lay}"] + ([f"u-{T.LAYOUT_UNIT[lay]}"] if lay in T.LAYOUT_UNIT else []) + ([o['cls']] if o['cls'] else [])
    at = []
    if o['bg'].get('color'): at.append(f"data-background-color='{E(o['bg']['color'])}'")
    if o['bg'].get('image'):
        u = img_data(root, o['bg']['image'][len('/files/'):])
        if u: at.append(f"data-background-image='{E(u)}'")
    if o['transition']: at.append(f"data-transition='{E(o['transition'])}'")
    body = deckmd.slide_html(s, root, links, deck['opts']['frag'], domains, mode)
    t = E(s.get('title') or '')
    if lay == 'title': inner = f"<div class=ctr><h1>{t}</h1>{body}</div>"
    elif lay == 'section': inner = f"<div class=ctr><h1>{t}</h1></div>"
    elif lay in T.NO_HEADER or not t: inner = body
    else: inner = f"<div class=hd><h2>{t}</h2></div>{body}"
    notes = f"<aside class=notes>{render_md(s['notes'], o['base'], embed_root=root)}</aside>" if (s.get('notes') or '').strip() else ''
    return f"<section class='{' '.join(cls)}' {' '.join(at)}>{inner}{notes}</section>"


def stacks(sl):
    """Ομαδοποίηση σε κάθετες στοίβες: down=1 κολλά κάτω από την προηγούμενη διαφάνεια (η πρώτη δεν μπορεί να είναι «κάτω»)."""
    out = []
    for i, s in enumerate(sl):
        if s.get('down') and out: out[-1].append(s)
        else: out.append([s])
    return out


def reveal(deck, sl, root, links=None, print_=False, publish=False, domains=None):
    """Αυτόνομο HTML Reveal.js. print_: διάταξη εκτύπωσης (?print-pdf) για PDF από τον browser (με σημειώσεις σε ξεχωριστή σελίδα αν opts.pdf_notes)."""
    o = deck['opts']; es = effective(deck, sl)
    domains = EM.hosts(settings.get('embed_domains')) if domains is None else domains; mode = 'print' if print_ else ('click' if publish else 'reveal')
    if not es: raise HTTPException(422, 'Η παρουσίαση δεν έχει εμφανίσιμες διαφάνειες.')
    parts = []
    for g in stacks(es):
        hs = [section_html(s, deck, root, links, domains, mode) for s in g]
        parts.append(hs[0] if len(hs) == 1 else '<section>' + ''.join(hs) + '</section>')
    w, h = T.RATIOS[o['ratio']]; style = style_of(deck['style'])
    cfg = {'width': w, 'height': h, 'transition': o['transition'], 'slide_number': 'c/t' if o['numbers'] else False, 'css': DECK_CSS, 'print_': print_,
           'show_notes': ('separate-page' if o['pdf_notes'] else False) if print_ else False, 'notes': (not print_) and any((s.get('notes') or '').strip() for s in es),
           'meta_csp': None if publish else f"frame-src {EM.csp_frames(domains)}; object-src 'none'; base-uri 'none'", 'js': EM.CLICK_JS if (publish and domains) else ''}
    return X.reveal_page(''.join(parts), deck.get('title') or deck['name'], style, cfg)


def _heading(s, deck):
    t = ' '.join((s.get('title') or '').split()) or '—'
    return f"# {t}" if s.get('layout') == 'section' else f"## {t}"


def pptx_markdown(deck, sl, root):
    """Markdown για Pandoc: section → `#`, κάθε άλλη διαφάνεια → `##` (--slide-level=2). Σημειώσεις σε `::: notes`, στήλες σε `:::: columns`."""
    out = []
    for s in effective(deck, sl):
        body = deckmd.slide_pandoc(s, root); out += [_heading(s, deck), '', body, '']
    return normalize_math_md('\n'.join(out))


def pptx_bytes(deck, sl, root):
    return X.pandoc_run(pptx_markdown(deck, sl, root), deck.get('title') or deck['name'], bool(deck['opts']['pptx_frag']), ext='+fenced_divs')


def site_files(deck, sl, root, links=None):
    """Για publish.save_site: ένα αυτόνομο index.html."""
    return {'index.html': reveal(deck, sl, root, links).encode('utf-8')}


def slug(s): return re.sub(r'[^\w-]+', '_', s or '', flags=re.U).strip('_')[:50] or 'paroysiasi'


def build(deck, sl, act):
    """-> (bytes, όνομα αρχείου, mime). act: reveal | print | pptx | md."""
    root = config.load()['data_root']; base = slug(deck.get('title') or deck['name'])
    if act == 'reveal': return reveal(deck, sl, root).encode('utf-8'), base + '.html', 'text/html; charset=utf-8'
    if act == 'print': return reveal(deck, sl, root, print_=True).encode('utf-8'), base + '-print.html', 'text/html; charset=utf-8'
    if act == 'pptx': return pptx_bytes(deck, sl, root), base + '.pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    if act == 'md': return deckmd.deck_md(deck, sl).encode('utf-8'), base + '.deck.md', 'text/markdown; charset=utf-8'
    raise HTTPException(404, 'Άγνωστη εξαγωγή.')
