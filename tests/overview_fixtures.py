from datetime import timedelta
from flowboard.database import connect


def seed_overview(db_path, today, *, long_list=False):
    conn = connect(db_path)
    ids = {}
    stamp = '2026-10-08T00:00:00+00:00'
    def project(key, name, creator='u1', archived=None, deleted=None, workspace=1):
        cur = conn.execute('INSERT INTO timeline_projects(workspace_id,name,created_by,created_at,updated_at,archived_at,deleted_at) VALUES (?,?,?,?,?,?,?)', (workspace,name,creator,stamp,stamp,archived,deleted))
        ids[key] = cur.lastrowid
        return cur.lastrowid
    def node(pid, name, days, stage='设计', track='main', done=False, remark='', deleted=None):
        date = (today+timedelta(days=days)).isoformat()
        return conn.execute('INSERT INTO timeline_nodes(project_id,track,stage,name,date,initial_date,done_at,remark,created_at,updated_at,deleted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (pid,track,stage,name,date,date,stamp if done else None,remark,stamp,stamp,deleted)).lastrowid
    pid=project('risk','疾风跑鞋 · 二代研发')
    ids['overdue_node']=node(pid,'鞋面材料确认',-20,'创意',remark='供应商色卡待确认')
    ids['today_node']=node(pid,'首轮样鞋评审',0,'开发',remark='主线评审与并行测试同日推进')
    node(pid,'鞋底耐磨测试',0,'测试','parallel',remark='检查弯折与耐磨表现')
    node(pid,'研发样品交付',2,'开发',done=True,remark='已提交研发样品')
    node(pid,'未来节点',60,'量产')
    node(pid,'删除节点机密',0,deleted=stamp)
    pid=project('team','跃动篮球鞋 · 缓震升级','u2')
    node(pid,'缓震结构设计',1,'设计',remark='前掌回弹对照试验')
    node(pid,'篮球鞋评审',2,'测试','parallel',done=True)
    pid=project('done','轻羽竞速 · 本周成果')
    node(pid,'鞋楦方案定稿',0,'设计',done=True,remark='本周设计节点已完成')
    pid=project('future','越野探索 · 远期项目')
    node(pid,'开模准备',60,'量产')
    project('empty','新季概念 · 待录入')
    pid=project('long','超长项目名称用于检查紧凑列表与详情全文展示' * 5,'u2')
    node(pid,'长节点名称' * 35,1,'应用迭代',remark='多行备注测试\n'+'复杂工艺说明与材料沟通记录，'*35)
    pid=project('archived','归档项目机密',archived=stamp)
    node(pid,'归档节点机密',0)
    pid=project('deleted','删除项目机密',deleted=stamp)
    node(pid,'删除项目节点机密',0)
    if long_list:
        for i in range(35):
            pid=project('list'+str(i),f'研发项目 {i+1:02d} · 多项目列表', 'u2' if i%2 else 'u1')
            node(pid,f'研发检验 {i+1:02d}',i%5,'开发')
            node(pid,f'并行完成 {i+1:02d}',i%5,'测试','parallel',done=True)
    conn.commit()
    conn.close()
    return ids
