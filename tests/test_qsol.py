"""Λύσεις εκπαιδευτικού (0.16.x): parser, σάρωση, migrations, rebuild, σελίδες και εξαγωγές. Συνθετικά δείγματα (νόμος του Ohm), όχι κείμενο ΙΕΠ."""
import io, json, os, pathlib, re, sqlite3, sys, xml.etree.ElementTree as ET
from html.parser import HTMLParser
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).parent.parent
SCHEMA = ROOT / 'app' / 'schema.sql'
A = ('admin', 'pw'); H = {'origin': 'http://testserver', 'host': 'testserver'}

QUIZ = r'''```yaml
type: mcq
stem: "Πόσο είναι το ρεύμα $I$;"
options: ["1 A", "2 A", "$\\dfrac{1}{2}\\,\\mathrm{A}$"]
answer: 1
feedback: "$I=V/R$"
points: 2
```

```yaml
type: true_false
stem: "Το ρεύμα είναι 2 A."
answer: true
```

```yaml
type: numeric
stem: "Υπολόγισε το $I$."
answer: 2
tolerance: 0.1
unit: "A"
image: images/ohm1.png
```

```yaml
type: short
stem: "Πώς λέγεται ο νόμος $V=I\\cdot R$;"
answer: ["Ohm", "νόμος του Ohm"]
```

```yaml
type: fill
stem: "Η αντίσταση μετριέται σε ___ και το ρεύμα σε ___."
answer: ["Ω", "A"]
```

```yaml
type: matching
stem: "Αντιστοίχισε μέγεθος και μονάδα."
pairs: [["Τάση", "V"], ["Ρεύμα", "A"], ["Αντίσταση $R$", "$\\Omega$"]]
points: 3
```'''

def sample(item='1', sub='2.1', fm_extra='', quiz=QUIZ, title='Αντιστάτης'):
    stem = f"{item}.{sub.replace('.', '-')}"
    return f'''---
id: "{stem}"
iep_id: {item}
topic: 2
sub: "{sub}"
course: C
points: 15
qtype: problem
tags: [νόμος Ohm]
status: draft
schema: 2
refs:
  statement: {{file: "04_TRAPEZA/orig/{item}.pdf", page: 1}}
{fm_extra}---
## Εκφώνηση
**{sub}** {title} $R=10\\,\\Omega$ σε τάση $V=20\\,\\mathrm{{V}}$. Βρες το $I$ και το $R_{{ολ}}$ (κόστος $5 και $10).

![κύκλωμα](images/ohm1.png)

---
## Ενδεικτική λύση ΙΕΠ
$$I=\\dfrac{{V}}{{R}}=2\\,\\mathrm{{A}}$$

---
## Λύση εκπαιδευτικού
### Στόχος και προαπαιτούμενα
Νόμος του Ohm με $a_1 * b_2 * c$.

### Καθοδήγηση
Ποια σχέση συνδέει τα $V$, $I$, $R$;

```text
---
όχι διαχωριστικό
```

--

### Πλήρης λύση βήμα-βήμα
$$I=\\frac{{V}}{{R}}\\\\ \\{{x\\}}$$

### Quiz
{quiz}

---
## Παραπομπές
- [Εκφώνηση](thilek://statement/{item}#p=1)
- [Θέμα](thilek://item/{item})
- [Βιβλίο σελ. 300](thilek://book/300)
'''

def png(path):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True); Image.new('RGB', (40, 20), (200, 30, 30)).save(path)

def old_schema():
    """Σχήμα 0.15.2: το schema.sql χωρίς τα νέα (qsolution, schema_version)."""
    t = SCHEMA.read_text(encoding='utf-8')
    t = re.sub(r'CREATE TABLE qsolution\(.*?\);[^\n]*\n', '', t, flags=re.S)
    return '\n'.join(l for l in t.split('\n') if 'schema_version' not in l)

def make_db(db, schema_text):
    c = sqlite3.connect(db); c.executescript(schema_text)
    c.execute("INSERT INTO course VALUES('C','Test','B','TTDD')"); c.execute("INSERT INTO book(id,course_code,pdf_offset) VALUES(1,'C',1)")
    c.execute("INSERT INTO item(id,course_code,source,position,iep_yli,solution_status,statement_path) VALUES('1','C','TTDD',2,'4.1 x','ok','C/04_TRAPEZA/orig/1.pdf')")
    c.execute("INSERT INTO question(id,item_id,code,points,text) VALUES(1,'1','2.1',15,'q1')")
    c.execute("INSERT INTO item(id,course_code,source,position,iep_yli,solution_status) VALUES('2','C','TTDD',2,'4.1 y','ok')")
    c.execute("INSERT INTO question(id,item_id,code,points,text) VALUES(2,'2','2.1',10,'q2')")
    c.commit(); c.close()

@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / 't.db'; root = tmp_path / 'data'; orig = root / 'C' / '04_TRAPEZA' / 'orig'; orig.mkdir(parents=True)
    (orig / '1.pdf').write_bytes(b'%PDF'); (orig / '1.2-1.md').write_text(sample(), encoding='utf-8'); png(orig / 'images' / 'ohm1.png')
    make_db(db, old_schema())                     # βάση 0.15.2: η εφαρμογή την αναβαθμίζει μόνη της
    monkeypatch.setenv('THILEK_DB', str(db)); monkeypatch.setenv('THILEK_ROOT', str(root)); monkeypatch.setenv('THILEK_PASSWORD', 'pw')
    monkeypatch.setenv('THILEK_CONFIG', str(tmp_path / 'none.yaml'))
    from app.main import app
    cl = TestClient(app)
    assert cl.post('/lyseis/scan', auth=A, headers=H, follow_redirects=False).status_code == 303
    return cl, tmp_path

# ---------- parser ----------
def test_parse_ok_and_fence_separator():
    from app.qsol import parse
    r = parse(sample(), '1.2-1.md')
    assert r['warnings'] == [] and r['status'] == 'draft' and (r['item_id'], r['qcode']) == ('1', '2.1')
    s = r['sections']; assert '$R=10\\,\\Omega$' in s['statement'] and '$$I=' in s['iep'] and 'thilek://item/1' in s['refs']
    assert [p['title'] for p in s['teacher_parts']] == ['Στόχος και προαπαιτούμενα', 'Καθοδήγηση', 'Πλήρης λύση βήμα-βήμα']
    assert 'όχι διαχωριστικό' in s['teacher_parts'][1]['body'] and '```text\n---' in s['teacher_parts'][1]['body']     # «---» μέσα σε code fence δεν χωρίζει
    q = r['quiz']; assert [x['type'] for x in q] == ['mcq', 'true_false', 'numeric', 'short', 'fill', 'matching'] and all(not x['err'] for x in q)
    assert q[0]['answer'] == 1 and q[1]['answer'] is True and q[2]['tolerance'] == 0.1 and q[3]['answer'] == ['Ohm', 'νόμος του Ohm'] and len(q[5]['pairs']) == 3

def test_parse_bad_yaml_wrong_id_and_quiz():
    from app.qsol import parse
    r = parse(sample().replace('topic: 2', 'topic: [2'), '1.2-1.md')
    assert any('σφάλμα YAML' in w for w in r['warnings']) and r['status'] == 'draft' and r['sections']['statement']
    r = parse(sample(item='1', sub='2.1'), '9.2-2.md')
    assert any('≠ όνομα αρχείου' in w for w in r['warnings']) and any('sub «2.1»' in w for w in r['warnings']) and (r['item_id'], r['qcode']) == ('9', '2.2')
    bad = '```yaml\ntype: essay\nstem: "x"\n```\n\n```yaml\ntype: mcq\nstem: "y"\noptions: [a, b]\nanswer: 5\n```\n\n```yaml\ntype: [\n```'
    r = parse(sample(quiz=bad), '1.2-1.md'); q = r['quiz']
    assert len(q) == 3 and 'άκυρος τύπος' in q[0]['err'][0] and 'εκτός ορίων' in q[1]['err'][0] and 'σφάλμα YAML' in q[2]['err'][0]
    assert sum('Quiz στοιχείο' in w for w in r['warnings']) == 3

def test_parse_garbage_never_raises():
    from app.qsol import parse
    for t in ('', 'καθόλου markdown', '---\n: : :\n---\n', '\x00\x01---'):
        r = parse(t, 'x.md'); assert r['status'] == 'error' and r['warnings']
    assert parse(sample().replace('## Παραπομπές', '## Κάτι άλλο'), '1.2-1.md')['warnings'][0].startswith('άγνωστη ενότητα')

# ---------- σάρωση ----------
def test_scan_link_orphan_fallback_and_precedence(tmp_path):
    from app import qsol
    db = tmp_path / 'x.db'; make_db(db, SCHEMA.read_text(encoding='utf-8')); root = tmp_path / 'data'
    orig = root / 'C' / '04_TRAPEZA' / 'orig'; ly = root / 'C' / '05_LYSEIS'; orig.mkdir(parents=True); ly.mkdir()
    (orig / '1.2-1.md').write_text(sample(title='ΑΠΟ_ORIG'), encoding='utf-8'); (ly / '1.2-1.md').write_text(sample(title='ΑΠΟ_05'), encoding='utf-8')
    (ly / '2.2-1.md').write_text(sample(item='2'), encoding='utf-8'); (orig / '7.2-3.md').write_text(sample(item='7', sub='2.3'), encoding='utf-8')
    (orig / '1.pdf').write_bytes(b'%PDF'); (orig / '12345_notes.md').write_text('x', encoding='utf-8'); (orig / 'README.md').write_text('x', encoding='utf-8')
    c = sqlite3.connect(db); res = qsol.scan(c, root); c.commit()
    assert res['files'] == 3 and res['linked'] == 2 and res['orphans'] == 1
    rows = {(r[0], r[1]): r for r in c.execute('SELECT item_id,qcode,question_id,relpath,sections FROM qsolution')}
    assert rows[('1', '2.1')][2] == 1 and 'ΑΠΟ_ORIG' in rows[('1', '2.1')][4] and rows[('1', '2.1')][3] == 'C/04_TRAPEZA/orig/1.2-1.md'
    assert rows[('2', '2.1')][3] == 'C/05_LYSEIS/2.2-1.md' and rows[('2', '2.1')][2] == 2 and rows[('7', '2.3')][2] is None
    w = '\n'.join(res['warnings']); assert 'ορφανό' in w and '12345_notes.md' in w and 'README' not in w and 'υπάρχει και στο 05_LYSEIS' in w
    (orig / '7.2-3.md').unlink(); res = qsol.scan(c, root, 'C'); assert res['files'] == 2 and c.execute('SELECT count(*) FROM qsolution').fetchone()[0] == 2
    assert 'αρχεία' in qsol.summary(res)

def test_ingest_ignores_md_in_orig(tmp_path):
    """Το ingest διαβάζει μόνο *.pdf του orig/: τα .md και το images/ δεν δημιουργούν «θέματα»."""
    import openpyxl
    sys.path.insert(0, str(ROOT / 'tools')); import ingest
    orig = tmp_path / 'C' / '04_TRAPEZA' / 'orig'; orig.mkdir(parents=True); (orig / '1.2-1.md').write_text(sample(), encoding='utf-8'); png(orig / 'images' / 'a.png')
    wb = openpyxl.Workbook(); wb.active.title = 'Θέματα'; x = tmp_path / 'i.xlsx'; wb.save(x)
    rows, warn = ingest.run(tmp_path / 'C', x); assert rows == [] and warn == []

# ---------- migrations ----------
def test_migrations_upgrade_idempotent_and_schema_latest(tmp_path):
    from app import migrations
    assert re.search(r'INSERT INTO schema_version\(version\) VALUES\((\d+)\)', SCHEMA.read_text(encoding='utf-8')).group(1) == str(migrations.LATEST)
    db = tmp_path / 'old.db'; make_db(db, old_schema()); c = sqlite3.connect(db)
    c.execute("INSERT INTO exam(id,title) VALUES(1,'Διαγώνισμα')"); c.execute("INSERT INTO question_tag VALUES('1','2.1','ohm')"); c.execute("INSERT INTO mdoc(name,markdown) VALUES('Δ','# x')")
    c.execute("INSERT INTO question_fav VALUES('1','2.1','t')"); c.commit()
    assert migrations.current(c) == 0 and 'qsolution' not in migrations.tables(c)
    assert migrations.migrate(c) == (0, migrations.LATEST) and migrations.migrate(c) == (migrations.LATEST, migrations.LATEST)
    assert 'qsolution' in migrations.tables(c) and c.execute('SELECT count(*) FROM schema_version').fetchone()[0] == 1
    assert [c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('exam', 'question_tag', 'mdoc', 'question_fav', 'question')] == [1, 1, 1, 1, 2]
    e = sqlite3.connect(tmp_path / 'empty.db'); assert migrations.migrate(e) == (None, None) and migrations.tables(e) == set()
    n = sqlite3.connect(':memory:'); n.executescript(SCHEMA.read_text(encoding='utf-8')); assert migrations.current(n) == migrations.LATEST and migrations.migrate(n) == (migrations.LATEST, migrations.LATEST)

def test_app_migrates_old_db_automatically(env):
    cl, tmp = env
    c = sqlite3.connect(os.environ['THILEK_DB']); assert c.execute('SELECT version FROM schema_version').fetchone()[0] >= 1
    assert c.execute('SELECT count(*) FROM qsolution').fetchone()[0] == 1

def test_rebuild_integration(tmp_path):
    """Πλήρες rebuild χωρίς πραγματικά PDF: xlsx + book_sections.csv + derived/item.json + λύση .md· μεταφέρονται τα δεδομένα χρήστη."""
    import datetime, openpyxl, subprocess
    root = tmp_path / 'data'; cdir = root / 'B-ILEKTROTECHNIA'; tt = cdir / '04_TRAPEZA'; (tt / 'orig').mkdir(parents=True); (cdir / '03_YLI').mkdir()
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Θέματα'
    for _ in range(4): ws.append(['h'])
    ws.append([1, datetime.datetime(2025, 1, 1), 'Θέμα 2', None, None, None, None, None, '4.1 Ηλεκτρικό πεδίο', 'Κεφ. 4']); wb.save(tt / 'iep_index_219.xlsx')
    (cdir / '03_YLI' / 'book_sections.csv').write_text('code,level,title,page_from,page_to_next_start,note\n4.1,2,Πεδίο,266,292,\n', encoding='utf-8')
    (tt / 'derived' / '1').mkdir(parents=True)
    (tt / 'derived' / '1' / 'item.json').write_text(json.dumps({'solution_status': 'ok', 'questions': [{'code': '2.1', 'points': 15, 'text': 'q'}]}), encoding='utf-8')
    (tt / 'orig' / '1.2-1.md').write_text(sample().replace('course: C', 'course: B-ILEKTROTECHNIA'), encoding='utf-8'); (tt / 'orig' / '1.2-5.md').write_text(sample(sub='2.5'), encoding='utf-8')
    db = tmp_path / 'r.db'; make_db(db, old_schema()); c = sqlite3.connect(db); c.execute("INSERT INTO question_tag VALUES('1','2.1','κρατιέται')"); c.execute("INSERT INTO mdoc(name,markdown) VALUES('Δ','# x')"); c.commit(); c.close()
    p = subprocess.run([sys.executable, str(ROOT / 'tools' / 'rebuild.py'), str(root), str(db)], capture_output=True, text=True, cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert 'λύσεις εκπαιδευτικού: 2 αρχεία, 1 συνδέθηκαν, 1 ορφανά' in p.stdout
    c = sqlite3.connect(db)
    assert c.execute('SELECT version FROM schema_version').fetchone()[0] >= 1 and c.execute("SELECT question_id FROM qsolution WHERE qcode='2.1'").fetchone()[0] is not None
    assert c.execute('SELECT tag FROM question_tag').fetchone()[0] == 'κρατιέται' and c.execute('SELECT count(*) FROM mdoc').fetchone()[0] == 1
    w = (tt / 'solution_warnings.txt').read_text(encoding='utf-8'); assert '1.2-5.md' in w and 'ορφανό' in w and 'course «C»' in w

# ---------- σελίδες ----------
def test_lyseis_and_lysi_pages(env):
    cl, tmp = env
    h = cl.get('/lyseis', auth=A).text; assert "href='/lysi/1/2.1'" in h and 'Σάρωση φακέλου' in h and 'name=act value=reveal' in h and 'name=qids value=1>' in h and "href='/lyseis'" in h
    r = cl.get('/lysi/1/2.1', auth=A); t = r.text; assert r.status_code == 200
    assert "/static/vendor/katex/katex.min.css" in t and '/static/vendor/katex/auto-render.min.js' in t and '/static/lysi.js' in t and 'data-copy=' in t and 'id=md-all' in t
    assert '$R=10\\,\\Omega$' in t and '$a_1 * b_2 * c$' in t and '<em>' not in t.split('class=lysi')[1]           # τα math μένουν ακέραια για το KaTeX
    assert "src='/files/C/04_TRAPEZA/orig/images/ohm1.png'" in t and 'href="/review/1"' in t and 'href="/book/1/300"' in t and 'href="/files/C/04_TRAPEZA/orig/1.pdf#page=1"' in t
    assert 'Quiz (6)' in t and 'action=\'/lyseis/export\'' in t and 'cdn' not in t.lower() and '<script>' not in t
    assert "style-src 'self'" in r.headers['content-security-policy'] and "default-src 'self'" in r.headers['content-security-policy']
    md = cl.get('/lysi/1/2.1/md', auth=A); assert md.status_code == 200 and md.text.startswith('---\nid: "1.2-1"') and 'attachment' in md.headers['content-disposition']
    assert cl.get('/lysi/1/2.1').status_code == 401 and cl.get('/lyseis').status_code == 401 and cl.get('/lysi/1/9.9', auth=A).status_code == 404 and cl.get('/lysi/1/9.9/md', auth=A).status_code == 404
    k = cl.get('/static/vendor/katex/katex.min.js'); assert k.status_code == 200 and 'katex' in k.text[:400]
    assert cl.get('/static/vendor/katex/fonts/KaTeX_Main-Regular.woff2').status_code == 200 and cl.get('/static/vendor/../main.py').status_code == 404
    assert 'execCommand' in cl.get('/static/lysi.js').text and 'navigator.clipboard' in cl.get('/static/lysi.js').text

def test_browse_filter_and_q_meta(env):
    cl, tmp = env
    h = cl.get('/browse?lsol=1', auth=A).text; assert 'name=qids value=1>' in h and 'name=qids value=2>' not in h and "href='/lysi/1/2.1'" in h and 'name=lsol' in h
    h = cl.get('/browse?lsol=0', auth=A).text; assert 'name=qids value=1>' not in h and 'name=qids value=2>' in h
    assert "λύση εκπαιδευτικού: <a href='/lysi/1/2.1'>προβολή</a>" in cl.get('/q/1', auth=A).text and 'λύση εκπαιδευτικού: —' in cl.get('/q/2', auth=A).text
    assert cl.get('/q/start?lsol=1', auth=A, follow_redirects=False).headers['location'] == '/q/1?lsol=1'
    assert 'name=lsol' in cl.get('/q/1?lsol=1', auth=A).text and cl.get('/q/1?sol=1', auth=A).status_code == 200

class _Strict(HTMLParser):
    def __init__(self): super().__init__(); self.tags = []
    def handle_starttag(self, tag, attrs): self.tags.append(tag)

EXTERNAL = re.compile(r'''(?:src|href)\s*=\s*["']?\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import''', re.I)

def test_act_reveal(env):
    cl, tmp = env
    r = cl.post('/select/act', data={'act': 'reveal', 'qids': ['1'], 'sol_title': 'Ohm <b>', 'rtheme': 'black'}, auth=A, headers=H)
    assert r.status_code == 200 and r.headers['content-type'].startswith('text/html') and 'thilek-reveal.html' in r.headers['content-disposition']
    t = r.text; p = _Strict(); p.feed(t); assert t.startswith('<!doctype html>') and p.tags.count('section') >= 12
    assert not EXTERNAL.search(t) and not re.search(r'''fetch\(\s*["'`]https?:|XMLHttpRequest''', t)
    assert t.index('renderMathInElement(document') < t.index('Reveal.initialize(') and 'width:1280,height:800' in t
    assert 'data:font/woff2;base64,' in t and 'url(fonts/' not in t and 'Source Sans Pro;src:url(data' not in t and len(t) < 2_500_000
    assert 'data:image/png;base64,' in t and 'class=\'fragment ans\'' in t and 'class=fragment' in t and '```yaml' not in t and 'type: mcq' not in t
    assert '$R=10\\,\\Omega$' in t and 'Ohm &lt;b&gt;' in t and '<section><section class=' in t
    only = cl.post('/select/act', data={'act': 'reveal', 'qids': ['1'], 'sx': ['statement']}, auth=A, headers=H).text
    assert 'Εκφώνηση' in only and 'Λύση εκπαιδευτικού</h2>' not in only and 'Quiz 1' not in only

def test_act_solmd_and_word(env):
    cl, tmp = env
    r = cl.post('/select/act', data={'act': 'solmd', 'qids': ['1'], 'sol_title': 'Λύσεις Ohm'}, auth=A, headers=H, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'].startswith('/docs/')
    did = r.headers['location'].rsplit('/', 1)[1]; md = cl.get(f'/docs/{did}/md', auth=A).text
    assert md.startswith('# Λύσεις Ohm') and '### Εκφώνηση' in md and '### Καθοδήγηση' in md and '### Λύση εκπαιδευτικού' not in md and '![κύκλωμα](/files/C/04_TRAPEZA/orig/images/ohm1.png)' in md
    assert '**Απάντηση:** β. 2 A' in md and '\n--\n' not in md and '```yaml' not in md
    d = cl.get(f'/docs/{did}/docx', auth=A); assert d.status_code == 200 and d.content[:2] == b'PK'
    from docx import Document
    doc = Document(io.BytesIO(d.content)); txt = '\n'.join(p.text for p in doc.paragraphs); M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
    mt = ''.join(t.text or '' for t in doc.element.body.iter(M + 't'))
    assert len(list(doc.element.body.iter(M + 'oMath'))) >= 4 and len(list(doc.element.body.iter(M + 'oMathPara'))) >= 1          # τύποι = εξισώσεις Word (OMML)
    assert 'R' in mt and '10' in mt and 'Ω' in mt and 'R=10' not in txt and '$5 και $10' in txt and len(doc.inline_shapes) >= 1
    assert '\n\n$$\nI=' in md                                                      # τα $$ του σύνθετου Markdown είναι δικά τους μπλοκ

def test_act_moodle(env):
    cl, tmp = env
    r = cl.post('/select/act', data={'act': 'moodle', 'qids': ['1'], 'sol_title': 'Ohm'}, auth=A, headers=H)
    assert r.status_code == 200 and r.headers['content-type'].startswith('application/xml') and 'thilek-moodle.xml' in r.headers['content-disposition'] and r.headers['x-skipped'] == '0'
    root = ET.fromstring(r.content); qs = root.findall('question')
    assert [q.get('type') for q in qs] == ['category', 'multichoice', 'truefalse', 'numerical', 'shortanswer', 'cloze', 'matching']
    assert qs[0].find('category/text').text == '$course$/top/Ohm' and qs[1].find('name/text').text == '1.2-1 · στοιχείο 1'
    texts = [q.find('questiontext/text').text for q in qs[1:]]; assert '\\(I\\)' in texts[0] and not any('$' in x for x in texts)
    assert not any('$' in (e.text or '') for e in root.iter('text') if '$course$' not in (e.text or ''))      # κανένα μονό $ ούτε στις απαντήσεις αντιστοίχισης
    assert qs[1].find('single').text == 'true' and [a.get('fraction') for a in qs[1].findall('answer')] == ['0', '100', '0'] and '\\(\\dfrac{1}{2}\\,\\mathrm{A}\\)' in qs[1].findall('answer')[2].find('text').text
    assert qs[1].find('defaultgrade').text == '2' and qs[1].find('generalfeedback/text').text == '\\(I=V/R\\)'
    assert qs[3].find('answer/tolerance').text == '0.1' and '(σε A)' in texts[2] and qs[3].find('units') is None and qs[3].find('questiontext/file').get('encoding') == 'base64' and '@@PLUGINFILE@@/ohm1.png' in texts[2]
    assert '{1:SHORTANSWER:=Ω}' in texts[4] and '{1:SHORTANSWER:=A}' in texts[4] and len(qs[6].findall('subquestion')) == 3
    bad = '```yaml\ntype: essay\nstem: "x"\n```\n\n' + QUIZ
    (tmp / 'data' / 'C' / '04_TRAPEZA' / 'orig' / '1.2-1.md').write_text(sample(quiz=bad), encoding='utf-8'); cl.post('/lyseis/scan', auth=A, headers=H)
    r = cl.post('/select/act', data={'act': 'moodle', 'qids': ['1']}, auth=A, headers=H); assert r.headers['x-skipped'] == '1' and b'essay' in r.content and len(ET.fromstring(r.content).findall('question')) == 7

def test_no_solution_422_and_same_origin(env):
    cl, tmp = env
    for act in ('reveal', 'solmd', 'moodle'):
        r = cl.post('/select/act', data={'act': act, 'qids': ['2']}, auth=A, headers=H); assert r.status_code == 422 and 'λύση εκπαιδευτικού' in r.json()['detail']
        assert cl.post('/select/act', data={'act': act, 'qids': ['1']}, auth=A).status_code == 403
    assert cl.post('/lyseis/scan', auth=A).status_code == 403 and cl.post('/lyseis/scan', headers=H).status_code == 401
    assert cl.post('/lyseis/export', data={'act': 'reveal', 'keys': ['1|2.1']}, auth=A).status_code == 403
    r = cl.post('/lyseis/export', data={'act': 'moodle', 'keys': ['1|2.1']}, auth=A, headers=H); assert r.status_code == 200 and b'<quiz>' in r.content
    assert cl.post('/lyseis/export', data={'act': 'reveal', 'keys': ['2|2.1']}, auth=A, headers=H).status_code == 422
    assert cl.post('/select/act', data={'act': 'doc', 'qids': ['1']}, auth=A, headers=H).status_code == 200      # οι παλιές ενέργειες δουλεύουν όπως πριν

# ---------- μαθηματικά ----------
def test_latex_to_text():
    from app.mdmath import latex_to_text as L
    assert L(r'\dfrac{a}{b}') == '(a)/(b)' and L(r'R=10\,\Omega') == 'R=10 Ω' and L(r'\varepsilon_r\,\varepsilon_0') == 'εᵣ ε₀' and L(r'\pi r^2') == 'π r²'
    assert L(r'\mathrm{N/C}') == 'N/C' and L(r'\vec{E}') == 'E\u20d7' and L(r'x \cdot y') == 'x · y' and L(r'90^\circ') == '90°' and L(r'\sqrt{2}') == '√2'
    assert L(r'\foo{x}+1') == r'\foo{x}+1' and L(r'R_{ολ}') == 'R_{ολ}' and L(r'10^{-3}') == '10⁻³'

def test_markdown_math_protection():
    from app.mdmath import render_md, protect, moodle_text
    h = render_md('Α $a\\,b$ και $x_1 * y_2 * z$ και $$a\\\\b \\{c\\}$$ και `$c_1$` και \\$5 και $5 με $10')
    assert '$a\\,b$' in h and '$x_1 * y_2 * z$' in h and '<em>' not in h and '$$a\\\\b \\{c\\}$$' in h and '<code>$c_1$</code>' in h and '$5 με $10' in h
    assert render_md('![x](../../etc/passwd.png) ![y](http://evil/x.png) ![z](images/ok.png)', 'C/o').count('<img') == 1
    assert '<script>' not in render_md('<script>alert(1)</script> [a](javascript:alert(1))') and 'href="javascript' not in render_md('[a](javascript:alert(1))')
    assert protect('$5 και $10 ή $5$', only_tex=True)[1] == [] and protect('$x_1$')[1] == ['$x_1$'] and protect('$E$ $F/q$', only_tex=True)[1] == ['$E$', '$F/q$']
    assert moodle_text('$$a<b$$') == '\\[a&lt;b\\]'


# ---------- 0.16.1: τύποι σε Markdown/Word ----------
def test_normalize_math_md():
    from app.mdmath import normalize_math_md as N
    t = 'Από $E=\\dfrac{F}{q}$\n$$[E]=\\dfrac{N}{C}$$\nκαι\n$$a=b$$\n$$c=d$$\nτέλος'
    n = N(t)
    assert n == 'Από $E=\\frac{F}{q}$\n\n$$\n[E]=\\dfrac{N}{C}\n$$\n\nκαι\n\n$$\na=b\n$$\n\n$$\nc=d\n$$\n\nτέλος' and N(n) == n          # idempotent
    keep = '```yaml\nstem: "$\\dfrac{a}{b}$ $$x$$"\n```\n`$\\dfrac{1}{2}$`\n| $\\dfrac{a}{b}$ | $$z$$ |\n- στοιχείο $$w$$\n   συνέχεια $$v$$'
    assert N(keep) == '```yaml\nstem: "$\\dfrac{a}{b}$ $$x$$"\n```\n`$\\dfrac{1}{2}$`\n| $\\frac{a}{b}$ | $$z$$ |\n- στοιχείο $$w$$\n   συνέχεια $$v$$'          # κώδικας, πίνακες, λίστες: μόνο το \\dfrac του πίνακα (inline) αλλάζει
    assert N('x $5 και $10 ή \\$7') == 'x $5 και $10 ή \\$7' and N('') == '' and N(None) == ''

def test_omml_conversion():
    from xml.etree import ElementTree as ET
    from app import omml
    NS = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'
    for tex, disp in [(r'E=\dfrac{F}{q}', False), (r'F=K\dfrac{Q_1Q_2}{r^2}\;\Rightarrow\;x', True), (r'\vec{E}', False), (r'R=4{,}7\,\mathrm{k\Omega}', False),
                      (r'\sqrt{x^2}', False), (r'\left(\dfrac{a}{b}\right)^2', False), (r'\overline{x}', False), (r'90^\circ', False)]:
        x = omml.latex_to_omml(tex, disp); assert x, tex
        root = ET.fromstring(x.replace('<m:oMath', f'<m:oMath {NS}', 1) if not disp else x.replace('<m:oMathPara>', f'<m:oMathPara {NS}>', 1))     # έγκυρο XML
        assert root.tag.endswith('oMathPara' if disp else 'oMath')
    u = omml.latex_to_omml(r'5\,\mathrm{k\Omega}'); assert '<m:sty m:val="p"/>' in u and 'Ω' in u          # μονάδες όρθιες
    assert '<m:f>' in omml.latex_to_omml(r'\dfrac{a}{b}') and '<m:sSub>' in omml.latex_to_omml('x_1') and '<m:acc>' in omml.latex_to_omml(r'\vec{F}')
    assert omml.latex_to_omml('') is None and omml.latex_to_omml('   ') is None

def test_word_equations_table_and_fallback(monkeypatch):
    import io
    from docx import Document
    from docx.shared import Inches
    from app.mddoc import md_to_docx
    M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
    md = ('Ένταση $\\vec{E}$: από $E=\\dfrac{F}{q}$\n$$[E]=\\dfrac{N}{C}$$\nμετά το τύπο.\n\n| Α | Β |\n|---|---|\n| $x$ | $\\dfrac{a}{b}$ |\n| κάτι πολύ μακρύ κείμενο εδώ | y |\n')
    doc = Document(io.BytesIO(md_to_docx(None, md))); body = doc.element.body
    paras = [p for p in doc.paragraphs]; k = [i for i, p in enumerate(paras) if p._p.findall(M + 'oMathPara')]
    assert len(k) == 1 and not paras[k[0]].text.strip()                                   # το $$ είναι σε δική του παράγραφο
    assert paras[k[0] - 1].text.startswith('Ένταση') and paras[k[0] + 1].text.strip() == 'μετά το τύπο.'
    assert len(list(body.iter(M + 'oMath'))) == 5 and not any('$' in p.text for p in paras)
    tb = doc.tables[0]; w = [c.width for c in tb.rows[1].cells]
    assert abs(sum(w) - Inches(6.6)) < Inches(0.05) and w[0] < w[1] + Inches(5) and all(x >= Inches(6.6 * 0.1) for x in w)       # πλήρες πλάτος, στήλες ανάλογες
    assert tb.rows[2].cells[0].width > tb.rows[2].cells[1].width
    monkeypatch.setattr('app.omml._L2M', None)                                            # χωρίς βιβλιοθήκη: αναγνώσιμο κείμενο, ποτέ σφάλμα
    d2 = Document(io.BytesIO(md_to_docx(None, md))); t2 = '\n'.join(p.text for p in d2.paragraphs)
    assert 'E=(F)/(q)' in t2 and not list(d2.element.body.iter(M + 'oMath'))

def test_docs_preview_keeps_math_and_loads_katex(env):
    cl, tmp = env
    h = cl.post('/docs/render', data={'md': 'Α $a\\,b$ και $$x\\;y$$ και $5 με $10'}, auth=A, headers=H).text
    assert '$a\\,b$' in h and '$$x\\;y$$' in h and '$5 με $10' in h
    cl.post('/lyseis/scan', auth=A, headers=H, follow_redirects=False)
    did = cl.post('/docs/from', data={'kind': 'collection', 'ref': 0}, auth=A, headers=H, follow_redirects=False)       # δεν υπάρχει συλλογή 0
    assert did.status_code == 404
    up = cl.post('/docs/upload', files={'file': ('t.md', 'x $a$'.encode())}, auth=A, headers=H, follow_redirects=False)
    page = cl.get(up.headers['location'], auth=A).text
    assert '/static/vendor/katex/katex.min.js' in page and '/static/vendor/katex/auto-render.min.js' in page and 'src=\'/static/md.js\'' in page


# ---------- 0.17.0: ενότητες, σειρά, στυλ, HTML μαθητή ----------
def test_units_order_and_presets():
    from app.solstyle import include_of, teacher_units, classify, PRESETS, KEYS, style_of
    assert include_of(None) == list(KEYS) and include_of(['x', 'y']) == list(KEYS)
    assert include_of(['guide', 'statement', 'guide', 'zzz']) == ['guide', 'statement']                 # σειρά φόρμας, χωρίς διπλά και άγνωστα
    assert include_of(['statement', 'teacher', 'quiz']) == ['statement', 'goal', 'guide', 'full', 'errors', 'ext', 'quiz']        # παλιό κλειδί
    assert [classify(t) for t in ('Στόχος και προαπαιτούμενα', 'Καθοδήγηση', 'Πλήρης λύση βήμα-βήμα', 'Συνήθη λάθη και έλεγχος', 'Επέκταση', 'Κάτι άλλο', '')] == ['goal', 'guide', 'full', 'errors', 'ext', '', '']
    tu = teacher_units([{'title': '', 'body': 'α'}, {'title': 'Καθοδήγηση', 'body': 'β'}, {'title': 'Καθοδήγηση', 'body': 'γ'}, {'title': 'Άγνωστος', 'body': 'δ'}, {'title': 'Πλήρης λύση', 'body': 'ε'}])
    assert tu == {'goal': ['α'], 'guide': ['β', 'γ', 'δ'], 'full': ['ε']}                           # `--` = νέο μέρος· άγνωστος τίτλος ανήκει στο προηγούμενο
    assert all(set(o) <= set(KEYS) for _, _, o in PRESETS) and style_of('black') == 'dark' and style_of('white') == 'calm' and style_of('x') == 'calm' and style_of('kids') == 'kids'

def test_reveal_order_and_styles(env):
    cl, tmp = env
    def rv(**kw): return cl.post('/select/act', data={'act': 'reveal', 'qids': ['1'], **kw}, auth=A, headers=H).text
    t = rv(sx=['guide', 'statement', 'quiz'], sstyle='kids')
    assert t.index('<h2>Καθοδήγηση') < t.index('<h2>Εκφώνηση') < t.index('<h2>Quiz') and 'Πλήρης λύση</h2>' not in t and 'Στόχος και προαπαιτούμενα</h2>' not in t
    assert '<span class=badge>💡</span>' in t and '.u-guide{--u:#d97706' in t and 'u-title' in t
    assert '<section><section class=' in t and t.count("class='u u-guide'") == 1                       # κάθε ενότητα λύσης είναι δική της κάθετη στοίβα
    assert 'badge>' not in rv(sstyle='print').split('</style>')[-1] and '--r-background-color:#ffffff' in rv(sstyle='print') and '#000000' in rv(sstyle='print')
    d = rv(sstyle='dark'); assert '--r-background-color:#12161d' in d and 'class=badge' in d
    assert '--r-background-color:#12161d' in rv(rtheme='black') and '--r-background-color:#f4f6f9' in rv(rtheme='white') and '--r-background-color:#f4f6f9' in rv()   # συμβατότητα
    for st in ('kids', 'calm', 'dark', 'print'):
        x = rv(sstyle=st); assert not EXTERNAL.search(x) and 'renderMathInElement(document' in x

def test_act_html_student(env):
    import json
    cl, tmp = env
    def hx(**kw):
        r = cl.post('/select/act', data={'act': 'html', 'qids': ['1'], 'sol_title': 'Φύλλο <b>', **kw}, auth=A, headers=H); assert r.status_code == 200 and 'thilek-mathitis.html' in r.headers['content-disposition']; return r.text
    t = hx(sx=['statement', 'guide', 'full', 'iep', 'quiz'], sstyle='kids', hide='1'); p = _Strict(); p.feed(t)
    assert t.startswith('<!doctype html>') and not EXTERNAL.search(t) and 'Φύλλο &lt;b&gt;' in t and 'data:font/woff2;base64,' in t and 'data:image/png;base64,' in t
    body = t.split('</head>')[1]
    assert body.index("unit u-statement") < body.index("unit u-guide") < body.index("<details class='unit u-full'>") < body.index("<details class='unit u-iep'>") < body.index("unit u-quiz")          # σειρά φόρμας
    assert '--accent:#2563eb' in t and '<span class=badge>💡</span>' in t and 'κλικ για εμφάνιση' in t
    q = json.loads(re.search(r"<script type='application/json' id=qz>(.*?)</script>", t, re.S).group(1).replace('<\\/', '</'))
    assert len(q) >= 3 and any(v['t'] == 'true_false' for v in q.values()) and all('ans' in v for v in q.values()) and 'data-do=check' in t
    nohide = hx(sx=['full'], hide=''); assert '<details' not in nohide and "<section class='unit u-full'>" in nohide and 'unit u-statement' not in nohide
    assert '.u-full{--u:#000000' in hx(sstyle='print') and '--bg:#12161d' in hx(sstyle='dark') and '--bg:#f4f6f9' in hx()
    assert 'beforeprint' in t and 'renderMathInElement(document.body' in t

def test_controls_and_static(env):
    cl, tmp = env
    cl.post('/lyseis/scan', auth=A, headers=H, follow_redirects=False)
    page = cl.get('/browse', auth=A).text
    order = [m.group(1) for m in re.finditer(r"<input type=checkbox name=sx value=(\w+) checked>", page)]
    assert order == ['statement', 'iep', 'goal', 'guide', 'full', 'errors', 'ext', 'quiz'] and "name=sstyle" in page and 'value=html' in page and '/static/solctl.js' in page and "name=hide" in page
    assert "<option value=kids selected>" in page and 'Φύλλο μαθητή' in page and 'class=up' in page
    js = cl.get('/static/solctl.js', auth=A); assert js.status_code == 200 and 'solpre' in js.text

def test_word_style_marker(env):
    import io
    from docx import Document
    from docx.shared import RGBColor
    cl, tmp = env
    r = cl.post('/select/act', data={'act': 'solmd', 'qids': ['1'], 'sx': ['guide', 'statement'], 'sstyle': 'kids'}, auth=A, headers=H, follow_redirects=False)
    did = r.headers['location'].rsplit('/', 1)[1]; md = cl.get(f'/docs/{did}/md', auth=A).text
    assert md.index('### 💡 Καθοδήγηση') < md.index('### ✏️ Εκφώνηση') and md.rstrip().endswith('[thilek-style]: #kids')
    assert 'thilek-style' not in cl.post('/docs/render', data={'md': md}, auth=A, headers=H).text                      # ο ορισμός δεν φαίνεται στην προεπισκόπηση
    doc = Document(io.BytesIO(cl.get(f'/docs/{did}/docx', auth=A).content)); h2 = [p for p in doc.paragraphs if p.style.name == 'Heading 2'][0]
    assert h2.runs[0].font.color.rgb == RGBColor.from_string('7C3AED') and not any('thilek-style' in p.text for p in doc.paragraphs)
    plain = cl.post('/select/act', data={'act': 'solmd', 'qids': ['1']}, auth=A, headers=H, follow_redirects=False)
    assert 'thilek-style' not in cl.get(plain.headers['location'] + '/md', auth=A).text


# ---------- 0.18.0: file browser, κάδος, εργαλειοθήκες, μαζικές ενέργειες εγγράφων, διεπαφή ----------
def _orig(tmp): return tmp / 'data' / 'C' / '04_TRAPEZA' / 'orig'

def test_fb_listing_and_traversal(env):
    cl, tmp = env
    t = cl.get('/fb', auth=A).text; assert '📂' in t and '📁 C<' in t and 'Ελεύθερος χώρος' in t and 'Τι προστατεύει' in t
    t = cl.get('/fb?p=C/04_TRAPEZA/orig', auth=A).text
    assert '1.pdf' in t and '🔒' in t and 'Εκφώνηση ΙΕΠ' in t and '✔ θέμα 1 στη βάση' in t and '1.2-1.md' in t and 'στον πίνακα λύσεων' in t and '⚠' in t
    r = cl.get('/fb?p=../etc', auth=A); assert r.status_code == 400 and 'δεν επιτρέπεται να βγει έξω' in r.text
    (tmp / 'secret').mkdir(); (tmp / 'secret' / 'a.txt').write_text('x'); os.symlink(tmp / 'secret', tmp / 'data' / 'C' / 'lnk')
    r = cl.get('/fb?p=C/lnk', auth=A); assert r.status_code == 400 and 'έξω από τον φάκελο δεδομένων' in r.text
    assert cl.get('/fb/raw?p=C/lnk/a.txt', auth=A).status_code == 400 and cl.get('/fb/raw?p=C/../../x', auth=A).status_code == 400
    assert 'lnk' not in cl.get('/fb?p=C', auth=A).text                                              # οι σύνδεσμοι δεν εμφανίζονται

def test_fb_blocks_dangerous_actions(env):
    cl, tmp = env; o = _orig(tmp)
    for sel in ('C/04_TRAPEZA/orig/1.pdf', 'C', 'C/04_TRAPEZA', 'C/04_TRAPEZA/orig'):
        r = cl.post('/fb/delete', data={'sel': sel}, auth=A, headers=H); assert r.status_code == 403 and 'Δεν έγινε καμία αλλαγή' in r.text, sel
    assert (o / '1.pdf').exists() and (o / '1.2-1.md').exists() and (tmp / 'data' / 'C').exists()
    r = cl.post('/fb/delete', data={'sel': ['C/04_TRAPEZA/orig/1.pdf', 'C/04_TRAPEZA/orig/1.2-1.md']}, auth=A, headers=H)
    assert r.status_code == 403 and 'κανένα' in r.text and (o / '1.2-1.md').exists() and 'Πρωτότυπο αρχείο του ΙΕΠ' in r.text      # όλα ή τίποτα
    r = cl.post('/fb/rename', data={'p': 'C/04_TRAPEZA/orig/1.pdf', 'name': 'x.pdf'}, auth=A, headers=H); assert r.status_code == 403 and (o / '1.pdf').exists()
    assert cl.post('/fb/delete', data={'sel': 'C'}, auth=('admin', 'pw'), headers={'origin': 'http://evil', 'host': 'testserver'}).status_code == 403   # CSRF

def test_fb_trash_restore_and_purge(env):
    cl, tmp = env; o = _orig(tmp); md = 'C/04_TRAPEZA/orig/1.2-1.md'
    r = cl.post('/fb/delete', data={'sel': md, 'back': 'C/04_TRAPEZA/orig'}, auth=A, headers=H); assert r.status_code == 200 and 'Χρειάζεται επιβεβαίωση' in r.text and (o / '1.2-1.md').exists()
    r = cl.post('/fb/delete', data={'sel': md, 'confirm': '1', 'back': 'C/04_TRAPEZA/orig'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and not (o / '1.2-1.md').exists()
    kad = list((tmp / 'data' / '_kados').rglob('1.2-1.md')); assert len(kad) == 1
    t = cl.get('/fb/trash', auth=A).text; assert '1.2-1.md' in t and 'Κάδος αρχείων' in t
    assert cl.get('/fb', auth=A).text.count('_kados') == 0 and cl.get('/fb?p=_kados', auth=A, follow_redirects=False).status_code == 303
    assert cl.get('/fb/raw?p=' + str(kad[0].relative_to(tmp / 'data')), auth=A).status_code == 403
    tid = int(re.search(r'name=ids value=(\d+)', t).group(1))
    (o / '1.2-1.md').write_text('άλλο'); r = cl.post('/fb/restore', data={'ids': tid}, auth=A, headers=H); assert r.status_code == 409 and 'υπάρχει ήδη άλλο στοιχείο' in r.text and (o / '1.2-1.md').read_text() == 'άλλο'
    (o / '1.2-1.md').unlink(); assert cl.post('/fb/restore', data={'ids': tid}, auth=A, headers=H, follow_redirects=False).status_code == 303 and 'Στόχος' in (o / '1.2-1.md').read_text(encoding='utf-8') and not kad[0].exists()
    cl.post('/fb/delete', data={'sel': md, 'confirm': '1'}, auth=A, headers=H); tid = int(re.search(r'name=ids value=(\d+)', cl.get('/fb/trash', auth=A).text).group(1))
    assert cl.post('/fb/purge', data={'ids': tid, 'phrase': 'ναι'}, auth=A, headers=H).status_code == 409 and list((tmp / 'data' / '_kados').rglob('1.2-1.md'))
    assert cl.post('/fb/purge', data={'ids': tid, 'phrase': 'ΔΙΑΓΡΑΦΗ'}, auth=A, headers=H, follow_redirects=False).status_code == 303 and not list((tmp / 'data' / '_kados').rglob('1.2-1.md'))
    assert 'trash' in cl.get('/fb', auth=A).text and 'purge' in cl.get('/fb', auth=A).text                    # ιστορικό ενεργειών

def test_fb_upload_rules(env, monkeypatch):
    from app import filebrowser
    cl, tmp = env; o = _orig(tmp); P = 'C/04_TRAPEZA/orig'
    up = lambda name, data, **kw: cl.post('/fb/upload', data={'p': P, **kw}, files={'files': (name, data)}, auth=A, headers=H, follow_redirects=False)
    r = up('note.txt', b'hello'); assert r.status_code == 303 and (o / 'note.txt').read_bytes() == b'hello'
    for bad in ('x.html', 'run.sh', 'evil.py', 'noext'): r = up(bad, b'x'); assert r.status_code == 422 and 'δεν επιτρέπεται' in r.text and not (o / bad).exists(), bad
    r = up('.hidden.txt', b'x'); assert r.status_code == 422 and 'κρυφά' in r.text
    r = up('1.pdf', b'NEW'); assert r.status_code == 422 and (o / '1.pdf').read_bytes() == b'%PDF' and 'Πρωτότυπο αρχείο του ΙΕΠ' in r.text         # δεν αντικαθίσταται πρωτότυπο ΙΕΠ
    r = up('note.txt', b'v2'); assert r.status_code == 409 and (o / 'note.txt').read_bytes() == b'hello' and 'επιτρέπω αντικατάσταση' in r.text
    r = up('note.txt', b'v2', confirm='1'); assert r.status_code == 303 and (o / 'note.txt').read_bytes() == b'v2' and any(p.read_bytes() == b'hello' for p in (tmp / 'data' / '_kados').rglob('note.txt'))
    assert cl.post('/fb/upload', data={'p': ''}, files={'files': ('a.txt', b'x')}, auth=A, headers=H).status_code == 403 and not (tmp / 'data' / 'a.txt').exists()
    monkeypatch.setattr(filebrowser, 'MAX_UPLOAD', 10); r = up('big.txt', b'x' * 11); assert r.status_code == 422 and 'όριο' in r.text and not (o / 'big.txt').exists() and not [p for p in o.iterdir() if p.name.startswith('.upload-')]
    monkeypatch.setattr(filebrowser, 'MAX_UPLOAD', 10 ** 8); monkeypatch.setattr(filebrowser, 'RESERVE', 10 ** 18); r = up('c.txt', b'x'); assert r.status_code == 422 and 'ελεύθερος χώρος' in r.text
    monkeypatch.setattr(filebrowser, 'RESERVE', 0); r = cl.post('/fb/upload', data={'p': P}, files=[('files', ('ok1.txt', b'1')), ('files', ('bad.exe', b'2'))], auth=A, headers=H); assert r.status_code == 422 and not (o / 'ok1.txt').exists()     # όλα ή τίποτα
    assert up('../esc.txt', b'x').status_code == 303 and (o / 'esc.txt').exists() and not (tmp / 'data' / 'C' / 'esc.txt').exists()

def test_fb_mkdir_rename_view_zip(env):
    cl, tmp = env; o = _orig(tmp); P = 'C/04_TRAPEZA/orig'
    assert cl.post('/fb/mkdir', data={'p': 'C', 'name': 'Σημειώσεις'}, auth=A, headers=H, follow_redirects=False).status_code == 303 and (tmp / 'data' / 'C' / 'Σημειώσεις').is_dir()
    for bad in ('a/b', '..', '.x', 'x.', '_kados'): assert cl.post('/fb/mkdir', data={'p': 'C', 'name': bad}, auth=A, headers=H).status_code == 422, bad
    assert cl.post('/fb/mkdir', data={'p': 'C', 'name': 'Σημειώσεις'}, auth=A, headers=H).status_code == 409 and cl.post('/fb/mkdir', data={'p': '', 'name': 'X'}, auth=A, headers=H).status_code == 403
    (o / 'a.txt').write_text('α'); r = cl.post('/fb/rename', data={'p': P + '/a.txt', 'name': 'b.txt'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and (o / 'b.txt').exists() and not (o / 'a.txt').exists()
    assert cl.post('/fb/rename', data={'p': P + '/b.txt', 'name': 'b.exe'}, auth=A, headers=H).status_code == 422 and cl.post('/fb/rename', data={'p': P + '/b.txt', 'name': '1.pdf'}, auth=A, headers=H).status_code in (409, 422)
    r = cl.post('/fb/rename', data={'p': P + '/1.2-1.md', 'name': 'x.md'}, auth=A, headers=H); assert r.status_code == 409 and 'επιβεβαίωση' in r.text and (o / '1.2-1.md').exists()
    v = cl.get('/fb/view?p=' + P + '/1.2-1.md', auth=A).text; assert 'Λύση εκπαιδευτικού (Markdown)' in v and 'Στόχος' in v and str(o) in v
    assert '/fb/raw?p=' in cl.get('/fb/view?p=' + P + '/images/ohm1.png', auth=A).text and 'iframe' in cl.get('/fb/view?p=' + P + '/1.pdf', auth=A).text
    r = cl.get('/fb/raw?p=' + P + '/images/ohm1.png', auth=A); assert r.headers['x-content-type-options'] == 'nosniff' and 'sandbox' in r.headers['content-security-policy']
    (o / 'images' / 's.svg').write_text("<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"); r = cl.get('/fb/raw?p=' + P + '/images/s.svg', auth=A); assert 'sandbox' in r.headers['content-security-policy'] and "default-src 'none'" in r.headers['content-security-policy']
    assert 'attachment' in cl.get('/fb/raw?p=' + P + '/1.pdf&dl=1', auth=A).headers['content-disposition']
    import zipfile, io as _io
    r = cl.post('/fb/zip', data={'sel': [P + '/1.pdf', P + '/images']}, auth=A, headers=H); z = zipfile.ZipFile(_io.BytesIO(r.content)); assert r.status_code == 200 and sorted(z.namelist())[0].endswith('1.pdf') and any(n.endswith('ohm1.png') for n in z.namelist())
    from app import filebrowser; filebrowser.MAX_ZIP = 3; assert cl.post('/fb/zip', data={'sel': [P + '/1.pdf']}, auth=A, headers=H).status_code == 413; filebrowser.MAX_ZIP = 300 * 1024 * 1024

def test_toolbox_api_save_and_assets(env):
    cl, tmp = env
    j = cl.get('/toolbox/api', auth=A).json(); assert [b['slot'] for b in j['boxes']] == [1, 2, 3] and [b['enabled'] for b in j['boxes']] == [True, True, False] and 'selall' in j['boxes'][0]['items'] and j['catalog']['files']['go'] == '/fb'
    r = cl.post('/toolbox/save', data={'n1': 'Δική μου', 'on1': '1', 'i1': ['docs', 'search', 'zzz', 'docs'], 'n2': 'Β', 'on2': '1', 'i2': [], 'n3': '', 'i3': ['top']}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    j = cl.get('/toolbox/api', auth=A).json(); assert j['boxes'][0] == {'slot': 1, 'name': 'Δική μου', 'items': ['docs', 'search'], 'enabled': True} and j['boxes'][1]['items'] == [] and j['boxes'][2]['enabled'] is False and j['boxes'][2]['name'] == 'Δική μου' and j['boxes'][2]['items'] == ['top']
    p = cl.get('/toolbox', auth=A).text; assert p.count('<fieldset>') == 3 and p.index("value='docs'") < p.index("value='search'") and 'class=up' in p
    assert cl.post('/toolbox/save', data={'reset': '1'}, auth=A, headers=H, follow_redirects=False).status_code == 303 and cl.get('/toolbox/api', auth=A).json()['boxes'][0]['name'] == 'Βασικά'
    assert cl.post('/toolbox/save', data={'n1': 'x'}, auth=('admin', 'pw'), headers={'origin': 'http://evil', 'host': 'testserver'}).status_code == 403
    js = cl.get('/static/ui.js', auth=A); assert js.status_code == 200 and 'tbfab' in js.text and 'thilek_tb' in js.text
    pg = cl.get('/review', auth=A).text; assert 'position:sticky;top:0;z-index:100' in pg and "src='/static/ui.js'" in pg and 'επιλογή γραμμών' in pg and "href='/fb'>Αρχεία" in pg and '.r-sel' in pg
    assert not EXTERNAL.search(pg) and cl.get('/review', auth=A).headers['content-security-policy'].startswith("default-src 'self'")

def test_docs_bulk_actions_and_location(env):
    import zipfile, io as _io
    cl, tmp = env
    ids = []
    for n in ('Α έγγραφο', 'Β/έγγραφο'):
        r = cl.post('/docs/new', data={'name': n}, auth=A, headers=H, follow_redirects=False); ids.append(int(r.headers['location'].rsplit('/', 1)[1]))
    t = cl.get('/docs', auth=A).text; assert 'μέσα στη βάση SQLite' in t and 'mdoc' in t and t.count('class=selbox') == 2 and 'data-selall' in t and 'βάση · mdoc #' in t
    r = cl.post('/docs/bulk', data={'act': 'zipmd', 'ids': ids}, auth=A, headers=H); z = zipfile.ZipFile(_io.BytesIO(r.content)); assert sorted(z.namelist()) == sorted([f'{ids[0]}-Α έγγραφο.md', f'{ids[1]}-Β_έγγραφο.md']) and '# Α έγγραφο' in z.read(z.namelist()[0]).decode()
    r = cl.post('/docs/bulk', data={'act': 'zipdocx', 'ids': ids}, auth=A, headers=H); z = zipfile.ZipFile(_io.BytesIO(r.content)); assert all(n.endswith('.docx') for n in z.namelist()) and len(z.namelist()) == 2 and z.read(z.namelist()[0])[:2] == b'PK'
    assert cl.post('/docs/bulk', data={'act': 'savesrv', 'ids': ids}, auth=A, headers=H, follow_redirects=False).status_code == 303
    sv = tmp / 'data' / 'C' / '07_EXAGOGES' / 'docs'; assert len(list(sv.glob('*.md'))) == 2 and 'docs' in cl.get('/fb?p=C/07_EXAGOGES', auth=A).text
    r = cl.post('/docs/bulk', data={'act': 'delete', 'ids': ids}, auth=A, headers=H); assert r.status_code == 200 and 'Διαγραφή εγγράφων' in r.text and cl.get('/docs', auth=A).text.count('class=selbox') == 2
    assert cl.post('/docs/bulk', data={'act': 'delete', 'ids': ids, 'confirm': '1'}, auth=A, headers=H, follow_redirects=False).status_code == 303 and cl.get('/docs', auth=A).text.count('class=selbox') == 0
    tr = cl.get('/fb/trash', auth=A).text; assert 'έγγραφο MD' in tr and tr.count('class=selbox') == 2
    tid = re.findall(r'name=ids value=(\d+)', tr); assert cl.post('/fb/restore', data={'ids': tid}, auth=A, headers=H, follow_redirects=False).status_code == 303
    d = cl.get('/docs', auth=A).text; assert d.count('class=selbox') == 2 and 'Α έγγραφο' in d and 'επαναφορά' in d
    assert cl.post('/docs/bulk', data={'act': 'delete'}, auth=A, headers=H, follow_redirects=False).status_code == 303                # χωρίς επιλογή: μήνυμα, όχι σφάλμα
