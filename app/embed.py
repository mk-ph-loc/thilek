"""0.33: ενσωμάτωση (embed) εξωτερικού περιεχομένου σε παρουσιάσεις. Καθαρές συναρτήσεις, χωρίς πρόσβαση σε βάση.
Κανόνας: iframe μόνο για https σε host της λίστας επιτρεπτών domains (ρύθμιση embed_domains)· αλλιώς κάρτα-σύνδεσμος. Ελέγχεται το ΤΕΛΙΚΟ src μετά τη μετατροπή."""
import html, ipaddress, re
from urllib.parse import parse_qs, urlsplit

E = html.escape
RATIOS = {'16:9': '16 / 9', '4:3': '4 / 3', '1:1': '1 / 1'}
H_MIN, H_MAX, START_MAX, URL_MAX = 200, 700, 86400, 4000
BAD = re.compile(r'[\s\x00-\x1f\x7f\\<>"\'`]')
YT_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
GG = re.compile(r'^/(?:m|classic|graphing|geometry|3d|calculator)/([A-Za-z0-9]{3,20})/?$')
IFRAME_SANDBOX = 'allow-scripts allow-same-origin allow-popups allow-presentation'     # το same-origin αφορά το ΤΡΙΤΟ origin, ποτέ της εφαρμογής
IFRAME_ALLOW = 'fullscreen; encrypted-media; picture-in-picture'
CLICK_JS = ("(function(){document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('.embgo');if(!b)return;var d=b.parentNode,s=d.getAttribute('data-embed');"
            "if(!s||s.indexOf('https://')!==0)return;var f=document.createElement('iframe');f.src=s;f.setAttribute('sandbox','" + IFRAME_SANDBOX + "');f.setAttribute('allow','" + IFRAME_ALLOW + "');"
            "f.setAttribute('allowfullscreen','');f.setAttribute('referrerpolicy','strict-origin-when-cross-origin');f.title=d.getAttribute('data-title')||'';d.innerHTML='';d.appendChild(f);});})();")


def hosts(raw):
    """'a.com, B.org' -> ['a.com', 'b.org'] (μόνο έγκυρα ονόματα)."""
    return [d for d in (x.strip().lower() for x in (raw or '').split(',')) if re.match(r'^[a-z0-9]([a-z0-9.-]{1,78})\.[a-z]{2,24}$', d)]


def split_arg(arg):
    """'URL ratio=4:3 h=400 start=30 περιττό' -> (url, params, unknown). Παράμετροι: ratio, h, start (με έλεγχο τιμών)."""
    toks = (arg or '').split(); url = toks[0] if toks else ''; params, unknown = {}, []
    for t in toks[1:]:
        k, _, v = t.partition('=')
        if k == 'ratio' and v in RATIOS: params['ratio'] = v
        elif k == 'h' and v.isdigit() and H_MIN <= int(v) <= H_MAX: params['h'] = int(v)
        elif k == 'start' and v.isdigit() and int(v) <= START_MAX: params['start'] = int(v)
        else: unknown.append(t[:40])
    return url, params, unknown


def arg_text(url, params):
    """Αντίστροφο του split_arg (σταθερή σειρά)."""
    p = params or {}
    return ' '.join([url] + [f'{k}={p[k]}' for k in ('ratio', 'h', 'start') if k in p]).strip()


def check(url, domains):
    """(ok, host, λόγος). Μόνο https, χωρίς userinfo, θύρα 443, όχι IP, host ίδιος ή υποτομέας επιτρεπτού domain."""
    if not url or len(url) > URL_MAX or BAD.search(url): return False, '', 'μη έγκυρος σύνδεσμος'
    try: sp = urlsplit(url); port = sp.port
    except ValueError: return False, '', 'μη έγκυρος σύνδεσμος'
    host = (sp.hostname or '').lower()
    if sp.scheme != 'https': return False, host, 'μόνο https'
    if sp.username or sp.password: return False, host, 'δεν επιτρέπονται στοιχεία σύνδεσης στον σύνδεσμο'
    if port not in (None, 443): return False, host, 'δεν επιτρέπεται θύρα'
    try: ipaddress.ip_address(host); return False, host, 'δεν επιτρέπονται διευθύνσεις IP'
    except ValueError: pass
    if not host or not re.match(r'^[a-z0-9.-]+$', host) or '..' in host: return False, host, 'μη έγκυρο όνομα host'
    if not any(host == d or host.endswith('.' + d) for d in domains): return False, host, f'ο host «{host}» δεν είναι στη λίστα επιτρεπτών (Ρυθμίσεις → embed)'
    return True, host, ''


def _yt_start(q, params):
    if 'start' in (params or {}): return int(params['start'])
    t = (q.get('t') or q.get('start') or [''])[0]
    if t.isdigit(): return min(int(t), START_MAX)
    m = re.match(r'^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$', t)
    return min(int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0), START_MAX) if m and t else 0


def to_src(url, params=None, domains=()):
    """Μετατρέπει γνωστές διευθύνσεις σε διευθύνσεις ενσωμάτωσης (YouTube, GeoGebra)· αλλιώς επιστρέφει την ίδια."""
    try: sp = urlsplit(url)
    except ValueError: return url
    host = (sp.hostname or '').lower(); h = host[4:] if host.startswith('www.') else (host[2:] if host.startswith('m.') else host); q = parse_qs(sp.query); vid = ''
    if h == 'youtu.be': vid = sp.path.strip('/').split('/')[0]
    elif h in ('youtube.com', 'youtube-nocookie.com'):
        m = re.match(r'^/(?:shorts|embed|live)/([^/]+)', sp.path)
        vid = m.group(1) if m else (q.get('v') or [''])[0]
    if vid:
        if not YT_ID.match(vid): return url
        st = _yt_start(q, params); dom = 'www.youtube-nocookie.com' if 'youtube-nocookie.com' in domains or not domains else 'www.youtube.com'
        return f'https://{dom}/embed/{vid}' + (f'?start={st}' if st else '')
    if h == 'geogebra.org':
        m = GG.match(sp.path)
        if m: return f'https://www.geogebra.org/material/iframe/id/{m.group(1)}'
    return url


def csp_frames(domains):
    """Τιμή frame-src για CSP: μόνο τα επιτρεπτά domains (και οι υποτομείς τους)."""
    return ' '.join(f'https://{d} https://*.{d}' for d in domains) or "'none'"


def link_card(url, cap, note='', show_url=False):
    c = E(cap or url); u = E(url, quote=True)
    return (f"<p class=embed>🔗 <a href='{u}' target=_blank rel='noopener noreferrer'>{c}</a>" + (f" — <small>{E(url)}</small>" if show_url and cap else '')
            + (f"<br><small>{E(note)}</small>" if note else '') + '</p>')


def _box_style(params):
    p = params or {}
    return f"aspect-ratio:{RATIOS[p.get('ratio', '16:9')]};" + (f"height:{int(p['h'])}px;" if 'h' in p else '')


def render(url, caption, params, domains, mode='reveal'):
    """HTML ενός μπλοκ embed. mode: 'live'/'reveal' (iframe που φορτώνει όταν φαίνεται η διαφάνεια) · 'click' (κουμπί· iframe μόνο μετά από κλικ, για δημοσιευμένες σελίδες) ·
    'print' (μόνο κάρτα). Χωρίς επιτρεπτό host: κάρτα-σύνδεσμος με εξήγηση."""
    cap = (caption or '').strip().split('\n')[0]; src = to_src(url, params, domains); ok, host, why = check(src, domains)      # ελέγχεται το τελικό src
    if not ok:
        base_ok = bool(re.match(r'^https://[^\s<>"\']+$', url or ''))
        return link_card(url, cap, 'Σύνδεσμος· ' + why) if base_ok else f"<p class=warn>⚠ embed: {E(why)} ({E(url[:60])})</p>"
    if mode == 'print': return link_card(url, cap, show_url=True)
    box = _box_style(params); t = E(cap or host, quote=True); card = link_card(url, '↗ Άνοιγμα σε νέα καρτέλα' + (f': {cap}' if cap else ''))
    if mode == 'click':
        return (f"<div class='emb embc' style='{box}' data-embed='{E(src, quote=True)}' data-title='{t}'><button type=button class=embgo>▶ Φόρτωση: {E(cap or host)}</button>"
                f"<small>Θα γίνει αίτημα στο {E(host)} μόνο αν πατήσεις.</small></div>{card}")
    return (f"<div class=emb style='{box}'><iframe data-src='{E(src, quote=True)}' title='{t}' sandbox='{IFRAME_SANDBOX}' allow='{IFRAME_ALLOW}' allowfullscreen "
            f"referrerpolicy='strict-origin-when-cross-origin' loading=lazy></iframe></div>{card}")
