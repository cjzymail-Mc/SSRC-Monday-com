from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[3]
p=ROOT/'overview-ui.js';s=p.read_text(encoding='utf-8')
old='<header class="ov-header"><h1>项目概览</h1><span>${payload?esc(payload.server_today):\'\'}</span></header>'
assert old in s
s=s.replace(old,'<header class="ov-header tl-home-head"><div><h1>项目概览</h1><small>今天 ${payload?esc(payload.server_today):\'\'}</small></div></header>')
start=s.index('<label class="ov-search">');end=s.index('</div><div class="ov-quick"',start)
s=s[:start]+'${secondaryControlsEnabled?`'+s[start:end]+"`:''}"+s[end:]
start=s.index('<div class="ov-advanced"');end=s.index('<div class="ov-content">',start)
s=s[:start]+'${secondaryControlsEnabled?`'+s[start:end]+"`:''}"+s[end:]
p.write_text(s,encoding='utf-8')
p=ROOT/'overview.css';s=p.read_text(encoding='utf-8')
s=re.sub(r'\.ov-header h1\{[^}]*\}|\.ov-header>span\{[^}]*\}','',s)
s+='\n.ov-header{font-family:"DM Sans",Segoe UI,sans-serif}\n'
p.write_text(s,encoding='utf-8')
p=ROOT/'index.html';s=p.read_text(encoding='utf-8').replace('20261009-f02-overview-polish','20261009-f02-minimal-feed');p.write_text(s,encoding='utf-8')
