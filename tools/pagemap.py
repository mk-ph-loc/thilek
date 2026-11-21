#!/usr/bin/env python3
"""Build subsection->pages map from the book's table of contents and verify printed-page offset on every page."""
import sys, re, json, subprocess, csv, collections
book, outdir = sys.argv[1], sys.argv[2]
n = int(re.search(r'Pages:\s+(\d+)', subprocess.run(['pdfinfo',book],capture_output=True,text=True).stdout).group(1))
def page(p): return subprocess.run(['pdftotext','-f',str(p),'-l',str(p),'-layout',book,'-'],capture_output=True,text=True).stdout
# 1) offset check: footer line "24-0332.indb <N>" holds PDF-visible number; the printed number is the lone number line above it
off = collections.Counter(); per={}
for p in range(1,n+1):
    t = page(p)
    m = re.search(r'24-0332\.indb\s+(\d+)', t)
    if m: per[p]=int(m.group(1)); off[p-int(m.group(1))]+=1
print('pages with footer:',len(per),'of',n,'| offsets (pdf-printed):',dict(off))
# 2) TOC entries  "1.3.1 Title ..... 62"  and unit headers
toc=[]
for p in range(6,19):
    for line in page(p).splitlines():
        m = re.match(r'\s*(\d+\.\d+(?:\.\d+)?)\.?\s+(.+?)[\s.]{3,}(\d{1,3})\s*$', line)
        if m: toc.append((m.group(1), m.group(2).strip(), int(m.group(3))))
toc.sort(key=lambda x:[int(v) for v in x[0].split('.')])
rows=[]
for i,(c,t,s) in enumerate(toc):
    e = toc[i+1][2] if i+1<len(toc) else None
    rows.append({'code':c,'level':c.count('.')+1,'title':t,'page_from':s,'page_to_next_start':e})
json.dump(rows, open(f'{outdir}/book_sections.json','w'), ensure_ascii=False, indent=1)
with open(f'{outdir}/book_sections.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(rows),'toc entries'); [print(r) for r in rows[:6]]; print('...'); [print(r) for r in rows[-4:]]
