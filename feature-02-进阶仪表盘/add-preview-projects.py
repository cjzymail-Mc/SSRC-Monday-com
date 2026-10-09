"""Add 30 varied projects only to the fixed feature02 local preview database."""
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flowboard.database import connect
from flowboard.overview import project_overview
from flowboard.timeline import TimelineService

DB=(ROOT/'local-test-data/feature02-preview/flowboard.db').resolve()
STAGES=('创意','设计','开发','测试','量产','应用迭代')
NAMES=('晨曦休闲鞋','凌云竞速跑鞋','跃影篮球鞋','霜羽羽毛球鞋','拓野徒步鞋','轻风训练鞋')
VARIANTS=('概念款','轻量款','竞赛款','耐磨款','联名款')
NODE_NAMES=('需求与材料沟通','技术方案确认','样品准备','阶段评审','主线交付检查','并行质量验证','团队复核','阶段成果交付')


def main():
    assert DB==ROOT/'local-test-data/feature02-preview/flowboard.db' and DB.is_file()
    evidence=ROOT/'team-progress/verification/20261008-feature02'
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
    backup=DB.parent/'backups'/f'preview-before-more-projects-{stamp}.db'
    backup.parent.mkdir(exist_ok=True)
    conn=connect(DB)
    with sqlite3.connect(backup) as restored:
        conn.backup(restored)
        assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    existing={row['name']:row['id'] for row in conn.execute('SELECT id,name FROM timeline_projects WHERE deleted_at IS NULL')}
    conn.close()
    today=datetime.now(timezone(timedelta(hours=8))).date()
    service=TimelineService(DB);created=[];skipped=[]
    for stage_index,stage in enumerate(STAGES):
        for variant_index,done_count in enumerate((0,2,4,6,8)):
            name=f'{NAMES[stage_index]} · {VARIANTS[variant_index]}（演示）'
            if name in existing:
                skipped.append(existing[name]);continue
            owner='dev' if (stage_index+variant_index)%2==0 else 'u2'
            user={'id':owner}
            project=service.create_project(user,1,{'name':name})
            changes=[]
            for i in range(8):
                node_stage=STAGES[max(0,stage_index-2+i)] if i<3 else stage
                days=(-12,-7,-3,0,1,2,4,9)[i]
                done=i<done_count
                if done:days=min(0,days)
                value=(today+timedelta(days=days)).isoformat()
                changes.append({'create':{'track':'main' if i%2==0 else 'parallel','stage':node_stage,'name':NODE_NAMES[i],
                                          'date':value,'done_at':done,'remark':f'{stage}阶段演示；{NODE_NAMES[i]}。'+('结果已确认，材料已归档。' if done else '等待团队确认下一步安排。')}})
            result=service.submit_batches(user,1,{'requests':[{'project_id':project['project_id'],'base_version':project['version'],'changes':changes}]})
            view=result['results'][0]['view']
            assert view['metrics']['current_stage']==stage
            assert len(view['nodes'])==8 and sum(n['done_at'] for n in view['nodes'])==done_count
            created.append({'id':project['project_id'],'name':name,'stage':stage,'progress':done_count*100//8,'creator':owner})
    payload=project_overview(service,{'id':'dev'},1,{'period':['all'],'completion':['all']})
    samples=[p for p in payload['projects'] if p['name'].endswith('（演示）')]
    assert len(samples)==30
    assert set(p['current_stage'] for p in samples)==set(STAGES)
    # Existing samples may have been refined or edited after their first creation.
    by_id={p['project_id']:p for p in samples}
    for item in created:
        assert by_id[item['id']]['node_count']==8
        assert by_id[item['id']]['progress']==item['progress']
    report={'created':created,'skipped':skipped,'backup':str(backup),'database':str(DB),'server_today':payload['server_today'],
            'sample_projects':30,'sample_nodes':sum(p['node_count'] for p in samples),'active_projects':payload['counts']['projects'],
            'sample_groups':dict(Counter(p['group'] for p in samples)), 'progress_distribution':dict(Counter(p['progress'] for p in samples))}
    # Preserve the original creation ledger used to identify these owned samples.
    ledger_path=evidence/'more-preview-projects.json'
    if ledger_path.exists() and not created:
        report_path=evidence/'more-preview-projects-check.json'
    else:
        if ledger_path.exists():
            prior=json.loads(ledger_path.read_text(encoding='utf-8'))
            ledger={item['name']:item for item in prior.get('created',[])}
            ledger.update({item['name']:item for item in created})
            report['created']=list(ledger.values())
        report_path=ledger_path
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('created','skipped')},ensure_ascii=False))


if __name__=='__main__':main()
