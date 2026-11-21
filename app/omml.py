"""LaTeX -> MathML (βιβλιοθήκη latex2mathml) -> OMML (εξισώσεις Word). Μικρός μετατροπέας MathML->OMML σε Python,
γιατί το MML2OMML.xsl είναι μέρος του Office και δεν υπάρχει στον server. Ό,τι δεν υποστηρίζεται δίνει None (ο καλών γράφει κείμενο)."""
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

try:
    import latex2mathml.converter as _L2M
except Exception:                      # χωρίς τη βιβλιοθήκη: όλοι οι τύποι πέφτουν σε αναγνώσιμο κείμενο
    _L2M = None

MML = '{http://www.w3.org/1998/Math/MathML}'
M_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
ACCENT = {'→': '\u20d7', '\u00af': '\u0305', '\u02c9': '\u0305', '^': '\u0302', '~': '\u0303', '.': '\u0307', '\u02d9': '\u0307', '\u203e': '\u0305', '\u2015': '\u0305'}

class Unsupported(Exception): pass

def _upright(tex):
    """\\mathrm{kΩ}, \\operatorname{..} -> \\text{..} (όρθια γράμματα, όπως οι μονάδες): οι εντολές μέσα μένουν εκτός \\text."""
    def sub(m):
        return ''.join(p if p.startswith('\\') else '\\text{' + p + '}' for p in re.findall(r'\\[A-Za-z]+|[^\\]+', m.group(2)))
    return re.sub(r'\\(mathrm|operatorname|textrm|mathbf|boldsymbol)\{([^{}]*)\}', sub, tex)

def _run(text, style=None):
    rpr = f'<m:rPr><m:sty m:val="{style}"/></m:rPr>' if style else ''
    return f'<m:r>{rpr}<m:t xml:space="preserve">{escape(text)}</m:t></m:r>'

def _space(width):
    try: em = float(re.sub(r'[^0-9.\-]', '', width or '0.2') or 0.2)
    except ValueError: em = 0.2
    return '\u2009' if em < 0.2 else '\u2004' if em < 0.5 else '\u2003' if em < 1.5 else '\u2003\u2003'

def _conv(e):
    t = e.tag.replace(MML, ''); k = list(e); c = lambda i: _conv(k[i])
    if t in ('math', 'mrow', 'mstyle', 'mpadded'): return ''.join(_conv(x) for x in k)
    if t == 'mi': s = e.text or ''; return _run(s, 'p' if len(s) > 1 else None)
    if t in ('mn', 'mo'): return _run(e.text or '')
    if t == 'mtext': return _run(e.text or '', 'p')
    if t == 'mspace': return _run(_space(e.get('width')))
    if t == 'mfrac': return f'<m:f><m:num>{c(0)}</m:num><m:den>{c(1)}</m:den></m:f>'
    if t == 'msup': return f'<m:sSup><m:e>{c(0)}</m:e><m:sup>{c(1)}</m:sup></m:sSup>'
    if t == 'msub': return f'<m:sSub><m:e>{c(0)}</m:e><m:sub>{c(1)}</m:sub></m:sSub>'
    if t == 'msubsup': return f'<m:sSubSup><m:e>{c(0)}</m:e><m:sub>{c(1)}</m:sub><m:sup>{c(2)}</m:sup></m:sSubSup>'
    if t == 'msqrt': return f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/><m:e>{"".join(_conv(x) for x in k)}</m:e></m:rad>'
    if t == 'mroot': return f'<m:rad><m:radPr/><m:deg>{c(1)}</m:deg><m:e>{c(0)}</m:e></m:rad>'
    if t == 'mover':
        o = k[1]
        if o.tag.replace(MML, '') == 'mo' and (o.text or '') in ACCENT:
            return f'<m:acc><m:accPr><m:chr m:val="{ACCENT[o.text]}"/></m:accPr><m:e>{c(0)}</m:e></m:acc>'
        return f'<m:limUpp><m:e>{c(0)}</m:e><m:lim>{c(1)}</m:lim></m:limUpp>'
    if t == 'munder': return f'<m:limLow><m:e>{c(0)}</m:e><m:lim>{c(1)}</m:lim></m:limLow>'
    if t == 'mtable':
        rows = ''.join('<m:mr>' + ''.join(f'<m:e>{"".join(_conv(y) for y in td)}</m:e>' for td in tr) + '</m:mr>' for tr in k)
        return f'<m:m>{rows}</m:m>'
    raise Unsupported(t)

def latex_to_omml(tex, display=False):
    """-> συμβολοσειρά XML (<m:oMath> ή <m:oMathPara>, χωρίς δήλωση namespace) ή None αν δεν μετατρέπεται."""
    if _L2M is None or not (tex or '').strip(): return None
    try:
        root = ET.fromstring(_L2M.convert(_upright(tex)))
        body = _conv(root)
    except Exception:
        return None
    return f'<m:oMathPara><m:oMath>{body}</m:oMath></m:oMathPara>' if display else f'<m:oMath>{body}</m:oMath>'
