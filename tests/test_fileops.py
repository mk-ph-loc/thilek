"""0.31.0: wizard αρχείων — split / merge / rename."""
import io, os, re, sqlite3
import pytest
from pypdf import PdfReader, PdfWriter
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_wizard import seed
from app import fileops as F


def pdf(n):
    w = PdfWriter()
    for _ in range(n): w.add_blank_page(200, 200)
    b = io.BytesIO(); w.write(b); return b.getvalue()


def setup(cl):
    seed(); root = os.environ['THILEK_ROOT']; o = os.path.join(root, 'C', '04_TRAPEZA', 'orig'); os.makedirs(o)
    open(os.path.join(o, '1.pdf'), 'wb').write(pdf(6)); open(os.path.join(o, '2.pdf'), 'wb').write(pdf(2))
    d = os.path.join(root, 'C', 'work'); os.makedirs(d)
    for n in ('a1.pdf', 'a2.pdf', 'a10.pdf'): open(os.path.join(d, n), 'wb').write(pdf(1))
    os.makedirs(os.path.join(root, 'C', '07_EXAGOGES'))
    return root


def post(cl, path, **d): return cl.post(path, data=d, auth=A, headers=H, follow_redirects=False)


def test_parse_ranges():
    assert F.parse_ranges('1-3, 4-6; 8', 8) == [(1, 3), (4, 6), (8, 8)]
    assert F.parse_ranges('5-', 7) == [(5, 7)] and F.parse_ranges('κάθε 3', 7) == [(1, 3), (4, 6), (7, 7)]
    for bad in ('', '0-2', '3-1', '1-9', 'abc', 'every 0'):
        with pytest.raises(ValueError): F.parse_ranges(bad, 8)


def test_pattern_whitelist():
    F.check_pattern('{name}_{n:02d}_{from}-{to}', F.SPLIT_KEYS)
    for bad in ('{name.__class__}', '{0}', '{name[0]}', '{n!r}', '{x}', '', '{from}'):
        with pytest.raises(ValueError): F.check_pattern(bad, F.RENAME_KEYS)


def test_split_preview_then_apply(cl):
    root = setup(cl); src = 'C/04_TRAPEZA/orig/1.pdf'
    data = dict(tab='split', dir='C/04_TRAPEZA/orig', src=src, spec='1-2, 3-6', pat='{name}_{n}', outdir='')
    r = post(cl, '/fileops/preview', **data); assert r.status_code == 200 and 'C/07_EXAGOGES/files/1_1.pdf' in r.text and 'Δεν έχει αλλάξει τίποτα' in r.text
    assert not os.path.exists(os.path.join(root, 'C', '07_EXAGOGES', 'files'))
    r = post(cl, '/fileops/apply', **data); assert r.status_code == 303 and 'Δημιουργ' in __import__('urllib.parse').parse.unquote(r.headers['location'])
    o = os.path.join(root, 'C', '07_EXAGOGES', 'files')
    assert len(PdfReader(os.path.join(o, '1_1.pdf')).pages) == 2 and len(PdfReader(os.path.join(o, '1_2.pdf')).pages) == 4
    assert len(PdfReader(os.path.join(root, 'C', '04_TRAPEZA', 'orig', '1.pdf')).pages) == 6        # η πηγή δεν άλλαξε
    again = post(cl, '/fileops/preview', **data).text; assert 'Υπάρχει ήδη' in again and 'Τίποτα δεν είναι έτοιμο' in again           # καμία αντικατάσταση
    assert post(cl, '/fileops/apply', **data).status_code == 409
    c = sqlite3.connect(os.environ['THILEK_DB']); assert c.execute("SELECT count(*) FROM fileops WHERE op='split'").fetchone()[0] == 2


def test_out_dir_must_be_exagoges(cl):
    setup(cl)
    r = post(cl, '/fileops/preview', tab='split', dir='C/04_TRAPEZA/orig', src='C/04_TRAPEZA/orig/1.pdf', spec='1', pat='{name}', outdir='C/04_TRAPEZA/orig')
    assert r.status_code == 422 and '07_EXAGOGES' in r.text
    r = post(cl, '/fileops/preview', tab='split', dir='C/04_TRAPEZA/orig', src='C/04_TRAPEZA/orig/1.pdf', spec='1', pat='{name}', outdir='C/07_EXAGOGES/../x')
    assert r.status_code in (400, 422)


def test_paths_cannot_escape(cl):
    setup(cl)
    for s in ('../etc/passwd', 'C/../../x.pdf', '/etc/passwd'):
        r = post(cl, '/fileops/preview', tab='split', dir='C', src=s, spec='1', pat='{name}', outdir='')
        assert r.status_code in (400, 404, 422)


def test_merge_natural_order_and_outline(cl):
    root = setup(cl)
    data = dict(tab='merge', dir='C/work', outname='all', order='name', outdir='C/07_EXAGOGES/m')
    data['src'] = [f'C/work/{n}' for n in ('a10.pdf', 'a1.pdf', 'a2.pdf')]
    r = cl.post('/fileops/preview', data=data, auth=A, headers=H); t = r.text
    assert t.index('a1.pdf') < t.index('a2.pdf') < t.index('a10.pdf') and 'C/07_EXAGOGES/m/all.pdf' in t
    assert cl.post('/fileops/apply', data=data, auth=A, headers=H, follow_redirects=False).status_code == 303
    rd = PdfReader(os.path.join(root, 'C', '07_EXAGOGES', 'm', 'all.pdf')); assert len(rd.pages) == 3 and [o.title for o in rd.outline] == ['a1.pdf', 'a2.pdf', 'a10.pdf']


def test_rename_copy_works_on_protected(cl):
    root = setup(cl)
    data = dict(tab='rename', dir='C/04_TRAPEZA/orig', mode='copy', find='', repl='', tpl='θέμα_{n}_{name}', start='1', width='3', outdir='', src=['C/04_TRAPEZA/orig/1.pdf', 'C/04_TRAPEZA/orig/2.pdf'])
    t = cl.post('/fileops/preview', data=data, auth=A, headers=H).text; assert 'θέμα_001_1.pdf' in t and 'θέμα_002_2.pdf' in t
    assert cl.post('/fileops/apply', data=data, auth=A, headers=H, follow_redirects=False).status_code == 303
    o = os.path.join(root, 'C', '07_EXAGOGES', 'files'); assert sorted(os.listdir(o)) == ['θέμα_001_1.pdf', 'θέμα_002_2.pdf']
    assert os.path.exists(os.path.join(root, 'C', '04_TRAPEZA', 'orig', '1.pdf'))


def test_rename_inplace_blocks_protected_and_renames_free(cl):
    root = setup(cl)
    data = dict(tab='rename', dir='C/04_TRAPEZA/orig', mode='inplace', find='1', repl='X', tpl='{name}', start='1', width='0', src=['C/04_TRAPEZA/orig/1.pdf'])
    t = cl.post('/fileops/preview', data=data, auth=A, headers=H).text; assert '🔒' in t and 'Τίποτα δεν είναι έτοιμο' in t
    assert cl.post('/fileops/apply', data=data, auth=A, headers=H, follow_redirects=False).status_code == 409
    assert os.path.exists(os.path.join(root, 'C', '04_TRAPEZA', 'orig', '1.pdf'))
    d2 = dict(tab='rename', dir='C/work', mode='inplace', find='a', repl='b', tpl='{name}', start='1', width='0', src=['C/work/a1.pdf', 'C/work/a2.pdf'])
    assert cl.post('/fileops/apply', data=d2, auth=A, headers=H, follow_redirects=False).status_code == 303
    assert sorted(os.listdir(os.path.join(root, 'C', 'work'))) == ['a10.pdf', 'b1.pdf', 'b2.pdf']


def test_rename_conflicts_and_regex(cl):
    root = setup(cl)
    d = dict(tab='rename', dir='C/work', mode='inplace', find='a(\\d)', repl='z', rx='1', tpl='{name}', start='1', width='0', src=['C/work/a1.pdf', 'C/work/a2.pdf'])
    t = cl.post('/fileops/preview', data=d, auth=A, headers=H).text; assert t.count('Διπλό όνομα') == 1        # και τα δύο γίνονται z.pdf
    bad = dict(d, find='(', rx='1'); assert cl.post('/fileops/preview', data=bad, auth=A, headers=H).status_code == 422
    assert cl.post('/fileops/preview', data=dict(d, tpl='{name.x}'), auth=A, headers=H).status_code == 422
    assert cl.post('/fileops/preview', data=dict(d, find='a', repl='../', rx=''), auth=A, headers=H).status_code == 200   # το «/» απορρίπτεται ως όνομα
    assert 'η ταυτίζεται' not in t


def test_requires_origin_and_page(cl):
    setup(cl)
    assert cl.get('/fileops', auth=A).status_code == 200 and 'Εργαλεία αρχείων' in cl.get('/fileops?tab=merge&dir=C/work', auth=A).text
    assert cl.post('/fileops/apply', data={'tab': 'merge'}, auth=A).status_code == 403
    assert cl.get('/fileops').status_code == 401
