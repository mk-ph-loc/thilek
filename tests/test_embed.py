"""0.33.0: embed με λίστα επιτρεπτών domains, designer (εργαλειοθήκη, ζωντανή προεπισκόπηση), CSP προεπισκόπησης και δημοσιεύσεων."""
import os, re, sqlite3
import pytest
from app import deck as D, deckexport as DX, deckmd, decktpl as T, embed as EM
from tests.test_docs import cl, A, H  # noqa: F401
from tests.test_deck import conn, mk, sl

DOM = EM.hosts('youtube.com,youtube-nocookie.com,geogebra.org,falstad.com')
YT = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'


def emb(url=YT, cap='Βίντεο', params=None, domains=DOM, mode='reveal'): return EM.render(url, cap, params or {}, domains, mode)


def test_round_trip_embed_with_params_and_legacy_form():
    bl, w = deckmd.parse('::: embed https://www.geogebra.org/m/abc123 h=400 ratio=4:3 start=5\nΛεζάντα\n:::'); assert not w
    b = bl[0]; assert b['url'] == 'https://www.geogebra.org/m/abc123' and b['params'] == {'ratio': '4:3', 'h': 400, 'start': 5} and b['caption'] == 'Λεζάντα'
    txt = deckmd.compose(bl); assert txt.splitlines()[0] == '::: embed https://www.geogebra.org/m/abc123 ratio=4:3 h=400 start=5' and deckmd.compose(deckmd.parse(txt)[0]) == txt
    old, w = deckmd.parse('::: embed https://youtu.be/dQw4w9WgXcQ\n:::'); assert not w and old[0]['params'] == {}


def test_unknown_and_out_of_range_params_warn():
    _, w = deckmd.parse('::: embed https://x.com/a h=9999 foo=1 ratio=9:9\n:::'); assert w and 'h=9999' in w[0] and 'foo=1' in w[0]


@pytest.mark.parametrize('url', ['http://www.youtube.com/watch?v=dQw4w9WgXcQ', 'https://user@www.youtube.com/x', 'https://www.youtube.com:8443/x', 'https://1.2.3.4/x', 'https://evil-youtube.com/x',
                                 'https://youtube.com.evil.org/x', 'https://www.youtube.com/x y', 'javascript:alert(1)', 'https://www.youtube.com/\\evil', "https://www.youtube.com/x'onload=1"])
def test_check_rejects(url): assert not EM.check(url, DOM)[0]


def test_check_accepts_subdomain_and_exact():
    assert EM.check('https://www.geogebra.org/m/x', DOM)[0] and EM.check('https://geogebra.org/m/x', DOM)[0] and EM.check('https://youtube.com:443/x', DOM)[0]
    assert not EM.check('https://www.geogebra.org/m/x', [])[0]


def test_youtube_conversion_and_start():
    for u in (YT, 'https://youtu.be/dQw4w9WgXcQ', 'https://www.youtube.com/shorts/dQw4w9WgXcQ', 'https://m.youtube.com/embed/dQw4w9WgXcQ'):
        assert EM.to_src(u, {}, DOM) == 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'
    assert EM.to_src(YT + '&t=1m30s', {}, DOM).endswith('?start=90') and EM.to_src(YT, {'start': 7}, DOM).endswith('?start=7')
    assert EM.to_src(YT, {}, EM.hosts('youtube.com')).startswith('https://www.youtube.com/embed/')          # χωρίς nocookie στη λίστα
    assert EM.to_src('https://www.youtube.com/watch?v=short', {}, DOM) == 'https://www.youtube.com/watch?v=short'


def test_geogebra_and_falstad():
    assert EM.to_src('https://www.geogebra.org/m/abc123', {}, DOM) == 'https://www.geogebra.org/material/iframe/id/abc123'
    f = 'https://www.falstad.com/circuit/circuitjs.html?ctz=CQAgjCAMB0'; assert EM.to_src(f, {}, DOM) == f and EM.check(f, DOM)[0]


def test_iframe_attributes_and_escaping():
    h = emb(cap='Α "β" <i>'); assert '<iframe data-src=' in h and "sandbox='allow-scripts allow-same-origin allow-popups allow-presentation'" in h and 'referrerpolicy=' in h and 'loading=lazy' in h
    assert '<i>' not in h and '&lt;i&gt;' in h and 'target=_blank' in h and 'noopener' in h and 'aspect-ratio:16 / 9' in h
    assert 'height:300px' in emb(params={'h': 300}) and 'aspect-ratio:4 / 3' in emb(params={'ratio': '4:3'})


def test_host_not_allowed_is_card_with_warning_no_iframe():
    h = emb('https://example.org/page'); assert '<iframe' not in h and 'example.org' in h and 'δεν είναι στη λίστα' in h
    assert '<iframe' not in emb(domains=[]) and '<iframe' not in emb(mode='print')
    s = sl(body='::: embed https://example.org/page\n:::'); assert any('δεν είναι στη λίστα' in x for x in deckmd.warnings(s, DOM)) and not deckmd.warnings(s)       # None = χωρίς έλεγχο host
    assert not deckmd.warnings(sl(body=f'::: embed {YT}\n:::'), DOM)


def test_click_mode_has_no_iframe_until_click():
    h = emb(mode='click'); assert '<iframe' not in h and 'embgo' in h and "data-embed='https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'" in h and 'μόνο αν πατήσεις' in h


def test_reveal_export_modes_and_meta_csp(cl):
    did, _ = mk(cl, recipe='free', members=()); c = conn(); d = D.get(c, did); s = D.slides(c, did)
    D.update_slide(c, did, s[0]['id'], body=f'::: embed {YT}\nΒίντεο\n:::'); s = D.slides(c, did)
    root = os.environ['THILEK_ROOT']; h = DX.reveal(d, s, root, domains=DOM)
    assert 'data-src=' in h and re.search(r"<meta http-equiv='Content-Security-Policy' content=\"frame-src https://youtube.com https://\*\.youtube\.com", h) and 'object-src &#x27;none&#x27;' in h
    p = DX.reveal(d, s, root, print_=True, domains=DOM); assert '<iframe data-src' not in p and 'youtube.com/watch' in p
    pub = DX.reveal(d, s, root, publish=True, domains=DOM); assert '<iframe data-src' not in pub and 'class=embgo' in pub and "document.createElement('iframe')" in pub and 'http-equiv' not in pub
    assert 'class=embgo' not in DX.reveal(d, s, root, publish=True, domains=[]) and "createElement('iframe')" not in DX.reveal(d, s, root, publish=True, domains=[])                  # χωρίς domains: μόνο κάρτα, χωρίς script


def test_pptx_markdown_keeps_embed_as_link():
    d = dict(name='N', title='T', subtitle='', style='calm', opts=T.load_opts('{}'))
    md = DX.pptx_markdown(d, [sl(body=f'::: embed {YT} ratio=4:3\nΒίντεο\n:::')], '/tmp'); assert 'youtube.com/watch' in md and '<iframe' not in md


def test_preview_post_same_origin_csp_and_no_db_write(cl):
    did, _ = mk(cl); c = conn(); sid = D.slides(c, did)[0]['id']; before = c.execute('SELECT body,updated FROM deck_slide WHERE id=?', (sid,)).fetchone(); c.close()
    data = {'layout': 'embed', 'title': 'Προβολή', 'body': f'::: embed {YT}\nΒ\n:::\n\n::: embed https://example.org/x\n:::', 'notes': '', 'frag': '', 'transition': '', 'cls': '', 'bgcolor': '', 'bgimage': ''}
    assert cl.post(f'/decks/{did}/preview/{sid}', data=data, auth=A, headers={'origin': 'http://evil', 'host': 'testserver'}).status_code == 403
    assert cl.post(f'/decks/{did}/preview/{sid}', data=data).status_code == 401 and cl.post(f'/decks/{did}/preview/9999', data=data, auth=A, headers=H).status_code == 404
    r = cl.post(f'/decks/{did}/preview/{sid}', data=data, auth=A, headers=H); assert r.status_code == 200
    csp = r.headers['content-security-policy']; assert 'frame-src https://youtube.com' in csp and 'example.org' not in csp and "default-src 'none'" in csp
    assert 'data-src=' in r.text and 'Προβολή' in r.text and 'δεν είναι στη λίστα' in r.text and 'position:fixed' in r.text          # μπάρα προειδοποίησης
    c = conn(); assert c.execute('SELECT body,updated FROM deck_slide WHERE id=?', (sid,)).fetchone() == before


def test_preview_post_limits_and_title_slide_off(cl):
    did, _ = mk(cl); c = conn(); sid = D.slides(c, did)[0]['id']; d = D.get(c, did); d['opts']['title_slide'] = True; D.save_deck(c, did, opts=d['opts']); c.commit(); c.close()
    r = cl.post(f'/decks/{did}/preview/{sid}', data={'layout': 'zzz', 'title': 'Μόνο αυτή', 'body': 'x' * (T.LIMITS['body'] + 500)}, auth=A, headers=H); assert r.status_code == 200
    assert r.text.count('<section') == 1 and 'Μόνο αυτή' in r.text


def test_embed_test_page(cl):
    did, _ = mk(cl); r = cl.get(f'/decks/{did}/embed', params={'u': YT}, auth=A); assert r.status_code == 200 and '<iframe' in r.text and 'youtube-nocookie.com/embed/dQw4w9WgXcQ' in r.text and 'script' not in r.headers['content-security-policy']
    assert cl.get(f'/decks/{did}/embed', params={'u': 'https://example.org/x'}, auth=A).status_code == 422 and cl.get(f'/decks/{did}/embed', params={'u': YT}).status_code == 401


def test_publish_csp_frames_follow_current_setting_and_no_same_origin(cl):
    from app import publish, settings
    c = publish.csp(); assert 'frame-src https://youtube.com' in c and 'allow-same-origin' not in c and 'allow-popups-to-escape-sandbox' in c and "default-src 'none'" in c
    assert cl.post('/settings', data={'embed_domains': 'geogebra.org'}, auth=A, headers=H, follow_redirects=False).status_code == 303
    c = publish.csp(); assert 'geogebra.org' in c and 'youtube' not in c


def test_editor_toolbar_script_static_and_no_inline_js(cl):
    did, _ = mk(cl); p = cl.get(f'/decks/{did}', auth=A); assert p.status_code == 200
    assert 'data-blk=yt' in p.text and 'data-blk=cols' in p.text and "src='/static/deck.js'" in p.text and 'name=dkprev' in p.text and 'id=dkform' in p.text
    assert not re.search(r'<script(?![^>]*\bsrc=)[^>]*>', p.text) and ' onclick=' not in p.text
    js = cl.get('/static/deck.js', auth=A); assert js.status_code == 200 and 'javascript' in js.headers['content-type'] and "'/preview/'" in js.text and 'inDirective' in js.text
