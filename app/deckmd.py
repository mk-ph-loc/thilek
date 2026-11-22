"""0.32: Markdown διαφανειών. Κάθε διαφάνεια έχει δικό της Markdown σώμα· ό,τι δεν είναι Markdown γράφεται με οδηγίες γραμμής `:::` (εκτός fenced code):
  ::: cols … ||| … :::   στήλες (έως 3)      ::: quiz + YAML :::   στοιχείο quiz     ::: step … :::   ομάδα που εμφανίζεται μαζί (fragment)
  ::: embed https://… [λεζάντα] :::   σύνδεσμος-κάρτα (το iframe έρχεται στην 0.33)
Άγνωστη οδηγία μένει ως κείμενο και βγάζει προειδοποίηση. Δεν υπάρχει εμφώλευση. Το blocks()/compose() είναι η βάση του designer 0.33 (round-trip).
Επίσης: εισαγωγή/εξαγωγή ολόκληρης παρουσίασης ως ένα αρχείο deck.md. Χωρίς FastAPI και χωρίς βάση."""
import html, json, re
import yaml
from . import decktpl as T, qsol, solexport as X
from .mdmath import FENCE, normalize_math_md, outside_fences, render_md

E = html.escape
DIRECTIVES = ('cols', 'quiz', 'step', 'embed')
DIR_LINE = re.compile(r'^:::[ \t]+([A-Za-z][A-Za-z0-9_-]*)(?:[ \t]+(.*))?$')
RE_URL = re.compile(r'^https://[A-Za-z0-9.-]+(?::\d+)?(?:/[^\s<>"\']*)?$')
MAX_COLS = 3
MAX_YAML = 6000
MAX_DECK_MD = 400_000


class Fence:
    """Παρακολούθηση fenced code γραμμή προς γραμμή."""
    def __init__(self): self.f = None

    def feed(self, line):
        """True αν η γραμμή είναι μέσα σε fence (ή το ανοίγει/κλείνει)."""
        if self.f:
            if re.match(r'^ {0,3}' + re.escape(self.f[0]) + '{%d,}\\s*$' % len(self.f), line): self.f = None
            return True
        m = FENCE.match(line)
        if m: self.f = m.group(1); return True
        return False


def parse(body):
    """body -> (blocks, warnings). Μπλοκ: {'t':'md','text'} · {'t':'cols','cols':[..]} · {'t':'quiz','yaml'} · {'t':'step','text'} · {'t':'embed','url','caption'}."""
    blocks, warns, md, fence = [], [], [], Fence(); cur = None

    def flush_md():
        txt = '\n'.join(md).strip('\n')
        if txt.strip(): blocks.append({'t': 'md', 'text': txt})
        md.clear()

    def close(c):
        name, arg, buf = c
        text = '\n'.join(buf).strip('\n')
        if name == 'cols':
            cols, curc, f2 = [], [], Fence()
            for l in text.split('\n'):
                if not f2.feed(l) and l.strip() == '|||': cols.append('\n'.join(curc).strip('\n')); curc = []
                else: curc.append(l)
            cols.append('\n'.join(curc).strip('\n'))
            if len(cols) > MAX_COLS: warns.append(f'στήλες: μέγιστο {MAX_COLS}, οι υπόλοιπες ενώνονται στην τελευταία'); cols = cols[:MAX_COLS - 1] + ['\n|||\n'.join(cols[MAX_COLS - 1:])]
            blocks.append({'t': 'cols', 'cols': cols})
        elif name == 'quiz': blocks.append({'t': 'quiz', 'yaml': text})
        elif name == 'step': blocks.append({'t': 'step', 'text': text})
        else: blocks.append({'t': 'embed', 'url': (arg or '').strip(), 'caption': text})

    for line in (body or '').split('\n'):
        if cur is None:
            infence = fence.feed(line)
            m = None if infence else DIR_LINE.match(line)
            if m and m.group(1) in DIRECTIVES: flush_md(); cur = [m.group(1), m.group(2), []]; fence = Fence(); continue
            if m: warns.append(f'άγνωστη οδηγία «::: {m.group(1)}» (μένει ως κείμενο)')
            md.append(line)
        else:
            infence = fence.feed(line)
            if not infence and line.strip() == ':::': close(cur); cur = None; fence = Fence(); continue
            cur[2].append(line)
    if cur is not None: warns.append(f'η οδηγία «::: {cur[0]}» δεν κλείνει με «:::»'); close(cur)
    flush_md()
    return blocks, warns


def blocks(body): return parse(body)[0]


def compose(bl):
    """Αντίστροφο του blocks(): κανονική μορφή (μπλοκ χωρισμένα με κενή γραμμή)."""
    out = []
    for b in bl:
        t = b.get('t')
        if t == 'md':
            if (b.get('text') or '').strip(): out.append(b['text'].strip('\n'))
        elif t == 'cols': out.append('::: cols\n' + '\n|||\n'.join(c.strip('\n') for c in b.get('cols') or ['']) + '\n:::')
        elif t == 'quiz': out.append('::: quiz\n' + (b.get('yaml') or '').strip('\n') + '\n:::')
        elif t == 'step': out.append('::: step\n' + (b.get('text') or '').strip('\n') + '\n:::')
        elif t == 'embed': out.append(f"::: embed {b.get('url', '')}".rstrip() + ('\n' + b['caption'].strip('\n') if (b.get('caption') or '').strip() else '') + '\n:::')
    return '\n\n'.join(out)


def quiz_item(text, n=1):
    """YAML ενός στοιχείου quiz -> (στοιχείο qsol.check_item ή None, σφάλμα ή '')."""
    if len(text) > MAX_YAML: return None, 'πολύ μεγάλο YAML (όριο 6000 χαρακτήρες)'
    try: d = yaml.safe_load(text)
    except yaml.YAMLError as ex: return None, 'σφάλμα YAML: ' + str(ex).split('\n')[0][:120]
    it = qsol.check_item(d, n)
    return (None, '; '.join(it['err'])) if it['err'] else (it, '')


def warnings(slide):
    """Προειδοποιήσεις για μια διαφάνεια (λίστα κειμένων)."""
    bl, w = parse(slide.get('body') or '')
    for b in bl:
        if b['t'] == 'quiz':
            it, err = quiz_item(b['yaml'])
            if err: w.append('quiz: ' + err)
        elif b['t'] == 'embed' and not RE_URL.match(b['url']): w.append(f"embed: μη επιτρεπτός σύνδεσμος «{b['url'][:60]}» (μόνο https)")
    if len(slide.get('body') or '') > T.LIMITS['body']: w.append('το σώμα ξεπερνά το όριο μεγέθους')
    return w


# ---------- απόδοση HTML (Reveal) ----------
def _md(text, base, root, links, frag):
    h = render_md(text, base, links=links, embed_root=root)
    return X.fragmentize(h) if frag else h


def slide_html(slide, root, links=None, frag=False):
    """Εσωτερικό HTML του σώματος μιας διαφάνειας. frag: προεπιλογή bullets ένα-ένα του deck (η διαφάνεια έχει προτεραιότητα αν opts.frag δεν είναι None)."""
    o = T.load_opts(slide.get('opts'), deck=False); base = o['base']
    if o['frag'] is not None: frag = o['frag']
    out = []
    for b in blocks(slide.get('body') or ''):
        t = b['t']
        if t == 'md': out.append(_md(b['text'], base, root, links, frag))
        elif t == 'cols': out.append("<div class=cols>" + ''.join(f"<div class=col>{_md(c, base, root, links, frag)}</div>" for c in b['cols']) + '</div>')
        elif t == 'step': out.append(f"<div class=fragment>{_md(b['text'], base, root, links, False)}</div>")
        elif t == 'quiz':
            it, err = quiz_item(b['yaml'])
            if err: out.append(f"<p class=warn>⚠ quiz: {E(err)}</p>")
            else: out.append(f"<div class=qz>{X.quiz_body({'base': base}, it, root, head=False, ans=o['ans'] is not False)}</div>")
        else:
            if RE_URL.match(b['url']):
                cap = E(b['caption'].strip().split('\n')[0]) if b['caption'].strip() else E(b['url'])
                out.append(f"<p class=embed>🔗 <a href='{E(b['url'])}' target=_blank rel='noopener noreferrer'>{cap}</a><br><small>Σύνδεσμος· η ενσωμάτωση (iframe) δεν είναι διαθέσιμη σε αυτή την έκδοση.</small></p>")
            else: out.append(f"<p class=warn>⚠ embed: μη επιτρεπτός σύνδεσμος ({E(b['url'][:60])})</p>")
    return ''.join(out)


# ---------- Markdown για Pandoc (PPTX) ----------
def _quiz_pandoc(it):
    t = it['type']; lines = [' '.join(it['stem'].split()), '']
    if t == 'mcq': lines += [f"- {X.LET[i] if i < len(X.LET) else i + 1}. {o}" for i, o in enumerate(it.get('options') or [])] + ['']
    elif t == 'true_false': lines += ['Σωστό ή Λάθος;', '']
    elif t == 'matching': lines += [f"- {a} → {b}" for a, b in it.get('pairs') or []] + ['']
    if t != 'matching':
        ans = X.answer_text(it)
        if ans: lines += [f"**Απάντηση:** {ans}", '']
    if it.get('feedback'): lines += [' '.join(it['feedback'].split()), '']
    return '\n'.join(lines)


def slide_pandoc(slide, root):
    """Σώμα (και σημειώσεις) διαφάνειας ως Markdown για Pandoc με +fenced_divs. Οι εικόνες περνούν από τον έλεγχο του solexport (/files/ ή images/ μέσα στο data_root)."""
    base = T.load_opts(slide.get('opts'), deck=False)['base']; out = []
    esc = lambda l: '\\' + l if l.startswith(':::') else l                       # άγνωστη οδηγία ::: δεν πρέπει να γίνει fenced div του Pandoc
    img = lambda t: outside_fences(X._pptx_images(t, base, root), esc)
    for b in blocks(slide.get('body') or ''):
        t = b['t']
        if t == 'md': out.append(img(b['text']))
        elif t == 'step': out.append(img(b['text']))
        elif t == 'cols': out.append(':::: columns\n' + '\n'.join(f"::: column\n{img(c)}\n:::" for c in b['cols']) + '\n::::')
        elif t == 'quiz':
            it, err = quiz_item(b['yaml']); out.append(_quiz_pandoc(it) if it else f'*[quiz: {err}]*')
        else: out.append(f"[{' '.join(b['caption'].split()) or b['url']}]({b['url']})" if RE_URL.match(b['url']) else f"*[embed: {b['url'][:60]}]*")
    notes = (slide.get('notes') or '').strip()
    txt = '\n\n'.join(x for x in out if x.strip())
    if notes: txt += ('\n\n' if txt else '') + '::: notes\n' + notes + '\n:::'
    return txt


# ---------- deck.md: εισαγωγή/εξαγωγή ολόκληρης παρουσίασης ----------
def _cj(d): return json.dumps(d, ensure_ascii=False, separators=(',', ':')).replace('>', '\\u003e')


def deck_md(deck, slides):
    """Ολόκληρη η παρουσίαση ως ένα Markdown: <!-- deck: {...} --> και ανά διαφάνεια `---`, <!-- slide: {...} -->, `# τίτλος`, σώμα, `Note:` σημειώσεις."""
    meta = {k: deck.get(k) or '' for k in ('name', 'title', 'subtitle', 'style', 'recipe')}; meta['opts'] = T.load_opts(deck.get('opts'))
    parts = [f"<!-- deck: {_cj(meta)} -->"]
    for s in slides:
        sm = {'layout': s.get('layout') or 'content', 'down': int(bool(s.get('down'))), 'hidden': int(bool(s.get('hidden'))), 'opts': {k: v for k, v in T.load_opts(s.get('opts'), deck=False).items() if v not in (None, '', {})}}
        seg = [f"<!-- slide: {_cj(sm)} -->"]
        if s.get('title'): seg.append('# ' + s['title'].replace('\n', ' '))
        if (s.get('body') or '').strip(): seg.append(s['body'].strip('\n'))
        if (s.get('notes') or '').strip(): seg.append('Note:\n\n' + s['notes'].strip('\n'))
        parts.append('\n\n'.join(seg))
    return normalize_math_md('\n\n---\n\n'.join(parts)) + '\n'


def parse_deck_md(text):
    """deck.md -> (meta dict, [slide dict]). Άκυρα στοιχεία παίρνουν προεπιλογές. ValueError για υπέρβαση ορίων."""
    if len(text or '') > MAX_DECK_MD: raise ValueError('Το αρχείο ξεπερνά το όριο μεγέθους (400 KB).')
    segs, cur, f = [], [], Fence()
    for line in (text or '').replace('\r\n', '\n').split('\n'):
        if not f.feed(line) and re.match(r'^---\s*$', line): segs.append('\n'.join(cur)); cur = []
        else: cur.append(line)
    segs.append('\n'.join(cur)); meta, slides = {}, []
    for i, seg in enumerate(segs):
        seg = seg.strip('\n')
        if not seg.strip(): continue
        m = re.match(r'^<!--\s*deck:\s*(\{.*\})\s*-->\s*', seg, re.S)
        if m and i == 0:
            try: d = json.loads(m.group(1)); meta = d if isinstance(d, dict) else {}
            except ValueError: meta = {}
            seg = seg[m.end():].strip('\n')
            if not seg.strip(): continue
        sm = {}; m = re.match(r'^<!--\s*slide:\s*(\{.*?\})\s*-->[ \t]*\n?', seg, re.S)
        if m:
            try: d = json.loads(m.group(1)); sm = d if isinstance(d, dict) else {}
            except ValueError: sm = {}
            seg = seg[m.end():]
        lines = seg.strip('\n').split('\n'); title = ''
        while lines and not lines[0].strip(): lines.pop(0)
        if lines and re.match(r'^# ', lines[0]): title = lines.pop(0)[2:].strip()
        f2, k = Fence(), None
        for n, l in enumerate(lines):
            if not f2.feed(l) and l.strip() == 'Note:': k = n; break
        body = '\n'.join(lines if k is None else lines[:k]).strip('\n'); notes = '' if k is None else '\n'.join(lines[k + 1:]).strip('\n')
        slides.append({'layout': T.layout_ok(sm.get('layout')), 'title': title[:T.LIMITS['title']], 'body': body[:T.LIMITS['body']], 'notes': notes[:T.LIMITS['notes']],
                       'opts': T.load_opts(sm.get('opts'), deck=False), 'down': 1 if sm.get('down') in (1, True) else 0, 'hidden': 1 if sm.get('hidden') in (1, True) else 0})
        if len(slides) > T.LIMITS['slides']: raise ValueError(f"Πάνω από {T.LIMITS['slides']} διαφάνειες.")
    return meta, slides
