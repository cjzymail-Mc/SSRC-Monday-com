"""Shared bounded scheduling projection for timeline and Gantt views."""
from datetime import date

MAX_SCHEDULE_TASKS=500
MAX_RANGE_DAYS=3660
SCALES={"day","week","month"}


class ScheduleError(Exception):
    def __init__(self,code,message,details=None):super().__init__(message);self.code=code;self.message=message;self.details=details or {}


def parse_day(value):
    if not isinstance(value,str) or len(value)!=10:return None
    try:parsed=date.fromisoformat(value)
    except ValueError:return None
    return parsed if 1900<=parsed.year<=2200 else None


def source_range(task,source,field_types):
    if source=={"kind":"fixed"}:
        raw_start,raw_end=task.get("start_date"),task.get("due");start=parse_day(raw_start);end=parse_day(raw_end)
        if raw_start not in {None,""} and not start:return None
        if raw_end not in {None,"","未设置"} and not end:return None
    else:
        field_id=source.get("id");kind=field_types.get(field_id);value=task.get("field_values",{}).get(str(field_id))
        if kind=="date":
            start=end=parse_day(value)
            if value not in {None,""} and not start:return None
        elif kind=="timeline" and isinstance(value,dict):
            raw_start,raw_end=value.get("start"),value.get("end");start=parse_day(raw_start);end=parse_day(raw_end)
            if (raw_start not in {None,""} and not start) or (raw_end not in {None,""} and not end):return None
        else:start=end=None
    if start and not end:end=start
    if end and not start:start=end
    if start and end and start>end:return None
    return (start,end) if start and end else None


def project(tasks,source,field_types):
    scheduled=[];unscheduled=[]
    for task in tasks:
        bounds=source_range(task,source,field_types)
        item={key:task.get(key) for key in ("id","title","group_id","group_name","parent_id","subtask_order","version")}
        if not bounds:unscheduled.append(item);continue
        start,end=bounds;item.update({"start":start.isoformat(),"end":end.isoformat(),"duration_days":(end-start).days+1,"milestone":start==end});scheduled.append(item)
    if scheduled:
        first=min(parse_day(item["start"]) for item in scheduled);last=max(parse_day(item["end"]) for item in scheduled);span=(last-first).days+1
        if span>MAX_RANGE_DAYS:raise ScheduleError("SCHEDULE_RANGE_LIMIT","排期范围超过安全上限",{"max_days":MAX_RANGE_DAYS,"span_days":span})
        bounds={"start":first.isoformat(),"end":last.isoformat(),"span_days":span}
    else:bounds=None
    return scheduled,unscheduled,bounds


def critical_path(items,edges):
    nodes={item["id"]:item for item in items};outgoing={node:[] for node in nodes};incoming={node:[] for node in nodes}
    visible=[]
    for edge in edges:
        predecessor,successor=edge["predecessor_id"],edge["successor_id"]
        if predecessor in nodes and successor in nodes:
            outgoing[predecessor].append(successor);incoming[successor].append(predecessor);visible.append({"id":edge["id"],"predecessor_id":predecessor,"successor_id":successor})
    indegree={node:len(incoming[node]) for node in nodes};queue=sorted(node for node,value in indegree.items() if value==0);order=[]
    while queue:
        node=queue.pop(0);order.append(node)
        for successor in sorted(outgoing[node]):
            indegree[successor]-=1
            if indegree[successor]==0:
                queue.append(successor);queue.sort()
    if len(order)!=len(nodes):return {"task_ids":[],"duration_days":0,"blocked":True,"diagnostic":{"code":"DEPENDENCY_CYCLE","message":"可见依赖存在循环，关键路径已停用"}},visible
    distance={};previous={}
    for node in order:
        duration=nodes[node]["duration_days"];candidates=[(distance[parent]+duration,parent) for parent in incoming[node]]
        if candidates:
            best,parent=max(candidates,key=lambda item:(item[0],-item[1]));distance[node]=best;previous[node]=parent
        else:distance[node]=duration
    if not distance:return {"task_ids":[],"duration_days":0,"blocked":False},visible
    current=max(distance,key=lambda node:(distance[node],-node));path=[]
    while current in nodes:path.append(current);current=previous.get(current)
    path.reverse();return {"task_ids":path,"duration_days":max(distance.values()),"blocked":False},visible
