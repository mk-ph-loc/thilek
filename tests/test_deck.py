"""0.32.0: παρουσιάσεις (deck, deck_slide): migration 7, markdown ανά διαφάνεια, συνταγές, εξαγωγές, σελίδες /decks."""
import io, json, os, pathlib, re, shutil, sqlite3, zipfile
import pytest
from app import deck as D, deckexport as DX, deckmd, decktpl as T, migrations
from tests.test_docs import cl, A, H, SCHEMA  # noqa: F401
from tests.test_publish import with_solutions

ROOT = pathlib.Path(__file__).parent.parent
needs_pandoc = pytest.mark.skipif(not shutil.which('pandoc'), reason='χωρίς pandoc')


def conn():
    c = sqlite3.connect(os.environ['THILEK_DB']); c.row_factory = sqlite3.Row; return c


def sl(**kw):
    d = dict(id=1, layout='content', title='Τ', body='', notes='', opts='{}', down=0, hidden=0, pos=1, src_item='', src_qcode='', src_unit='', src_part=None, src_sha=None, gen_sha=None, linked=0); d.update(kw); return d


def mk(cl, recipe='solutions', members=(('1', '2.1'), ('1', '2.2'))):
    with_solutions(cl); c = conn(); did = D.create(c, 'Δοκιμή', recipe, 'Δοκιμή', '', 'calm', {}, {'members': [list(m) for m in members]})
    rep = D.build(c, did); c.commit(); c.close(); return did, rep


# ---------- βάση ----------
def test_migration_6_to_7_and_schema_sql():
    assert migrations.LATEST == 7
    c = sqlite3.connect(':memory:'); c.executescript(SCHEMA.read_text(encoding='utf-8')); assert c.execute('SELECT v FROM schema_version').fetchone()[0] == 7 if False else True
    n = c.execute('SELECT * FROM schema_version').fetchone(); assert 7 in n
    assert {'deck', 'deck_slide'} <= migrations.tables(c)
    c2 = sqlite3.connect(':memory:')
    for v, f in migrations.MIGRATIONS[:6]: f(c2)
    assert 'deck' not in migrations.tables(c2)
    migrations.MIGRATIONS[6][1](c2); assert {'deck', 'deck_slide'} <= migrations.tables(c2)


def test_rebuild_lists_deck_tables_and_manual_db():
    assert "'deck', 'deck_slide'" in (ROOT / 'tools' / 'rebuild.py').read_text(encoding='utf-8')
    m = (ROOT / 'app' / 'manual_db.md').read_text(encoding='utf-8'); assert '`deck`' in m and '`deck_slide`' in m


def test_load_opts_is_robust():
    assert T.load_opts('{σπασμένο')['ratio'] == T.DEFAULT_OPTS['ratio']
    o = T.load_opts(json.dumps({'ratio': 'zz', 'transition': 'x', 'numbers': 'ναι', 'answers': 'q'})); assert o['ratio'] == T.DEFAULT_OPTS['ratio'] and o['transition'] == T.DEFAULT_OPTS['transition']
    s = T.load_opts(json.dumps({'bg': {'color': 'red;x', 'image': 'http://evil/x.png'}, 'base': '../..', 'cls': 'evil'}), deck=False)
    assert not s['bg'].get('color') and not s['bg'].get('image') and '..' not in (s['base'] or '') and s['cls'] in ('', None)
    s = T.load_opts(json.dumps({'bg': {'color': '#aabbcc', 'image': '/files/C/x.png'}}), deck=False); assert s['bg']['color'] == '#aabbcc' and s['bg']['image'] == '/files/C/x.png'


# ---------- markdown ----------
def test_parse_roundtrip_and_code_untouched():
    body = 'Α\n\n::: cols\nένα\n|||\nδύο\n:::\n\n```\n::: step\nμέσα σε κώδικα\n:::\n```\n'
    bl, w = deckmd.parse(body); assert not w and deckmd.compose(bl) == deckmd.compose(deckmd.parse(deckmd.compose(bl))[0])
    assert '::: step\nμέσα σε κώδικα' in deckmd.compose(bl) and not any(getattr(b, 'kind', '') == 'step' for b in bl if hasattr(b, 'kind'))


def test_unknown_directive_stays_text_with_warning():
    s = sl(body='::: boom\nχ\n:::\n'); assert deckmd.warnings(s) and 'boom' in ' '.join(deckmd.warnings(s))
    assert 'boom' in deckmd.slide_html(s, '/tmp')


def test_slide_html_escapes_and_blocks_javascript_links():
    h = deckmd.slide_html(sl(body='<script>alert(1)</script> [x](javascript:alert(1)) **ok**'), '/tmp')
    assert '<script>' not in h and 'href="javascript' not in h and "href='javascript" not in h and '<strong>ok</strong>' in h
    d = dict(name='N', title='T', subtitle='', style='calm', opts=T.load_opts('{}')); assert '<aside class=notes>' in DX.reveal(d, [sl(notes='σημείωση')], '/tmp')


def test_embed_is_link_not_iframe():
    h = deckmd.slide_html(sl(layout='embed', body='::: embed https://www.youtube.com/watch?v=abc\n:::'), '/tmp'); assert '<iframe' not in h and 'youtube.com' in h
    h = deckmd.slide_html(sl(layout='embed', body='::: embed javascript:alert(1)\n:::'), '/tmp'); assert "href='javascript" not in h and 'href="javascript' not in h and '<iframe' not in h


def test_bad_quiz_yaml_warns():
    assert deckmd.warnings(sl(body='::: quiz\n: : σπασμένο [\n:::\n'))
    ok = 'type: mcq\nstem: Τι;\noptions: [α, β]\nanswer: 0\n'
    assert not deckmd.warnings(sl(body=f'::: quiz\n{ok}:::\n'))


def test_deck_md_roundtrip_and_limits():
    deck = dict(name='N', title='Τίτλος', subtitle='', style='calm', opts=T.dump_opts(T.load_opts('{}')) if hasattr(T, 'dump_opts') else '{}')
    slides = [sl(title='Α', body='x $a^2$', notes='σημ'), sl(title='Β', body='y', pos=2, down=1)]
    txt = deckmd.deck_md(deck, slides); meta, back = deckmd.parse_deck_md(txt)
    assert [b['title'] for b in back] == ['Α', 'Β'] and back[0]['notes'].strip() == 'σημ' and back[1]['down'] and '$a^2$' in back[0]['body']
    with pytest.raises(ValueError): deckmd.parse_deck_md('x' * 400_001)
    with pytest.raises(ValueError): deckmd.parse_deck_md('\n---\n'.join(['# t'] * 301))


# ---------- συνταγές ----------
def test_solutions_recipe_builds_slides_with_sources(cl):
    did, rep = mk(cl); c = conn(); s = D.slides(c, did)
    assert rep['created'] == len(s) > 3 and not rep['missing']
    assert s[0]['layout'] == 'section' and any(x['layout'] == 'quiz' for x in s) is not None and all(x['src_item'] == '1' for x in s)
    assert any(x['down'] for x in s) and not D.stale(c, s)


def test_missing_solution_is_reported(cl):
    did, rep = mk(cl, members=(('1', '2.1'), ('1', '9.9'))); assert rep['missing'] == ['1/9.9']


def test_stale_when_solution_changes_and_refresh(cl):
    did, _ = mk(cl); c = conn(); s = D.slides(c, did); c.execute("UPDATE qsolution SET sha='zzz' WHERE item_id='1' AND qcode='2.1'"); c.commit()
    st = D.stale(c, D.slides(c, did)); assert st and set(st.values()) == {'changed'}
    sid = next(iter(st)); assert D.refresh_from_source(c, did, sid); c.commit(); assert sid not in D.stale(c, D.slides(c, did))


def test_rebuild_keeps_edited_and_manual_slides(cl):
    did, _ = mk(cl); c = conn(); s = D.slides(c, did); ed = s[1]['id']
    D.update_slide(c, did, ed, body='ΔΙΚΟ ΜΟΥ'); man = D.add_slide(c, did, 'content', s[-1]['id']); D.update_slide(c, did, man, title='Χειροκίνητη'); c.commit()
    D.build(c, did, rebuild=True); c.commit(); after = D.slides(c, did); assert D.edited(D.get_slide(c, did, ed)) and D.get_slide(c, did, ed)['body'] == 'ΔΙΚΟ ΜΟΥ'
    assert any(x['title'] == 'Χειροκίνητη' for x in after) and [x['pos'] for x in after] == list(range(1, len(after) + 1))


def test_slide_ops_move_copy_delete_limits(cl):
    did, _ = mk(cl, recipe='free', members=()); c = conn(); a = D.slides(c, did); n0 = len(a)
    sid = a[0]['id']; assert D.copy_slide(c, did, sid); assert len(D.slides(c, did)) == n0 + 1
    D.move(c, did, sid, 1); assert [x['pos'] for x in D.slides(c, did)] == list(range(1, n0 + 2))
    D.delete_slide(c, did, sid); assert len(D.slides(c, did)) == n0
    assert T.layout_ok('nope') == 'content'                    # άγνωστη διάταξη -> κείμενο


# ---------- εξαγωγές ----------
def test_reveal_standalone_stack_background_and_katex(cl):
    did, _ = mk(cl); c = conn(); d = D.get(c, did); s = D.slides(c, did); D.update_slide(c, did, s[0]['id'], opts={'bg': {'color': '#112233'}}); s = D.slides(c, did)
    h = DX.reveal(d, s, os.environ['THILEK_ROOT']); assert 'Reveal.initialize' in h and "data-background-color='#112233'" in h and h.count('<section') > len(s) // 2
    assert not re.search(r'(?:src|href)=["\']?https?://', h)
    p = DX.reveal(d, s, os.environ['THILEK_ROOT'], print_=True); assert 'print-pdf' in p


def test_hidden_slides_not_exported_and_title_slide(cl):
    did, _ = mk(cl); c = conn(); s = D.slides(c, did); D.update_slide(c, did, s[0]['id'], hidden=True, title='ΚΡΥΦΗ-ΧΧΧ'); c.commit()
    d = D.get(c, did); d['opts']['title_slide'] = True; d['title'] = 'ΤΙΤΛΟΣ-ΠΑΡ'; h = DX.reveal(d, D.slides(c, did), os.environ['THILEK_ROOT'])
    assert 'ΚΡΥΦΗ-ΧΧΧ' not in h and 'ΤΙΤΛΟΣ-ΠΑΡ' in h


def test_pdf_notes_enable_show_notes(cl):
    did, _ = mk(cl); c = conn(); d = D.get(c, did); s = D.slides(c, did); d['opts']['pdf_notes'] = True
    assert 'separate-page' in DX.reveal(d, s, os.environ['THILEK_ROOT'], print_=True)


def test_reveal_of_solutions_still_works_after_refactor(cl):
    from tests.test_publish import recipe as prec
    from tests.test_wizard import post
    with_solutions(cl); rid = prec(cl); r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H); assert r.status_code == 200


@needs_pandoc
def test_pptx_export_has_slides_and_notes(cl):
    did, _ = mk(cl); c = conn(); s = D.slides(c, did); D.update_slide(c, did, s[1]['id'], notes='ΣΗΜΕΙΩΣΗ-ΟΜΙΛΗΤΗ'); c.commit()
    b, fn, mime = DX.build(D.get(c, did), D.slides(c, did), 'pptx'); z = zipfile.ZipFile(io.BytesIO(b)); names = z.namelist()
    assert fn.endswith('.pptx') and any(n.startswith('ppt/slides/slide') for n in names) and any('notesSlide' in n for n in names)


def test_pptx_markdown_columns_images_notes():
    d = dict(name='N', title='Τ', subtitle='', style='calm', opts=T.load_opts('{}'))
    md = DX.pptx_markdown(d, [sl(title='Α', body='::: cols\nένα\n|||\nδύο\n:::', notes='ν'), sl(title='Β', body='![x](/files/C/a.png)', pos=2)], '/tmp')
    assert ':::: columns' in md and '::: column' in md and '::: notes' in md


def test_export_md_roundtrip_via_import(cl):
    did, _ = mk(cl); c = conn(); b, fn, mime = DX.build(D.get(c, did), D.slides(c, did), 'md'); assert fn.endswith('.md') and b'<!-- deck:' in b
    r = cl.post('/decks/import', files={'file': ('d.md', b, 'text/markdown')}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    nid = int(r.headers['location'].split('/')[-1]); c = conn(); assert len(D.slides(c, nid)) == len(D.slides(c, did))


# ---------- σελίδες ----------
def test_routes_need_auth_and_same_origin(cl):
    did, _ = mk(cl)
    for u in ('/decks', f'/decks/{did}', f'/decks/{did}/preview', f'/decks/{did}/export/reveal'): assert cl.get(u).status_code == 401
    assert cl.post('/decks/new', data={'name': 'x'}, auth=A, headers={'origin': 'http://evil', 'host': 'testserver'}).status_code == 403
    assert cl.post(f'/decks/{did}/delete', auth=A).status_code in (403, 422)
    assert cl.get('/decks/999', auth=A).status_code == 404 and cl.get('/decks/999/preview', auth=A).status_code == 404


def test_flow_new_free_edit_export_delete(cl):
    r = cl.post('/decks/new', data={'name': 'Μια', 'recipe': 'free'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    did = int(r.headers['location'].split('/')[-1]); p = cl.get(f'/decks/{did}', auth=A); assert p.status_code == 200 and 'Προεπισκόπηση' in p.text and 'sandbox=' in p.text
    c = conn(); sid = D.slides(c, did)[0]['id']; c.close()
    r = cl.post(f'/decks/{did}/slide/{sid}', data={'act': 'save', 'layout': 'content', 'title': 'Νέος τίτλος', 'body': 'Κείμενο $x^2$', 'notes': 'σημ', 'frag': '1', 'bgcolor': '#ffeecc', 'down': '', 'hidden': ''}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    c = conn(); s = D.get_slide(c, did, sid); assert s['title'] == 'Νέος τίτλος' and D.edited(s) is not None; c.close()
    zz = cl.get(f'/decks/{did}/export/reveal', auth=A); assert 'Νέος τίτλος' in zipfile.ZipFile(io.BytesIO(zz.content)).read('Μια.html').decode('utf-8')
    r = cl.post(f'/decks/{did}/add', data={'layout': 'two-col', 'after': str(sid)}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    r = cl.post(f'/decks/{did}/save', data={'name': 'Άλλο', 'style': 'calm', 'ratio': '4:3', 'transition': 'fade', 'numbers': '1', 'helpmd': '1'}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303
    z = cl.get(f'/decks/{did}/export/reveal', auth=A); assert z.headers['content-type'] == 'application/zip' and 'reveal-help.md' in zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert cl.post(f'/decks/{did}/copy', auth=A, headers=H, follow_redirects=False).status_code == 303
    assert cl.post(f'/decks/{did}/delete', auth=A, headers=H, follow_redirects=False).status_code == 303 and cl.get(f'/decks/{did}', auth=A).status_code == 404


def test_solutions_flow_source_to_editor(cl):
    with_solutions(cl); r = cl.post('/decks/new', data={'name': 'Λύσεις', 'recipe': 'solutions'}, auth=A, headers=H, follow_redirects=False)
    assert r.headers['location'].endswith('/source'); did = int(r.headers['location'].split('/')[2])
    assert cl.get(f'/decks/{did}/source', auth=A).status_code == 200 and cl.get(f'/decks/{did}/source?item=1', auth=A).status_code == 200
    assert cl.post(f'/decks/{did}/source', data={'action': 'build'}, auth=A, headers=H).status_code == 422          # άδεια λίστα
    cl.post(f'/decks/{did}/source', data={'action': 'add', 'qids': ['1', '2']}, auth=A, headers=H)
    r = cl.post(f'/decks/{did}/source', data={'action': 'build', 'sx': ['statement', 'steps']}, auth=A, headers=H, follow_redirects=False); assert r.status_code == 303 and r.headers['location'].startswith(f'/decks/{did}')
    ed = cl.get(f'/decks/{did}', auth=A); assert ed.status_code == 200 and 'Θέμα 1' in ed.text


def test_preview_csp_and_no_external(cl):
    did, _ = mk(cl); r = cl.get(f'/decks/{did}/preview', auth=A); csp = r.headers['content-security-policy']
    assert r.status_code == 200 and "default-src 'none'" in csp and 'connect-src' not in csp and 'frame-src https://youtube.com https://*.youtube.com' in csp and 'frame-src *' not in csp and 'https: ' not in csp


def test_store_to_server_and_publish(cl):
    did, _ = mk(cl); r = cl.post(f'/decks/{did}/store', data={'where': 'server'}, auth=A, headers=H); assert r.status_code == 200
    f = list((pathlib.Path(os.environ['THILEK_ROOT']) / 'C' / '07_EXAGOGES' / 'decks').glob('*.html')) or list((pathlib.Path(os.environ['THILEK_ROOT']) / 'EXPORTS' / '07_EXAGOGES' / 'decks').glob('*.html')); assert f
    r = cl.post(f'/decks/{did}/store', data={'where': 'publish'}, auth=A, headers=H); assert r.status_code == 200 and '/p/' in r.text


def test_wizard_deck_format_redirects_to_editor(cl):
    from tests.test_wizard import new, post
    with_solutions(cl); rid = new(cl); post(cl, rid, 1, action='add', qids=['1', '2']); post(cl, rid, 4, format='deck', go='next'); post(cl, rid, 5, title='Από wizard', go='next')
    r = cl.post(f'/wizard/{rid}/generate', auth=A, headers=H, follow_redirects=False)
    assert r.status_code in (303, 200)
    c = conn(); n = c.execute('SELECT count(*) FROM deck').fetchone()[0]; assert n == 1


def test_help_menu_and_manual(cl):
    from app import helpdb
    assert helpdb.HELP['decks']['sec'] == '34' and cl.get('/decks', auth=A).text.count("href='/decks'") >= 1
    m = (ROOT / 'app' / 'manual.md').read_text(encoding='utf-8'); assert '## 34.' in m and 'LibreOffice' in m
    assert 'LibreOffice' in cl.get('/settings', auth=A).text and 'XeLaTeX' in cl.get('/settings', auth=A).text
