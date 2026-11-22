"""Έλεγχοι για app/ommllatex.py (OMML -> LaTeX)."""
from xml.etree import ElementTree as ET

import pytest

from app import omml
from app.ommllatex import NS, omml_to_latex, omml_to_latex_str

DECL = f'xmlns:m="{NS}"'


def M(body):
    return omml_to_latex_str(f'<m:oMath {DECL}>{body}</m:oMath>')


def r(text, sty=None, nor=False):
    pr = ''
    if sty or nor:
        pr = '<m:rPr>' + (f'<m:sty m:val="{sty}"/>' if sty else '') + ('<m:nor/>' if nor else '') + '</m:rPr>'
    return f'<m:r>{pr}<m:t xml:space="preserve">{text}</m:t></m:r>'


def balanced(s):
    d = 0
    prev = ''
    for ch in s:
        if prev != '\\':
            d += ch == '{'
            d -= ch == '}'
            if d < 0:
                return False
        prev = '' if prev == '\\' else ch
    return d == 0


def test_ns_constant():
    assert NS == 'http://schemas.openxmlformats.org/officeDocument/2006/math'


def test_plain_run_and_greek():
    assert M(r('α+β=Ω')) == r'\alpha+\beta=\Omega'


def test_symbols_and_minus():
    assert M(r('a·b×c≤d≥e≠f≈g±h∓i−j')) == r'a\cdot b\times c\leq d\geq e\neq f\approx g\pm h\mp i-j'


def test_infinity_arrow_degree():
    assert M(r('x→∞')) == r'x\rightarrow\infty'
    assert M(r('30°')) == r'30^{\circ}'


def test_invisible_operators_dropped():
    assert M(r('f⁡(x)⁢y⁣z⁤')) == 'f(x)yz'


def test_upright_unit_mathrm():
    assert M(r('5') + r(' ') + r('kΩ', 'p')) == r'5\,\mathrm{k\Omega}'


def test_upright_split_runs_merge():
    # το app/omml.py γράφει \mathrm{k\Omega} ως "k"(sty p) + "Ω"(απλό)
    assert M(r('k', 'p') + r('Ω')) == r'\mathrm{k\Omega}'


def test_nor_text():
    assert M(r('if x', nor=True)) == r'\text{if x}'


def test_upright_function_name():
    assert M(r('sin', 'p') + r('x')) == r'\sin x'


def test_fraction():
    assert M(f'<m:f><m:num>{r("a")}</m:num><m:den>{r("b")}</m:den></m:f>') == r'\frac{a}{b}'


def test_fraction_types():
    f = lambda t: M(f'<m:f><m:fPr><m:type m:val="{t}"/></m:fPr><m:num>{r("a")}</m:num><m:den>{r("b")}</m:den></m:f>')
    assert f('lin') == 'a/b'
    assert f('skw') == '{}^{a}/_{b}'
    assert f('noBar') == r'\genfrac{}{}{0pt}{}{a}{b}'


def test_sub_sup_subsup():
    assert M(f'<m:sSub><m:e>{r("R")}</m:e><m:sub>{r("1")}</m:sub></m:sSub>') == 'R_{1}'
    assert M(f'<m:sSup><m:e>{r("x")}</m:e><m:sup>{r("2")}</m:sup></m:sSup>') == 'x^{2}'
    assert M(f'<m:sSubSup><m:e>{r("x")}</m:e><m:sub>{r("i")}</m:sub><m:sup>{r("2")}</m:sup></m:sSubSup>') == 'x_{i}^{2}'


def test_multi_atom_base_is_braced():
    assert M(f'<m:sSup><m:e>{r("ab")}</m:e><m:sup>{r("2")}</m:sup></m:sSup>') == '{ab}^{2}'


def test_spre():
    out = M(f'<m:sPre><m:sub>{r("6")}</m:sub><m:sup>{r("14")}</m:sup><m:e>{r("C")}</m:e></m:sPre>')
    assert out == '{}_{6}^{14}C'


def test_radicals():
    assert M(f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>{r("x")}</m:e></m:rad>') == r'\sqrt{x}'
    assert M(f'<m:rad><m:deg>{r("3")}</m:deg><m:e>{r("x")}</m:e></m:rad>') == r'\sqrt[3]{x}'
    assert M(f'<m:rad><m:deg/><m:e>{r("y")}</m:e></m:rad>') == r'\sqrt{y}'


def test_delimiters_default_and_custom():
    assert M(f'<m:d><m:e>{r("a+b")}</m:e></m:d>') == r'\left(a+b\right)'
    assert M(f'<m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr><m:e>{r("x")}</m:e></m:d>') == r'\left[x\right]'
    assert M(f'<m:d><m:dPr><m:begChr m:val="|"/><m:endChr m:val="|"/></m:dPr><m:e>{r("x")}</m:e></m:d>') == r'\left|x\right|'
    assert M(f'<m:d><m:dPr><m:begChr m:val="‖"/><m:endChr m:val="‖"/></m:dPr><m:e>{r("v")}</m:e></m:d>') == r'\left\|v\right\|'


def test_delimiter_none_and_sep():
    out = M(f'<m:d><m:dPr><m:begChr m:val="{{"/><m:endChr m:val=""/></m:dPr><m:e>{r("x")}</m:e></m:d>')
    assert out == r'\left\{x\right.'
    out = M(f'<m:d><m:dPr><m:sepChr m:val=","/></m:dPr><m:e>{r("a")}</m:e><m:e>{r("b")}</m:e></m:d>')
    assert out == r'\left(a,b\right)'


def test_nary_sum_and_integral():
    s = M(f'<m:nary><m:naryPr><m:chr m:val="∑"/></m:naryPr><m:sub>{r("i=1")}</m:sub><m:sup>{r("n")}</m:sup><m:e>{r("i")}</m:e></m:nary>')
    assert s == r'\sum_{i=1}^{n} i'
    i = M(f'<m:nary><m:sub>{r("0")}</m:sub><m:sup>{r("1")}</m:sup><m:e>{r("x")}</m:e></m:nary>')
    assert i == r'\int_{0}^{1} x'


def test_nary_oint_hidden_limits_limloc():
    out = M('<m:nary><m:naryPr><m:chr m:val="∮"/><m:subHide m:val="1"/><m:supHide m:val="1"/></m:naryPr>'
            f'<m:sub/><m:sup/><m:e>{r("E")}</m:e></m:nary>')
    assert out == r'\oint E'
    out = M(f'<m:nary><m:naryPr><m:chr m:val="∫"/><m:limLoc m:val="undOvr"/></m:naryPr><m:sub>{r("a")}</m:sub>'
            f'<m:sup>{r("b")}</m:sup><m:e>{r("f")}</m:e></m:nary>')
    assert out == r'\int\limits_{a}^{b} f'
    out = M(f'<m:nary><m:naryPr><m:chr m:val="∏"/></m:naryPr><m:sub>{r("k")}</m:sub><m:sup/><m:e>{r("a")}</m:e></m:nary>')
    assert out == r'\prod_{k} a'


@pytest.mark.parametrize('ch,cmd', [('⃗', r'\vec'), ('̂', r'\hat'), ('̃', r'\tilde'),
                                    ('̇', r'\dot'), ('̈', r'\ddot'), ('̅', r'\bar')])
def test_accents(ch, cmd):
    assert M(f'<m:acc><m:accPr><m:chr m:val="{ch}"/></m:accPr><m:e>{r("x")}</m:e></m:acc>') == cmd + '{x}'


def test_accent_default_and_wide():
    assert M(f'<m:acc><m:e>{r("a")}</m:e></m:acc>') == r'\hat{a}'
    assert M(f'<m:acc><m:accPr><m:chr m:val="̅"/></m:accPr><m:e>{r("AB")}</m:e></m:acc>') == r'\overline{AB}'
    assert M(f'<m:acc><m:accPr><m:chr m:val="⃗"/></m:accPr><m:e>{r("AB")}</m:e></m:acc>') == r'\overrightarrow{AB}'


def test_bar_and_groupchr():
    assert M(f'<m:bar><m:barPr><m:pos m:val="top"/></m:barPr><m:e>{r("z")}</m:e></m:bar>') == r'\overline{z}'
    assert M(f'<m:bar><m:e>{r("z")}</m:e></m:bar>') == r'\underline{z}'
    assert M(f'<m:groupChr><m:e>{r("a+b")}</m:e></m:groupChr>') == r'\underbrace{a+b}'
    out = M(f'<m:limLow><m:e><m:groupChr><m:e>{r("a+b")}</m:e></m:groupChr></m:e><m:lim>{r("n")}</m:lim></m:limLow>')
    assert out == r'\underbrace{a+b}_{n}'


def test_limlow_limupp():
    assert M(f'<m:limLow><m:e>{r("A")}</m:e><m:lim>{r("x")}</m:lim></m:limLow>') == r'\underset{x}{A}'
    assert M(f'<m:limUpp><m:e>{r("=")}</m:e><m:lim>{r("def")}</m:lim></m:limUpp>') == r'\overset{def}{=}'


def test_func_sin_and_lim():
    assert M(f'<m:func><m:fName>{r("sin", "p")}</m:fName><m:e>{r("θ")}</m:e></m:func>') == r'\sin \theta'
    out = M(f'<m:func><m:fName><m:limLow><m:e>{r("lim", "p")}</m:e><m:lim>{r("x→0")}</m:lim></m:limLow></m:fName>'
            f'<m:e>{r("f")}</m:e></m:func>')
    assert out == r'\lim_{x\rightarrow0} f'
    assert M(f'<m:func><m:fName>{r("sgn", "p")}</m:fName><m:e>{r("x")}</m:e></m:func>') == r'\operatorname{sgn} x'


MAT = (f'<m:m><m:mr><m:e>{r("1")}</m:e><m:e>{r("2")}</m:e></m:mr>'
       f'<m:mr><m:e>{r("3")}</m:e><m:e>{r("4")}</m:e></m:mr></m:m>')


def test_matrix_plain_and_delimited():
    assert M(MAT) == r'\begin{matrix}1 & 2 \\ 3 & 4\end{matrix}'
    assert M(f'<m:d><m:e>{MAT}</m:e></m:d>') == r'\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}'
    out = M(f'<m:d><m:dPr><m:begChr m:val="["/><m:endChr m:val="]"/></m:dPr><m:e>{MAT}</m:e></m:d>')
    assert out == r'\begin{bmatrix}1 & 2 \\ 3 & 4\end{bmatrix}'


def test_eqarr_aligned_and_cases():
    arr = f'<m:eqArr><m:e>{r("x&amp;=1")}</m:e><m:e>{r("y&amp;=2")}</m:e></m:eqArr>'
    assert M(arr) == r'\begin{aligned}x & =1 \\ y & =2\end{aligned}'
    out = M(f'<m:d><m:dPr><m:begChr m:val="{{"/><m:endChr m:val=""/></m:dPr><m:e>{arr}</m:e></m:d>')
    assert out.startswith(r'\begin{cases}') and out.endswith(r'\end{cases}')


def test_ampersand_escaped_outside_eqarr():
    assert M(r('a&amp;b')) == r'a\&b'


def test_box_borderbox_phant_passthrough():
    for tag in ('box', 'borderBox', 'phant'):
        assert M(f'<m:{tag}><m:e>{r("x")}</m:e></m:{tag}>') == 'x'


def test_omathpara_body_only():
    s = f'<m:oMathPara {DECL}><m:oMath>{r("E=mc")}</m:oMath></m:oMathPara>'
    assert omml_to_latex_str(s) == 'E=mc'
    s2 = f'<m:oMathPara {DECL}><m:oMath>{r("a")}</m:oMath><m:oMath>{r("b")}</m:oMath></m:oMathPara>'
    assert omml_to_latex_str(s2) == r'\begin{gathered}a \\ b\end{gathered}'


def test_unknown_elements_never_raise():
    s = (f'<m:oMath {DECL} xmlns:x="urn:x"><x:weird><m:mystery>{r("q")}</m:mystery></x:weird>'
         f'<m:f><m:num/></m:f><m:sSub/></m:oMath>')
    out = omml_to_latex_str(s)
    assert out.startswith('q') and balanced(out)
    assert omml_to_latex(None) == '' and omml_to_latex_str('') == '' and omml_to_latex_str('<broken') == ''


def test_element_input_and_missing_namespace_decl():
    el = ET.fromstring(f'<m:oMath {DECL}>{r("x")}</m:oMath>')
    assert omml_to_latex(el) == 'x'
    assert omml_to_latex_str(f'<m:oMath>{r("y")}</m:oMath>') == 'y'


def test_lxml_element_if_available():
    etree = pytest.importorskip('lxml.etree')
    el = etree.fromstring(f'<m:oMath {DECL}><!-- c -->{r("x")}</m:oMath>')
    assert omml_to_latex(el) == 'x'


def test_special_chars_escaped_balanced():
    out = M(r('{a}%#_$'))
    assert out == r'\{a\}\%\#\_\$' and balanced(out)


def test_complex_nested_balanced():
    body = (f'<m:f><m:num><m:rad><m:deg/><m:e><m:sSup><m:e>{r("x")}</m:e><m:sup>{r("2")}</m:sup></m:sSup></m:e></m:rad></m:num>'
            f'<m:den><m:d><m:e><m:sSub><m:e>{r("R")}</m:e><m:sub>{r("1")}</m:sub></m:sSub>{r("+")}'
            f'<m:acc><m:accPr><m:chr m:val="⃗"/></m:accPr><m:e>{r("F")}</m:e></m:acc></m:e></m:d></m:den></m:f>')
    out = M(body)
    assert out == r'\frac{\sqrt{x^{2}}}{\left(R_{1}+\vec{F}\right)}'
    assert balanced(out)


# ---------- round trip LaTeX -> OMML (app/omml.py) -> LaTeX ----------
needs_l2m = pytest.mark.skipif(omml._L2M is None, reason='latex2mathml not installed')


@needs_l2m
@pytest.mark.parametrize('tex,expected', [
    (r'\frac{a}{b}', r'\frac{a}{b}'),
    (r'\dfrac{V}{R}', r'\frac{V}{R}'),
    (r'R_{1}', r'R_{1}'),
    (r'\sqrt{x}', r'\sqrt{x}'),
    (r'\sqrt[3]{x}', r'\sqrt[3]{x}'),
    (r'\vec{F}', r'\vec{F}'),
    (r'x^{2}', r'x^{2}'),
    (r'5\,\mathrm{k\Omega}', r'5\,\mathrm{k\Omega}'),
    (r'\alpha\cdot\beta', r'\alpha\cdot\beta'),
    (r'\hat{x}', r'\hat{x}'),
    (r'\overline{AB}', r'\overline{AB}'),
    (r'\sin x', r'\sin x'),
    (r'\begin{pmatrix}1&2\\3&4\end{pmatrix}', r'\begin{pmatrix}1 & 2 \\ 3 & 4\end{pmatrix}'),
    (r'I=\frac{V}{R_{1}+R_{2}}', r'I=\frac{V}{R_{1}+R_{2}}'),
])
def test_round_trip(tex, expected):
    for display in (False, True):
        xml = omml.latex_to_omml(tex, display)
        assert xml is not None
        assert omml_to_latex_str(xml) == expected
