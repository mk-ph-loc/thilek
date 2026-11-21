"""0.24.0: Moodle (κατηγορίες, ετικέτες), Google Form script, H5P JSON από τον wizard."""
import io, json, os, pathlib, re, sqlite3, zipfile, xml.etree.ElementTree as ET
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_wizard import new, post
from tests.test_publish import with_solutions


def recipe(cl, fmt, **kw):
    with_solutions(cl); im = pathlib.Path(os.environ['THILEK_ROOT']) / 'C' / '04_TRAPEZA' / 'orig' / 'images'; im.mkdir(exist_ok=True); (im / 'ohm1.png').write_bytes(b'\x89PNG\r\n')
    rid = new(cl, 'Q'); post(cl, rid, 1, action='add', qids=['1', '2']); post(cl, rid, 4, format=fmt, go='next')
    d = dict(title='Κουίζ Ohm', m_cat='single', m_tags='1', g_name='required', g_img='default', go='next'); d.update(kw); post(cl, rid, 5, **d); return rid


def gen(cl, rid): return cl.post(f'/wizard/{rid}/generate', auth=A, headers=H)


def cats(xml): return [q.find('category/text').text for q in ET.fromstring(xml).findall('question') if q.get('type') == 'category']


def test_moodle_categories_and_tags(cl):
    rid = recipe(cl, 'moodle'); r = gen(cl, rid); assert r.status_code == 200 and 'xml' in r.headers['content-type']
    root = ET.fromstring(r.content); qs = [q for q in root.findall('question') if q.get('type') != 'category']
    assert cats(r.content) == ['$course$/top/Κουίζ Ohm'] and len(qs) >= 4
    tg = [t.find('text').text for t in qs[0].findall('tags/tag')]; assert 'θέμα-1' in tg and 'ερώτημα-2.1' in tg and 'mcq' in tg
    post(cl, rid, 5, title='Κουίζ Ohm', m_cat='item', go='next'); r = gen(cl, rid)                               # χωρίς m_tags: καθόλου ετικέτες
    assert cats(r.content) == ['$course$/top/Κουίζ Ohm/Θέμα 1'] and b'<tags>' not in r.content
    post(cl, rid, 5, title='Κουίζ Ohm', m_cat='qtype', m_tags='1', go='next'); c = cats(gen(cl, rid).content)
    assert len(c) >= 3 and all(x.startswith('$course$/top/Κουίζ Ohm/') for x in c) and c == sorted(c) and len(set(c)) == len(c)       # μία κατηγορία ανά τύπο, ταξινομημένες


def test_moodle_category_path_is_safe(cl):
    rid = recipe(cl, 'moodle', title='Α/Β'); assert cats(gen(cl, rid).content) == ['$course$/top/Α-Β']


def test_gform_script_zip(cl):
    rid = recipe(cl, 'gform'); r = gen(cl, rid); assert r.headers['content-type'] == 'application/zip'
    z = zipfile.ZipFile(io.BytesIO(r.content)); gs = z.read('create_form.gs').decode('utf-8'); rd = z.read('README.txt').decode('utf-8')
    assert 'FormApp.create(TITLE)' in gs and "var TITLE = \"Κουίζ Ohm\"" in gs and "setTitle('Ονοματεπώνυμο').setRequired(true)" in gs and 'mcq_(form,' in gs and 'text_(form,' in gs
    assert '$' not in gs.split('function createForm')[1].split('function mcq_')[0] and 'Σωστό' in gs                  # τύποι σε Unicode, όχι LaTeX
    assert 'ΧΕΙΡΟΚΙΝΗΤΑ' in gs and 'αριθμός' in rd and 'Ohm' in rd and 'IMAGE_FOLDER_ID' in rd and any(n.startswith('images/') for n in z.namelist())
    for nm, tail in (('optional', 'setRequired(false);\n'), ('none', None)):
        post(cl, rid, 5, title='Κουίζ Ohm', g_name=nm, go='next'); g = zipfile.ZipFile(io.BytesIO(gen(cl, rid).content)).read('create_form.gs').decode('utf-8')
        assert ('Ονοματεπώνυμο' in g) == (nm != 'none') and (nm != 'optional' or "'Ονοματεπώνυμο').setRequired(false)" in g)


def test_gform_images_mode_and_setting_default(cl, monkeypatch):
    from app import wizquiz, settings
    b = b'\xff\xd8jpegbytes'; monkeypatch.setattr(wizquiz, 'crop_bytes', lambda c, qid, sol=0, dpi=130: (b, 'g'))
    rid = recipe(cl, 'gform', g_img='images'); z = zipfile.ZipFile(io.BytesIO(gen(cl, rid).content)); gs = z.read('create_form.gs').decode('utf-8')
    assert 'q1_2.1.jpg' in z.namelist()[0] + ' '.join(z.namelist()) and 'addImage_(form, "q1_2.1.jpg"' in gs and 'Ερώτημα 2.1 — στοιχείο 1' in gs
    post(cl, rid, 5, title='Κουίζ Ohm', g_img='default', go='next'); assert 'q1_2.1.jpg' not in ' '.join(zipfile.ZipFile(io.BytesIO(gen(cl, rid).content)).namelist())     # προεπιλογή ρυθμίσεων: text
    assert cl.post('/settings', data={'gform_images': 'images'}, auth=A, headers=H, follow_redirects=False).status_code == 303 and settings.get('gform_images') == 'images'
    assert 'q1_2.1.jpg' in ' '.join(zipfile.ZipFile(io.BytesIO(gen(cl, rid).content)).namelist())                                               # τώρα η ρύθμιση ισχύει
    assert cl.post('/settings', data={'gform_images': 'zzz'}, auth=A, headers=H, follow_redirects=False).status_code == 303 and settings.get('gform_images') == 'images'


def test_h5p_content_json_and_readme(cl):
    rid = recipe(cl, 'h5p'); r = gen(cl, rid); z = zipfile.ZipFile(io.BytesIO(r.content)); assert {'content.json', 'h5p.json', 'README.txt'} <= set(z.namelist())
    d = json.loads(z.read('content.json')); libs = {q['library'].split()[0] for q in d['questions']}
    assert 'H5P.MultiChoice' in libs and 'H5P.TrueFalse' in libs and 'H5P.Blanks' in libs and d['questions']
    mc = next(q for q in d['questions'] if q['library'].startswith('H5P.MultiChoice')); assert sum(a['correct'] for a in mc['params']['answers']) == 1
    tf = next(q for q in d['questions'] if q['library'].startswith('H5P.TrueFalse')); assert tf['params']['correct'] in ('true', 'false')
    bl = next(q for q in d['questions'] if q['library'].startswith('H5P.Blanks')); assert re.search(r'\*[^*]+\*', bl['params']['questions'][0])
    assert json.loads(z.read('h5p.json'))['mainLibrary'] == 'H5P.QuestionSet' and 'ΔΕΝ είναι έτοιμο αρχείο' in z.read('README.txt').decode('utf-8')


def test_no_quiz_blocks_is_explained_and_warned(cl):
    import os, pathlib
    from tests.test_wizard import seed
    seed(); rid = new(cl, 'N'); post(cl, rid, 1, action='add', qids=['1']); post(cl, rid, 4, format='gform', go='next')
    assert 'δεν έχουν αρχείο λύσης' in cl.get(f'/wizard/{rid}/6', auth=A).text and gen(cl, rid).status_code == 422
    for f in ('moodle', 'h5p'): post(cl, rid, 4, format=f, go='next'); assert gen(cl, rid).status_code == 422


def test_checks_gform_manual_key_warning_and_state(cl):
    from app import wizmodel as M
    rid = recipe(cl, 'gform'); t = cl.get(f'/wizard/{rid}/6', auth=A).text; assert 'δεν παίρνουν αυτόματο κλειδί' in t
    st = M.load_state(json.dumps({'m_cat': 'x', 'g_name': 'x', 'g_img': 'x', 'm_tags': False})); assert (st['m_cat'], st['g_name'], st['g_img'], st['m_tags']) == ('single', 'required', 'default', False)
    assert 'name=m_cat' in cl.get(f'/wizard/{rid}/5', auth=A).text and 'name=g_img' in cl.get(f'/wizard/{rid}/5', auth=A).text and 'gform_images' in cl.get('/settings', auth=A).text
