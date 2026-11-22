"""OMML (εξισώσεις Word, m:oMath / m:oMathPara) -> LaTeX συμβατό με KaTeX. Αντίστροφο του app/omml.py.
Δεν σηκώνει ποτέ εξαίρεση για άγνωστα στοιχεία: κατεβαίνει στα παιδιά και ενώνει το κείμενο.
Το $$...$$ για m:oMathPara το βάζει ο καλών· εδώ επιστρέφεται μόνο το σώμα."""
import re
from xml.etree import ElementTree as ET

NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
_M = '{' + NS + '}'
_VAL = _M + 'val'

# ---------- χαρακτήρες ----------
_GREEK = {
    'α': r'\alpha', 'β': r'\beta', 'γ': r'\gamma', 'δ': r'\delta', 'ε': r'\varepsilon', 'ϵ': r'\epsilon',
    'ζ': r'\zeta', 'η': r'\eta', 'θ': r'\theta', 'ϑ': r'\vartheta', 'ι': r'\iota', 'κ': r'\kappa',
    'λ': r'\lambda', 'μ': r'\mu', 'ν': r'\nu', 'ξ': r'\xi', 'ο': 'o', 'π': r'\pi', 'ϖ': r'\varpi',
    'ρ': r'\rho', 'ϱ': r'\varrho', 'σ': r'\sigma', 'ς': r'\varsigma', 'τ': r'\tau', 'υ': r'\upsilon',
    'φ': r'\varphi', 'ϕ': r'\phi', 'χ': r'\chi', 'ψ': r'\psi', 'ω': r'\omega',
    'Α': 'A', 'Β': 'B', 'Γ': r'\Gamma', 'Δ': r'\Delta', 'Ε': 'E', 'Ζ': 'Z', 'Η': 'H', 'Θ': r'\Theta',
    'Ι': 'I', 'Κ': 'K', 'Λ': r'\Lambda', 'Μ': 'M', 'Ν': 'N', 'Ξ': r'\Xi', 'Ο': 'O', 'Π': r'\Pi',
    'Ρ': 'P', 'Σ': r'\Sigma', 'Τ': 'T', 'Υ': r'\Upsilon', 'Φ': r'\Phi', 'Χ': 'X', 'Ψ': r'\Psi',
    'Ω': r'\Omega', 'Ω': r'\Omega', 'µ': r'\mu',
}
_SYM = {
    '·': r'\cdot', '⋅': r'\cdot', '∙': r'\cdot', '×': r'\times', '÷': r'\div', '−': '-', '–': '-',
    '±': r'\pm', '∓': r'\mp', '≤': r'\leq', '≦': r'\leq', '≥': r'\geq', '≧': r'\geq', '≠': r'\neq',
    '≈': r'\approx', '≃': r'\simeq', '≅': r'\cong', '≡': r'\equiv', '∼': r'\sim', '∝': r'\propto',
    '≪': r'\ll', '≫': r'\gg', '∞': r'\infty', '∂': r'\partial', '∇': r'\nabla', '∘': r'\circ',
    '°': r'^{\circ}', '′': "'", '″': "''", '…': r'\ldots', '⋯': r'\cdots', '⋮': r'\vdots', '⋱': r'\ddots',
    '→': r'\rightarrow', '←': r'\leftarrow', '↔': r'\leftrightarrow', '⇒': r'\Rightarrow',
    '⇐': r'\Leftarrow', '⇔': r'\Leftrightarrow', '↦': r'\mapsto', '↑': r'\uparrow', '↓': r'\downarrow',
    '⟶': r'\longrightarrow', '⟹': r'\Longrightarrow', '⇌': r'\rightleftharpoons',
    '∈': r'\in', '∉': r'\notin', '∋': r'\ni', '⊂': r'\subset', '⊃': r'\supset', '⊆': r'\subseteq',
    '⊇': r'\supseteq', '∪': r'\cup', '∩': r'\cap', '∅': r'\emptyset', '∀': r'\forall', '∃': r'\exists',
    '¬': r'\neg', '∧': r'\land', '∨': r'\lor', '⊕': r'\oplus', '⊗': r'\otimes', '∠': r'\angle',
    '⊥': r'\perp', '⟂': r'\perp', '∥': r'\parallel', '∣': r'\mid', '⟨': r'\langle', '⟩': r'\rangle',
    'ℏ': r'\hbar', 'ℓ': r'\ell', 'ℝ': r'\mathbb{R}', 'ℕ': r'\mathbb{N}', 'ℤ': r'\mathbb{Z}',
    'ℚ': r'\mathbb{Q}', 'ℂ': r'\mathbb{C}', '∗': r'\ast', '⋆': r'\star', '•': r'\bullet', '√': r'\surd',
    '⌊': r'\lfloor', '⌋': r'\rfloor', '⌈': r'\lceil', '⌉': r'\rceil', '△': r'\triangle', '∆': r'\Delta',
    '∑': r'\sum', '∏': r'\prod', '∫': r'\int', '∮': r'\oint', '‰': r'\text{‰}',
    '\u2009': r'\,', '\u2006': r'\,', '\u205f': r'\:', '\u2005': r'\:', '\u2004': r'\;', '\u2002': r'\;',
    '\u2003': r'\quad', '\u00a0': '~',
    '{': r'\{', '}': r'\}', '#': r'\#', '%': r'\%', '$': r'\$', '_': r'\_', '&': r'\&',
    '\\': r'\backslash', '^': r'\wedge', '~': r'\sim',
}
_DROP = set('\u2061\u2062\u2063\u2064\u200b\u200c\u200d\ufeff')
_CHARS = {**_GREEK, **_SYM}
_TEXT_ESC = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '#': r'\#', '%': r'\%', '$': r'\$',
             '_': r'\_', '&': r'\&', '^': r'\^{}', '~': r'\~{}'}

_FUNCS = {'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'sinh', 'cosh', 'tanh', 'coth', 'arcsin', 'arccos',
          'arctan', 'ln', 'log', 'lg', 'exp', 'lim', 'max', 'min', 'sup', 'inf', 'det', 'deg', 'dim',
          'gcd', 'ker', 'arg', 'Pr', 'liminf', 'limsup', 'hom'}
_LIMOPS = {r'\lim', r'\max', r'\min', r'\sup', r'\inf', r'\liminf', r'\limsup', r'\det', r'\gcd', r'\Pr'}

_NARY = {'∑': r'\sum', '∏': r'\prod', '∐': r'\coprod', '∫': r'\int', '∬': r'\iint', '∭': r'\iiint',
         '∮': r'\oint', '∯': r'\oiint', '∰': r'\oiiint', '⋃': r'\bigcup', '⋂': r'\bigcap', '⋁': r'\bigvee',
         '⋀': r'\bigwedge', '⨁': r'\bigoplus', '⨂': r'\bigotimes', '⨀': r'\bigodot', '⨄': r'\biguplus'}
_INTS = {r'\int', r'\iint', r'\iiint', r'\oint', r'\oiint', r'\oiiint'}

_ACC = {'\u20d7': r'\vec', '→': r'\vec', '\u0302': r'\hat', '^': r'\hat', 'ˆ': r'\hat',
        '\u0303': r'\tilde', '~': r'\tilde', '˜': r'\tilde', '\u0307': r'\dot', '˙': r'\dot', '.': r'\dot',
        '\u0308': r'\ddot', '¨': r'\ddot', '\u030c': r'\check', 'ˇ': r'\check', '\u0301': r'\acute',
        '´': r'\acute', '\u0300': r'\grave', '`': r'\grave', '\u0306': r'\breve', '˘': r'\breve',
        '\u030a': r'\mathring', '\u20d6': r'\overleftarrow', '\u20e1': r'\overleftrightarrow',
        '\u0305': 'BAR', '\u00af': 'BAR', '\u02c9': 'BAR', '\u203e': 'BAR', '\u2015': 'BAR', '\u0304': 'BAR'}

_DELIM = {'(': '(', ')': ')', '[': '[', ']': ']', '{': r'\{', '}': r'\}', '|': '|', '‖': r'\|',
          '⟨': r'\langle', '⟩': r'\rangle', '〈': r'\langle', '〉': r'\rangle', '⌊': r'\lfloor',
          '⌋': r'\rfloor', '⌈': r'\lceil', '⌉': r'\rceil', '/': '/', '\\': r'\backslash', '': '.'}
_MATENV = {('(', ')'): 'pmatrix', ('[', ']'): 'bmatrix', ('{', '}'): 'Bmatrix', ('|', '|'): 'vmatrix',
           ('‖', '‖'): 'Vmatrix'}
_BARCH = set('\u0305\u00af\u02c9\u203e\u2015_\u0332')


def _local(e):
    t = e.tag
    if not isinstance(t, str):
        return ''
    return t.split('}', 1)[1] if t.startswith('{') else t


def _is_m(e):
    return isinstance(e.tag, str) and e.tag.startswith(_M)


def _child(e, name):
    for c in e:
        if _is_m(c) and _local(c) == name:
            return c
    return None


def _prop(e, pr, name, default=None):
    """Τιμή m:val του m:<name> μέσα στο m:<pr> (π.χ. dPr/begChr). Παρόν χωρίς val -> '' για chr, αλλιώς 'on'."""
    p = _child(e, pr)
    if p is None:
        return default
    c = _child(p, name)
    if c is None:
        return default
    v = c.get(_VAL)
    if v is None:
        return '' if name.endswith('Chr') or name == 'chr' else 'on'
    return v


def _on(v):
    return v is not None and v.lower() not in ('0', 'off', 'false')


def _cat(parts):
    """Ενώνει κομμάτια LaTeX: κενό μετά από εντολή-λέξη όταν ακολουθεί γράμμα."""
    out = ''
    for p in parts:
        if not p:
            continue
        if out and re.search(r'\\[A-Za-z]+$', out) and re.match(r'[A-Za-z]', p):
            out += ' '
        out += p
    return out


def _chars(s, amp=False):
    parts = []
    for ch in s:
        if ch in _DROP:
            continue
        if amp and ch == '&':
            parts.append(' & ')
        else:
            parts.append(_CHARS.get(ch, ch))
    return _cat(parts)


def _atom(s):
    """Αρκεί χωρίς άγκιστρα ως βάση δείκτη/εκθέτη;"""
    return bool(re.fullmatch(r'[A-Za-z0-9]|[0-9.]+|\\[A-Za-z]+|\\[A-Za-z]+\{[^{}]*\}|\{.*\}', s)) and \
        (not s.startswith('{') or _balanced_group(s))


def _balanced_group(s):
    d = 0
    for i, ch in enumerate(s):
        if ch == '{' and (i == 0 or s[i - 1] != '\\'):
            d += 1
        elif ch == '}' and (i == 0 or s[i - 1] != '\\'):
            d -= 1
            if d == 0 and i != len(s) - 1:
                return False
    return d == 0


def _base(s):
    s = s.strip()
    if not s:
        return '{}'
    return s if _atom(s) else '{' + s + '}'


def _run_info(r):
    """-> (κείμενο, είδος) με είδος 'text' (m:nor), 'up' (sty p/b) ή 'it'."""
    text = ''.join((t.text or '') for t in r.iter() if _is_m(t) and _local(t) == 't')
    rpr = _child(r, 'rPr')
    kind = 'it'
    if rpr is not None:
        nor = _child(rpr, 'nor')
        if nor is not None and _on(nor.get(_VAL, 'on')):
            kind = 'text'
        else:
            sty = _child(rpr, 'sty')
            if sty is not None and sty.get(_VAL) in ('p', 'b'):
                kind = 'up'
    return text, kind


class _Conv:
    def __init__(self):
        self.amp = 0          # μέσα σε m:eqArr: το '&' είναι σημείο στοίχισης

    # ---- βοηθητικά ----
    def kids(self, e):
        """Μετατρέπει τα παιδιά ενός κοντέινερ, ενώνοντας διαδοχικά m:r ίδιου είδους."""
        items = [c for c in e if isinstance(c.tag, str)]
        groups = []          # [kind, text] ή ('el', element)
        for c in items:
            if _is_m(c) and _local(c) == 'r':
                text, kind = _run_info(c)
                if groups and groups[-1][0] == kind:
                    groups[-1][1] += text
                else:
                    groups.append([kind, text])
            else:
                groups.append(['el', c])
        # μονάδες: \mathrm{k}Ω -> \mathrm{kΩ}, μ\mathrm{A} -> \mathrm{μA}
        merged = []
        for g in groups:
            if merged and g[0] == 'it' and merged[-1][0] == 'up' and re.fullmatch(r'[ΩΩμµ]+', g[1]) \
                    and re.search(r'[A-Za-z]$', merged[-1][1]):
                merged[-1][1] += g[1]
                continue
            if merged and g[0] == 'up' and merged[-1][0] == 'it' and re.search(r'[μµ]$', merged[-1][1]) \
                    and re.match(r'[A-Za-z]', g[1]):
                prev = merged[-1][1]
                m = re.search(r'[μµ]+$', prev)
                merged[-1][1] = prev[:m.start()]
                g = ['up', prev[m.start():] + g[1]]
            merged.append(g)
        # "(" m:m ")" ως απλοί χαρακτήρες (έτσι γράφει το app/omml.py) -> pmatrix/bmatrix/...
        for i in range(1, len(merged) - 1):
            g = merged[i]
            if g[0] == 'el' and _is_m(g[1]) and _local(g[1]) == 'm' and merged[i - 1][0] == 'it' \
                    and merged[i + 1][0] == 'it' and merged[i - 1][1][-1:] and merged[i + 1][1][:1]:
                key = (merged[i - 1][1][-1], merged[i + 1][1][0])
                if key in _MATENV:
                    merged[i - 1][1] = merged[i - 1][1][:-1]
                    merged[i + 1][1] = merged[i + 1][1][1:]
                    merged[i] = ['tex', self.matrix(g[1], _MATENV[key])]
        return _cat(g[1] if g[0] == 'tex' else self.conv(g[1]) if g[0] == 'el' else self.text(g[1], g[0])
                    for g in merged)

    def arg(self, e, name):
        c = _child(e, name)
        return self.kids(c) if c is not None else ''

    def text(self, s, kind):
        if not s:
            return ''
        if kind == 'text':
            s2 = ''.join(ch for ch in s if ch not in _DROP)
            return r'\text{' + ''.join(_TEXT_ESC.get(ch, ch) for ch in s2) + '}' if s2 else ''
        stripped = ''.join(ch for ch in s if ch not in _DROP).strip()
        if stripped in _FUNCS:
            lead = ' ' if s[:1] == ' ' else ''
            return lead + '\\' + stripped
        if kind == 'up' and re.search(r'[A-Za-zΑ-Ωα-ωΩµ]', s):
            # όρθιο κείμενο/μονάδα: κρατάμε τα κενά μπροστά/πίσω έξω από το \mathrm
            m = re.fullmatch(r'(\s*)(.*?)(\s*)', s, re.S)
            inner = _chars(m.group(2).replace(' ', '\u0001'))
            inner = inner.replace('\u0001', r'\ ')
            return _chars(m.group(1)) + r'\mathrm{' + inner + '}' + _chars(m.group(3))
        return _chars(s, amp=bool(self.amp))

    # ---- διανομέας ----
    def conv(self, e):
        try:
            if not _is_m(e):
                return self.kids(e) if _local(e) not in ('rPr', 'pPr') else ''
            t = _local(e)
            f = getattr(self, 'm_' + t, None)
            if f is not None:
                return f(e)
            if t.endswith('Pr'):
                return ''
            return self.kids(e)
        except Exception:
            try:
                return _cat(_chars(x) for x in e.itertext())
            except Exception:
                return ''

    # ---- κοντέινερ ----
    def m_oMathPara(self, e):
        maths = [c for c in e if _is_m(c) and _local(c) == 'oMath']
        if not maths:
            return self.kids(e)
        bodies = [self.kids(m) for m in maths]
        if len(bodies) == 1:
            return bodies[0]
        return r'\begin{gathered}' + r' \\ '.join(bodies) + r'\end{gathered}'

    def m_oMath(self, e):
        return self.kids(e)

    def m_r(self, e):
        text, kind = _run_info(e)
        return self.text(text, kind)

    def m_t(self, e):
        return _chars(e.text or '')

    # ---- κλάσματα ----
    def m_f(self, e):
        num, den = self.arg(e, 'num'), self.arg(e, 'den')
        typ = _prop(e, 'fPr', 'type', 'bar')
        if typ == 'skw':
            return '{}^{' + num + '}/_{' + den + '}'
        if typ == 'lin':
            return _base(num) + '/' + _base(den)
        if typ == 'noBar':
            return r'\genfrac{}{}{0pt}{}{' + num + '}{' + den + '}'
        return r'\frac{' + num + '}{' + den + '}'

    # ---- δείκτες ----
    def m_sSub(self, e):
        return _base(self.arg(e, 'e')) + '_{' + self.arg(e, 'sub') + '}'

    def m_sSup(self, e):
        return _base(self.arg(e, 'e')) + '^{' + self.arg(e, 'sup') + '}'

    def m_sSubSup(self, e):
        return _base(self.arg(e, 'e')) + '_{' + self.arg(e, 'sub') + '}^{' + self.arg(e, 'sup') + '}'

    def m_sPre(self, e):
        return _cat(['{}_{' + self.arg(e, 'sub') + '}^{' + self.arg(e, 'sup') + '}', _base(self.arg(e, 'e'))])

    # ---- ρίζες ----
    def m_rad(self, e):
        body = self.arg(e, 'e')
        deg = self.arg(e, 'deg').strip()
        if _on(_prop(e, 'radPr', 'degHide')) or not deg:
            return r'\sqrt{' + body + '}'
        return r'\sqrt[' + deg + ']{' + body + '}'

    # ---- παρενθέσεις ----
    def m_d(self, e):
        beg = _prop(e, 'dPr', 'begChr', '(')
        end = _prop(e, 'dPr', 'endChr', ')')
        sep = _prop(e, 'dPr', 'sepChr', '|')
        es = [c for c in e if _is_m(c) and _local(c) == 'e']
        # πίνακας μέσα σε παρενθέσεις -> pmatrix/bmatrix/...
        if len(es) == 1:
            inner = [c for c in es[0] if isinstance(c.tag, str) and not _local(c).endswith('Pr')]
            if len(inner) == 1 and _is_m(inner[0]):
                k = _local(inner[0])
                if k == 'm' and (beg, end) in _MATENV:
                    return self.matrix(inner[0], _MATENV[(beg, end)])
                if k == 'eqArr' and beg == '{' and end == '':
                    return self.rows(inner[0], 'cases')
                if k == 'f' and (beg, end) == ('(', ')') and _prop(inner[0], 'fPr', 'type') == 'noBar':
                    return r'\binom{' + self.arg(inner[0], 'num') + '}{' + self.arg(inner[0], 'den') + '}'
        sepl = r' \mid ' if sep == '|' else (_DELIM.get(sep) or _chars(sep))
        body = sepl.join(self.kids(x) for x in es)
        lb = _DELIM.get(beg, '.') if beg in _DELIM else '.'
        rb = _DELIM.get(end, '.') if end in _DELIM else '.'
        return r'\left' + lb + (' ' if lb[-1:].isalpha() else '') + body + r'\right' + rb

    # ---- n-αδικοί ----
    def m_nary(self, e):
        ch = _prop(e, 'naryPr', 'chr', '∫') or '∫'
        op = _NARY.get(ch) or _chars(ch) or r'\int'
        loc = _prop(e, 'naryPr', 'limLoc')
        if loc == 'undOvr' and op in _INTS:
            op += r'\limits'
        elif loc == 'subSup' and op not in _INTS:
            op += r'\nolimits'
        sub = '' if _on(_prop(e, 'naryPr', 'subHide')) else self.arg(e, 'sub')
        sup = '' if _on(_prop(e, 'naryPr', 'supHide')) else self.arg(e, 'sup')
        s = op + ('_{' + sub + '}' if sub else '') + ('^{' + sup + '}' if sup else '')
        body = self.arg(e, 'e')
        return s + (' ' + body if body else '')

    # ---- τόνοι/γραμμές ----
    def m_acc(self, e):
        ch = _prop(e, 'accPr', 'chr', '\u0302')
        if ch == '':
            ch = '\u0302'
        body = self.arg(e, 'e')
        cmd = _ACC.get(ch)
        if cmd == 'BAR':
            cmd = r'\bar' if _atom(body) and len(re.sub(r'\\[A-Za-z]+', 'x', body)) == 1 else r'\overline'
        if cmd is None:
            return r'\overset{' + _chars(ch) + '}{' + body + '}'
        if cmd == r'\vec' and not (_atom(body) and len(re.sub(r'\\[A-Za-z]+', 'x', body)) == 1):
            cmd = r'\overrightarrow'
        return cmd + '{' + body + '}'

    def m_bar(self, e):
        pos = _prop(e, 'barPr', 'pos', 'bot')
        return (r'\overline{' if pos == 'top' else r'\underline{') + self.arg(e, 'e') + '}'

    def m_groupChr(self, e):
        ch = _prop(e, 'groupChrPr', 'chr', '\u23df') or '\u23df'
        pos = _prop(e, 'groupChrPr', 'pos', 'bot')
        body = self.arg(e, 'e')
        if ch == '\u23df':
            return r'\underbrace{' + body + '}'
        if ch == '\u23de':
            return r'\overbrace{' + body + '}'
        sym = _chars(ch)
        return (r'\overset{' if pos == 'top' else r'\underset{') + sym + '}{' + body + '}'

    def _lim_one(self, e):
        c = _child(e, 'lim')
        if c is None:
            return None
        txt = ''.join(c.itertext()).strip()
        return txt if len(txt) == 1 else None

    def m_limLow(self, e):
        base, lim = self.arg(e, 'e'), self.arg(e, 'lim')
        one = self._lim_one(e)
        if one and one in _BARCH:
            return r'\underline{' + base + '}'
        if one == '\u23df':
            return r'\underbrace{' + base + '}'
        if base.startswith(r'\underbrace{') and _balanced_group(base[len(r'\underbrace'):]):
            return base + '_{' + lim + '}'
        if base.strip() in _LIMOPS:
            return base.strip() + '_{' + lim + '}'
        return r'\underset{' + lim + '}{' + base + '}'

    def m_limUpp(self, e):
        base, lim = self.arg(e, 'e'), self.arg(e, 'lim')
        one = self._lim_one(e)
        if one and one in _BARCH:
            return r'\overline{' + base + '}'
        if one == '\u23de':
            return r'\overbrace{' + base + '}'
        if one in ('→', '\u20d7'):
            return r'\overrightarrow{' + base + '}'
        if base.startswith(r'\overbrace{') and _balanced_group(base[len(r'\overbrace'):]):
            return base + '^{' + lim + '}'
        return r'\overset{' + lim + '}{' + base + '}'

    # ---- συναρτήσεις ----
    def m_func(self, e):
        name = self.arg(e, 'fName').strip()
        body = self.arg(e, 'e').strip()
        m = re.fullmatch(r'\\mathrm\{([A-Za-z]+)\}|([A-Za-z]{2,})', name)
        if m:
            w = m.group(1) or m.group(2)
            name = '\\' + w if w in _FUNCS else r'\operatorname{' + w + '}'
        return name + ' ' + body if body else name

    # ---- πίνακες ----
    def matrix(self, e, env):
        rows = []
        for mr in e:
            if _is_m(mr) and _local(mr) == 'mr':
                rows.append(' & '.join(self.kids(c) for c in mr if _is_m(c) and _local(c) == 'e'))
        return r'\begin{' + env + '}' + r' \\ '.join(rows) + r'\end{' + env + '}'

    def m_m(self, e):
        return self.matrix(e, 'matrix')

    def rows(self, e, env):
        self.amp += 1
        try:
            rows = [self.kids(c) for c in e if _is_m(c) and _local(c) == 'e']
        finally:
            self.amp -= 1
        return r'\begin{' + env + '}' + r' \\ '.join(rows) + r'\end{' + env + '}'

    def m_eqArr(self, e):
        return self.rows(e, 'aligned')

    # ---- πέρασμα περιεχομένου ----
    def m_box(self, e):
        return self.arg(e, 'e')

    def m_borderBox(self, e):
        return self.arg(e, 'e')

    def m_phant(self, e):
        return self.arg(e, 'e')


def _tidy(s):
    s = re.sub(r'[ \t\r\n]+', ' ', s).strip()
    return s


def omml_to_latex(elem) -> str:
    """m:oMath ή m:oMathPara (ElementTree ή lxml) -> LaTeX. Ποτέ εξαίρεση· σε αποτυχία ''."""
    if elem is None:
        return ''
    try:
        return _tidy(_Conv().conv(elem))
    except Exception:
        return ''


def omml_to_latex_str(xml_string) -> str:
    """Όπως omml_to_latex, από συμβολοσειρά XML. Αν λείπει η δήλωση namespace του 'm:', προστίθεται."""
    if not xml_string or not str(xml_string).strip():
        return ''
    s = xml_string.decode('utf-8') if isinstance(xml_string, bytes) else str(xml_string)
    s = re.sub(r'^\s*<\?xml[^>]*\?>', '', s).strip()
    try:
        root = ET.fromstring(s)
    except ET.ParseError:
        decl = f' xmlns:m="{NS}" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        try:
            root = ET.fromstring(f'<wrap{decl}>{s}</wrap>')
        except ET.ParseError:
            return ''
        kids = list(root)
        root = kids[0] if len(kids) == 1 else root
    return omml_to_latex(root)
