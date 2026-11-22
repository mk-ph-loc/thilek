"""0.22.0: ένα-ένα εξαγωγή (σελίδα ανά θέμα/ερώτημα + index + data.json + zip) και δημοσίευση με κωδικό μαθητή."""
import base64, io, json, os, pathlib, sqlite3, zipfile
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_qsol import sample
from tests.test_wizard import seed, new, post


def with_solutions(cl):
    seed(); root = pathlib.Path(os.environ['THILEK_ROOT']); o = root / 'C' / '04_TRAPEZA' / 'orig'; o.mkdir(parents=True, exist_ok=True)
    (o / '1.2-1.md').write_text(sample(item='1', sub='2.1'), encoding='utf-8'); (o / '1.2-2.md').write_text(sample(item='1', sub='2.2'), encoding='utf-8')
    assert cl.post('/lyseis/scan', auth=A, headers=H, follow_redirects=False).status_code in (200, 303)


def recipe(cl, fmt='reveal', gran='item', store='download', qids=('1', '2', '3'), helpmd='1', frag=''):
    rid = new(cl); post(cl, rid, 1, action='add', qids=list(qids)); post(cl, rid, 2, mode='each', gran=gran, order='item', unsel='omit', go='next')
    post(cl, rid, 4, format=fmt, go='next'); post(cl, rid, 5, title='Σειρά Ι', store=store, helpmd=helpmd, frag=frag, go='next'); return rid


def bauth(pw, user='mathitis'): return {'Authorization': 'Basic ' + base64.b64encode(f'{user}:{pw}'.encode()).decode()}


def test_each_by_item_zip_has_pages_index_data(cl):
    with_solutions(cl); rid = recipe(cl)
    r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H); assert r.headers['content-type'] == 'application/zip'
    z = zipfile.ZipFile(io.BytesIO(r.content)); n = set(z.namelist())
    assert {'index.html', 'data.json', 'README.txt', 't1.html'} <= n
    d = json.loads(z.read('data.json')); assert len(d['pages']) == 1 and d['total'] == 10 and d['skipped'] == ['1/2.3'] and 'keys' not in d['pages'][0]
    ix = z.read('index.html').decode('utf-8'); assert 't1.html' in ix and 'Θέμα 1' in ix and '1/2.3' in ix and '10 μον.' in ix
    assert b'reveal' in z.read('t1.html').lower() 
    assert 'reveal-help.md' in n and b'Reveal.js' in z.read('reveal-help.md')


def test_each_by_question_and_student_format(cl):
    with_solutions(cl); rid = recipe(cl, fmt='student', gran='question')
    z = zipfile.ZipFile(io.BytesIO(cl.post(f'/wizard/{rid}/generate', auth=A, headers=H).content)); n = set(z.namelist())
    assert {'q1_2-1.html', 'q1_2-2.html', 'index.html', 'data.json'} <= n and 't1.html' not in n


def test_each_without_any_solution_is_explained(cl):
    seed(); rid = recipe(cl); r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H); assert r.status_code == 422 and 'λύσης' in r.text


def test_checks_warn_each_and_publish_on_wrong_format(cl):
    with_solutions(cl); rid = recipe(cl, fmt='excel', store='publish')
    t = cl.get(f'/wizard/{rid}/6', auth=A).text; assert 'ένα-ένα» ισχύει μόνο' in t and 'δεν μπορεί να δημοσιευτεί' in t
    assert cl.post(f'/wizard/{rid}/generate', auth=A, headers=H).status_code == 422


def test_publish_and_student_access(cl):
    with_solutions(cl); rid = recipe(cl, store='publish')
    assert cl.get('/p/').status_code == 401 and cl.get('/p/', headers=bauth('λάθος')).status_code == 401
    r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H); assert r.status_code == 200 and 'Δημοσιεύτηκε' in r.text and 'Δεν υπάρχει κωδικός μαθητή' in r.text
    slug = [s for s in os.listdir(pathlib.Path(os.environ['THILEK_ROOT']) / '_publish') if not s.startswith('.')][0]
    assert cl.get(f'/p/{slug}/', headers=bauth('x')).status_code == 401                       # χωρίς κωδικό μαθητή δεν μπαίνει κανείς εκτός διαχειριστή
    assert cl.get(f'/p/{slug}/', auth=A).status_code == 200
    assert cl.post('/publish/password', data={'pw': 'ab'}, auth=A, headers=H).status_code == 422
    assert cl.post('/publish/password', data={'pw': 'mathitis7'}, auth=A, headers=H, follow_redirects=False).status_code == 303
    assert cl.get('/p/', headers=bauth('mathitis7')).status_code == 200 and slug in cl.get('/p/', headers=bauth('mathitis7')).text
    p = cl.get(f'/p/{slug}/t1.html', headers=bauth('mathitis7')); assert p.status_code == 200 and 'sandbox' in p.headers['content-security-policy'] and p.headers['x-content-type-options'] == 'nosniff'
    assert cl.get(f'/p/{slug}/', headers=bauth('mathitis7')).status_code == 200 and cl.get(f'/p/{slug}/data.json', headers=bauth('mathitis7')).status_code == 200
    # ο κωδικός μαθητή δεν ανοίγει τίποτα άλλο
    assert cl.get('/wizard', headers=bauth('mathitis7')).status_code == 401 and cl.get('/publish', headers=bauth('mathitis7')).status_code == 401 and cl.get('/files/x', headers=bauth('mathitis7')).status_code in (401, 404)
    h = sqlite3.connect(os.environ['THILEK_DB']).execute("SELECT v FROM setting WHERE k='student_pw'").fetchone()[0]; assert 'mathitis7' not in h and '$' in h


def test_publish_path_safety_and_delete(cl):
    from app import publish
    with_solutions(cl); publish.set_pw('abcd1')
    s = publish.save_site('Δοκιμή', {'index.html': b'<p>x</p>', 'a.json': b'{}'})
    for bad in ('meta.json', '../meta.json', '..%2Fmeta.json', 'x/y.html', '.hidden.html', 'evil.py', 'a.exe'):
        assert cl.get(f'/p/{s}/{bad}', headers=bauth('abcd1')).status_code in (404, 401), bad
    assert cl.get('/p/..%2f/index.html', headers=bauth('abcd1')).status_code in (404, 307, 308)
    try: publish.save_site('x', {'../x.html': b''}); assert False
    except Exception as e: assert getattr(e, 'status_code', 0) == 422
    try: publish.save_site('x', {'a.py': b''}); assert False
    except Exception as e: assert getattr(e, 'status_code', 0) == 422
    assert cl.post(f'/publish/{s}/delete', auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
    assert cl.post(f'/publish/{s}/delete', auth=A, headers=H, follow_redirects=False).status_code == 303 and cl.get(f'/p/{s}/', auth=A).status_code == 404
    assert cl.post('/publish/..%2fx/delete', auth=A, headers=H).status_code in (404, 405)


def test_publish_single_html_and_same_title_unique(cl):
    with_solutions(cl); rid = new(cl); post(cl, rid, 1, action='add', qids=['1', '2']); post(cl, rid, 4, format='htmldoc', go='next'); post(cl, rid, 5, title='Ίδιος', store='publish', go='next')
    for _ in range(2): assert 'Δημοσιεύτηκε' in cl.post(f'/wizard/{rid}/generate', auth=A, headers=H).text
    assert len(os.listdir(pathlib.Path(os.environ['THILEK_ROOT']) / '_publish')) == 2
    t = cl.get('/publish', auth=A).text; assert 'Ίδιος' in t and 'Κατάργηση' in t and 'Δεν έχει οριστεί κωδικός μαθητή' in t


def test_publish_and_wizard_in_menu_and_load_state(cl):
    from app import wizmodel as M
    assert 'href=\'/publish\'' in cl.get('/review', auth=A).text
    st = M.load_state(json.dumps({'gran': 'zzz', 'store': 'zzz'})); assert st['gran'] == 'item' and st['store'] == 'download'
    assert M.load_state(json.dumps({'gran': 'question', 'store': 'publish'}))['store'] == 'publish'
