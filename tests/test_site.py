"""0.34.0: site builder μέρος 1 (site, site_page): migration 8, σελίδες/μενού, μπλοκ (quiz-ref, deck-ref, file, callout, embed), απόδοση, zip, σελίδες /sites."""
import io, json, os, pathlib, re, sqlite3, zipfile
import pytest
from app import deck as D, deckmd, embed as EM, migrations, publish, site as S
from tests.test_docs import cl, A, H, SCHEMA  # noqa: F401
from tests.test_deck import conn

ROOT = pathlib.Path(__file__).parent.parent
DOM = EM.hosts('youtube.com,geogebra.org')


def mk(cl, name='Μάθημα'):
    c = conn(); sid = S.create(c, name); c.commit(); c.close(); return sid


def titles(c, sid): return [(p['title'], d) for p, d in S.order(S.rows(c, sid))]


def ctx_of(c, sid, mode='export', domains=DOM):
    return S.Ctx(c, S.get(c, sid), os.environ['THILEK_ROOT'], domains, mode)


# ---------- βάση ----------
def test_migration_7_to_8_and_schema_sql():
    assert migrations.LATEST == 8
    c = sqlite3.connect(':memory:'); c.executescript(SCHEMA.read_text(encoding='utf-8')); assert {'site', 'site_page'} <= migrations.tables(c)
    c = sqlite3.connect(':memory:'); c.execute('CREATE TABLE item(id TEXT)'); c.execute('CREATE TABLE schema_version(version INTEGER)'); c.execute('INSERT INTO schema_version VALUES(7)')
    assert migrations.migrate(c) == (7, 8) and {'site', 'site_page'} <= migrations.tables(c) and migrations.migrate(c) == (8, 8)


def test_user_tables_in_rebuild_and_manual_db():
    assert "'site', 'site_page'" in (ROOT / 'tools' / 'rebuild.py').read_text(encoding='utf-8')
    md = (ROOT / 'app' / 'manual_db.md').read_text(encoding='utf-8'); assert '**`site`**' in md and '**`site_page`**' in md


# ---------- slug ----------
def test_slugify_greek_and_reserved(cl):
    assert S.slugify('Ηλεκτρικά κυκλώματα') == 'ilektrika-kyklomata' and S.slugify('Άσκηση 3') == 'askisi-3'
    assert re.fullmatch(r'[a-z0-9-]{1,50}', S.slugify('Άσκηση Νο 3!')) and S.slugify('!!!') == 'selida'
    assert S.clean_slug('index') == 'p-index' and S.clean_slug('deck-3') == 'p-deck-3' and S.clean_slug('file-x') == 'p-file-x'
    sid = mk(cl); c = conn(); a = S.add_page(c, sid, 'Index'); b = S.add_page(c, sid, 'Index')
    assert S.get_page(c, sid, a)['slug'] == 'p-index' and S.get_page(c, sid, b)['slug'] == 'p-index-2'


# ---------- δέντρο ----------
def test_tree_add_move_delete(cl):
    sid = mk(cl); c = conn(); a = S.add_page(c, sid, 'Α'); b = S.add_page(c, sid, 'Β'); a1 = S.add_page(c, sid, 'Α1', parent=a); a2 = S.add_page(c, sid, 'Α2', parent=a)
    assert titles(c, sid) == [('Αρχική', 0), ('Α', 0), ('Α1', 1), ('Α2', 1), ('Β', 0)]
    assert S.move(c, sid, b, 'up') and [t for t, _ in titles(c, sid)][:3] == ['Αρχική', 'Β', 'Α']
    assert not S.move(c, sid, a2, 'down') and S.move(c, sid, a2, 'up') and [t for t, _ in titles(c, sid)][-2:] == ['Α2', 'Α1']
    assert S.move(c, sid, b, 'in') and ('Β', 1) in titles(c, sid)                 # παιδί της «Αρχική»
    assert S.move(c, sid, b, 'out') and ('Β', 0) in titles(c, sid)
    assert S.move(c, sid, a1, 'out') and ('Α1', 0) in titles(c, sid)
    assert not S.move(c, sid, a1, 'out')                                                    # ήδη στη ρίζα
    assert S.move(c, sid, a1, 'in') and ('Α1', 1) in titles(c, sid)                       # ξανά υποσελίδα της προηγούμενης (Α)
    n = S.delete_page(c, sid, a); assert n == 3 and [t for t, _ in titles(c, sid)] == ['Αρχική', 'Β']
    assert S.get_page(c, sid, a1) is None


def test_depth_limit_and_parent_check(cl):
    sid = mk(cl); c = conn(); l1 = S.add_page(c, sid, 'L1'); l2 = S.add_page(c, sid, 'L2', parent=l1); l3 = S.add_page(c, sid, 'L3', parent=l2)
    assert l3 and S.add_page(c, sid, 'L4', parent=l3) is None and S.add_page(c, sid, 'X', parent=99999) is None
    sid2 = S.create(c, 'Άλλο'); assert S.add_page(c, sid2, 'Ξένος γονέας', parent=l1) is None           # γονέας από άλλο site


def test_page_limit(cl, monkeypatch):
    sid = mk(cl); c = conn(); monkeypatch.setattr(S, 'MAX_PAGES', 3); S.add_page(c, sid, 'x'); S.add_page(c, sid, 'y'); assert S.add_page(c, sid, 'z') is None


def test_orphans_and_cycles_do_not_hang(cl):
    sid = mk(cl); c = conn(); a = S.add_page(c, sid, 'Α'); b = S.add_page(c, sid, 'Β')
    c.execute('UPDATE site_page SET parent_id=? WHERE id=?', (b, a)); c.execute('UPDATE site_page SET parent_id=? WHERE id=?', (a, b)); c.execute('UPDATE site_page SET parent_id=777 WHERE title=?', ('Αρχική',))
    od = S.order(S.rows(c, sid)); assert 'Αρχική' in [p['title'] for p, _ in od]           # δεν κρεμάει· το ορφανό γίνεται ρίζα


def test_copy_site_keeps_tree_and_home(cl):
    sid = mk(cl); c = conn(); a = S.add_page(c, sid, 'Α'); S.add_page(c, sid, 'Α1', parent=a); S.save_site(c, sid, home=a, footer='υποσέλιδο'); n = S.copy_site(c, sid)
    assert titles(c, n) == titles(c, sid) and S.get(c, n)['opts']['footer'] == 'υποσέλιδο' and S.get(c, n)['opts']['home'] not in (0, a)
    S.delete_site(c, sid); assert c.execute('SELECT count(*) FROM site_page WHERE site_id=?', (sid,)).fetchone()[0] == 0 and titles(c, n)


def test_home_reset_when_deleted(cl):
    sid = mk(cl); c = conn(); a = S.add_page(c, sid, 'Α'); S.save_site(c, sid, home=a); S.delete_page(c, sid, a); assert S.get(c, sid)['opts']['home'] == 0
    S.save_site(c, sid, home=424242); assert S.get(c, sid)['opts']['home'] == 0


# ---------- deckmd με άλλο σύνολο οδηγιών ----------
def test_deckmd_site_directives_and_decks_unchanged():
    body = 'α\n\n::: quiz-ref 3\n:::\n\n::: callout tip Τίτλος\nκείμενο\n:::\n\n::: file a/b.pdf Λεζάντα\n:::'
    bl, w = deckmd.parse(body, S.DIRS); assert not w and [b['t'] for b in bl] == ['md', 'quiz-ref', 'callout', 'file'] and bl[1]['arg'] == '3' and bl[2]['arg'] == 'tip Τίτλος'
    assert deckmd.compose(deckmd.parse(deckmd.compose(bl), S.DIRS)[0]) == deckmd.compose(bl)
    bl2, w2 = deckmd.parse(body); assert [b['t'] for b in bl2] == ['md'] and any('quiz-ref' in x for x in w2)          # στις παρουσιάσεις μένουν ως κείμενο με προειδοποίηση
    assert deckmd.parse('::: step\nx\n:::', S.DIRS)[1] and deckmd.parse('::: step\nx\n:::')[0][0]['t'] == 'step' and deckmd.parse('::: embed https://x.com/a\n:::')[0][0]['t'] == 'embed'


# ---------- μπλοκ ----------
def page(sid, body, mode='export', domains=DOM, title='Σελίδα'):
    c = conn(); pid = S.add_page(c, sid, title, body=body); c.commit(); p = S.get_page(c, sid, pid); ctx = ctx_of(c, sid, mode, domains)
    h, w = S.page_html(ctx, p); c.close(); return h, w


def seed_quiz(c):
    qid = c.execute("INSERT INTO quiz(name,description) VALUES('Ερωτήσεις','περιγραφή')").lastrowid
    c.execute("INSERT INTO quiz_item(quiz_id,pos,kind,stem,options,answer,points,feedback,use_image) VALUES(?,?,?,?,?,?,?,?,?)", (qid, 1, 'tf', 'Το $V=IR$;', '[]', 'Σωστό', 1, '', 0))
    c.execute("INSERT INTO quiz_item(quiz_id,pos,kind,stem,options,answer,points,feedback,use_image) VALUES(?,?,?,?,?,?,?,?,?)", (qid, 2, 'mcq', 'Ποιο;', '["Α","Β"]', '1', 2, 'ναι', 1))
    c.execute("INSERT INTO quiz_item(quiz_id,pos,kind,stem,options,answer,points,feedback,use_image) VALUES(?,?,?,?,?,?,?,?,?)", (qid, 3, 'free', 'Εξήγησε', '[]', 'απάντηση <b>', 1, '', 0))
    return qid


def test_callout_and_markdown_and_escape(cl):
    sid = mk(cl); h, w = page(sid, '::: callout warning Πρόσεχε <x>\nΚείμενο **έντονο**\n:::\n\n<script>alert(1)</script>', title='<img src=x onerror=1>')
    assert "co-warning" in h and '<strong>έντονο</strong>' in h and 'Πρόσεχε &lt;x&gt;' in h and not w
    assert '<script>alert(1)' not in h and '<img src=x' not in h and '&lt;img src=x' in h


def test_callout_unknown_kind_warns(cl):
    sid = mk(cl); h, w = page(sid, '::: callout foo Τίτλος\nx\n:::'); assert any('callout' in x for x in w) and 'co-note' in h


def test_quiz_ref_snapshot_and_warnings(cl):
    sid = mk(cl); c = conn(); qid = seed_quiz(c); c.commit(); c.close()
    h, w = page(sid, f'::: quiz-ref {qid}\n:::')
    assert 'class=sqw' in h and h.count("class='q qi'") == 3 and 'sq-check' in h and 'data-answer=\'Σωστό\'' in h and 'απάντηση &lt;b&gt;' in h and 'katex' in h.lower()
    assert any('εικόνα' in x for x in w) and '<b>' not in h.split('Εξήγησε')[1][:200].replace('<b>Εξήγησε', '')
    h2, w2 = page(sid, '::: quiz-ref 9999\n:::'); assert 'Δεν υπάρχει quiz' in h2 and w2
    h3, w3 = page(sid, '::: quiz-ref abc\n:::'); assert w3 and 'sqw' not in h3


def test_quiz_ref_two_quizzes_same_page_and_empty(cl):
    sid = mk(cl); c = conn(); q1 = seed_quiz(c); q2 = seed_quiz(c); empty = c.execute("INSERT INTO quiz(name) VALUES('Κενό')").lastrowid; c.commit(); c.close()
    h, w = page(sid, f'::: quiz-ref {q1}\n:::\n\n::: quiz-ref {q2}\n:::\n\n::: quiz-ref {empty}\n:::'); assert h.count('<section class=sqw>') == 2 and any('κενό' in x for x in w)
    assert h.count("querySelectorAll('.sqw')") == 1                # ένα script για όλα τα quiz


def test_quiz_yaml_block(cl):
    sid = mk(cl); h, w = page(sid, '::: quiz\ntype: mcq\nstem: Ποιο;\noptions:\n  - Α\n  - Β\nanswer: 1\n:::'); assert not w and '<details><summary>Απάντηση</summary>' in h and 'Β' in h
    h2, w2 = page(sid, '::: quiz\ntype: mcq\nstem: x\n:::'); assert any(x.startswith('quiz:') for x in w2)


def test_deck_ref_card_and_missing(cl):
    sid = mk(cl); c = conn(); did = D.create(c, 'Παρουσίαση Α', 'free', 'Τίτλος Π'); D.add_slide(c, did); c.commit(); c.close()
    h, w = page(sid, f'::: deck-ref {did} Δες την παρουσίαση\n:::'); assert not w and f"href='deck-{did}.html'" in h and 'Δες την παρουσίαση' in h and 'target=_blank' in h
    hp, _ = page(sid, f'::: deck-ref {did}\n:::', mode='preview'); assert f"/sites/{sid}/deck/{did}" in hp
    assert page(sid, '::: deck-ref 4242\n:::')[1] and page(sid, '::: deck-ref x\n:::')[1]
    c = conn(); empty = D.create(c, 'Κενή', 'free'); c.commit(); c.close(); assert any('εμφανίσιμες' in x for x in page(sid, f'::: deck-ref {empty}\n:::')[1])


def test_file_block_safe_paths(cl, tmp_path):
    root = pathlib.Path(os.environ['THILEK_ROOT']); (root / 'C' / 'x').mkdir(parents=True, exist_ok=True)
    (root / 'C' / 'x' / 'a.pdf').write_bytes(b'%PDF-1.4 x'); (root / 'C' / 'x' / 'p.png').write_bytes(b'\x89PNG\r\n\x1a\nx'); (root / 'C' / 'x' / 'e.exe').write_bytes(b'MZ'); (root / 'C' / 'x' / 'big.pdf').write_bytes(b'0' * 10_000_001)
    (tmp_path / 'secret.pdf').write_bytes(b'TOPSECRET'); os.symlink(tmp_path / 'secret.pdf', root / 'C' / 'x' / 'link.pdf'); (root / '_kados').mkdir(exist_ok=True); (root / '_kados' / 'k.pdf').write_bytes(b'k')
    sid = mk(cl); h, w = page(sid, '::: file C/x/a.pdf Φυλλάδιο\n:::'); assert not w and 'file-a.pdf' in h and 'Φυλλάδιο' in h and 'PDF' in h
    hi, wi = page(sid, '::: file /C/x/p.png Εικόνα\n:::'); assert not wi and 'data:image/png;base64' in hi and '<figcaption>Εικόνα</figcaption>' in hi
    for bad in ('../secret.pdf', 'C/x/e.exe', 'C/x/missing.pdf', 'C/x/link.pdf', 'C/x/big.pdf', '_kados/k.pdf', 'C/../../secret.pdf', 'C/x/.hid.pdf', ''):
        hb, wb = page(sid, f'::: file {bad}\n:::'); assert wb and 'TOPSECRET' not in hb and 'file-' not in hb.split('<main>')[1], bad
    hp, _ = page(sid, '::: file C/x/a.pdf\n:::', mode='preview'); assert f'/sites/{sid}/file?p=C/x/a.pdf' in hp


def test_embed_block_click_and_domain_check(cl):
    sid = mk(cl); h, w = page(sid, '::: embed https://www.youtube.com/watch?v=dQw4w9WgXcQ\nΒίντεο\n:::'); assert not w and 'embgo' in h and 'youtube.com/embed/dQw4w9WgXcQ' in h and 'iframe' in h.split('<script>')[-1] and 'frame-src' in h
    h2, w2 = page(sid, '::: embed https://evil.example.org/x\n:::'); assert any('embed' in x for x in w2) and "class='emb embc'" not in h2 and 'Σύνδεσμος· ' in h2
    h3, w3 = page(sid, '::: embed http://www.youtube.com/watch?v=dQw4w9WgXcQ\n:::'); assert w3


def test_math_katex_only_when_needed(cl):
    sid = mk(cl); a, _ = page(sid, 'Χωρίς τύπους.'); b, _ = page(sid, 'Τύπος $x^2$ εδώ.')
    assert 'renderMathInElement' not in a and 'renderMathInElement' in b and len(b) > len(a) + 50_000


# ---------- σελίδα: μενού, κρυφές, σύνδεσμοι ----------
def test_menu_hidden_section_cards_and_prev_next(cl):
    sid = mk(cl); c = conn(); sec = S.add_page(c, sid, 'Κεφάλαιο 1', kind='section'); p1 = S.add_page(c, sid, 'Θεωρία', parent=sec, body='Δες [την άσκηση](thilek://page/askisi) και [άγνωστη](thilek://page/nope).')
    p2 = S.add_page(c, sid, 'Άσκηση', parent=sec); S.update_page(c, sid, p2, slug='askisi'); S.add_page(c, sid, 'Κρυφή σελίδα', body='x'); hid = S.get_page(c, sid, S.add_page(c, sid, 'Μυστικό'))['id']; S.update_page(c, sid, hid, hidden=True)
    S.add_page(c, sid, 'Παιδί του κρυφού', parent=hid); c.commit(); ctx = ctx_of(c, sid); p = S.get_page(c, sid, p1); h, w = S.page_html(ctx, p)
    nav = h.split('<nav')[1].split('</nav>')[0]
    assert 'Κεφάλαιο 1' in nav and "class=sec" in nav and 'Μυστικό' not in h and 'Παιδί του κρυφού' not in h and 'href="askisi.html"' in h and 'class="broken"' in h
    assert "href='askisi.html'>Άσκηση →" in h and "← Αρχική" in h and 'Κεφάλαιο 1 ›' not in nav                                          # επόμενη/προηγούμενη χωρίς ενότητες
    hs, _ = S.page_html(ctx, S.get_page(c, sid, sec)); assert 'class=card' in hs and 'Θεωρία' in hs and 'Άσκηση' in hs
    assert '<div class=crumb>Κεφάλαιο 1</div>' in h


def test_home_and_footer(cl):
    sid = mk(cl); c = conn(); a = S.add_page(c, sid, 'Η αρχική μου'); S.save_site(c, sid, title='Τίτλος site', footer='© Σχολείο', home=a); c.commit()
    ctx = ctx_of(c, sid); assert ctx.home()['id'] == a; h, _ = S.page_html(ctx, S.get_page(c, sid, a)); assert '© Σχολείο' in h and 'Τίτλος site' in h


def test_live_override_does_not_change_db(cl):
    sid = mk(cl); c = conn(); p = S.get_page(c, sid, S.pages(c, sid)[0]['id']); ctx = ctx_of(c, sid, 'preview')
    h, _ = S.page_html(ctx, p, body='ΝΕΟ ΚΕΙΜΕΝΟ', title='Νέος τίτλος'); assert 'ΝΕΟ ΚΕΙΜΕΝΟ' in h and 'Νέος τίτλος' in h and S.get_page(c, sid, p['id'])['title'] == 'Αρχική'


# ---------- zip ----------
def test_build_zip_structure_and_flat_names(cl):
    root = pathlib.Path(os.environ['THILEK_ROOT']); (root / 'C').mkdir(exist_ok=True); (root / 'C' / 'a.pdf').write_bytes(b'%PDF-1.4 x')
    sid = mk(cl); c = conn(); qid = seed_quiz(c); did = D.create(c, 'Π', 'free', 'Π'); s1 = D.add_slide(c, did); D.update_slide(c, did, s1, title='Διαφάνεια', body='Κείμενο')
    pg = S.add_page(c, sid, 'Υλικό', body=f'::: quiz-ref {qid}\n:::\n\n::: deck-ref {did}\n:::\n\n::: file C/a.pdf\n:::\n\nΤύπος $x$')
    hid = S.add_page(c, sid, 'Κρυφό'); S.update_page(c, sid, hid, hidden=True); c.commit()
    data, fname, model = S.build_zip(c, sid, DOM); c.close(); z = zipfile.ZipFile(io.BytesIO(data)); names = set(z.namelist())
    assert fname.endswith('-site.zip') and {'index.html', 'archiki.html', 'data.json', 'README.txt', f'deck-{did}.html', 'file-a.pdf'} <= names
    assert not any('/' in n or '\\' in n for n in names) and 'kryfo.html' not in names and z.read('index.html') == z.read('archiki.html')
    assert all(pathlib.Path(n).suffix.lower() in publish.ALLOWED | {'.txt'} for n in names if n != 'README.txt'), names                 # ώστε να περνούν από publish.save_site (0.35)
    dj = json.loads(z.read('data.json')); assert dj['home'] == 'archiki.html' and [p['title'] for p in dj['pages']] == ['Αρχική', 'Υλικό'] and dj['decks'][0]['file'] == f'deck-{did}.html' and dj['warnings']
    assert b'class=sqw' in z.read([n for n in names if n.endswith('.html') and n not in ('index.html', 'archiki.html') and not n.startswith('deck-')][0]) and b'<section' in z.read(f'deck-{did}.html')
    assert z.read('file-a.pdf') == b'%PDF-1.4 x'


def test_build_zip_errors(cl):
    sid = mk(cl); c = conn(); c.execute('UPDATE site_page SET hidden=1 WHERE site_id=?', (sid,)); c.commit()
    with pytest.raises(ValueError): S.build_zip(c, sid, DOM)
    with pytest.raises(ValueError): S.build_zip(c, 9999, DOM)


# ---------- HTTP ----------
def test_pages_need_auth(cl):
    for u in ('/sites', '/sites/1', '/sites/1/view/index', '/sites/1/export.zip', '/sites/1/file?p=x.pdf', '/sites/1/deck/1', '/static/site.js'):
        r = cl.get(u); assert r.status_code == 401 or u == '/static/site.js', u


def test_post_needs_same_origin(cl):
    sid = mk(cl); assert cl.post('/sites/new', data={'name': 'x'}, auth=A, headers={'origin': 'http://evil.example'}, follow_redirects=False).status_code == 403
    assert cl.post(f'/sites/{sid}/delete', auth=A, headers={'origin': 'http://evil.example'}, follow_redirects=False).status_code == 403 and conn().execute('SELECT count(*) FROM site').fetchone()[0] == 1


def test_http_flow(cl):
    r = cl.get('/sites', auth=A); assert r.status_code == 200 and 'Νέο site' in r.text
    r = cl.post('/sites/new', data={'name': 'Ηλεκτρολογία Α'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303; sid = int(r.headers['location'].split('/')[-1])
    r = cl.get(f'/sites/{sid}', auth=A); assert r.status_code == 200 and 'Αρχική' in r.text and 'data-blk=quizref' in r.text and '/static/site.js' in r.text and '<script>' not in r.text.replace('<script src', '')
    r = cl.post(f'/sites/{sid}/add', data={'title': 'Θεωρία', 'kind': 'page'}, auth=A, headers=H, follow_redirects=False); pid = int(r.headers['location'].split('p=')[-1])
    r = cl.post(f'/sites/{sid}/page/{pid}', data={'act': 'save', 'title': 'Θεωρία <b>', 'slug': 'theoria', 'kind': 'page', 'body': 'Γεια **σου** $x$', 'hidden': ''}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    c = conn(); p = S.get_page(c, sid, pid); assert p['title'] == 'Θεωρία <b>' and p['slug'] == 'theoria' and '**σου**' in p['body']; c.close()
    r = cl.get(f'/sites/{sid}/view/theoria', auth=A); csp = r.headers['content-security-policy']
    assert r.status_code == 200 and '<strong>σου</strong>' in r.text and 'Θεωρία &lt;b&gt;' in r.text and 'Θεωρία <b>' not in r.text and "default-src 'none'" in csp and 'nosniff' == r.headers['x-content-type-options']
    assert cl.get(f'/sites/{sid}/view/index', auth=A).status_code == 200 and cl.get(f'/sites/{sid}/view/nope', auth=A).status_code == 404
    r = cl.post(f'/sites/{sid}/page/{pid}', data={'act': 'up'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    r = cl.post(f'/sites/{sid}/preview/{pid}', data={'title': 'Προβολή', 'body': 'ΖΩΝΤΑΝΟ', 'kind': 'page'}, auth=A, headers=H); assert r.status_code == 200 and 'ΖΩΝΤΑΝΟ' in r.text
    c = conn(); assert S.get_page(c, sid, pid)['title'] == 'Θεωρία <b>'; c.close()                       # η προεπισκόπηση δεν γράφει
    r = cl.post(f'/sites/{sid}/save', data={'name': 'Νέο όνομα', 'title': 'Τ', 'theme': 'dark', 'footer': 'φουτερ', 'home': str(pid)}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    c = conn(); s = S.get(c, sid); assert s['theme'] == 'dark' and s['opts']['home'] == pid and s['name'] == 'Νέο όνομα'; c.close()
    r = cl.get(f'/sites/{sid}/export.zip', auth=A); assert r.status_code == 200 and r.headers['content-type'] == 'application/zip' and 'filename*=UTF-8' in r.headers['content-disposition']
    assert 'index.html' in zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    r = cl.post(f'/sites/{sid}/page/{pid}', data={'act': 'delete'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and S.get_page(conn(), sid, pid) is None
    r = cl.post(f'/sites/{sid}/copy', auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    assert cl.post(f'/sites/{sid}/delete', auth=A, headers=H, follow_redirects=False).status_code == 303 and conn().execute('SELECT count(*) FROM site WHERE id=?', (sid,)).fetchone()[0] == 0


def test_http_missing_and_bad_input(cl):
    assert cl.get('/sites/999', auth=A).status_code == 404 and cl.get('/sites/999/export.zip', auth=A).status_code == 404
    sid = mk(cl); assert cl.post(f'/sites/{sid}/page/99999', data={'act': 'save'}, auth=A, headers=H).status_code == 404
    pid = S.pages(conn(), sid)[0]['id']; assert cl.post(f'/sites/{sid}/page/{pid}', data={'act': 'boom'}, auth=A, headers=H).status_code == 422
    c = conn(); c.execute('UPDATE site_page SET hidden=1'); c.commit(); assert cl.get(f'/sites/{sid}/export.zip', auth=A).status_code == 422


def test_file_route_rejects_traversal_and_serves_sandboxed(cl, tmp_path):
    root = pathlib.Path(os.environ['THILEK_ROOT']); (root / 'C').mkdir(exist_ok=True); (root / 'C' / 'a.pdf').write_bytes(b'%PDF-1.4 x'); (tmp_path / 'secret.txt').write_text('secret')
    sid = mk(cl); r = cl.get(f'/sites/{sid}/file?p=C/a.pdf', auth=A); assert r.status_code == 200 and r.content.startswith(b'%PDF') and 'sandbox' in r.headers['content-security-policy'] and r.headers['content-disposition'].startswith('inline')
    for bad in ('../secret.txt', '..%2Fsecret.txt', '/etc/passwd', 'C/../../secret.txt', 'C/a.exe', ''): assert cl.get(f'/sites/{sid}/file', params={'p': bad}, auth=A).status_code == 404, bad


def test_deck_route_and_help_and_menu(cl):
    sid = mk(cl); c = conn(); did = D.create(c, 'Π', 'free', 'Π'); s1 = D.add_slide(c, did); D.update_slide(c, did, s1, title='Τ', body='κείμενο'); c.commit(); c.close()
    r = cl.get(f'/sites/{sid}/deck/{did}', auth=A); assert r.status_code == 200 and '<section' in r.text and 'frame-src' in r.headers['content-security-policy'] and cl.get(f'/sites/{sid}/deck/777', auth=A).status_code == 404
    r = cl.get('/sites', auth=A); assert "href='/sites'" in r.text and 'Site μαθήματος' in r.text
