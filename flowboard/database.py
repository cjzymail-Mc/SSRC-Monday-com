import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .security import hash_password


SCHEMA_VERSION = 16


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(conn):
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _backup_database(path):
    source = Path(path)
    if not source.exists() or source.stat().st_size == 0:
        return None
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = backup_dir / f"{source.stem}-pre-v{SCHEMA_VERSION}-{stamp}.db"
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity_check failed; migration aborted")
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return str(target)


def migrate(path, initial_password=None):
    path = str(Path(path).resolve())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    probe = sqlite3.connect(path)
    try:
        version = probe.execute("PRAGMA user_version").fetchone()[0]
    finally:
        probe.close()
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"database version {version} is newer than supported {SCHEMA_VERSION}"
        )
    backup = None
    has_existing_database = os.path.exists(path) and os.path.getsize(path) > 0
    if version < SCHEMA_VERSION and has_existing_database:
        backup = _backup_database(path)
    conn = connect(path)
    try:
        if version < 1:
            _migration_v1(conn, initial_password or os.getenv("FLOWBOARD_INITIAL_PASSWORD", "flowboard"))
        if version < 2:
            _migration_v2(conn)
        if version < 3:
            _migration_v3(conn)
        if version < 4:
            _migration_v4(conn)
        if version < 5:
            _migration_v5(conn)
        if version < 6:
            _migration_v6(conn)
        if version < 7:
            _migration_v7(conn)
        if version < 8:
            _migration_v8(conn)
        if version < 9:
            _migration_v9(conn)
        if version < 10:
            _migration_v10(conn)
        if version < 11:
            _migration_v11(conn)
        if version < 12:
            _migration_v12(conn)
        if version < 13:
            _migration_v13(conn)
        if version < 14:
            _migration_v14(conn)
        if version < 15:
            _migration_v15(conn)
        if version < 16:
            _migration_v16(conn)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return backup
    finally:
        conn.close()


def _rows(conn, table):
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")] if _table_exists(conn, table) else []


def _migration_v1(conn, initial_password):
    old = {
        name: _rows(conn, name)
        for name in ("members", "boards", "groups_", "tasks", "comments", "activity")
    }
    with transaction(conn):
        conn.execute("PRAGMA foreign_keys = OFF")
        for name in ("activity", "comments", "tasks", "groups_", "boards", "members"):
            if _table_exists(conn, name):
                conn.execute(f"ALTER TABLE {name} RENAME TO legacy_{name}")
        _execute_ddl(conn,
            """
            CREATE TABLE users(
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                avatar TEXT,
                avatar_class TEXT,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                created_at TEXT NOT NULL
            );
            CREATE TABLE workspaces(
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE workspace_memberships(
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                user_id TEXT NOT NULL REFERENCES users(id),
                role TEXT NOT NULL CHECK(role IN ('admin','member','viewer')),
                PRIMARY KEY(workspace_id,user_id)
            );
            CREATE TABLE boards(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT 'purple',
                access_type TEXT NOT NULL DEFAULT 'open' CHECK(access_type IN ('open','private')),
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                created_at TEXT NOT NULL
            );
            CREATE TABLE board_memberships(
                board_id INTEGER NOT NULL REFERENCES boards(id),
                user_id TEXT NOT NULL REFERENCES users(id),
                PRIMARY KEY(board_id,user_id)
            );
            CREATE TABLE groups_(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL REFERENCES boards(id),
                name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT 'purple',
                sort_order INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id)
            );
            CREATE TABLE tasks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES groups_(id),
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '待开始',
                priority TEXT NOT NULL DEFAULT '中',
                due TEXT NOT NULL DEFAULT '未设置',
                owner_id TEXT REFERENCES users(id),
                sort_order INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE comments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                user_id TEXT NOT NULL REFERENCES users(id),
                body TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                created_at TEXT NOT NULL
            );
            CREATE TABLE activity(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER REFERENCES tasks(id),
                user_id TEXT REFERENCES users(id),
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE sessions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                csrf_token TEXT NOT NULL,
                user_id TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE schema_migrations(
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            CREATE INDEX idx_groups_board ON groups_(board_id,sort_order);
            CREATE INDEX idx_tasks_group ON tasks(group_id,sort_order);
            CREATE INDEX idx_comments_task ON comments(task_id,id);
            CREATE INDEX idx_sessions_hash ON sessions(token_hash);
            """
        )
        stamp = utc_now()
        password = hash_password(initial_password)
        members = old["members"] or [
            {"id": "u1", "name": "管理员", "avatar": "管", "avatar_class": "avatar-blue"}
        ]
        for index, member in enumerate(members):
            username = member["id"]
            conn.execute(
                "INSERT INTO users VALUES (?,?,?,?,?,?,1,?)",
                (member["id"], username, member["name"], password, member.get("avatar"), member.get("avatar_class"), stamp),
            )
        conn.execute("INSERT INTO workspaces VALUES (1,?,?)", ("Northstar Studio", stamp))
        for index, member in enumerate(members):
            conn.execute(
                "INSERT INTO workspace_memberships VALUES (1,?,?)",
                (member["id"], "admin" if index == 0 else "member"),
            )
        boards = old["boards"] or [{"id": 1, "name": "欢迎看板", "description": "", "color": "purple", "created_at": stamp}]
        for board in boards:
            conn.execute(
                "INSERT INTO boards(id,workspace_id,name,description,color,created_at) VALUES (?,?,?,?,?,?)",
                (board["id"], 1, board["name"], board.get("description") or "", board.get("color") or "purple", board.get("created_at") or stamp),
            )
        for group in old["groups_"]:
            conn.execute(
                "INSERT INTO groups_(id,board_id,name,color,sort_order) VALUES (?,?,?,?,?)",
                (group["id"], group["board_id"], group["name"], group.get("color") or "purple", group.get("sort_order") or 0),
            )
        for task in old["tasks"]:
            conn.execute(
                """INSERT INTO tasks(id,group_id,title,status,priority,due,owner_id,sort_order,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (task["id"], task["group_id"], task["title"], task.get("status") or "待开始", task.get("priority") or "中", task.get("due") or "未设置", task.get("owner_id"), task.get("sort_order") or 0, task.get("created_at") or stamp, task.get("updated_at") or stamp),
            )
        for comment in old["comments"]:
            conn.execute(
                "INSERT INTO comments(id,task_id,user_id,body,created_at) VALUES (?,?,?,?,?)",
                (comment["id"], comment["task_id"], comment["user_id"], comment["body"], comment.get("created_at") or stamp),
            )
        for event in old["activity"]:
            conn.execute(
                "INSERT INTO activity(id,task_id,user_id,action,created_at) VALUES (?,?,?,?,?)",
                (event["id"], event.get("task_id"), event.get("user_id"), event["action"], event.get("created_at") or stamp),
            )
        conn.execute(
            "INSERT INTO schema_migrations VALUES (1,?,?,?)",
            ("secure_foundation", "flowboard-schema-v1", stamp),
        )
        conn.execute("PRAGMA user_version = 1")
        for name, rows in old.items():
            if rows:
                target = "users" if name == "members" else name
                count = conn.execute(f"SELECT COUNT(*) FROM {target}").fetchone()[0]
                if count != len(rows):
                    raise RuntimeError(f"migration row count mismatch for {name}")
        for name in ("activity", "comments", "tasks", "groups_", "boards", "members"):
            if _table_exists(conn, f"legacy_{name}"):
                conn.execute(f"DROP TABLE legacy_{name}")
        conn.execute("PRAGMA foreign_keys = ON")


def _execute_ddl(conn, script):
    """Execute simple DDL statements without executescript's implicit commit."""
    for statement in script.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)


def _migration_v2(conn):
    with transaction(conn):
        for table in ("boards", "groups_", "tasks"):
            columns = _columns(conn, table)
            if "archived_at" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN archived_at TEXT")
            if "archived_by" not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN archived_by TEXT REFERENCES users(id)"
                )

        if "action_code" not in _columns(conn, "activity"):
            conn.execute("ALTER TABLE activity RENAME TO legacy_activity_v1")
            conn.execute(
                """CREATE TABLE activity(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    board_id INTEGER NOT NULL REFERENCES boards(id),
                    task_id INTEGER REFERENCES tasks(id),
                    entity_type TEXT NOT NULL CHECK(entity_type IN ('board','group','task','comment')),
                    entity_id INTEGER NOT NULL,
                    user_id TEXT REFERENCES users(id),
                    action_code TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )"""
            )
            legacy_rows = conn.execute(
                "SELECT * FROM legacy_activity_v1 ORDER BY id"
            ).fetchall()
            for row in legacy_rows:
                board = conn.execute(
                    """SELECT g.board_id FROM tasks t JOIN groups_ g ON g.id=t.group_id
                       WHERE t.id=?""",
                    (row["task_id"],),
                ).fetchone()
                if not board:
                    continue
                details = {
                    "legacy_action": row["action"],
                    "legacy_details": row["details"] if "details" in row.keys() else "{}",
                }
                import json

                conn.execute(
                    """INSERT INTO activity(
                           id,board_id,task_id,entity_type,entity_id,user_id,
                           action_code,details_json,created_at
                       ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        row["id"],
                        board["board_id"],
                        row["task_id"],
                        "task",
                        row["task_id"],
                        row["user_id"],
                        "legacy.imported",
                        json.dumps(details, ensure_ascii=False),
                        row["created_at"],
                    ),
                )
            conn.execute("DROP TABLE legacy_activity_v1")

        _normalize_order(conn, "groups_", "board_id")
        _normalize_order(conn, "tasks", "group_id")
        _execute_ddl(
            conn,
            """
            CREATE INDEX IF NOT EXISTS idx_boards_workspace_lifecycle
                ON boards(workspace_id,deleted_at,archived_at,id);
            CREATE INDEX IF NOT EXISTS idx_groups_board_lifecycle_order
                ON groups_(board_id,deleted_at,archived_at,sort_order,id);
            CREATE INDEX IF NOT EXISTS idx_tasks_group_lifecycle_order
                ON tasks(group_id,deleted_at,archived_at,sort_order,id);
            CREATE INDEX IF NOT EXISTS idx_activity_board_created
                ON activity(board_id,created_at,id);
            CREATE INDEX IF NOT EXISTS idx_activity_task_created
                ON activity(task_id,created_at,id);
            """,
        )
        conn.execute(
            "INSERT INTO schema_migrations VALUES (2,?,?,?)",
            ("core_lifecycle", "flowboard-schema-v2", utc_now()),
        )
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"foreign key check failed: {len(violations)} violation(s)")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed after v2 migration")
        conn.execute("PRAGMA user_version = 2")


def _normalize_order(conn, table, parent_column):
    parents = conn.execute(
        f"SELECT DISTINCT {parent_column} FROM {table}"
    ).fetchall()
    for parent in parents:
        rows = conn.execute(
            f"SELECT id FROM {table} WHERE {parent_column}=? ORDER BY sort_order,id",
            (parent[0],),
        ).fetchall()
        for index, row in enumerate(rows):
            conn.execute(
                f"UPDATE {table} SET sort_order=? WHERE id=?", (index, row["id"])
            )


def _migration_v3(conn):
    """Add the typed dynamic-field model without discarding v2 projections."""
    import json
    import re

    with transaction(conn):
        _execute_ddl(conn, """
            CREATE TABLE field_definitions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL REFERENCES boards(id),
                system_key TEXT,
                name TEXT NOT NULL,
                field_type TEXT NOT NULL CHECK(field_type IN ('text','number','status','person','date','checkbox','tags','link')),
                config_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(board_id,system_key)
            );
            CREATE TABLE field_options(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_id INTEGER NOT NULL REFERENCES field_definitions(id),
                label TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT 'purple',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                UNIQUE(field_id,id),
                UNIQUE(field_id,label)
            );
            CREATE TABLE task_field_values(
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                field_id INTEGER NOT NULL REFERENCES field_definitions(id),
                text_value TEXT,
                number_value REAL,
                option_id INTEGER,
                user_id TEXT REFERENCES users(id),
                date_value TEXT,
                boolean_value INTEGER CHECK(boolean_value IN (0,1)),
                link_url TEXT,
                link_label TEXT,
                PRIMARY KEY(task_id,field_id),
                FOREIGN KEY(field_id,option_id) REFERENCES field_options(field_id,id),
                CHECK((text_value IS NOT NULL)+(number_value IS NOT NULL)+(option_id IS NOT NULL)+
                      (user_id IS NOT NULL)+(date_value IS NOT NULL)+(boolean_value IS NOT NULL)+
                      (link_url IS NOT NULL)=1)
            );
            CREATE TABLE task_field_tag_values(
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                field_id INTEGER NOT NULL REFERENCES field_definitions(id),
                option_id INTEGER NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(task_id,field_id,option_id),
                FOREIGN KEY(field_id,option_id) REFERENCES field_options(field_id,id)
            );
            CREATE TABLE legacy_task_field_values(
                task_id INTEGER NOT NULL REFERENCES tasks(id),
                field_id INTEGER NOT NULL REFERENCES field_definitions(id),
                raw_value TEXT NOT NULL,
                reason TEXT NOT NULL,
                PRIMARY KEY(task_id,field_id)
            );
            CREATE INDEX idx_fields_board_order ON field_definitions(board_id,deleted_at,is_active,sort_order,id);
            CREATE INDEX idx_field_options_order ON field_options(field_id,deleted_at,is_active,sort_order,id);
            CREATE INDEX idx_task_field_values_field ON task_field_values(field_id,task_id);
        """)
        stamp = utc_now()
        specs = (("status", "状态", "status"), ("priority", "优先级", "status"),
                 ("owner", "负责人", "person"), ("due", "截止日期", "date"))
        for board in conn.execute("SELECT id FROM boards ORDER BY id").fetchall():
            field_ids = {}
            for order, (key, name, kind) in enumerate(specs):
                cursor = conn.execute(
                    """INSERT INTO field_definitions(board_id,system_key,name,field_type,sort_order,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?)""", (board["id"], key, name, kind, order, stamp, stamp))
                field_ids[key] = cursor.lastrowid
            tasks = conn.execute("""SELECT t.* FROM tasks t JOIN groups_ g ON g.id=t.group_id
                                    WHERE g.board_id=? ORDER BY t.id""", (board["id"],)).fetchall()
            for key in ("status", "priority"):
                values = sorted({row[key] for row in tasks if row[key]})
                for order, value in enumerate(values):
                    conn.execute("INSERT INTO field_options(field_id,label,sort_order) VALUES (?,?,?)",
                                 (field_ids[key], value, order))
            for task in tasks:
                for key in ("status", "priority"):
                    if task[key]:
                        option = conn.execute("SELECT id FROM field_options WHERE field_id=? AND label=?",
                                              (field_ids[key], task[key])).fetchone()
                        conn.execute("INSERT INTO task_field_values(task_id,field_id,option_id) VALUES (?,?,?)",
                                     (task["id"], field_ids[key], option["id"]))
                if task["owner_id"]:
                    conn.execute("INSERT INTO task_field_values(task_id,field_id,user_id) VALUES (?,?,?)",
                                 (task["id"], field_ids["owner"], task["owner_id"]))
                due = task["due"]
                if due and due != "未设置":
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
                        conn.execute("INSERT INTO task_field_values(task_id,field_id,date_value) VALUES (?,?,?)",
                                     (task["id"], field_ids["due"], due))
                    else:
                        conn.execute("INSERT INTO legacy_task_field_values VALUES (?,?,?,?)",
                                     (task["id"], field_ids["due"], due, "invalid_date"))
        conn.execute("INSERT INTO schema_migrations VALUES (3,?,?,?)",
                     ("dynamic_fields", "flowboard-schema-v3", stamp))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign key check failed after v3 migration")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed after v3 migration")
        conn.execute("PRAGMA user_version = 3")


def _migration_v4(conn):
    with transaction(conn):
        _execute_ddl(conn, """
            CREATE TABLE saved_views(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL REFERENCES boards(id),
                owner_id TEXT NOT NULL REFERENCES users(id),
                scope TEXT NOT NULL CHECK(scope IN ('personal','shared')),
                view_type TEXT NOT NULL CHECK(view_type IN ('table','kanban','calendar')),
                name TEXT NOT NULL,
                filter_json TEXT NOT NULL DEFAULT '{"op":"and","children":[]}',
                sort_json TEXT NOT NULL DEFAULT '[]',
                visible_fields_json TEXT NOT NULL DEFAULT '[]',
                column_order_json TEXT NOT NULL DEFAULT '[]',
                is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id)
            );
            CREATE INDEX idx_saved_views_board_scope ON saved_views(board_id,scope,deleted_at,name,id);
            CREATE INDEX idx_saved_views_owner ON saved_views(owner_id,board_id,deleted_at,id);
            CREATE UNIQUE INDEX uq_saved_view_personal_default ON saved_views(board_id,owner_id)
                WHERE scope='personal' AND is_default=1 AND deleted_at IS NULL;
            CREATE UNIQUE INDEX uq_saved_view_shared_default ON saved_views(board_id)
                WHERE scope='shared' AND is_default=1 AND deleted_at IS NULL;
        """)
        conn.execute("INSERT INTO schema_migrations VALUES (4,?,?,?)",
                     ("saved_views", "flowboard-schema-v4", utc_now()))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign key check failed after v4 migration")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed after v4 migration")
        conn.execute("PRAGMA user_version = 4")


def _migration_v5(conn):
    with transaction(conn):
        conn.execute("ALTER TABLE saved_views ADD COLUMN presentation_json TEXT NOT NULL DEFAULT '{\"version\":1}'")
        conn.execute("INSERT INTO schema_migrations VALUES (5,?,?,?)",
                     ("saved view presentation", "flowboard-schema-v5", utc_now()))
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("foreign key check failed after v5 migration")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed after v5 migration")
        conn.execute("PRAGMA user_version = 5")


def _migration_v6(conn):
    with transaction(conn):
        conn.execute("ALTER TABLE tasks ADD COLUMN board_order INTEGER NOT NULL DEFAULT 0")
        board_ids=[row["id"] for row in conn.execute("SELECT id FROM boards ORDER BY id")]
        for board_id in board_ids:
            rows=conn.execute("""SELECT t.id FROM groups_ g JOIN tasks t ON t.group_id=g.id
                WHERE g.board_id=? ORDER BY g.sort_order,t.sort_order,t.id""",(board_id,)).fetchall()
            for index,row in enumerate(rows): conn.execute("UPDATE tasks SET board_order=? WHERE id=?",(index,row["id"]))
        conn.execute("CREATE INDEX idx_tasks_board_order ON tasks(board_order,id)")
        conn.execute("INSERT INTO schema_migrations VALUES (6,?,?,?)",
                     ("global board task order", "flowboard-schema-v6", utc_now()))
        if conn.execute("PRAGMA foreign_key_check").fetchall(): raise RuntimeError("foreign key check failed after v6 migration")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise RuntimeError("database integrity check failed after v6 migration")
        conn.execute("PRAGMA user_version = 6")


def _migration_v7(conn):
    with transaction(conn):
        conn.execute("ALTER TABLE tasks ADD COLUMN parent_id INTEGER REFERENCES tasks(id)")
        conn.execute("ALTER TABLE tasks ADD COLUMN subtask_order INTEGER NOT NULL DEFAULT 0")
        conn.execute("""CREATE TABLE task_dependencies(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predecessor_id INTEGER NOT NULL REFERENCES tasks(id),
            successor_id INTEGER NOT NULL REFERENCES tasks(id),
            version INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by TEXT REFERENCES users(id),
            CHECK(predecessor_id <> successor_id),
            UNIQUE(predecessor_id,successor_id)
        )""")
        conn.execute("CREATE INDEX idx_tasks_parent_order ON tasks(parent_id,subtask_order,id)")
        conn.execute("CREATE INDEX idx_dependencies_successor ON task_dependencies(successor_id,deleted_at,predecessor_id)")
        conn.execute("CREATE INDEX idx_dependencies_predecessor ON task_dependencies(predecessor_id,deleted_at,successor_id)")
        conn.execute("INSERT INTO schema_migrations VALUES (7,?,?,?)",
                     ("task hierarchy and dependencies", "flowboard-schema-v7", utc_now()))
        if conn.execute("PRAGMA foreign_key_check").fetchall(): raise RuntimeError("foreign key check failed after v7 migration")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise RuntimeError("database integrity check failed after v7 migration")
        conn.execute("PRAGMA user_version = 7")


def _migration_v8(conn):
    """Advanced field definitions and cross-board relation edges.

    Values for scalar advanced fields continue to use the typed value table's
    text/number columns. Relation values are edges and derived fields are never
    persisted as a second copy of business data.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with transaction(conn):
            conn.execute("""CREATE TABLE field_definitions_v8(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL REFERENCES boards(id),
                system_key TEXT,
                name TEXT NOT NULL,
                field_type TEXT NOT NULL CHECK(field_type IN (
                    'text','number','status','person','date','checkbox','tags','link',
                    'timeline','rating','file','email','phone','relation','mirror','formula')),
                config_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(board_id,system_key)
            )""")
            conn.execute("""INSERT INTO field_definitions_v8
                SELECT id,board_id,system_key,name,field_type,config_json,sort_order,is_active,
                       version,deleted_at,deleted_by,created_at,updated_at FROM field_definitions""")
            conn.execute("DROP TABLE field_definitions")
            conn.execute("ALTER TABLE field_definitions_v8 RENAME TO field_definitions")
            conn.execute("CREATE INDEX idx_fields_board_order ON field_definitions(board_id,deleted_at,is_active,sort_order,id)")
            conn.execute("""CREATE TABLE task_relation_values(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_id INTEGER NOT NULL REFERENCES field_definitions(id),
                source_task_id INTEGER NOT NULL REFERENCES tasks(id),
                target_task_id INTEGER NOT NULL REFERENCES tasks(id),
                version INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                CHECK(source_task_id <> target_task_id),
                UNIQUE(field_id,source_task_id,target_task_id)
            )""")
            conn.execute("CREATE INDEX idx_relation_source ON task_relation_values(field_id,source_task_id,deleted_at,target_task_id)")
            conn.execute("CREATE INDEX idx_relation_target ON task_relation_values(field_id,target_task_id,deleted_at,source_task_id)")
            conn.execute("INSERT INTO schema_migrations VALUES (8,?,?,?)",
                         ("advanced fields and relations", "flowboard-schema-v8", utc_now()))
            conn.execute("PRAGMA user_version = 8")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("foreign key check failed after v8 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("database integrity check failed after v8 migration")


def _migration_v9(conn):
    """Reusable board snapshots and bounded import preview batches."""
    with transaction(conn):
        conn.execute("""CREATE TABLE board_templates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            source_board_id INTEGER REFERENCES boards(id),
            template_type TEXT NOT NULL CHECK(template_type IN ('board','project')),
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            include_tasks INTEGER NOT NULL DEFAULT 0 CHECK(include_tasks IN (0,1)),
            snapshot_json TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            deleted_by TEXT REFERENCES users(id)
        )""")
        conn.execute("CREATE INDEX idx_templates_workspace ON board_templates(workspace_id,deleted_at,updated_at,id)")
        conn.execute("""CREATE TABLE import_batches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER NOT NULL REFERENCES boards(id),
            filename TEXT NOT NULL,
            file_format TEXT NOT NULL CHECK(file_format IN ('csv','xlsx')),
            content_sha256 TEXT NOT NULL,
            preview_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'previewed' CHECK(status IN ('previewed','committed','failed')),
            version INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            committed_at TEXT
        )""")
        conn.execute("CREATE INDEX idx_import_batches_board ON import_batches(board_id,created_by,status,id)")
        conn.execute("INSERT INTO schema_migrations VALUES (9,?,?,?)",("templates and bounded tabular transfer","flowboard-schema-v9",utc_now()))
        conn.execute("PRAGMA user_version = 9")
    if conn.execute("PRAGMA foreign_key_check").fetchall():raise RuntimeError("foreign key check failed after v9 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("database integrity check failed after v9 migration")


def _migration_v10(conn):
    """Fixed scheduling start date and timeline/gantt saved-view types."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with transaction(conn):
            conn.execute("ALTER TABLE tasks ADD COLUMN start_date TEXT")
            conn.execute("""CREATE TABLE saved_views_v10(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL REFERENCES boards(id),owner_id TEXT NOT NULL REFERENCES users(id),
                scope TEXT NOT NULL CHECK(scope IN ('personal','shared')),
                view_type TEXT NOT NULL CHECK(view_type IN ('table','kanban','calendar','timeline','gantt')),
                name TEXT NOT NULL,filter_json TEXT NOT NULL DEFAULT '{"op":"and","children":[]}',sort_json TEXT NOT NULL DEFAULT '[]',
                visible_fields_json TEXT NOT NULL DEFAULT '[]',column_order_json TEXT NOT NULL DEFAULT '[]',is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
                version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT,deleted_by TEXT REFERENCES users(id),
                presentation_json TEXT NOT NULL DEFAULT '{"version":1}'
            )""")
            conn.execute("""INSERT INTO saved_views_v10(id,board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,is_default,version,created_at,updated_at,deleted_at,deleted_by,presentation_json)
                SELECT id,board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,is_default,version,created_at,updated_at,deleted_at,deleted_by,presentation_json FROM saved_views""")
            conn.execute("DROP TABLE saved_views");conn.execute("ALTER TABLE saved_views_v10 RENAME TO saved_views")
            conn.execute("CREATE INDEX idx_saved_views_board_scope ON saved_views(board_id,scope,deleted_at,name,id)");conn.execute("CREATE INDEX idx_saved_views_owner ON saved_views(owner_id,board_id,deleted_at,id)")
            conn.execute("CREATE UNIQUE INDEX uq_saved_view_personal_default ON saved_views(board_id,owner_id) WHERE scope='personal' AND is_default=1 AND deleted_at IS NULL")
            conn.execute("CREATE UNIQUE INDEX uq_saved_view_shared_default ON saved_views(board_id) WHERE scope='shared' AND is_default=1 AND deleted_at IS NULL")
            conn.execute("INSERT INTO schema_migrations VALUES (10,?,?,?)",("timeline and gantt scheduling","flowboard-schema-v10",utc_now()));conn.execute("PRAGMA user_version = 10")
    finally:conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_key_check").fetchall():raise RuntimeError("foreign key check failed after v10 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("database integrity check failed after v10 migration")


def _migration_v11(conn):
    """Chart saved views and current-data dashboard configuration."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with transaction(conn):
            conn.execute("""CREATE TABLE saved_views_v11(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL REFERENCES boards(id),owner_id TEXT NOT NULL REFERENCES users(id),
                scope TEXT NOT NULL CHECK(scope IN ('personal','shared')),
                view_type TEXT NOT NULL CHECK(view_type IN ('table','kanban','calendar','timeline','gantt','chart')),
                name TEXT NOT NULL,filter_json TEXT NOT NULL DEFAULT '{"op":"and","children":[]}',sort_json TEXT NOT NULL DEFAULT '[]',
                visible_fields_json TEXT NOT NULL DEFAULT '[]',column_order_json TEXT NOT NULL DEFAULT '[]',is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
                version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT,deleted_by TEXT REFERENCES users(id),
                presentation_json TEXT NOT NULL DEFAULT '{"version":1}'
            )""")
            conn.execute("""INSERT INTO saved_views_v11 SELECT id,board_id,owner_id,scope,view_type,name,filter_json,sort_json,visible_fields_json,column_order_json,is_default,version,created_at,updated_at,deleted_at,deleted_by,presentation_json FROM saved_views""")
            conn.execute("DROP TABLE saved_views");conn.execute("ALTER TABLE saved_views_v11 RENAME TO saved_views")
            conn.execute("CREATE INDEX idx_saved_views_board_scope ON saved_views(board_id,scope,deleted_at,name,id)");conn.execute("CREATE INDEX idx_saved_views_owner ON saved_views(owner_id,board_id,deleted_at,id)")
            conn.execute("CREATE UNIQUE INDEX uq_saved_view_personal_default ON saved_views(board_id,owner_id) WHERE scope='personal' AND is_default=1 AND deleted_at IS NULL");conn.execute("CREATE UNIQUE INDEX uq_saved_view_shared_default ON saved_views(board_id) WHERE scope='shared' AND is_default=1 AND deleted_at IS NULL")
            conn.executescript("""
                CREATE TABLE dashboards(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,workspace_id INTEGER NOT NULL REFERENCES workspaces(id),owner_id TEXT NOT NULL REFERENCES users(id),
                    scope TEXT NOT NULL CHECK(scope IN ('personal','shared')),name TEXT NOT NULL,global_filters_json TEXT NOT NULL DEFAULT '{"version":1,"by_source":{}}',
                    version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT,deleted_by TEXT REFERENCES users(id));
                CREATE INDEX idx_dashboards_workspace ON dashboards(workspace_id,scope,deleted_at,id);
                CREATE TABLE dashboard_sources(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,dashboard_id INTEGER NOT NULL REFERENCES dashboards(id),source_key TEXT NOT NULL,board_id INTEGER NOT NULL REFERENCES boards(id),
                    query_json TEXT NOT NULL DEFAULT '{"version":1,"filter":{"op":"and","children":[]},"sort":[]}',sort_order INTEGER NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT,deleted_by TEXT REFERENCES users(id),UNIQUE(dashboard_id,source_key));
                CREATE INDEX idx_dashboard_sources ON dashboard_sources(dashboard_id,deleted_at,sort_order,id);
                CREATE TABLE dashboard_widgets(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,dashboard_id INTEGER NOT NULL REFERENCES dashboards(id),widget_type TEXT NOT NULL CHECK(widget_type IN ('number','chart','progress','calendar','table')),
                    title TEXT NOT NULL,config_json TEXT NOT NULL,x INTEGER NOT NULL,y INTEGER NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,sort_order INTEGER NOT NULL DEFAULT 0,
                    version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT,deleted_by TEXT REFERENCES users(id));
                CREATE INDEX idx_dashboard_widgets ON dashboard_widgets(dashboard_id,deleted_at,sort_order,id);
                CREATE TABLE dashboard_activity(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,dashboard_id INTEGER NOT NULL REFERENCES dashboards(id),user_id TEXT NOT NULL REFERENCES users(id),action_code TEXT NOT NULL,details_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
                CREATE INDEX idx_dashboard_activity ON dashboard_activity(dashboard_id,id);
            """)
            conn.execute("INSERT INTO schema_migrations VALUES (11,?,?,?)",("charts and current-data dashboards","flowboard-schema-v11",utc_now()));conn.execute("PRAGMA user_version = 11")
    finally:conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_key_check").fetchall():raise RuntimeError("foreign key check failed after v11 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("database integrity check failed after v11 migration")


def _migration_v12(conn):
    """Threaded comments, mentions, subscriptions, attachment metadata and collaboration outbox."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with transaction(conn):
            conn.executescript("""
                CREATE TABLE comments_v12(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER NOT NULL REFERENCES tasks(id),user_id TEXT NOT NULL REFERENCES users(id),
                    parent_id INTEGER REFERENCES comments_v12(id),body TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,edited_at TEXT,deleted_at TEXT,deleted_by TEXT REFERENCES users(id));
                INSERT INTO comments_v12(id,task_id,user_id,body,created_at,updated_at)
                    SELECT id,task_id,user_id,body,created_at,created_at FROM comments;
                DROP TABLE comments;
                ALTER TABLE comments_v12 RENAME TO comments;
                CREATE INDEX idx_comments_task ON comments(task_id,deleted_at,parent_id,id);
                CREATE INDEX idx_comments_parent ON comments(parent_id,id);
                CREATE TABLE comment_versions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,comment_id INTEGER NOT NULL REFERENCES comments(id),version INTEGER NOT NULL,
                    body TEXT NOT NULL,edited_by TEXT NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,UNIQUE(comment_id,version));
                INSERT INTO comment_versions(comment_id,version,body,edited_by,created_at)
                    SELECT id,1,body,user_id,created_at FROM comments;

                CREATE TABLE comment_mentions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,comment_id INTEGER NOT NULL REFERENCES comments(id),
                    target_key TEXT NOT NULL,user_id TEXT REFERENCES users(id),mention_type TEXT NOT NULL CHECK(mention_type IN ('user','all')),
                    created_at TEXT NOT NULL,UNIQUE(comment_id,target_key));
                CREATE INDEX idx_comment_mentions_user ON comment_mentions(user_id,comment_id);

                CREATE TABLE task_subscriptions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER NOT NULL REFERENCES tasks(id),user_id TEXT NOT NULL REFERENCES users(id),
                    reason TEXT NOT NULL CHECK(reason IN ('manual','creator','comment','mention')),version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,deleted_at TEXT,UNIQUE(task_id,user_id,reason));
                CREATE INDEX idx_task_subscriptions_task ON task_subscriptions(task_id,deleted_at,user_id);

                CREATE TABLE attachments(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER NOT NULL REFERENCES tasks(id),uploader_id TEXT NOT NULL REFERENCES users(id),
                    storage_name TEXT NOT NULL UNIQUE,original_name TEXT NOT NULL,content_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,preview_kind TEXT NOT NULL CHECK(preview_kind IN ('image','text','none')),version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT,deleted_by TEXT REFERENCES users(id));
                CREATE INDEX idx_attachments_task ON attachments(task_id,deleted_at,id);

                CREATE TABLE collaboration_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,event_key TEXT NOT NULL UNIQUE,event_type TEXT NOT NULL,
                    board_id INTEGER NOT NULL REFERENCES boards(id),task_id INTEGER NOT NULL REFERENCES tasks(id),actor_id TEXT NOT NULL REFERENCES users(id),
                    comment_id INTEGER REFERENCES comments(id),attachment_id INTEGER REFERENCES attachments(id),recipient_user_id TEXT REFERENCES users(id),
                    payload_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
                CREATE INDEX idx_collaboration_events_task ON collaboration_events(task_id,id);
                CREATE INDEX idx_collaboration_events_recipient ON collaboration_events(recipient_user_id,id);
            """)
            conn.execute("INSERT INTO schema_migrations VALUES (12,?,?,?)",("comments mentions subscriptions attachments and collaboration outbox","flowboard-schema-v12",utc_now()))
            conn.execute("PRAGMA user_version = 12")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_key_check").fetchall():raise RuntimeError("foreign key check failed after v12 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("database integrity check failed after v12 migration")


def _migration_v13(conn):
    """Collapse subscription reasons into one deterministic user/task follow state."""
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        with transaction(conn):
            conn.executescript("""
                CREATE TABLE task_subscriptions_v13(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,task_id INTEGER NOT NULL REFERENCES tasks(id),user_id TEXT NOT NULL REFERENCES users(id),
                    state TEXT NOT NULL CHECK(state IN ('following','opted_out')),source TEXT NOT NULL CHECK(source IN ('manual','creator','comment','mention')),
                    version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(task_id,user_id));
                INSERT INTO task_subscriptions_v13(task_id,user_id,state,source,version,created_at,updated_at)
                SELECT task_id,user_id,
                    CASE WHEN SUM(CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END)>0 THEN 'following' ELSE 'opted_out' END,
                    CASE WHEN SUM(CASE WHEN deleted_at IS NULL AND reason='manual' THEN 1 ELSE 0 END)>0 THEN 'manual'
                         WHEN SUM(CASE WHEN deleted_at IS NULL AND reason='creator' THEN 1 ELSE 0 END)>0 THEN 'creator'
                         WHEN SUM(CASE WHEN deleted_at IS NULL AND reason='comment' THEN 1 ELSE 0 END)>0 THEN 'comment'
                         WHEN SUM(CASE WHEN deleted_at IS NULL AND reason='mention' THEN 1 ELSE 0 END)>0 THEN 'mention' ELSE 'manual' END,
                    MAX(version),MIN(created_at),MAX(COALESCE(deleted_at,created_at))
                FROM task_subscriptions GROUP BY task_id,user_id;
                DROP TABLE task_subscriptions;
                ALTER TABLE task_subscriptions_v13 RENAME TO task_subscriptions;
                CREATE INDEX idx_task_subscriptions_task ON task_subscriptions(task_id,state,user_id);
            """)
            conn.execute("INSERT INTO schema_migrations VALUES (13,?,?,?)",("deterministic per-user task subscription state","flowboard-schema-v13",utc_now()))
            conn.execute("PRAGMA user_version = 13")
    finally:conn.execute("PRAGMA foreign_keys = ON")
    if conn.execute("PRAGMA foreign_key_check").fetchall():raise RuntimeError("foreign key check failed after v13 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("database integrity check failed after v13 migration")


def _migration_v14(conn):
    """Notifications, deterministic consumers, realtime cursors and safe audit."""
    with transaction(conn):
        conn.executescript("""
            CREATE TABLE notifications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_user_id TEXT NOT NULL REFERENCES users(id),
                event_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                actor_user_id TEXT REFERENCES users(id),
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                board_id INTEGER REFERENCES boards(id),
                task_id INTEGER REFERENCES tasks(id),
                comment_id INTEGER REFERENCES comments(id),
                created_at TEXT NOT NULL,read_at TEXT,version INTEGER NOT NULL DEFAULT 1,
                UNIQUE(recipient_user_id,event_key));
            CREATE INDEX idx_notifications_recipient ON notifications(recipient_user_id,id DESC);
            CREATE TABLE event_consumers(
                consumer_key TEXT PRIMARY KEY,last_event_id INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
            CREATE TABLE audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,source_key TEXT NOT NULL UNIQUE,
                workspace_id INTEGER REFERENCES workspaces(id),actor_user_id TEXT REFERENCES users(id),
                action_code TEXT NOT NULL,outcome TEXT NOT NULL CHECK(outcome IN ('success','denied','failure')),
                entity_type TEXT,entity_id TEXT,request_id TEXT,details_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
            CREATE INDEX idx_audit_workspace_id ON audit_log(workspace_id,id DESC);
            CREATE TABLE realtime_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,event_key TEXT NOT NULL UNIQUE,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),board_id INTEGER REFERENCES boards(id),
                task_id INTEGER REFERENCES tasks(id),actor_user_id TEXT REFERENCES users(id),
                action_code TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE INDEX idx_realtime_workspace_id ON realtime_events(workspace_id,id);
        """)
        conn.execute("""INSERT OR IGNORE INTO audit_log(source_key,workspace_id,actor_user_id,action_code,outcome,entity_type,entity_id,details_json,created_at)
            SELECT 'activity:'||a.id,b.workspace_id,a.user_id,a.action_code,'success',a.entity_type,CAST(a.entity_id AS TEXT),a.details_json,a.created_at
            FROM activity a JOIN boards b ON b.id=a.board_id""")
        conn.execute("""INSERT OR IGNORE INTO realtime_events(event_key,workspace_id,board_id,task_id,actor_user_id,action_code,created_at)
            SELECT 'activity:'||a.id,b.workspace_id,a.board_id,a.task_id,a.user_id,a.action_code,a.created_at
            FROM activity a JOIN boards b ON b.id=a.board_id""")
        conn.execute("INSERT INTO event_consumers VALUES ('collaboration_notifications',0,?)",(utc_now(),))
        conn.execute("INSERT INTO event_consumers VALUES ('activity_notifications',0,?)",(utc_now(),))
        conn.execute("INSERT INTO schema_migrations VALUES (14,?,?,?)",("notifications search realtime cursors and audit","flowboard-schema-v14",utc_now()))
        conn.execute("PRAGMA user_version = 14")
    if conn.execute("PRAGMA foreign_key_check").fetchall():raise RuntimeError("foreign key check failed after v14 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("database integrity check failed after v14 migration")


def _migration_v15(conn):
    with transaction(conn):
        if "description" not in _columns(conn,"tasks"):
            conn.execute("ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "trash_retention_days" not in _columns(conn,"workspaces"):
            conn.execute("ALTER TABLE workspaces ADD COLUMN trash_retention_days INTEGER NOT NULL DEFAULT 30 CHECK(trash_retention_days BETWEEN 1 AND 3650)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_deleted_at ON tasks(deleted_at,id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_deleted_at ON groups_(deleted_at,id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_boards_deleted_at ON boards(deleted_at,id)")
        conn.execute("INSERT INTO schema_migrations VALUES (15,?,?,?)",("bulk task operations retention backup and production closeout","flowboard-schema-v15",utc_now()))
        conn.execute("PRAGMA user_version = 15")
    if conn.execute("PRAGMA foreign_key_check").fetchall():raise RuntimeError("foreign key check failed after v15 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("database integrity check failed after v15 migration")


def _migration_v16(conn):
    with transaction(conn):
        _execute_ddl(conn,"""
            CREATE TABLE timeline_projects(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                name TEXT NOT NULL,
                created_by TEXT NOT NULL REFERENCES users(id),
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX idx_timeline_projects_active_name
                ON timeline_projects(workspace_id, name) WHERE deleted_at IS NULL;
            CREATE TABLE timeline_nodes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES timeline_projects(id),
                track TEXT NOT NULL CHECK(track IN ('main','parallel')),
                stage TEXT NOT NULL CHECK(stage IN ('创意','设计','开发','测试','量产','应用迭代')),
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                initial_date TEXT NOT NULL,
                done_at TEXT,
                remark TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL DEFAULT 1,
                deleted_at TEXT,
                deleted_by TEXT REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX idx_tln_project ON timeline_nodes(project_id, deleted_at, track, date);
            CREATE TABLE timeline_change_batches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES timeline_projects(id),
                actor_user_id TEXT NOT NULL REFERENCES users(id),
                change_kind TEXT NOT NULL CHECK(change_kind IN ('direct_edit','status_toggle','initial_correction','undo')),
                trigger_source TEXT NOT NULL CHECK(trigger_source IN ('editor','drag','import','undo','admin')),
                project_version_before INTEGER NOT NULL,
                project_version_after INTEGER NOT NULL,
                undone_batch_id INTEGER REFERENCES timeline_change_batches(id),
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX idx_tlcb_project ON timeline_change_batches(project_id, id);
            CREATE TABLE timeline_node_changes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL REFERENCES timeline_change_batches(id),
                node_id INTEGER NOT NULL REFERENCES timeline_nodes(id),
                change_role TEXT NOT NULL CHECK(change_role IN ('direct','cascaded')),
                field TEXT NOT NULL CHECK(field IN ('date','done_at','initial_date','stage','track','name','remark','created','deleted')),
                old_value TEXT,
                new_value TEXT
            );
            CREATE INDEX idx_tlnc_batch ON timeline_node_changes(batch_id, node_id);
            CREATE TABLE timeline_import_batches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
                filename TEXT NOT NULL,
                file_format TEXT NOT NULL CHECK(file_format IN ('csv','xlsx')),
                content_sha256 TEXT NOT NULL,
                preview_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'previewed' CHECK(status IN ('previewed','committed')),
                version INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                committed_at TEXT
            );
            CREATE INDEX idx_timeline_import_batches_workspace
                ON timeline_import_batches(workspace_id, created_by, status, id);
        """)
        conn.execute("INSERT INTO schema_migrations VALUES (16,?,?,?)",("project timeline five-table model","flowboard-schema-v16",utc_now()))
        conn.execute("PRAGMA user_version = 16")
    if conn.execute("PRAGMA foreign_key_check").fetchall():raise RuntimeError("foreign key check failed after v16 migration")
    if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise RuntimeError("database integrity check failed after v16 migration")


def copy_database(source, target):
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
