"""Read-only project overview. No second persisted status or progress model."""
from collections import defaultdict
from datetime import timedelta

from .service import ApiError
from .timeline import STAGES, _natural_key


CHOICES = {
    "period": ("week", "month", "next30", "all"),
    "scope": ("all", "mine"),
    "stage": ("all", *STAGES),
    "track": ("all", "main", "parallel"),
    "completion": ("open", "all", "done"),
    "focus": ("all", "attention", "overdue", "today", "done"),
    "search_in": ("all", "project", "node"),
}


def project_overview(service, user, workspace_id, query):
    if set(query) - {*CHOICES, "q", "tag_id"}:
        raise ApiError(422, "VALIDATION_ERROR", "未知项目总览筛选参数")
    filters = {}
    for key, choices in CHOICES.items():
        values = query.get(key, [choices[0]])
        if len(values) != 1 or values[0] not in choices:
            raise ApiError(422, "VALIDATION_ERROR", f"无效的 {key} 筛选")
        filters[key] = values[0]
    searches = query.get("q", [""])
    if len(searches) != 1 or not isinstance(searches[0], str) or len(searches[0]) > 100:
        raise ApiError(422, "VALIDATION_ERROR", "搜索限100个字符")
    filters["q"] = searches[0].strip()
    tags = query.get("tag_id", ["all"])
    if len(tags) != 1 or not (tags[0] in ("all", "uncategorized") or (len(tags[0]) <= 18 and tags[0].isascii() and tags[0].isdigit() and int(tags[0]) > 0)):
        raise ApiError(422, "VALIDATION_ERROR", "无效的项目标签")
    filters["tag_id"] = tags[0]
    conn = service._db()
    try:
        conn.execute("BEGIN")  # ACL, projects and nodes share one read snapshot.
        role = service._workspace_access(conn, user["id"], workspace_id)
        if filters["tag_id"] not in ("all", "uncategorized"):
            tag = conn.execute("SELECT id FROM timeline_tags WHERE workspace_id=? AND id=? AND deleted_at IS NULL", (workspace_id, int(filters["tag_id"]))).fetchone()
            if tag is None:
                raise ApiError(422, "VALIDATION_ERROR", "项目标签已不可用")
        today = service._server_today()
        start, end = None, None
        if filters["period"] == "week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
        elif filters["period"] == "month":
            start = today.replace(day=1)
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        elif filters["period"] == "next30":
            start, end = today, today + timedelta(days=29)
        projects = conn.execute(
            """SELECT p.*,u.name creator_name,u.avatar_class creator_avatar_class
               FROM timeline_projects p LEFT JOIN users u ON u.id=p.created_by
               WHERE p.workspace_id=? AND p.deleted_at IS NULL AND p.archived_at IS NULL
               AND (?='all' OR (?='uncategorized' AND NOT EXISTS(
                   SELECT 1 FROM timeline_project_tags pt JOIN timeline_tags t ON t.id=pt.tag_id
                   WHERE pt.project_id=p.id AND pt.workspace_id=p.workspace_id AND t.workspace_id=p.workspace_id AND pt.deleted_at IS NULL AND t.deleted_at IS NULL
               )) OR EXISTS(
                   SELECT 1 FROM timeline_project_tags pt JOIN timeline_tags t ON t.id=pt.tag_id
                   WHERE pt.project_id=p.id AND pt.workspace_id=p.workspace_id AND t.workspace_id=p.workspace_id AND pt.tag_id=? AND pt.deleted_at IS NULL AND t.deleted_at IS NULL
               ))
               AND (?='all' OR p.created_by=?) ORDER BY p.id""",
            (workspace_id, filters["tag_id"], filters["tag_id"], filters["tag_id"], filters["scope"], user["id"]),
        ).fetchall()
        grouped = defaultdict(list)
        # Join constrains the node query before projection; no cross-workspace fetch.
        for node in conn.execute(
            """SELECT n.* FROM timeline_nodes n JOIN timeline_projects p ON p.id=n.project_id
               WHERE p.workspace_id=? AND p.deleted_at IS NULL AND p.archived_at IS NULL
               AND n.deleted_at IS NULL AND (?='all' OR p.created_by=?)""",
            (workspace_id, filters["scope"], user["id"]),
        ):
            grouped[node["project_id"]].append(node)
        result = []
        search = filters["q"].casefold()
        for project in projects:
            nodes = sorted(grouped[project["id"]], key=lambda n: (n["date"], _natural_key(n["name"]), n["id"]))
            view = service._view(conn, project, user_id=user["id"], role=role, nodes=nodes, today=today)
            project_match = not search or (filters["search_in"] != "node" and search in (project["name"] + " " + (project["creator_name"] or "")).casefold())
            matched = []
            for node in view["nodes"]:
                date = service._date(node["date"])
                overdue = not node["done_at"] and date < today
                if filters["completion"] == "open" and node["done_at"]:
                    continue
                if filters["completion"] == "done" and not node["done_at"]:
                    continue
                focus = filters["focus"]
                if focus == "attention" and not (overdue or (not node["done_at"] and date == today)):
                    continue
                if focus == "overdue" and not overdue:
                    continue
                if focus == "today" and not (not node["done_at"] and date == today):
                    continue
                if focus == "done" and not node["done_at"]:
                    continue
                if start is not None and not (start <= date <= end or overdue):
                    continue
                if filters["stage"] != "all" and node["stage"] != filters["stage"]:
                    continue
                if filters["track"] != "all" and node["track"] != filters["track"]:
                    continue
                if not project_match and (filters["search_in"] == "project" or search not in (node["name"] + " " + node["remark"]).casefold()):
                    continue
                matched.append({**node, "overdue": overdue, "is_today": date == today})
            empty_match = not nodes and filters["period"] == "all" and filters["stage"] == "all" and filters["track"] == "all" and filters["focus"] == "all" and filters["completion"] != "done" and project_match
            if not matched and not empty_match:
                continue
            incomplete = sorted((n for n in view["nodes"] if not n["done_at"]), key=lambda n: (n["date"], STAGES.index(n["stage"]), n["track"] != "main", _natural_key(n["name"]), n["id"]))
            next_nodes = [n for n in incomplete if n["date"] == incomplete[0]["date"]] if incomplete else []
            upcoming = [n for n in incomplete if n["date"] >= today.isoformat()]
            upcoming_nodes = [n for n in upcoming if n["date"] == upcoming[0]["date"]] if upcoming else []
            overdue_count = sum(n["overdue"] for n in matched)
            today_count = sum(n["is_today"] and not n["done_at"] for n in matched)
            total_overdue_count = sum(n["date"] < today.isoformat() for n in incomplete)
            total_today_count = sum(n["date"] == today.isoformat() for n in incomplete)
            done = sum(n["done_at"] for n in matched)
            result.append({
                "project_id": project["id"], "name": project["name"],
                "created_by": project["created_by"], "creator_name": project["creator_name"] or "成员已不可用",
                "creator_avatar_class": project["creator_avatar_class"],
                "can_edit": role == "admin" or project["created_by"] == user["id"],
                "current_stage": view["metrics"]["current_stage"] if nodes else "未录入节点",
                "group": "attention" if total_overdue_count or total_today_count else "recent",
                "matched_nodes": matched, "next_nodes": next_nodes, "upcoming_nodes": upcoming_nodes,
                "node_count": len(matched), "done_count": done,
                "progress": round(done * 100 / len(matched)) if matched else None,
                "overdue_count": overdue_count, "today_count": today_count,
                "total_overdue_count": total_overdue_count, "total_today_count": total_today_count,
                "total_node_count": len(nodes), "total_done_count": sum(n["done_at"] for n in view["nodes"]),
                "total_progress": round(sum(n["done_at"] for n in view["nodes"]) * 100 / len(nodes)) if nodes else None,
            })
        def urgency(project):
            rank = (0 if project["total_overdue_count"] else 1 if project["total_today_count"]
                    else 2 if project["next_nodes"] else 3 if project["total_node_count"] else 4)
            return (rank, project["next_nodes"][0]["date"] if project["next_nodes"] else "9999",
                    -project["total_overdue_count"], -project["total_today_count"], project["project_id"])
        result.sort(key=urgency)
        return {
            "filters": filters, "server_today": today.isoformat(),
            "range_start": start.isoformat() if start else None, "range_end": end.isoformat() if end else None,
            "projects": result,
            "counts": {"projects": len(result), "nodes": sum(p["node_count"] for p in result),
                       "done": sum(p["done_count"] for p in result), "overdue": sum(p["overdue_count"] for p in result)},
        }
    finally:
        conn.close()
