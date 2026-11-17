"""Summarize already-produced evaluation; never selects or retunes a candidate."""
import csv,json
from statistics import mean
from pathlib import Path
from benchmark_scheduling import OUT,FAMILIES,write,run
from queuepact.models import Policy
from queuepact.presets import presets

def load(name):
 with (OUT/name).open(encoding='utf-8') as f:return list(csv.DictReader(f))

rows=load('heldout.csv');pairs=[]
for family in FAMILIES:
 for seed in range(200,210):
  rr={r['policy']:r for r in rows if r['family']==family and int(r['seed'])==seed}
  for ref in ('Ordinary','v1'):
   a,b=rr['v2'],rr[ref];complete=int(a['unfinished'])==int(b['unfinished'])==0
   pairs.append(dict(family=family,seed=seed,reference=ref,complete=complete,**{k:float(a[k])-float(b[k]) if complete else None for k in ('wait','p90','maximum','visit','makespan')},outcome='incomplete' if not complete else 'win' if float(a['wait'])<float(b['wait'])-.01 else 'loss' if float(a['wait'])>float(b['wait'])+.01 else 'tie'))
write('heldout-paired.csv',pairs)
summary=[]
for family in (*FAMILIES,'ALL'):
 for ref in ('Ordinary','v1'):
  rr=[r for r in pairs if r['reference']==ref and (r['family']==family or family=='ALL')]
  summary.append(dict(family=family,reference=ref,**{k:mean(r[k] for r in rr) if all(r['complete'] for r in rr) else None for k in ('wait','p90','maximum','visit','makespan')},**{k:sum(r['outcome']==k for r in rr) for k in ('win','tie','loss','incomplete')}))
write('heldout-paired-summary.csv',summary)
write('worst-regressions.csv',sorted((r for r in pairs if r['complete']),key=lambda r:r['wait'],reverse=True)[:20])
pp=[]
for preset in presets():
 for p in Policy:
  _,m=run(preset.specification,p);pp.append(dict(preset=preset.name,policy=p.label,**m))
write('presets.csv',pp)
# Small inline SVG plots: no export dependency/CDN.
for metric in ('wait','p90'):
 svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 560"><rect width="1000" height="560" fill="white"/><g font-family="Arial" font-size="14" fill="#172b4d"><text x="30" y="28">Held-out v2 minus reference: '+metric+' (minutes; positive is worse)</text>'
 maximum=max((abs(r[metric]) for r in summary if r['family']!='ALL' and r[metric] is not None),default=1) or 1
 for i,family in enumerate(FAMILIES):
  y=60+i*45;svg+=f'<text x="15" y="{y+14}">{family}</text><path d="M480 {y-3}v38" stroke="#999"/>'
  for j,ref in enumerate(('Ordinary','v1')):
   v=next(r[metric] for r in summary if r['family']==family and r['reference']==ref)
   if v is None:
    svg+=f'<text x="820" y="{y+12+j*17}">{ref}: incomplete</text>';continue
   w=abs(v)/maximum*300;x=480 if v>=0 else 480-w
   svg+=f'<rect x="{x}" y="{y+j*17}" width="{w}" height="13" fill="{("#2563eb","#7c3aed")[j]}"/><text x="820" y="{y+12+j*17}">{ref}: {v:+.2f}</text>'
 svg+='</g></svg>';(OUT/f'{metric}-differences.svg').write_text(svg)
print(json.dumps(dict(overall=[r for r in summary if r['family']=='ALL'],presets=pp,worst=sorted((r for r in pairs if r['complete']),key=lambda r:r['wait'],reverse=True)[:2]),indent=2))
