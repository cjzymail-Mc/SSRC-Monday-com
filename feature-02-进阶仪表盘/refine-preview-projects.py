"""Rebuild owned demo samples from read-only production timeline shapes."""
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flowboard.database import connect
from flowboard.overview import project_overview
from flowboard.timeline import TimelineService

PRODUCTION=(ROOT/'flowboard.db').resolve()
PREVIEW=(ROOT/'local-test-data/feature02-preview/flowboard.db').resolve()
EVIDENCE=ROOT/'team-progress/verification/20261008-feature02'
REMARKS={
    '创意':'目标人群与需求已沟通，下一轮确认产品定位。',
    '设计':'已同步配色与鞋楦方案，等待工艺图确认。',
    '开发':'工厂正在核对样品与模具细节，按实际打样结果复核。',
    '测试':'已安排试穿与性能验证，收齐报告后复核结论。',
    '量产':'核对BOM、齐色和模具状态后确认量产安排。',
    '应用迭代':'收集上市后穿着反馈，用于下一轮版本调整。',
}


def signature(nodes):
    return sorted((n['name'],n['stage'],n['track'],n['date'],bool(n['done_at']),n['remark']) for n in nodes)


def load_shapes():
    # URI mode=ro cannot open a write-capable handle; query_only adds a second guard.
    conn=sqlite3.connect(PRODUCTION.as_uri()+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON');conn.execute('BEGIN')
    profiles=[]
    try:
        for p in conn.execute('SELECT id FROM timeline_projects WHERE workspace_id=1 AND deleted_at IS NULL AND archived_at IS NULL ORDER BY id'):
            nodes=[]
            for n in conn.execute('SELECT name,stage,track,date,done_at,length(remark) remark_length FROM timeline_nodes WHERE project_id=? AND deleted_at IS NULL ORDER BY date,id',(p['id'],)):
                # Keep the real milestone vocabulary and geometry; comments are synthetic.
                nodes.append({'name':n['name'],'stage':n['stage'],'track':n['track'],'date':n['date'],
                              'done_at':bool(n['done_at']),'remark':REMARKS[n['stage']] if n['remark_length'] else ''})
            profiles.append({'template_id':p['id'],'nodes':nodes})
    finally:
        conn.close()
    return profiles


def main():
    assert PRODUCTION!=PREVIEW and PRODUCTION.is_file() and PREVIEW.is_file()
    originals=json.loads((EVIDENCE/'more-preview-projects.json').read_text(encoding='utf-8'))['created']
    assert len(originals)==30
    profiles=load_shapes()
    assert len(profiles)>=5
    # Cover every current real shape, then repeat dense shapes for long-detail inspection.
    chosen=(profiles+sorted(profiles,key=lambda p:len(p['nodes']),reverse=True))[:len(originals)]
    assert len(chosen)==len(originals)
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    backup=PREVIEW.parent/'backups'/f'preview-before-realistic-shapes-{stamp}.db'
    conn=connect(PREVIEW)
    with sqlite3.connect(backup) as destination:
        conn.backup(destination)
        assert destination.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    conn.close()
    service=TimelineService(PREVIEW);updated=[];unchanged=[];protected=[]
    for sample,shape in zip(originals,chosen):
        project=service.get_project({'id':'dev'},sample['id'])
        if signature(project['nodes'])==signature(shape['nodes']):
            unchanged.append(sample['id']);continue
        if project['version']!=2 or project['name']!=sample['name']:
            # A later user edit takes precedence over replacing an agent-owned sample.
            protected.append(sample['id']);continue
        changes=[{'node_id':n['id'],'remove':True} for n in project['nodes']]
        changes += [{'create':n} for n in shape['nodes']]
        if changes:
            result=service.submit_batches({'id':'dev'},1,{'requests':[{'project_id':project['project_id'],'base_version':project['version'],'changes':changes}]})
            view=result['results'][0]['view']
        else:
            view=project
        assert signature(view['nodes'])==signature(shape['nodes'])
        updated.append({'project_id':project['project_id'],'template_id':shape['template_id'],
                        'nodes':len(view['nodes']),'done':sum(n['done_at'] for n in view['nodes']),
                        'tracks':dict(Counter(n['track'] for n in view['nodes']))})
    payload=project_overview(service,{'id':'dev'},1,{'period':['all'],'completion':['all'],'q':['（演示）']})
    samples=payload['projects']
    assert len(samples)==30
    spans=[]
    for p in samples:
        if p['matched_nodes']:
            dates=[date.fromisoformat(n['date']) for n in p['matched_nodes']]
            spans.append((max(dates)-min(dates)).days)
    report={'production_access':'mode=ro; PRAGMA query_only=ON; read transaction',
            'production_profiles':len(profiles),'production_profile_hash':hashlib.sha256(json.dumps(profiles,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
            'preview_database':str(PREVIEW),'backup':str(backup),'updated':updated,'unchanged':unchanged,'protected_user_edits':protected,
            'counts':payload['counts'],'node_count_distribution':dict(sorted(Counter(p['node_count'] for p in samples).items())),
            'progress_distribution':dict(sorted(Counter(p['progress'] for p in samples).items(),key=lambda v:-1 if v[0] is None else v[0])),
            'date_span_days_min':min(spans),'date_span_days_max':max(spans),
            'track_distribution':dict(Counter(n['track'] for p in samples for n in p['matched_nodes'])),
            'sample_groups':dict(Counter(p['group'] for p in samples))}
    (EVIDENCE/'realistic-preview-projects.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('updated','unchanged')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
