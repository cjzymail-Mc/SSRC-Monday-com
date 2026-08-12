"""Bounded evaluator for Flowboard derived fields; never executes user code."""
import ast


MAX_EXPRESSION = 500
MAX_NODES = 80
MAX_DEPTH = 12
MAX_ARGS = 20
FUNCTIONS = {"IF", "SUM", "AVG", "MIN", "MAX", "CONCAT", "PROGRESS"}


class FormulaError(ValueError):
    pass


def parse(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > MAX_EXPRESSION:
        raise FormulaError("FORMULA_INVALID")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError):
        raise FormulaError("FORMULA_INVALID")
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_NODES:
        raise FormulaError("FORMULA_LIMIT")
    allowed = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
               ast.BoolOp, ast.Compare, ast.IfExp, ast.Call, ast.Add, ast.Sub, ast.Mult,
               ast.Div, ast.Mod, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or, ast.Eq,
               ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
    if any(not isinstance(node, allowed) for node in nodes):
        raise FormulaError("FORMULA_UNSAFE")
    for node in nodes:
        if isinstance(node, ast.Name) and not (node.id in FUNCTIONS or (node.id.startswith("f") and node.id[1:].isdigit())):
            raise FormulaError("FORMULA_NAME")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords or len(node.args) > MAX_ARGS:
                raise FormulaError("FORMULA_CALL")
    return tree


def references(expression):
    return {int(node.id[1:]) for node in ast.walk(parse(expression))
            if isinstance(node, ast.Name) and node.id.startswith("f")}


def evaluate(expression, values):
    tree = parse(expression)

    def run(node, depth=0):
        if depth > MAX_DEPTH:
            raise FormulaError("FORMULA_LIMIT")
        if isinstance(node, ast.Expression): return run(node.body, depth + 1)
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.Name): return values.get(int(node.id[1:]))
        if isinstance(node, ast.UnaryOp):
            value = run(node.operand, depth + 1)
            if isinstance(node.op, ast.Not): return not value
            return (+value) if isinstance(node.op, ast.UAdd) else (-value)
        if isinstance(node, ast.BinOp):
            left, right = run(node.left, depth + 1), run(node.right, depth + 1)
            if left is None or right is None: return None
            operations = {ast.Add: lambda: left + right, ast.Sub: lambda: left - right,
                          ast.Mult: lambda: left * right, ast.Div: lambda: left / right,
                          ast.Mod: lambda: left % right}
            return operations[type(node.op)]()
        if isinstance(node, ast.BoolOp):
            items = [run(value, depth + 1) for value in node.values]
            return all(items) if isinstance(node.op, ast.And) else any(items)
        if isinstance(node, ast.Compare):
            left = run(node.left, depth + 1)
            for op, comparator in zip(node.ops, node.comparators):
                right = run(comparator, depth + 1)
                funcs = {ast.Eq: lambda: left == right, ast.NotEq: lambda: left != right,
                         ast.Lt: lambda: left < right, ast.LtE: lambda: left <= right,
                         ast.Gt: lambda: left > right, ast.GtE: lambda: left >= right}
                if not funcs[type(op)](): return False
                left = right
            return True
        if isinstance(node, ast.IfExp): return run(node.body if run(node.test, depth + 1) else node.orelse, depth + 1)
        if isinstance(node, ast.Call):
            name = node.func.id; args = [run(arg, depth + 1) for arg in node.args]
            if name == "IF":
                if len(args) != 3: raise FormulaError("FORMULA_ARGUMENTS")
                return args[1] if args[0] else args[2]
            if name == "CONCAT": return "".join("" if item is None else str(item) for item in args)
            flat=[]
            for item in args: flat.extend(item if isinstance(item,list) else [item])
            nums = [item for item in flat if isinstance(item, (int, float)) and not isinstance(item, bool)]
            if name == "SUM": return sum(nums)
            if name == "AVG": return sum(nums) / len(nums) if nums else None
            if name == "MIN": return min(nums) if nums else None
            if name == "MAX": return max(nums) if nums else None
            if name == "PROGRESS":
                if len(args) != 2 or not args[1]: return None
                return round(float(args[0] or 0) * 100 / float(args[1]), 2)
        raise FormulaError("FORMULA_INVALID")

    try:
        result = run(tree)
    except FormulaError:
        raise
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        raise FormulaError("FORMULA_EVALUATION")
    if isinstance(result, str) and len(result) > 10000: raise FormulaError("FORMULA_LIMIT")
    if isinstance(result, (int, float)) and abs(result) > 1e15: raise FormulaError("FORMULA_LIMIT")
    return result
