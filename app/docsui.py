"""Βοήθεια ανά σελίδα και κοινό JS εγχειριδίων (0.19.0).
- Pure-ASGI middleware κρατά τη διαδρομή του αιτήματος σε contextvar, ώστε το review.page() να βάζει το σωστό help χωρίς να αλλάξει κανένα module σελίδας.
- Το help είναι <details class=help data-hk=ΚΛΕΙΔΙ>· το static/docs.js θυμάται ανοιχτό/κλειστό ανά σελίδα (localStorage)."""
import contextvars, html, pathlib
from fastapi import APIRouter
from fastapi.responses import Response
from . import helpdb, mdrich

router = APIRouter()
PATH = contextvars.ContextVar('thilek_path', default='')
STATIC = pathlib.Path(__file__).parent / 'static'
E = html.escape


class PathMiddleware:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        tok = PATH.set(scope.get('path', '')) if scope['type'] == 'http' else None
        try: await self.app(scope, receive, send)
        finally:
            if tok is not None: PATH.reset(tok)


@router.get('/static/docs.js', include_in_schema=False)
def docs_js(): return Response((STATIC / 'docs.js').read_text(encoding='utf-8'), media_type='application/javascript')


def _ul(items): return '<ul>' + ''.join(f'<li>{mdrich.inline(x)}</li>' for x in items) + '</ul>'


def settings_now():
    from . import settings as st
    return st.get_all()


def html_attrs(s):
    """Χαρακτηριστικά του <html> που διαβάζουν τα static scripts (CSP: όχι inline JS): είδη χωρίς tooltip και τρόπος βοήθειας."""
    off = ','.join(k for k in ('hdr', 'btn', 'danger', 'sel', 'opt', 'list', 'txt', 'file', 'sum') if s.get('tip_' + k) == 'off')
    return f" data-notips='{off}' data-helpmode='{E(s.get('help_mode', 'remember'))}'"


def help_html(path=None, settings=None):
    """Το πλαίσιο βοήθειας για τη διαδρομή (ή '' αν δεν υπάρχει ή είναι απενεργοποιημένο)."""
    key = helpdb.key_for(path if path is not None else PATH.get())
    if not key: return ''
    if settings is None:
        from . import settings as st; settings = st.get_all()
    if settings.get('help_show') == 'off': return ''
    h = helpdb.HELP[key]
    see = ' · '.join(f"<a href='{E(u)}'>{E(t)}</a>" for u, t in h['see'])
    sec = f" · Πλήρης οδηγός: <a href='/manual#s{E(h['sec'])}'>§{E(h['sec'])}</a>" if h.get('sec') else ''
    grid = (f"<div class='adm adm-tip'><p class=adm-t>✔ Τι μπορείς</p>{_ul(h['can'])}</div>"
            f"<div class='adm adm-warning'><p class=adm-t>✖ Τι ΔΕΝ μπορεί</p>{_ul(h['cannot'])}</div>"
            f"<div class='adm adm-info'><p class=adm-t>💾 Πού αποθηκεύονται τα δεδομένα</p><p>{mdrich.inline(h['data'])}</p></div>"
            f"<div class='adm adm-note'><p class=adm-t>🔗 Δες επίσης</p><p>{see}</p></div>")
    extra = (f"<details class=help-extra><summary>📄 Πρότυπο αρχείου λύσης, σημειώσεις και επεκτάσεις</summary>{mdrich.render(h['extra'], settings.get('diagram_mode', 'svg'), 'hx')[0]}</details>") if h.get('extra') else ''
    return (f"<details class=help data-hk='{key}' data-def='{'open' if settings.get('help_default') == 'open' else 'closed'}'><summary>ℹ Βοήθεια σελίδας: {E(h['title'])}</summary>"
            f"<div class=help-grid>{grid}</div>{extra}<p class=help-foot>Ό,τι αλλάζει εδώ ρυθμίζεται στις <a href='/settings'>Ρυθμίσεις</a>{sec} · <a href='/manual/faq'>Ερωτήσεις-απαντήσεις</a></p></details>")
