"""0.27.0: ανάγνωση Word του ΙΕΠ (κείμενο, εξισώσεις, εικόνες), σύγκριση με το PDF, ένδειξη W και φίλτρο."""
import io, json, os, pathlib, sqlite3, zipfile
import docx
from lxml import etree
from PIL import Image
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_wizard import seed
from app import wordsrc, omml

MNS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'


def make(path, lines, eq=None, img=False, table=None):
    d = docx.Document()
    for ln in lines: d.add_paragraph(ln)
    if eq:
        p = d.add_paragraph('Ισχύει ')
        p._p.append(etree.fromstring(f'<w xmlns:m="{MNS}">' + omml.latex_to_omml(eq) + '</w>')[0])
    if table:
        t = d.add_table(rows=len(table), cols=len(table[0]))
        for i, r in enumerate(table):
            for j, v in enumerate(r): t.cell(i, j).text = v
    if img:
        b = io.BytesIO(); Image.new('RGB', (8, 8), 'red').save(b, 'PNG'); b.seek(0); d.add_picture(b)
    d.save(path); return path


GOOD = ['ΘΕΜΑ 2', '2.1 Να υπολογίσετε το ρεύμα. (Μονάδες 5)', '2.2 Να υπολογίσετε την τάση. (Μονάδες 5)', '2.3 Να βρείτε την ισχύ. (Μονάδες 5)', '2.4 Να σχεδιάσετε το κύκλωμα. (Μονάδες 10)']


def orig(cl):
    p = pathlib.Path(os.environ['THILEK_ROOT']) / 'C' / '04_TRAPEZA' / 'orig'; p.mkdir(parents=True, exist_ok=True); return p


def con():
    c = sqlite3.connect(os.environ['THILEK_DB']); c.row_factory = sqlite3.Row; return c


def run_scan(cl):
    r = cl.post('/word/scan', auth=A, headers=H, follow_redirects=False); assert r.status_code == 303; return r


def test_read_docx_text_tables_equations_images(tmp_path):
    p = make(tmp_path / 'a.docx', ['Πρώτη παράγραφος', 'Δεύτερη'], eq='R_{1}+R_{2}', img=True, table=[['α', 'β'], ['γ', 'δ']])
    r = wordsrc.read_docx(p); t = r['text']
    assert 'Πρώτη παράγραφος' in t and 'α | β' in t and 'γ | δ' in t and r['n_eq'] == 1 and '$' in t and '[εικόνα 1]' in t
    assert len(r['images']) == 1 and r['images'][0][0] == '1.png' and r['images'][0][1][:4] == b'\x89PNG'
    try:
        from app.ommllatex import omml_to_latex  # noqa: F401
        assert 'R_{1}' in t.replace(' ', '') or 'R_1' in t.replace(' ', '')
    except ImportError: pass


def test_read_docx_rejects_bad_files(tmp_path):
    (tmp_path / 'x.docx').write_bytes(b'not a zip')
    for name, files, msg in (('nozip', None, 'έγκυρο'), ('nodoc', {'a.txt': b'x'}, 'document.xml'), ('doctype', {'word/document.xml': b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'}, 'DOCTYPE'),
                             ('broken', {'word/document.xml': b'<w:document'}, 'XML')):
        p = tmp_path / (name + '.docx')
        if files is None: p.write_bytes(b'not a zip')
        else:
            with zipfile.ZipFile(p, 'w') as z:
                for k, v in files.items(): z.writestr(k, v)
        try: wordsrc.read_docx(p); assert False, name
        except ValueError as ex: assert msg in str(ex), (name, str(ex))


def test_images_outside_package_and_svg_are_skipped(tmp_path):
    p = make(tmp_path / 'i.docx', ['x'], img=True)
    z = zipfile.ZipFile(p); data = {n: z.read(n) for n in z.namelist()}; z.close()
    rels = data['word/_rels/document.xml.rels'].decode().replace('media/image1.png', '../../etc/passwd'); data['word/_rels/document.xml.rels'] = rels.encode()
    q = tmp_path / 'j.docx'
    with zipfile.ZipFile(q, 'w') as z:
        for k, v in data.items(): z.writestr(k, v)
    r = wordsrc.read_docx(q); assert r['images'] == [] and any('παραλείφθηκε' in w for w in r['warn'])


def test_scan_ok_warn_solution_and_errors(cl):
    seed(4); o = orig(cl); make(o / '1.docx', GOOD, img=True); make(o / '1_SOLUTION.docx', GOOD)
    make(o / '2.docx', GOOD); (o / '3.docx').write_bytes(b'junk'); (o / 'notes.docx').write_bytes(b'x')
    run_scan(cl); c = con(); rows = {(r['item_id'], r['kind']): r for r in c.execute('SELECT * FROM wordsrc')}
    assert set(rows) == {('1', 'statement'), ('1', 'solution')} and rows[('1', 'statement')]['status'] == 'ok' and rows[('1', 'statement')]['n_q'] == 4 and rows[('1', 'statement')]['pts'] == 25
    assert rows[('1', 'statement')]['n_img'] == 1 and (pathlib.Path(os.environ['THILEK_ROOT']) / json.loads(rows[('1', 'statement')]['images'])[0]).is_file()
    # αλλαγμένο Word: λείπει ερώτημα και διαφορετικές μονάδες
    make(o / '1.docx', GOOD[:3] + ['2.3 Να βρείτε την ισχύ. (Μονάδες 7)']); run_scan(cl)
    r = con().execute("SELECT * FROM wordsrc WHERE item_id='1' AND kind='statement'").fetchone(); w = json.loads(r['warn'])
    assert r['status'] == 'warn' and any('2.4' in x and 'δεν βρέθηκαν' in x for x in w) and any('μονάδες 2.3' in x and 'Word 7' in x for x in w) and any('πλήθος' in x for x in w)
    r = con().execute("SELECT status FROM wordsrc WHERE item_id='1' AND kind='solution'").fetchone(); assert r[0] == 'ok'


def test_scan_works_with_plain_tuple_connection(cl):
    """Όπως στο thilek-rebuild: σύνδεση χωρίς row_factory (παλιότερα: «tuple indices must be integers»)."""
    seed(4); o = orig(cl); make(o / '1.docx', GOOD); make(o / '1_SOLUTION.docx', GOOD)
    c = sqlite3.connect(os.environ['THILEK_DB']); assert c.row_factory is None
    res = wordsrc.scan(c, os.environ['THILEK_ROOT'], 'C'); assert res['files'] == 2 and res['errors'] == 0 and c.row_factory is None
    assert c.execute('SELECT count(*) FROM wordsrc').fetchone()[0] == 2; c.close()


def test_word_with_unknown_item_and_bad_name_reported_not_stored(cl):
    seed(4); o = orig(cl); make(o / '999.docx', GOOD); (o / 'x.docx').write_bytes(b'x')
    res = wordsrc.scan(con(), os.environ['THILEK_ROOT']); assert res['errors'] == 1 and any('999' in m for m in res['messages']) and any('όνομα εκτός μορφής' in m for m in res['messages'])
    assert con().execute('SELECT count(*) FROM wordsrc').fetchone()[0] == 0


def test_pages_filter_columns_and_security(cl):
    seed(4); o = orig(cl); make(o / '1.docx', GOOD, eq='x^{2}')
    assert 'Καμία εγγραφή' in cl.get('/word', auth=A).text; run_scan(cl)
    t = cl.get('/word', auth=A).text; assert '/word/1' in t and '4 ερωτ.' in t and '1 εξισ.' in t
    d = cl.get('/word/1', auth=A).text; assert 'Εκφώνηση' in d and 'Μονάδες PDF' in d and 'ΘΕΜΑ 2' in d
    assert cl.get('/word/777', auth=A).status_code == 404 and cl.get('/word').status_code == 401 and cl.get('/word/1').status_code == 401
    assert cl.post('/word/scan', auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
    assert 'W' in cl.get('/review', auth=A).text.split('<table')[1] and "href=/word/1" in cl.get('/review', auth=A).text
    b = cl.get('/browse', auth=A).text; assert "href='/word/1'" in b
    from app import library
    c = con(); f = lambda w: {r['item_id'] for r in library.select_questions(c, {'qtype': [], 'word': w})}
    assert f('1') == {'1'} and f('0') == set() and f('') == {'1'}
    c.execute("INSERT INTO item(id,course_code,source,solution_status) VALUES('2','C','TTDD','ok')"); c.execute("INSERT INTO question(item_id,code,points,text,qtype) VALUES('2','1.1',5,'x','problem')"); c.commit()
    assert f('0') == {'2'} and f('1') == {'1'}
    assert 'name=word' in cl.get('/browse', auth=A).text


def test_wizard_word_criterion_and_schema(cl):
    from tests.test_wizard import new
    seed(2); rid = new(cl); assert 'name=word' in cl.get(f'/wizard/{rid}/1', auth=A).text
    assert con().execute("SELECT 1 FROM sqlite_master WHERE name='wordsrc'").fetchone()
    from app import migrations as m; c = sqlite3.connect(':memory:'); m._v6(c); m._v6(c); assert c.execute("SELECT 1 FROM sqlite_master WHERE name='wordsrc'").fetchone()
