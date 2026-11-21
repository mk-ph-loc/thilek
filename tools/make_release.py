#!/usr/bin/env python3
"""Δημιουργεί thilek-vX.Y.Z.zip με φάκελο thilek/ στη ρίζα."""
import pathlib, re, zipfile, stat
root = pathlib.Path(__file__).resolve().parent.parent
ver = re.search(r'"([^"]+)"', (root / 'app' / '__init__.py').read_text()).group(1)
out = root / f'thilek-v{ver}.zip'
skip = {'__pycache__', '.git', '.venv', '.pytest_cache'}
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob('*')):
        if p.is_dir() or skip & set(p.parts) or p.suffix in ('.zip', '.pyc', '.db'): continue
        zi = zipfile.ZipInfo(f'thilek/{p.relative_to(root).as_posix()}', (2026, 11, 19, 0, 0, 0))
        zi.external_attr = ((0o755 if p.suffix == '.sh' else 0o644) | stat.S_IFREG) << 16
        z.writestr(zi, p.read_bytes(), zipfile.ZIP_DEFLATED)
print(out)
