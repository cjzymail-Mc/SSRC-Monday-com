from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'overview-ui.js'
s=p.read_text(encoding='utf-8')
assert '<col style="width:32%">' in s
p.write_text(s.replace('<col style="width:32%">','<col style="width:16%">'),encoding='utf-8')
