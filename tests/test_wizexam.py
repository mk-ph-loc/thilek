"""0.23.0: διαγώνισμα/τεστ Word με πρότυπο σχολείου (πεδία, σημείο ερωτημάτων, ομαδοποίηση, εκδόσεις, ανέβασμα προτύπων)."""
import io, os, pathlib, sqlite3, zipfile
from docx import Document
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_wizard import seed, new, post
from app import wizexam as X


def texts(data):
    d = Document(io.BytesIO(data)); out = [p.text for p in X.paragraphs(d)]; return d, '\n'.join(out)


def recipe(cl, **kw):
    if not sqlite3.connect(os.environ['THILEK_DB']).execute('SELECT 1 FROM question').fetchone(): seed()
    rid = new(cl, 'Διαγ'); post(cl, rid, 1, action='add', qids=['1', '2', '3', '4']); post(cl, rid, 4, format='exam', go='next')
    base = dict(title='Διαγώνισμα Α΄ τετραμήνου', x_school='1ο ΕΠΑΛ Δοκιμής', x_course='Ηλεκτροτεχνία', x_class='Β1', x_date='12/12', x_dur='2 ώρες', x_notes='Επιτρέπεται υπολογιστής.', x_mode='text', x_grp='item', x_ver='student', x_tpl='default', preview='1', go='next')
    base.update(kw); post(cl, rid, 5, **base); return rid


def gen(cl, rid): return cl.post(f'/wizard/{rid}/generate', auth=A, headers=H)


def upload(cl, data, name='sxoleio.docx'):
    return cl.post('/wizard-templates/upload', files={'file': (name, data, 'application/octet-stream')}, auth=A, headers=H, follow_redirects=False)


def school_template(split=True, marker=True, strip_styles=False):
    d = Document(); d.add_paragraph().add_run('ΕΠΑΛ ΔΟΚΙΜΗΣ').bold = True
    p = d.add_paragraph()
    if split: p.add_run('Τίτλος: {{ΤΙ').bold = True; p.add_run('ΤΛΟΣ}}')                         # πεδίο σπασμένο σε runs
    else: p.add_run('Τίτλος: {{ΤΙΤΛΟΣ}}')
    t = d.add_table(rows=1, cols=2); t.cell(0, 0).text = 'Τάξη {{ΤΑΞΗ}}'; t.cell(0, 1).text = 'Σύνολο {{ΜΟΝΑΔΕΣ}}'
    d.sections[0].header.paragraphs[0].text = 'Κεφαλίδα {{ΣΧΟΛΕΙΟ}}'
    if marker: d.add_paragraph('{{ΕΡΩΤΗΜΑΤΑ}}')
    d.add_paragraph('ΤΕΛΟΣ ΘΕΜΑΤΩΝ — καλή επιτυχία')
    if strip_styles:
        for n in ('Heading 1', 'Heading 2', 'Heading 3', 'Heading 4', 'List Bullet', 'Table Grid', 'Quote'):
            try: d.styles.element.remove(d.styles[n].element)
            except KeyError: pass
    b = io.BytesIO(); d.save(b); return b.getvalue()


def test_default_template_fills_fields_and_questions(cl):
    rid = recipe(cl); r = gen(cl, rid); assert r.status_code == 200 and 'wordprocessingml' in r.headers['content-type']
    d, t = texts(r.content); assert '{{' not in t and '1ο ΕΠΑΛ Δοκιμής' in t and 'Διαγώνισμα Α΄ τετραμήνου' in t and 'Β1' in t and 'Επιτρέπεται υπολογιστής.' in t and 'Σύνολο μονάδων: 25' in t
    assert 'ΘΕΜΑ Α (25 μονάδες)' in t and 'Α1. (5 μον.)' in t and 'ερώτημα 1' in t and 'Α4. (10 μον.)' in t and 'Μαθητή' in t


def test_custom_template_split_runs_table_header_marker_position(cl):
    ok = upload(cl, school_template()); assert ok.status_code == 303 and 'bad=0' in ok.headers['location'] and 'sxoleio.docx' in X.list_templates()
    rid = recipe(cl, x_tpl='sxoleio.docx'); d, t = texts(gen(cl, rid).content)
    assert 'Τίτλος: Διαγώνισμα Α΄ τετραμήνου' in t and 'Τάξη Β1' in t and 'Σύνολο 25' in t and 'Κεφαλίδα 1ο ΕΠΑΛ Δοκιμής' in t and '{{' not in t
    ls = [x for x in t.split('\n')]; i_q = next(i for i, x in enumerate(ls) if x.startswith('ΘΕΜΑ Α')); i_end = next(i for i, x in enumerate(ls) if x.startswith('ΤΕΛΟΣ')); i_head = next(i for i, x in enumerate(ls) if x.startswith('Τίτλος'))
    assert i_head < i_q < i_end                                                       # τα ερωτήματα μπαίνουν ακριβώς στη θέση του πεδίου
    assert not any('{{ΕΡΩΤΗΜΑΤΑ}}' in x for x in ls)


def test_template_without_marker_appends_and_warns_without_styles_crash(cl):
    r = upload(cl, school_template(marker=False, strip_styles=True), 'xwris.docx'); assert 'bad=1' in r.headers['location'] and 'ΠΡΟΣΟΧΗ' in __import__('urllib.parse').parse.unquote(r.headers['location'])
    rid = recipe(cl, x_tpl='xwris.docx'); d, t = texts(gen(cl, rid).content)
    assert t.index('ΤΕΛΟΣ ΘΕΜΑΤΩΝ') < t.index('ΘΕΜΑ Α') and 'ερώτημα 1' in t


def test_grouping_modes_and_adjusted_points(cl):
    rid = recipe(cl, x_grp='none'); post(cl, rid, 3, action='x', pk=['1|2.1', '1|2.4'], pv=['7,5', '2.5'])
    d, t = texts(gen(cl, rid).content); assert 'ΘΕΜΑ' not in t.replace('ΤΕΛΟΣ ΘΕΜΑΤΩΝ', '') and '1. (7.5 μον.)' in t and '4. (2.5 μον.)' in t and 'Σύνολο μονάδων: 20' in t
    rid = recipe(cl, x_grp='qtype'); d, t = texts(gen(cl, rid).content); assert 'ΘΕΜΑ Α (25 μονάδες)' in t and 'ΘΕΜΑ Β' not in t       # όλα τύπου problem


def test_versions_both_zip_and_teacher_warning(cl):
    rid = recipe(cl, x_ver='both'); r = gen(cl, rid); z = zipfile.ZipFile(io.BytesIO(r.content)); n = z.namelist()
    assert r.headers['content-type'] == 'application/zip' and len(n) == 2 and any('kathigiti' in x for x in n) and any('mathiti' in x for x in n)
    assert 'Καθηγητή' in texts(z.read([x for x in n if 'kathigiti' in x][0]))[1] and 'Μαθητή' in texts(z.read([x for x in n if 'mathiti' in x][0]))[1]
    assert 'δεν έχουν εικόνα λύσης ΙΕΠ' in cl.get(f'/wizard/{rid}/6', auth=A).text


def test_missing_template_and_bad_names_are_explained(cl):
    rid = recipe(cl, x_tpl='default'); sub = lambda t: sqlite3.connect(os.environ['THILEK_DB'])
    c = sqlite3.connect(os.environ['THILEK_DB']); import json
    st = json.loads(c.execute('SELECT state FROM wizard_recipe WHERE id=?', (rid,)).fetchone()[0]); st['x_tpl'] = 'ghost.docx'
    c.execute('UPDATE wizard_recipe SET state=? WHERE id=?', (json.dumps(st), rid)); c.commit()
    assert 'δεν υπάρχει πια' in cl.get(f'/wizard/{rid}/6', auth=A).text and gen(cl, rid).status_code == 422
    post(cl, rid, 5, title='x', x_tpl='../../etc/passwd', go='next'); st2 = json.loads(c.execute('SELECT state FROM wizard_recipe WHERE id=?', (rid,)).fetchone()[0]); assert st2['x_tpl'] == 'ghost.docx'


def test_upload_validation_delete_and_path_safety(cl):
    assert 'bad=1' in upload(cl, b'not a docx').headers['location']
    assert 'bad=1' in upload(cl, b'x' * (X.MAX_TPL + 10)).headers['location']
    assert 'bad=1' in cl.post('/wizard-templates/upload', data={}, auth=A, headers=H, follow_redirects=False).headers['location']
    assert upload(cl, school_template(), '../../evil name.docx').status_code == 303
    names = X.list_templates(); assert len(names) == 1 and '/' not in names[0] and names[0].endswith('.docx') and not (pathlib.Path(os.environ['THILEK_ROOT']) / 'evil name.docx').exists()
    assert cl.get(f'/wizard-templates/file/{names[0]}', auth=A).status_code == 200 and cl.get('/wizard-templates/file/..%2f..%2fx.docx', auth=A).status_code in (404, 400)
    assert cl.get('/wizard-templates/sample.docx', auth=A).status_code == 200 and 'Μάθημα' in cl.get('/wizard-templates', auth=A).text
    assert cl.post('/wizard-templates/upload', files={'file': ('a.docx', school_template(), 'x')}, auth=A, headers={'origin': 'http://evil.example', 'host': 'testserver'}).status_code == 403
    assert cl.post(f'/wizard-templates/{names[0]}/delete', auth=A, headers=H, follow_redirects=False).status_code == 303 and X.list_templates() == []
    assert cl.get('/wizard-templates').status_code == 401 and cl.get('/wizard-templates/sample.docx').status_code == 401


def test_step5_fields_and_state_validation(cl):
    from app import wizmodel as M; import json
    st = M.load_state(json.dumps({'x_ver': 'zzz', 'x_grp': 'zzz', 'x_mode': 'zzz', 'x_school': 'Σχολείο'})); assert st['x_ver'] == 'student' and st['x_grp'] == 'item' and st['x_mode'] == 'image' and st['x_school'] == 'Σχολείο'
    rid = recipe(cl); t = cl.get(f'/wizard/{rid}/5', auth=A).text; assert 'name=x_tpl' in t and 'value=\'1ο ΕΠΑΛ Δοκιμής\'' in t and '/wizard-templates' in t
    assert 'Προεπισκόπηση (σώμα ερωτημάτων' in cl.get(f'/wizard/{rid}/6', auth=A).text and 'ΘΕΜΑ Α' in cl.get(f'/wizard/{rid}/6', auth=A).text


def test_image_mode_embeds_crops_in_template_and_teacher_solution(cl, monkeypatch):
    from PIL import Image; from app import mddoc
    b = io.BytesIO(); Image.new('RGB', (200, 80), 'white').save(b, 'JPEG'); jpg = b.getvalue()
    monkeypatch.setattr(mddoc, 'crop_bytes', lambda c, qid, sol=0, dpi=110: (jpg, 'geo')); monkeypatch.setattr(mddoc.crops, 'width_pt', lambda g: 200)
    rid = recipe(cl, x_mode='image', x_ver='teacher'); c = sqlite3.connect(os.environ['THILEK_DB'])
    c.execute("UPDATE question SET geo='g', sol_geo='s' WHERE id IN (1,2)"); c.commit()
    assert upload(cl, school_template()).status_code == 303
    post(cl, rid, 5, title='Εικόνες', x_tpl='sxoleio.docx', x_mode='image', x_ver='teacher', x_grp='item', go='next')
    r = gen(cl, rid); assert r.status_code == 200, r.text[:300]
    d, t = texts(r.content); assert len(d.inline_shapes) == 4 and 'Λύση ΙΕΠ' in t and '{{' not in t       # 2 εκφωνήσεις + 2 λύσεις
