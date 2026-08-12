from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import isfinite


MAX_BUCKETS = 200
MAX_SERIES = 12
MAX_RESULT_CELLS = 2000
MAX_WIDGET_TASKS = 5000
CHART_TYPES = {"bar", "line", "pie", "stacked_bar"}
METRICS = {"count", "sum", "avg", "min", "max"}


class AggregationError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}


def _field_key(binding):
    if not isinstance(binding, dict):
        raise AggregationError("AGGREGATION_SPEC_INVALID", "字段绑定无效")
    if binding.get("kind") == "core" and set(binding) == {"kind", "key"} and binding["key"] in {"status", "priority", "owner_id", "due", "start_date", "board"}:
        return ("core", binding["key"])
    if binding.get("kind") == "dynamic" and set(binding) == {"kind", "id"} and isinstance(binding.get("id"), int) and not isinstance(binding["id"], bool):
        return ("dynamic", binding["id"])
    if binding.get("kind") == "mapped" and set(binding) == {"kind", "by_source"} and isinstance(binding.get("by_source"), dict) and binding["by_source"]:
        return ("mapped", tuple(sorted((key,_field_key(value)) for key,value in binding["by_source"].items() if isinstance(key,str) and key)))
    raise AggregationError("AGGREGATION_SPEC_INVALID", "字段绑定无效")


def validate_spec(spec, catalogs):
    if not isinstance(spec, dict) or set(spec) - {"version", "chart_type", "dimension", "series", "metric", "date_bucket", "top_n", "null_policy"} or spec.get("version") != 1:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "聚合配置无效")
    chart_type = spec.get("chart_type", "bar")
    if chart_type not in CHART_TYPES:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "图表类型无效")
    dimension = _field_key(spec.get("dimension"))
    series = _field_key(spec["series"]) if spec.get("series") is not None else None
    metric = spec.get("metric", {"op": "count"})
    if not isinstance(metric, dict) or set(metric) - {"op", "field"} or metric.get("op") not in METRICS:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "度量无效")
    metric_field = _field_key(metric["field"]) if metric.get("op") != "count" and metric.get("field") is not None else None
    if metric.get("op") != "count" and metric_field is None:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "数值度量需要字段")
    if metric.get("op") == "count" and "field" in metric:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "count 不接受字段")
    date_bucket = spec.get("date_bucket", "none")
    if date_bucket not in {"none", "day", "week", "month"}:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "日期分桶无效")
    top_n = spec.get("top_n", 20)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= 50:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "显示上限无效")
    if spec.get("null_policy", "exclude") not in {"exclude", "include"}:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "空值策略无效")
    if chart_type == "pie" and series:
        raise AggregationError("AGGREGATION_SPEC_INVALID", "饼图不支持系列")
    if chart_type == "line" and date_bucket == "none":
        raise AggregationError("AGGREGATION_SPEC_INVALID", "折线图必须使用日期分桶")
    allowed_dimensions = {"status", "priority", "person", "date", "timeline", "select", "tags", "checkbox", "board"}
    numeric = {"number", "rating", "formula"}
    def resolved(binding,catalog):
        if binding and binding[0]=="mapped":return dict(binding[1]).get(catalog.get("__source_key__"))
        return binding
    for catalog in catalogs:
        for binding in filter(None, (dimension, series)):
            binding=resolved(binding,catalog)
            if not binding:raise AggregationError("AGGREGATION_FIELD_INVALID", "来源缺少显式字段映射")
            kind = "board" if binding == ("core", "board") else catalog.get(binding)
            if kind not in allowed_dimensions:
                raise AggregationError("AGGREGATION_FIELD_INVALID", "维度字段类型无效")
        resolved_metric=resolved(metric_field,catalog)
        if metric_field and (not resolved_metric or catalog.get(resolved_metric) not in numeric):
            raise AggregationError("AGGREGATION_FIELD_INVALID", "度量字段必须为数值类型")
    return {"version": 1, "chart_type": chart_type, "dimension": dimension, "series": series, "metric": {"op": metric["op"], "field": metric_field}, "date_bucket": date_bucket, "top_n": top_n, "null_policy": spec.get("null_policy", "exclude")}


def _value(row, binding):
    kind, key = binding
    if kind == "mapped":
        mapped=dict(key).get(row.get("source_key"))
        return _value(row,mapped) if mapped else None
    if kind == "core":
        return row.get("board_name") if key == "board" else row.get(key)
    return (row.get("field_values") or {}).get(str(key))


def _bucket(value, mode):
    if mode == "none":
        return value
    if isinstance(value, dict):
        value = value.get("start")
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if mode == "day":
        return parsed.isoformat()
    if mode == "month":
        return parsed.strftime("%Y-%m")
    year, week, _ = parsed.isocalendar()
    return f"{year}-W{week:02d}"


def _values(value):
    if isinstance(value, list):
        return value or [None]
    return [value]


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and isfinite(value):
        return float(value)
    return None


def _finish(op, values):
    if op == "count":
        return len(values)
    if not values:
        return None
    if op == "sum":
        return sum(values)
    if op == "avg":
        return sum(values) / len(values)
    if op == "min":
        return min(values)
    return max(values)


def aggregate_value(rows, raw_spec, catalogs):
    """Return one global KPI without re-aggregating chart buckets."""
    if len(rows) > MAX_WIDGET_TASKS:
        raise AggregationError("AGGREGATION_TASK_LIMIT", "聚合任务超过安全上限", {"max_tasks": MAX_WIDGET_TASKS, "total": len(rows)})
    spec = validate_spec(raw_spec, catalogs)
    op = spec["metric"]["op"]
    values = [1.0] * len(rows) if op == "count" else [value for row in rows if (value := _number(_value(row, spec["metric"]["field"]))) is not None]
    value = _finish(op, values)
    return {"value": 0 if value is None and op in {"count", "sum"} else value, "empty": not values, "meta": {"task_count": len(rows), "value_count": len(values)}}


def aggregate(rows, raw_spec, catalogs):
    if len(rows) > MAX_WIDGET_TASKS:
        raise AggregationError("AGGREGATION_TASK_LIMIT", "聚合任务超过安全上限", {"max_tasks": MAX_WIDGET_TASKS, "total": len(rows)})
    spec = validate_spec(raw_spec, catalogs)
    cells = defaultdict(list)
    dimensions_seen, series_seen = set(), set()
    for row in rows:
        dimensions = _values(_bucket(_value(row, spec["dimension"]), spec["date_bucket"]))
        series_values = _values(_value(row, spec["series"])) if spec["series"] else [None]
        metric_value = 1.0 if spec["metric"]["op"] == "count" else _number(_value(row, spec["metric"]["field"]))
        if metric_value is None:
            continue
        for dimension in dimensions:
            if dimension in (None, ""):
                if spec["null_policy"] == "exclude":
                    continue
                dimension = "未设置"
            for series in series_values:
                if series in (None, "") and spec["series"]:
                    if spec["null_policy"] == "exclude":
                        continue
                    series = "未设置"
                dimension_key, series_key = str(dimension), None if series is None else str(series)
                new_dimensions = dimensions_seen | {dimension_key}
                new_series = series_seen | ({series_key} if series_key is not None else set())
                key = (dimension_key, series_key)
                if len(new_dimensions) > MAX_BUCKETS or len(new_series) > MAX_SERIES or key not in cells and len(cells) >= MAX_RESULT_CELLS:
                    raise AggregationError("AGGREGATION_RESULT_LIMIT", "聚合结果超过安全上限")
                dimensions_seen, series_seen = new_dimensions, new_series
                cells[key].append(metric_value)
    op = spec["metric"]["op"]
    def finish(values): return _finish(op, values)
    totals = defaultdict(float)
    for (label, _), values in cells.items(): totals[label] += finish(values)
    ranked = sorted(totals, key=lambda label: (-totals[label], label))
    keep = set(ranked[:spec["top_n"]])
    if len(ranked) > spec["top_n"]:
        collapsed = defaultdict(list)
        for (label, series), values in cells.items(): collapsed[(label if label in keep else "其他", series)].extend(values)
        cells = collapsed
    categories = sorted({key[0] for key in cells}, key=lambda label: (label == "其他", -sum(finish(v) for (name, _), v in cells.items() if name == label), label))
    series_names = sorted({key[1] for key in cells if key[1] is not None})
    if len(categories) > MAX_BUCKETS or len(series_names) > MAX_SERIES or len(categories) * max(1, len(series_names)) > MAX_RESULT_CELLS:
        raise AggregationError("AGGREGATION_RESULT_LIMIT", "聚合结果超过安全上限")
    names = series_names or [None]
    series = [{"name": name or op, "values": [finish(cells[(category, name)]) if (category, name) in cells else 0 for category in categories]} for name in names]
    return {"spec": raw_spec, "categories": categories, "series": series, "empty": not categories, "meta": {"task_count": len(rows), "bucket_count": len(categories), "series_count": len(series_names), "multi_value_rule": "each_value_membership"}}
