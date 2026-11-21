"""Markdown με τύπους LaTeX: προστασία των $..$ / $$..$$ από το CommonMark (placeholders), απόδοση HTML για KaTeX,
μετατροπή τύπων σε αναγνώσιμο κείμενο (Word) και σε \\(..\\) / \\[..\\] (Moodle). Χωρίς FastAPI."""
import base64, html, mimetypes, pathlib, re
from markdown_it import MarkdownIt

PH_L, PH_R = '', ''                 # ιδιωτική περιοχή Unicode: το markdown-it δεν τα αγγίζει
PH = re.compile(PH_L + r'(\d+)' + PH_R)
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')
# κώδικας `..` (μένει ως έχει) | $$..$$ (και σε πολλές γραμμές) | $..$ σε μία γραμμή, όχι \$, όχι «$ » στην αρχή/« $» στο τέλος, όχι $ πριν από ψηφίο (ποσά «$5»)
TOK = re.compile(r'(`+)(?:.+?)(?<!`)\1(?!`)|\$\$(?:.+?)\$\$|(?<![\\$])\$(?![\s$])(?:\\.|[^$\\\n])+?(?<!\s)\$(?!\d)', re.S)
IMG = re.compile(r'^images/[A-Za-z0-9_.-]+\.(?:png|jpe?g|svg)$', re.I)
FILES = re.compile(r'^/files/[A-Za-z0-9_./-]+\.(?:png|jpe?g|svg)$', re.I)

def fences(text):
    """Χωρίζει σε τμήματα (κείμενο, είναι_fenced_code) διατηρώντας τις γραμμές."""
    out, buf, fence = [], [], None
    for line in text.split('\n'):
        if fence:
            buf.append(line)
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{%d,}\\s*$' % len(fence), line): out.append(('\n'.join(buf), True)); buf, fence = [], None
            continue
        m = FENCE.match(line)
        if m:
            if buf: out.append(('\n'.join(buf), False))
            buf, fence = [line], m.group(1); continue
        buf.append(line)
    if buf: out.append(('\n'.join(buf), bool(fence)))
    return out

def protect(text, only_tex=False):
    """Αντικαθιστά τα math spans με placeholders. only_tex (Word): μόνο όσα έχουν \\ ^ _ ή γράμμα (π.χ. $E$, $F/q$)·
    καθαροί αριθμοί/ποσά («$5$», «$5 και $10») μένουν όπως είναι."""
    maths = []
    def sub(m):
        s = m.group(0)
        if s.startswith('`') or (only_tex and not re.search(r'[\\^_A-Za-z\u0370-\u03ff]', s)): return s
        maths.append(s); return f'{PH_L}{len(maths) - 1}{PH_R}'
    return '\n'.join(seg if code else TOK.sub(sub, seg) for seg, code in fences(text or '')), maths

def restore(s, maths, fn=html.escape):
    return PH.sub(lambda m: fn(maths[int(m.group(1))]) if int(m.group(1)) < len(maths) else '', s)

def outside_fences(text, fn):
    """Εφαρμόζει fn(γραμμή) -> γραμμή ή None (διαγραφή) μόνο εκτός fenced code."""
    out = []
    for seg, code in fences(text or ''):
        if code: out.append(seg); continue
        out.append('\n'.join(x for x in (fn(l) for l in seg.split('\n')) if x is not None))
    return '\n'.join(out)

def img_data(root, rel):
    p = pathlib.Path(root) / rel
    try:
        if p.resolve().is_relative_to(pathlib.Path(root).resolve()) and p.is_file():
            return f"data:{mimetypes.guess_type(p.name)[0] or 'image/png'};base64," + base64.b64encode(p.read_bytes()).decode()
    except OSError: pass
    return None

def img_url(src, base_dir_rel, embed_root=None):
    """images/x.png -> /files/<base>/images/x.png (ή data URI με embed_root). /files/... επιτρέπεται. Αλλιώς None."""
    if '..' in src or '\\' in src: return None
    if IMG.match(src) and base_dir_rel:
        rel = f'{base_dir_rel.strip("/")}/{src}'
        return img_data(embed_root, rel) if embed_root else '/files/' + rel
    if FILES.match(src): return img_data(embed_root, src[len('/files/'):]) if embed_root else src
    return None

def render_md(text, base_dir_rel='', links=None, embed_root=None):
    """Markdown -> HTML (html: False). Τα math μένουν ως ακατέργαστο $..$ (HTML-escaped) για το KaTeX auto-render.
    links: συνάρτηση href -> url ή None για τα thilek://· embed_root: εικόνες ως data URI (αυτόνομα αρχεία)."""
    src, maths = protect(text)
    md = MarkdownIt('commonmark', {'html': False}).enable('table')
    def image(self, tokens, idx, options, env):
        t = tokens[idx]; alt = self.renderInlineAsText(t.children or [], options, env)
        u = img_url(t.attrGet('src') or '', base_dir_rel, embed_root)
        if not u: return f"<span class=noimg>[εικόνα: {html.escape(alt)}]</span>"
        return f"<img src='{html.escape(u)}' alt='{html.escape(alt)}' loading=lazy style='max-width:100%'>"
    def link_open(self, tokens, idx, options, env):
        t = tokens[idx]; href = t.attrGet('href') or ''
        if href.startswith('thilek://'):
            u = links(href) if links else None
            t.attrSet('href', u or '#')
            if not u: t.attrSet('class', 'broken'); t.attrSet('title', 'άγνωστη παραπομπή')
        elif href.startswith(('http://', 'https://')): t.attrSet('target', '_blank'); t.attrSet('rel', 'noopener noreferrer')
        return self.renderToken(tokens, idx, options, env)
    md.add_render_rule('image', image); md.add_render_rule('link_open', link_open)
    md.validateLink = lambda url: not re.match(r'^\s*(javascript|vbscript|file|data):', url, re.I)
    return restore(md.render(src), maths)

def md_text(s):
    """Απλό κείμενο (με τύπους) -> HTML για KaTeX: escape, νέες γραμμές -> <br>. Για stem/feedback του quiz."""
    p, maths = protect(s or '')
    return restore(html.escape(p).replace('\n', '<br>'), maths)

def moodle_text(s):
    """Κείμενο -> HTML για Moodle: escape, <br>, και τα math ως \\(..\\) / \\[..\\] (το MathJax του Moodle δεν δέχεται μονό $)."""
    p, maths = protect(s or '')
    def tex(m):
        return '\\[' + m[2:-2].strip() + '\\]' if m.startswith('$$') else '\\(' + m[1:-1] + '\\)'
    return restore(html.escape(p).replace('\n', '<br>'), maths, lambda m: html.escape(tex(m), quote=False))

LISTLINE = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s|^\s*\||^\s{2,}')

def normalize_math_md(text):
    """Για προγράμματα ανάγνωσης Markdown εκτός εφαρμογής (VS Code, GitHub, Obsidian): κάθε $$..$$ γίνεται δικό του μπλοκ
    (κενή γραμμή πριν/μετά, $$ σε δική τους γραμμές)· στους τύπους μέσα στο κείμενο το \\dfrac γίνεται \\frac, ώστε να μη μεγαλώνει η γραμμή.
    Δεν αγγίζει κώδικα, πίνακες και στοιχεία λιστών. Επαναλαμβανόμενη εφαρμογή δεν αλλάζει τίποτα."""
    def seg_fn(seg):
        def sub(m):
            s = m.group(0)
            if s.startswith('`'): return s
            if s.startswith('$$'):
                ls = seg.rfind('\n', 0, m.start()) + 1; le = seg.find('\n', m.end()); le = len(seg) if le < 0 else le
                if LISTLINE.match(seg[ls:le]): return s
                return '\n\n$$\n' + s[2:-2].strip() + '\n$$\n\n'
            return s.replace('\\dfrac', '\\frac').replace('\\tfrac', '\\frac')
        return re.sub(r'\n{3,}', '\n\n', TOK.sub(sub, seg))
    return '\n'.join(seg if code else seg_fn(seg) for seg, code in fences(text or ''))

# ---------- LaTeX -> αναγνώσιμο κείμενο (Word) ----------
GREEK = dict(alpha='α', beta='β', gamma='γ', delta='δ', epsilon='ε', varepsilon='ε', zeta='ζ', eta='η', theta='θ', vartheta='θ', iota='ι', kappa='κ', lambda_='λ',
             mu='μ', nu='ν', xi='ξ', pi='π', rho='ρ', varrho='ρ', sigma='σ', tau='τ', upsilon='υ', phi='φ', varphi='φ', chi='χ', psi='ψ', omega='ω',
             Gamma='Γ', Delta='Δ', Theta='Θ', Lambda='Λ', Xi='Ξ', Pi='Π', Sigma='Σ', Upsilon='Υ', Phi='Φ', Psi='Ψ', Omega='Ω')
GREEK['lambda'] = GREEK.pop('lambda_')
SYM = dict(cdot='·', times='×', div='÷', pm='±', mp='∓', approx='≈', simeq='≃', sim='∼', neq='≠', ne='≠', leq='≤', le='≤', geq='≥', ge='≥', ll='≪', gg='≫', infty='∞',
           to='→', rightarrow='→', leftarrow='←', Rightarrow='⇒', Leftarrow='⇐', Leftrightarrow='⇔', leftrightarrow='↔', uparrow='↑', downarrow='↓', degree='°', circ='∘',
           parallel='∥', perp='⊥', propto='∝', equiv='≡', sum='Σ', prod='Π', int='∫', oint='∮', partial='∂', nabla='∇', angle='∠', ldots='…', dots='…', cdots='⋯',
           quad=' ', qquad='  ', cdotp='·', prime='′', hbar='ħ', ell='ℓ', Re='ℜ', Im='ℑ', triangle='△', checkmark='✓', lvert='|', rvert='|', vert='|', lbrace='{', rbrace='}',
           langle='⟨', rangle='⟩', sin='sin', cos='cos', tan='tan', ln='ln', log='log', exp='exp', max='max', min='min', lim='lim')
ESC = {',': ' ', ';': ' ', ':': ' ', ' ': ' ', '!': '', '%': '%', '{': '{', '}': '}', '\\': ' ', '$': '$', '_': '_', '&': '&', '#': '#', '|': '‖'}
ONE = {'mathrm', 'text', 'textrm', 'mathbf', 'mathit', 'mathsf', 'mathtt', 'textbf', 'textit', 'operatorname', 'boldsymbol', 'mbox', 'mathnormal', 'displaystyle', 'textstyle'}
ACC = {'vec': '⃗', 'overrightarrow': '⃗', 'overline': '̅', 'bar': '̄', 'hat': '̂', 'tilde': '̃', 'dot': '̇', 'underline': '̲'}
SUP = dict(zip('0123456789+-=()ni', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ')); SUP['−'] = '⁻'
SUB = dict(zip('0123456789+-=()aeoxhklmnpstijruvβγρφχ', '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥᵦᵧᵨᵩᵪ')); SUB['−'] = '₋'

def _arg(s, i):
    """Επόμενο όρισμα από τη θέση i: {...} (ισορροπημένο), \\εντολή ή ένας χαρακτήρας. -> (κείμενο, νέο i, ήταν_σε_άγκιστρα)."""
    while i < len(s) and s[i] == ' ': i += 1
    if i >= len(s): return '', i, False
    if s[i] == '{':
        d, j = 0, i
        while j < len(s):
            if s[j] == '\\': j += 2; continue
            if s[j] == '{': d += 1
            elif s[j] == '}':
                d -= 1
                if d == 0: return s[i + 1:j], j + 1, True
            j += 1
        return s[i + 1:], len(s), True
    if s[i] == '\\':
        m = re.match(r'\\([A-Za-z]+|.)', s[i:])
        return m.group(0), i + len(m.group(0)), False
    return s[i], i + 1, False

def _script(x, table, mark):
    if x and all(ch in table for ch in x): return ''.join(table[ch] for ch in x)
    return mark + (x if len(x) == 1 else '{' + x + '}')

def latex_to_text(s):
    """Μικρός μετατροπέας LaTeX -> Unicode κείμενο (π.χ. \\dfrac{a}{b} -> (a)/(b), \\Omega -> Ω, ^2 -> ²). Ό,τι δεν αναγνωρίζει μένει ως έχει."""
    out, i = [], 0
    while i < len(s):
        ch = s[i]
        if ch == '\\':
            m = re.match(r'\\([A-Za-z]+)', s[i:])
            if not m:
                nx = s[i + 1:i + 2]; out.append(ESC.get(nx, nx)); i += 2; continue
            name = m.group(1); i += len(m.group(0))
            if name in ('frac', 'dfrac', 'tfrac', 'cfrac'):
                a, i, _ = _arg(s, i); b, i, _ = _arg(s, i); out.append(f'({latex_to_text(a)})/({latex_to_text(b)})')
            elif name == 'sqrt':
                a, i, _ = _arg(s, i); a = latex_to_text(a); out.append('√' + (a if len(a) == 1 else f'({a})'))
            elif name in ONE:
                if name in ('displaystyle', 'textstyle'): continue
                a, i, _ = _arg(s, i); out.append(latex_to_text(a))
            elif name in ACC:
                a, i, _ = _arg(s, i); out.append(latex_to_text(a) + ACC[name])
            elif name in ('left', 'right', 'big', 'Big', 'bigg', 'Bigg', 'bigl', 'bigr', 'Bigl', 'Bigr'):
                if i < len(s) and s[i] == '.': i += 1
            elif name in GREEK: out.append(GREEK[name])
            elif name in SYM: out.append(SYM[name])
            else:                                   # άγνωστη εντολή: μένει όπως είναι (μαζί με το όρισμα σε άγκιστρα)
                out.append('\\' + name)
                if i < len(s) and s[i] == '{': a, j, _ = _arg(s, i); out.append(s[i:j]); i = j
        elif ch in '^_':
            a, i, br = _arg(s, i + 1)
            if ch == '^' and a in ('\\circ', '\\degree'): out.append('°'); continue
            out.append(_script(latex_to_text(a), SUP if ch == '^' else SUB, ch))
        elif ch == '{':
            a, i, _ = _arg(s, i); out.append(latex_to_text(a))
        elif ch == '}': i += 1
        elif ch == '~': out.append(' '); i += 1
        else: out.append(ch); i += 1
    return re.sub(r' {2,}', ' ', ''.join(out))

def math_to_text(m):
    """«$..$» ή «$$..$$» -> κείμενο."""
    return latex_to_text(m[2:-2].strip() if m.startswith('$$') else m[1:-1])
