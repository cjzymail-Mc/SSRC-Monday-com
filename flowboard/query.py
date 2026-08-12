"""Validated query AST and parameter-only SQLite compiler for board tasks."""
import math
from datetime import date

class QueryValidationError(Exception):
    def __init__(self, message, details=None):
        super().__init__(message); self.message, self.details = message, details

MAX_DEPTH = 4
MAX_NODES = 32
MAX_CONDITIONS = 24
MAX_SORTS = 5
MAX_SET_VALUES = 50
MAX_TEXT = 1000


def active_task_sql(task_alias="t", group_alias="g", board_alias="b"):
    """Single lifecycle predicate for an active task and its complete ancestor chain."""
    return " AND ".join(f"{alias}.{column} IS NULL" for alias in (task_alias,group_alias,board_alias) for column in ("deleted_at","archived_at"))

OPERATORS = {
    "title": {"contains", "equals", "is_empty", "is_not_empty"},
    "text": {"contains", "equals", "is_empty", "is_not_empty"},
    "link": {"contains", "equals", "is_empty", "is_not_empty"},
    "number": {"equals", "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty"},
    "date": {"equals", "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty"},
    "status": {"equals", "in", "is_empty", "is_not_empty"},
    "person": {"equals", "in", "is_empty", "is_not_empty"},
    "checkbox": {"equals"},
    "tags": {"contains_any", "contains_all", "is_empty", "is_not_empty"},
    "email": {"contains", "equals", "is_empty", "is_not_empty"},
    "phone": {"contains", "equals", "is_empty", "is_not_empty"},
    "file": {"contains", "is_empty", "is_not_empty"},
    "timeline": {"equals", "is_empty", "is_not_empty"},
    "rating": {"equals", "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty"},
    "relation": {"contains_any", "is_empty", "is_not_empty"},
    "mirror": {"contains", "equals", "is_empty", "is_not_empty"},
    "formula": {"contains", "equals", "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty"},
}


def _invalid(message, details=None):
    raise QueryValidationError(message, details)


def _field(conn, board_id, ref):
    if not isinstance(ref, dict) or set(ref) not in ({"kind", "key"}, {"kind", "id"}):
        _invalid("field reference is invalid")
    if ref.get("kind") == "core" and ref.get("key") == "title":
        return {"kind": "core", "key": "title", "field_type": "title"}
    if ref.get("kind") != "dynamic" or isinstance(ref.get("id"), bool) or not isinstance(ref.get("id"), int):
        _invalid("field reference is invalid")
    row = conn.execute(
        "SELECT * FROM field_definitions WHERE id=? AND board_id=? AND deleted_at IS NULL AND is_active=1",
        (ref["id"], board_id),
    ).fetchone()
    if not row:
        _invalid("field is unavailable", {"field": ref})
    return dict(row)


def _validate_value(conn, field, operator, value):
    kind = field["field_type"]
    if operator in {"is_empty", "is_not_empty"}:
        if value is not None:
            _invalid("empty operators require null value")
        return
    if operator == "between":
        if not isinstance(value, list) or len(value) != 2:
            _invalid("between requires two values")
        values = value
    elif operator in {"in", "contains_any", "contains_all"}:
        if not isinstance(value, list) or not value or len(value) > MAX_SET_VALUES:
            _invalid("set operator requires a bounded non-empty array")
        if len(value) != len(set(value)):
            _invalid("set values must be unique")
        values = value
    else:
        values = [value]
    if kind in {"title", "text", "link", "date", "person", "email", "phone", "file", "timeline"}:
        if any(not isinstance(item, str) or len(item) > MAX_TEXT for item in values):
            _invalid("query value type is invalid")
        if kind in {"date","timeline"}:
            try:
                for item in values: date.fromisoformat(item)
            except ValueError:
                _invalid("date query value must use YYYY-MM-DD")
    elif kind in {"number","rating"}:
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in values):
            _invalid("number query value is invalid")
    elif kind == "checkbox":
        if len(values) != 1 or not isinstance(values[0], bool):
            _invalid("checkbox query value is invalid")
    elif kind == "formula":
        if any(isinstance(item,(dict,list)) or (not isinstance(item,(str,int,float)) or isinstance(item,bool)) or isinstance(item,(int,float)) and not math.isfinite(item) for item in values):
            _invalid("formula query value is invalid")
    elif kind == "mirror":
        if any(isinstance(item,(dict,list)) or not isinstance(item,(str,int,float,bool)) for item in values):
            _invalid("mirror query value is invalid")
    elif kind in {"status", "tags", "relation"}:
        if any(isinstance(item, bool) or not isinstance(item, int) for item in values):
            _invalid("option query value is invalid")
        if kind == "relation": return
        count = conn.execute(
            f"SELECT COUNT(*) FROM field_options WHERE field_id=? AND id IN ({','.join('?' for _ in values)}) AND deleted_at IS NULL AND is_active=1",
            (field["id"], *values),
        ).fetchone()[0]
        if count != len(values):
            _invalid("option query value is unavailable")


def _value_expr(field):
    kind = field["field_type"]
    if kind in {"mirror","formula"}: return "NULL"
    if kind in {"timeline","file"}:
        path="$.start" if kind=="timeline" else "$.name"
        return f"(SELECT CASE WHEN json_valid(v.text_value) THEN json_extract(v.text_value,'{path}') END FROM task_field_values v WHERE v.task_id=t.id AND v.field_id=? LIMIT 1)"
    column = {"text": "text_value", "email":"text_value", "phone":"text_value",
              "number": "number_value", "rating":"number_value", "status": "option_id", "person": "user_id",
              "date": "date_value", "checkbox": "boolean_value", "link": "link_url"}[kind]
    return f"(SELECT v.{column} FROM task_field_values v WHERE v.task_id=t.id AND v.field_id=? LIMIT 1)"


def _condition_sql(conn, board_id, condition):
    if not isinstance(condition, dict) or set(condition) != {"field", "operator", "value"}:
        _invalid("condition shape is invalid")
    field = _field(conn, board_id, condition["field"]); operator = condition["operator"]
    if not isinstance(operator, str) or operator not in OPERATORS[field["field_type"]]:
        _invalid("operator is invalid for field", {"operator": operator})
    value = condition["value"]; _validate_value(conn, field, operator, value)
    if field["field_type"] == "title":
        expr, params = "t.title", []
    elif field["field_type"] in {"tags","relation"}:
        fid = field["id"]
        table="task_field_tag_values" if field["field_type"]=="tags" else "task_relation_values"
        value_column="option_id" if field["field_type"]=="tags" else "target_task_id"
        task_column="task_id" if field["field_type"]=="tags" else "source_task_id"
        deleted="" if field["field_type"]=="tags" else f" AND tv.deleted_at IS NULL AND EXISTS(SELECT 1 FROM tasks rt JOIN groups_ rg ON rg.id=rt.group_id JOIN boards rb ON rb.id=rg.board_id WHERE rt.id=tv.target_task_id AND {active_task_sql('rt','rg','rb')})"
        if operator in {"is_empty", "is_not_empty"}:
            sql = f"EXISTS(SELECT 1 FROM {table} tv WHERE tv.{task_column}=t.id AND tv.field_id=?{deleted})"
            return (("NOT " if operator == "is_empty" else "") + sql), [fid]
        marks = ",".join("?" for _ in value)
        if field["field_type"]=="relation":
            return f"EXISTS(SELECT 1 FROM task_relation_values tv JOIN tasks rt ON rt.id=tv.target_task_id JOIN groups_ rg ON rg.id=rt.group_id JOIN boards rb ON rb.id=rg.board_id WHERE tv.source_task_id=t.id AND tv.field_id=? AND tv.deleted_at IS NULL AND {active_task_sql('rt','rg','rb')} AND tv.target_task_id IN ({marks}))",[fid,*value]
        if operator == "contains_any":
            return f"EXISTS(SELECT 1 FROM task_field_tag_values tv WHERE tv.task_id=t.id AND tv.field_id=? AND tv.option_id IN ({marks}))", [fid, *value]
        return f"(SELECT COUNT(DISTINCT tv.option_id) FROM task_field_tag_values tv WHERE tv.task_id=t.id AND tv.field_id=? AND tv.option_id IN ({marks}))=?", [fid, *value, len(value)]
    else:
        expr, params = _value_expr(field), [field["id"]]
    if operator == "is_empty": return f"{expr} IS NULL", params
    if operator == "is_not_empty": return f"{expr} IS NOT NULL", params
    if operator == "contains": return f"LOWER({expr}) LIKE ?", params + [f"%{value.lower()}%"]
    if operator == "equals": return f"{expr} = ?", params + [int(value) if isinstance(value, bool) else value]
    if operator == "in": return f"{expr} IN ({','.join('?' for _ in value)})", params + value
    comparisons = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    if operator in comparisons: return f"{expr} {comparisons[operator]} ?", params + [value]
    if operator == "between": return f"{expr} BETWEEN ? AND ?", params + value
    _invalid("operator is not implemented")


def compile_filter(conn, board_id, node, *, depth=1, stats=None):
    stats = stats or {"nodes": 0, "conditions": 0}; stats["nodes"] += 1
    if depth > MAX_DEPTH or stats["nodes"] > MAX_NODES: _invalid("query is too complex")
    if not isinstance(node, dict): _invalid("filter node must be an object")
    if "op" in node:
        if set(node) != {"op", "children"} or node["op"] not in {"and", "or"} or not isinstance(node["children"], list): _invalid("filter group is invalid")
        if not node["children"]: return "1=1", []
        compiled = [compile_filter(conn, board_id, child, depth=depth+1, stats=stats) for child in node["children"]]
        return "(" + f" {node['op'].upper()} ".join(item[0] for item in compiled) + ")", [value for item in compiled for value in item[1]]
    stats["conditions"] += 1
    if stats["conditions"] > MAX_CONDITIONS: _invalid("query has too many conditions")
    return _condition_sql(conn, board_id, node)


def compile_sorts(conn, board_id, sorts):
    if not isinstance(sorts, list) or len(sorts) > MAX_SORTS: _invalid("sort must be a bounded array")
    clauses, params, seen = [], [], set()
    for item in sorts:
        if not isinstance(item, dict) or set(item) != {"field", "direction", "nulls"}: _invalid("sort item is invalid")
        field = _field(conn, board_id, item["field"]); key = (field.get("kind","dynamic"),field.get("key",field.get("id")))
        if key in seen: _invalid("sort fields must be unique")
        seen.add(key)
        if item["direction"] not in {"asc","desc"} or item["nulls"] not in {"first","last"}: _invalid("sort direction or null rule is invalid")
        if field["field_type"] == "title": expr, expression_params = "LOWER(t.title)", []
        elif field["field_type"] == "tags":
            expr = "(SELECT MIN(o.sort_order) FROM task_field_tag_values tv JOIN field_options o ON o.id=tv.option_id WHERE tv.task_id=t.id AND tv.field_id=?)"; expression_params=[field["id"]]
        elif field["field_type"] == "status":
            expr = "(SELECT o.sort_order FROM task_field_values v JOIN field_options o ON o.id=v.option_id WHERE v.task_id=t.id AND v.field_id=? LIMIT 1)"; expression_params=[field["id"]]
        elif field["field_type"] == "person":
            expr = "(SELECT LOWER(u.name) FROM task_field_values v JOIN users u ON u.id=v.user_id WHERE v.task_id=t.id AND v.field_id=? LIMIT 1)"; expression_params=[field["id"]]
        elif field["field_type"] == "relation":
            expr = f"(SELECT COUNT(*) FROM task_relation_values e JOIN tasks rt ON rt.id=e.target_task_id JOIN groups_ rg ON rg.id=rt.group_id JOIN boards rb ON rb.id=rg.board_id WHERE e.source_task_id=t.id AND e.field_id=? AND e.deleted_at IS NULL AND {active_task_sql('rt','rg','rb')})"; expression_params=[field["id"]]
        elif field["field_type"] in {"mirror","formula"}: expr,expression_params="NULL",[]
        else: expr, expression_params = _value_expr(field), [field["id"]]
        null_dir = "DESC" if item["nulls"] == "first" else "ASC"
        clauses.extend([f"({expr} IS NULL) {null_dir}", f"{expr} {item['direction'].upper()}"])
        params.extend(expression_params); params.extend(expression_params)
    clauses.extend(["g.sort_order ASC", "t.sort_order ASC", "t.id ASC"])
    return ",".join(clauses), params


def normalize_query(conn, board_id, payload):
    if not isinstance(payload, dict) or set(payload)-{"version","filter","sort","limit","offset"}: _invalid("query payload is invalid")
    if payload.get("version",1) != 1: _invalid("query version is unsupported")
    filter_ast=payload.get("filter",{"op":"and","children":[]});sorts=payload.get("sort",[])
    where, where_params=compile_filter(conn,board_id,filter_ast);order,order_params=compile_sorts(conn,board_id,sorts)
    limit=payload.get("limit",100);offset=payload.get("offset",0)
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=200 or isinstance(offset,bool) or not isinstance(offset,int) or not 0<=offset<=10000: _invalid("pagination is invalid")
    return {"version":1,"filter":filter_ast,"sort":sorts}, where, where_params, order, order_params, limit, offset


def python_value(field, raw, *, option_orders=None, user_names=None, purpose="filter"):
    """Canonical in-memory projection used only when derived fields require post-processing."""
    kind=field["field_type"]
    if raw is None: return None
    if kind=="link": return raw.get("url") if isinstance(raw,dict) else None
    if kind=="file": return raw.get("name") if isinstance(raw,dict) else None
    if kind=="timeline": return raw.get("start") if isinstance(raw,dict) else None
    if kind=="relation":
        ids=[item.get("id") for item in raw if isinstance(item,dict) and isinstance(item.get("id"),int)] if isinstance(raw,list) else []
        return len(ids) if purpose=="sort" else ids
    if kind=="tags":
        if purpose=="sort": return min((option_orders or {}).get(item,10**9) for item in raw) if raw else None
        return raw
    if kind=="status" and purpose=="sort": return (option_orders or {}).get(raw)
    if kind=="person" and purpose=="sort": return (user_names or {}).get(raw,"").lower() or None
    if kind=="mirror":
        if not isinstance(raw,list): return raw
        if purpose=="sort": return next((item for item in raw if item is not None),None)
        return raw
    if isinstance(raw,float) and not math.isfinite(raw): return None
    return raw.lower() if purpose=="sort" and isinstance(raw,str) else raw


def _safe_order_compare(value, wanted, operator):
    if isinstance(value,bool) or isinstance(wanted,bool): return False
    if isinstance(value,(int,float)) and isinstance(wanted,(int,float)):
        if not math.isfinite(value) or not math.isfinite(wanted): return False
    elif not (isinstance(value,str) and isinstance(wanted,str)):
        return False
    return {"gt":value>wanted,"gte":value>=wanted,"lt":value<wanted,"lte":value<=wanted}[operator]


def _python_sort_key(value):
    if isinstance(value,bool): return (0,int(value))
    if isinstance(value,(int,float)) and math.isfinite(value): return (0,value)
    if isinstance(value,str): return (1,value.lower())
    return None


def python_matches(field, raw, operator, wanted):
    value=python_value(field,raw)
    if operator=="is_empty": return value in (None,"",[])
    if operator=="is_not_empty": return value not in (None,"",[])
    if operator=="contains":
        candidates=value if isinstance(value,list) else [value]
        return any(str(wanted).lower() in str(item or "").lower() for item in candidates)
    if operator=="equals":
        return wanted in value if isinstance(value,list) else value==wanted
    if operator=="in": return value in wanted
    if operator=="contains_any": return isinstance(value,list) and any(item in value for item in wanted)
    if operator=="contains_all": return isinstance(value,list) and all(item in value for item in wanted)
    if operator=="between": return value is not None and _safe_order_compare(value,wanted[0],"gte") and _safe_order_compare(value,wanted[1],"lte")
    if value is None:return False
    return _safe_order_compare(value,wanted,operator)


def apply_python_query(tasks, filter_ast, sorts, fields, *, option_orders=None, user_names=None):
    """Replay a normalized query over derived candidates with deterministic SQL-equivalent ordering."""
    def field_and_raw(task, ref):
        if ref.get("kind")=="core": return {"field_type":"title"},task["title"]
        return fields[ref["id"]],task["field_values"].get(str(ref["id"]))
    def matches(task,node):
        if "op" in node:
            values=[matches(task,child) for child in node["children"]]
            return all(values) if node["op"]=="and" else any(values)
        field,raw=field_and_raw(task,node["field"])
        return python_matches(field,raw,node["operator"],node["value"])
    result=[task for task in tasks if matches(task,filter_ast)]
    # Candidate order is already the canonical group/task/id tie-break; Python's stable sort preserves it.
    for spec in reversed(sorts):
        def projected(task):
            field,raw=field_and_raw(task,spec["field"])
            return python_value(field,raw,option_orders=option_orders,user_names=user_names,purpose="sort")
        decorated=[(task,_python_sort_key(projected(task))) for task in result]
        nonnull=[item for item in decorated if item[1] is not None];nulls=[item for item in decorated if item[1] is None]
        nonnull.sort(key=lambda item:item[1],reverse=spec["direction"]=="desc")
        ordered=(nulls+nonnull) if spec["nulls"]=="first" else (nonnull+nulls);result=[item[0] for item in ordered]
    return result
