from datetime import date, timedelta
from pathlib import Path

from flowboard.database import SCHEMA_VERSION, connect, migrate, utc_now
from flowboard.security import hash_password, verify_password
from flowboard.service import FlowboardService
from flowboard.timeline import TimelineService


ROOT = Path(__file__).resolve().parent
LOCAL_TEST_ROOT = ROOT / "local-test-data"
LOCAL_TEST_DB = LOCAL_TEST_ROOT / "flowboard.db"
REAL_DB = ROOT / "flowboard.db"
LOCAL_TEST_PASSWORD = "localtest"
DEVELOPER_USERNAME = "test"
DEVELOPER_PASSWORD = "test"


def _row(db_path, sql, parameters=()):
    conn = connect(db_path)
    try:
        row = conn.execute(sql, parameters).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _ensure_users(db_path):
    password = hash_password(LOCAL_TEST_PASSWORD)
    stamp = utc_now()
    conn = connect(db_path)
    try:
        developer = conn.execute("SELECT * FROM users WHERE id='dev'").fetchone()
        if developer is None:
            conn.execute(
                """INSERT INTO users(
                       id,username,name,password_hash,avatar,avatar_class,is_active,created_at
                   ) VALUES ('dev',?,?,?,'开','avatar-blue',1,?)""",
                (DEVELOPER_USERNAME, "本地开发者", hash_password(DEVELOPER_PASSWORD), stamp),
            )
        else:
            developer_hash = developer["password_hash"]
            conn.execute(
                """UPDATE users
                   SET username=?,name='本地开发者',avatar='开',avatar_class='avatar-blue',is_active=1,
                       password_hash=?
                   WHERE id='dev'""",
                (
                    DEVELOPER_USERNAME,
                    developer_hash if verify_password(DEVELOPER_PASSWORD, developer_hash) else hash_password(DEVELOPER_PASSWORD),
                ),
            )
        conn.execute(
            "INSERT OR IGNORE INTO workspace_memberships(workspace_id,user_id,role) VALUES (1,'dev','admin')"
        )
        conn.execute(
            "UPDATE workspace_memberships SET role='admin' WHERE workspace_id=1 AND user_id='dev'"
        )
        for user_id, name, avatar, avatar_class, role in (
            ("u2", "测试成员", "员", "avatar-green", "member"),
            ("u3", "只读成员", "读", "avatar-orange", "viewer"),
        ):
            conn.execute(
                """INSERT OR IGNORE INTO users(
                       id,username,name,password_hash,avatar,avatar_class,is_active,created_at
                   ) VALUES (?,?,?,?,?,?,1,?)""",
                (user_id, user_id, name, password, avatar, avatar_class, stamp),
            )
            conn.execute(
                "INSERT OR IGNORE INTO workspace_memberships(workspace_id,user_id,role) VALUES (1,?,?)",
                (user_id, role),
            )
        conn.commit()
    finally:
        conn.close()


def _ensure_board_data(db_path, admin):
    service = FlowboardService(db_path)
    board = _row(
        db_path,
        "SELECT id FROM boards WHERE workspace_id=1 AND name='本地测试看板' AND deleted_at IS NULL",
    )
    board_id = board["id"] if board else service.create_board(
        admin,
        1,
        {
            "name": "本地测试看板",
            "description": "仅用于本机开发调试的虚构数据",
            "color": "blue",
            "access_type": "open",
        },
    )["id"]

    group = _row(
        db_path,
        "SELECT id FROM groups_ WHERE board_id=? AND name='本周任务' AND deleted_at IS NULL",
        (board_id,),
    )
    group_id = group["id"] if group else service.create_group(
        admin, board_id, {"name": "本周任务", "color": "green"}
    )["id"]

    today = date.today()
    examples = (
        ("确认需求", "已完成", "中", today - timedelta(days=2), "u1"),
        ("修复示例 Bug", "进行中", "高", today + timedelta(days=2), "u2"),
        ("回归检查", "待开始", "中", today + timedelta(days=5), "u2"),
    )
    for title, status, priority, due, owner_id in examples:
        existing = _row(
            db_path,
            "SELECT id FROM tasks WHERE group_id=? AND title=? AND deleted_at IS NULL",
            (group_id, title),
        )
        if existing:
            continue
        created = service.create_task(
            admin,
            group_id,
            {
                "title": title,
                "status": status,
                "priority": priority,
                "due": due.isoformat(),
                "owner_id": owner_id,
                "description": "本地测试数据，可自由修改或删除。",
            },
        )
        if title == "修复示例 Bug":
            service.create_comment(
                admin,
                created["id"],
                {"body": "这是一条本地测试评论。", "mentions": []},
            )


def _ensure_timeline_data(db_path, admin):
    service = TimelineService(db_path)
    project = _row(
        db_path,
        """SELECT id,version FROM timeline_projects
           WHERE workspace_id=1 AND name='本地测试项目' AND deleted_at IS NULL""",
    )
    if not project:
        project_id = service.create_project(admin, 1, {"name": "本地测试项目"})["project_id"]
        project = {"id": project_id, "version": 1}

    existing = _row(
        db_path,
        "SELECT id FROM timeline_nodes WHERE project_id=? LIMIT 1",
        (project["id"],),
    )
    if existing:
        return

    today = date.today()
    nodes = (
        {"track": "main", "stage": "创意", "name": "提出想法", "date": (today - timedelta(days=8)).isoformat()},
        {"track": "main", "stage": "设计", "name": "确认方案", "date": (today - timedelta(days=3)).isoformat()},
        {"track": "main", "stage": "开发", "name": "实现功能", "date": (today + timedelta(days=3)).isoformat()},
        {"track": "parallel", "stage": "测试", "name": "并行验证", "date": (today + timedelta(days=5)).isoformat()},
    )
    service.submit_batches(
        admin,
        1,
        {
            "requests": [
                {
                    "project_id": project["id"],
                    "base_version": project["version"],
                    "changes": [{"create": node} for node in nodes],
                }
            ]
        },
    )


def seed_database(db_path=LOCAL_TEST_DB):
    db_path = Path(db_path).resolve()
    if db_path == REAL_DB.resolve():
        raise RuntimeError("Refusing to initialize the real flowboard.db")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    migrate(db_path, initial_password=LOCAL_TEST_PASSWORD)
    _ensure_users(db_path)
    admin = _row(db_path, "SELECT * FROM users WHERE id='u1'")
    if not admin:
        raise RuntimeError("Local test administrator was not created")
    _ensure_board_data(db_path, admin)
    _ensure_timeline_data(db_path, admin)

    conn = connect(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()
    if version != SCHEMA_VERSION or integrity != "ok" or foreign_keys:
        raise RuntimeError(
            f"Local test database check failed: schema={version}, integrity={integrity}, foreign_keys={foreign_keys}"
        )
    return db_path


if __name__ == "__main__":
    database = seed_database()
    print("LOCAL_TEST_DB_READY")
    print(f"database={database}")
    print("developer_account=test/admin; password=test")
    print("permission_test_accounts=u2/member,u3/viewer; password=localtest")
