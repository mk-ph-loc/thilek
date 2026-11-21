"""Εμπλουτισμένος renderer Markdown για εγχειρίδια και help (0.19.0).

Επεκτάσεις πάνω στο CommonMark (markdown-it-py, χωρίς ωμό HTML):
  !!! note "Τίτλος"      πλαίσιο (note, tip, warning, danger, info, example, success)· σώμα με εσοχή 4 κενών
  ??? tip "Τίτλος"       ίδιο, αναδιπλούμενο (κλειστό)·  ???+ = αναδιπλούμενο, ανοιχτό
  === "Καρτέλα"          καρτέλες (διαδοχικά blocks === σχηματίζουν ομάδα)· σώμα με εσοχή 4 κενών
  ::: group Τίτλος ... :::   πλαίσιο ομαδοποίησης
  - [ ] / - [x]          λίστα εργασιών (η επιλογή θυμάται στον browser)
  {{λέξη}} {{ok:λέξη}}   badge / λέξη-κλειδί (ok, warn, danger, info)
  ```mermaid             διάγραμμα (τοπικό Mermaid ή έτοιμο SVG από app/diagrams)
"""
import hashlib, html, pathlib, re
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token

DIAGRAMS = pathlib.Path(__file__).parent / 'diagrams'
ADM = {'note': ('ℹ️', 'Σημείωση'), 'tip': ('💡', 'Συμβουλή'), 'warning': ('⚠️', 'Προσοχή'), 'danger': ('⛔', 'Κίνδυνος'),
       'info': ('📌', 'Πληροφορία'), 'example': ('🧪', 'Παράδειγμα'), 'success': ('✅', 'Έτοιμο'), 'faq': ('❓', '')}
BADGE = {'ok', 'warn', 'danger', 'info'}


def slug(t):
    return re.sub(r'[^\w\- ]', '', t.lower(), flags=re.U).strip().replace(' ', '-') or 'x'


def diagram_hash(src):
    return hashlib.sha1(src.strip().encode('utf-8')).hexdigest()[:12]


class _R(RendererHTML):
    def fence(self, tokens, idx, options, env):
        t = tokens[idx]; info = t.info.strip().split()[0] if t.info.strip() else ''
        if info != 'mermaid': return super().fence(tokens, idx, options, env)
        src = t.content; h = diagram_hash(src)
        if env.get('mermaid') == 'svg':
            f = DIAGRAMS / f'{h}.svg'
            if f.is_file(): return f"<figure class='diagram diagram-svg' data-h='{h}'>{f.read_text(encoding='utf-8')}</figure>\n"
        env['mermaid_local'] = True
        return f"<figure class='diagram'><pre class=mermaid data-h='{h}'>{html.escape(src)}</pre></figure>\n"


def _post(state):
    env = state.env; toks = state.tokens
    for i, t in enumerate(toks):
        if t.type == 'heading_open' and t.tag in ('h2', 'h3'):
            title = toks[i + 1].content; used = env.setdefault('used', set()); sid = base = slug(title); n = 2
            while sid in used: sid = f'{base}-{n}'; n += 1
            used.add(sid); t.attrSet('id', sid)
            if t.tag == 'h2':
                env.setdefault('toc', []).append((sid, title)); mm = re.match(r'(\d+)\.', title)
                if mm and toks[i + 1].children is not None:
                    a = Token('html_inline', '', 0); a.content = f"<a id='s{mm.group(1)}'></a>"; toks[i + 1].children.insert(0, a)
        if t.type != 'inline' or not t.children: continue
        if i >= 2 and toks[i - 1].type == 'paragraph_open' and toks[i - 2].type == 'list_item_open':
            m = re.match(r'\[([ xX])\] ', t.children[0].content) if t.children[0].type == 'text' else None
            if m:
                env['ck_n'] = env.get('ck_n', 0) + 1; cid = f"{env.get('ck_prefix', 'm')}-{env['ck_n']}"
                toks[i - 2].attrJoin('class', 'task')
                box = Token('html_inline', '', 0); box.content = f"<input type=checkbox class='ck r-opt' data-ck='{html.escape(cid)}'{' checked' if m.group(1) in 'xX' else ''}> "
                t.children[0].content = t.children[0].content[m.end():]; t.children.insert(0, box)
        out = []
        for c in t.children:
            if c.type != 'text' or '{{' not in c.content: out.append(c); continue
            pos = 0
            for m in re.finditer(r'\{\{(?:(\w+):)?([^{}]+)\}\}', c.content):
                if m.group(1) and m.group(1) not in BADGE: continue
                if m.start() > pos: tx = Token('text', '', 0); tx.content = c.content[pos:m.start()]; out.append(tx)
                b = Token('html_inline', '', 0); b.content = f"<span class='kw kw-{m.group(1) or 'key'}'>{html.escape(m.group(2).strip())}</span>"; out.append(b); pos = m.end()
            if pos < len(c.content): tx = Token('text', '', 0); tx.content = c.content[pos:]; out.append(tx)
        t.children = out


def _md():
    md = MarkdownIt('commonmark', {'html': False}, renderer_cls=_R).enable('table')
    md.core.ruler.push('thilek_post', _post)
    return md

_MD = _md()


def _body(lines, i):
    """Σώμα με εσοχή: επιστρέφει (κείμενο χωρίς εσοχή, επόμενο i)."""
    out = []; j = i
    while j < len(lines) and (not lines[j].strip() or lines[j].startswith('    ') or lines[j].startswith('\t')):
        out.append(lines[j][4:] if lines[j].startswith('    ') else lines[j].lstrip('\t')); j += 1
    while out and not out[-1].strip(): out.pop()
    return '\n'.join(out), j


def _title(raw, default=''):
    m = re.search(r'"([^"]*)"', raw)
    return m.group(1) if m else (raw.strip() or default)


def _blocks(text):
    """Σπάει το κείμενο σε τμήματα: ('md', κείμενο) | ('adm', kind, title, mode, body) | ('tabs', [(title, body)]) | ('grp', title, body)."""
    lines = text.split('\n'); segs = []; buf = []; i = 0; fence = False

    def flush():
        if buf and ''.join(buf).strip(): segs.append(('md', '\n'.join(buf)))
        buf.clear()
    while i < len(lines):
        ln = lines[i]
        if not fence and (ln.startswith('```') or ln.startswith('~~~')): fence = True
        elif fence and re.fullmatch(r'(```|~~~)\s*', ln.strip()): fence = False
        m = None if fence else re.match(r'^(!!!|\?\?\?\+?)\s+(\w+)(.*)$', ln)
        if m:
            flush(); body, i = _body(lines, i + 1); mode = 'static' if m.group(1) == '!!!' else ('open' if m.group(1).endswith('+') else 'closed')
            segs.append(('adm', m.group(2), _title(m.group(3)), mode, body)); continue
        if not fence and re.match(r'^=== ', ln):
            flush(); tabs = []
            while i < len(lines) and re.match(r'^=== ', lines[i]):
                title = _title(lines[i][4:]); body, i = _body(lines, i + 1); tabs.append((title, body))
                j = i
                while j < len(lines) and not lines[j].strip(): j += 1
                if j < len(lines) and re.match(r'^=== ', lines[j]): i = j
            segs.append(('tabs', tabs)); continue
        if not fence and re.match(r'^::: \S', ln):
            flush(); depth = 1; body = []; i += 1
            while i < len(lines):
                if re.match(r'^::: \S', lines[i]): depth += 1
                elif lines[i].strip() == ':::':
                    depth -= 1
                    if depth == 0: break
                body.append(lines[i]); i += 1
            segs.append(('grp', re.sub(r'^group\s*', '', ln[4:].strip()), '\n'.join(body))); i += 1; continue
        buf.append(ln); i += 1
    flush(); return segs


_TAB_N = [0]


def _render(text, env):
    out = []
    for s in _blocks(text):
        if s[0] == 'md': out.append(_MD.render(s[1], env))
        elif s[0] == 'adm':
            _, kind, title, mode, body = s; ic, dt = ADM.get(kind, ADM['note']); title = title or dt; inner = _render(body, env)
            head = f"<span class=adm-i>{ic}</span> {html.escape(title)}"
            if mode == 'static': out.append(f"<div class='adm adm-{kind}'><p class=adm-t>{head}</p>{inner}</div>\n")
            else: out.append(f"<details class='adm adm-{kind}'{' open' if mode == 'open' else ''}{' data-faq=1' if kind == 'faq' else ''}><summary>{head}</summary>{inner}</details>\n")
        elif s[0] == 'tabs':
            _TAB_N[0] += 1; g = f"tg{_TAB_N[0]}"; tabs = s[1][:8]; ins = []; labs = []; pans = []
            for k, (title, body) in enumerate(tabs, 1):
                ins.append(f"<input type=radio name={g} id={g}-{k} class=tabr{' checked' if k == 1 else ''}>")
                labs.append(f"<label for={g}-{k}>{html.escape(title)}</label>"); pans.append(f"<div class=tp>{_render(body, env)}</div>")
            out.append(f"<div class=tabs2>{''.join(ins)}<nav class=tabl>{''.join(labs)}</nav>{''.join(pans)}</div>\n")
        else: out.append(f"<section class=grp><h4 class=grp-t>{html.escape(s[1])}</h4>{_render(s[2], env)}</section>\n")
    return ''.join(out)


def render(text, mermaid='svg', ck_prefix='m'):
    """Επιστρέφει (html, toc, env). env['mermaid_local'] = True αν χρειάζεται το mermaid.min.js στη σελίδα."""
    env = {'mermaid': mermaid, 'ck_prefix': ck_prefix}; body = _render(text, env)
    return body, env.get('toc', []), env


def inline(text):
    """Μικρό κείμενο (help): μόνο inline Markdown, χωρίς παράγραφο."""
    return _MD.renderInline(text, {})


def _tabcss():
    r = []
    for n in range(1, 9):
        r.append(f".tabs2>input:nth-of-type({n}):checked~.tp:nth-of-type({n}){{display:block}}.tabs2>input:nth-of-type({n}):checked~.tabl label:nth-of-type({n}){{background:var(--accent);color:#fff;border-color:var(--accent)}}")
    return ''.join(r)

RICH_CSS = ("""
.adm{--c:var(--c-list);border:1px solid color-mix(in srgb,var(--c) 45%,var(--border));border-left:5px solid var(--c);border-radius:var(--radius);background:color-mix(in srgb,var(--c) 9%,var(--card));margin:.8rem 0;padding:.1rem .9rem .3rem}
.adm>.adm-t,.adm>summary{font-weight:700;color:var(--c);margin:.45rem 0 .2rem}.adm>summary{cursor:pointer;margin:.1rem 0;padding:.3rem 0}.adm[open]>summary{border-bottom:1px dashed var(--border);margin-bottom:.3rem}
.adm-i{margin-right:.25rem}.adm-note,.adm-faq{--c:var(--c-list)}.adm-tip,.adm-success{--c:var(--c-sel)}.adm-warning{--c:var(--c-txt)}.adm-danger{--c:var(--c-danger)}.adm-info{--c:var(--c-file)}.adm-example{--c:var(--c-opt)}
.grp{border:2px solid var(--border);border-radius:calc(var(--radius) + 4px);padding:.2rem 1rem .6rem;margin:1rem 0;background:var(--card);box-shadow:var(--shadow)}.grp-t{margin:.5rem 0 .3rem;color:var(--accent);text-transform:uppercase;font-size:.8rem;letter-spacing:.05em}
.kw{display:inline-block;border-radius:999px;padding:0 .6rem;font-size:.82em;font-weight:600;background:color-mix(in srgb,var(--accent) 16%,var(--card));color:var(--accent);border:1px solid color-mix(in srgb,var(--accent) 40%,transparent);white-space:nowrap}
.kw-ok{--k:var(--c-sel)}.kw-warn{--k:var(--c-txt)}.kw-danger{--k:var(--c-danger)}.kw-info{--k:var(--c-file)}.kw-ok,.kw-warn,.kw-danger,.kw-info{background:color-mix(in srgb,var(--k) 16%,var(--card));color:var(--k);border-color:color-mix(in srgb,var(--k) 45%,transparent)}
li.task{list-style:none;margin-left:-1.3rem}li.task input{margin-right:.4rem;vertical-align:-2px}li.task:has(input:checked){opacity:.65;text-decoration:line-through}
.tabs2{margin:1rem 0;position:relative}.tabs2>input{position:absolute;opacity:0;width:1px;height:1px}.tabl{display:flex;flex-wrap:wrap;gap:2px;border-bottom:2px solid var(--accent)}
.tabl label{padding:.4rem .9rem;border:1px solid var(--border);border-bottom:0;border-radius:var(--radius) var(--radius) 0 0;background:var(--card);cursor:pointer;font-weight:600}.tabs2>input:focus-visible~.tabl label{outline:1px dotted var(--accent)}
.tp{display:none;border:1px solid var(--border);border-top:0;padding:.3rem 1rem .6rem;background:var(--card);border-radius:0 0 var(--radius) var(--radius)}
"""
            + _tabcss() + """
figure.diagram{margin:1rem 0;padding:.6rem;background:#fff;color:#222;border:1px solid var(--border);border-radius:var(--radius);overflow:auto;text-align:center}figure.diagram svg{max-width:100%;height:auto}figure.diagram pre.mermaid{background:none;border:0;max-height:none;white-space:pre;text-align:left;color:#222}
details.help{margin:0 0 .8rem;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);box-shadow:var(--shadow)}details.help>summary{cursor:pointer;padding:.35rem .8rem;font-weight:600;color:var(--accent)}
details.help[open]>summary{border-bottom:1px solid var(--border)}.help-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0 1rem;padding:.2rem .8rem .5rem}.help-grid .adm{margin:.5rem 0}.help-grid ul{margin:.2rem 0;padding-left:1.1rem}.help-foot{padding:0 .8rem .5rem;font-size:.9rem}
@media print{.tabs2 .tp{display:block!important}.tabl{display:none}}
""")


def diagram_sources(text):
    """Όλα τα μπλοκ ```mermaid του κειμένου (και μέσα σε πλαίσια/καρτέλες), με τη σειρά τους. Για το tools/render_diagrams.py."""
    out = []
    for s in _blocks(text):
        if s[0] == 'md':
            out += [t.content for t in _MD.parse(s[1]) if t.type == 'fence' and t.info.strip().split()[:1] == ['mermaid']]
        elif s[0] == 'adm': out += diagram_sources(s[4])
        elif s[0] == 'tabs':
            for _, body in s[1]: out += diagram_sources(body)
        else: out += diagram_sources(s[2])
    return out
