"""Κοπή εικόνας ερωτήματος (ή λύσης του) από το PDF με βάση τις θέσεις που υπολογίστηκαν στο ingest."""
import io, json, pathlib, subprocess, tempfile
from PIL import Image, ImageDraw

def render(pdf, geo_json, dpi=130):
    geo = json.loads(geo_json) if isinstance(geo_json, str) else geo_json
    s = dpi / 72.0; parts = []
    with tempfile.TemporaryDirectory() as d:
        for k, r in enumerate(geo['regions']):
            out = pathlib.Path(d) / f'r{k}'
            subprocess.run(['pdftoppm', '-jpeg', '-singlefile', '-r', str(dpi), '-f', str(r['p']), '-l', str(r['p']), '-x', str(int(r['x0'] * s)), '-y', str(int(r['y0'] * s)),
                            '-W', str(max(1, int((r['x1'] - r['x0']) * s))), '-H', str(max(1, int((r['y1'] - r['y0']) * s))), str(pdf), str(out)], check=True, capture_output=True, timeout=60)
            im = Image.open(str(out) + '.jpg').convert('RGB')
            m = geo.get('mask')
            if k == 0 and m and m[0] == r['p']:                 # σβήνει τον αρχικό αριθμό ερωτήματος (π.χ. «2.1»)
                ImageDraw.Draw(im).rectangle([(m[1] - r['x0']) * s, (m[2] - r['y0']) * s, (m[3] - r['x0']) * s, (m[4] - r['y0']) * s], fill='white')
            parts.append(im)
    w = max(p.width for p in parts); h = sum(p.height for p in parts)
    canvas = Image.new('RGB', (w, h), 'white'); y = 0
    for p in parts: canvas.paste(p, (0, y)); y += p.height
    buf = io.BytesIO(); canvas.save(buf, 'JPEG', quality=82); return buf.getvalue()

def width_pt(geo_json):
    geo = json.loads(geo_json) if isinstance(geo_json, str) else geo_json
    return max(r['x1'] - r['x0'] for r in geo['regions'])
