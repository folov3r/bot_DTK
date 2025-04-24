import sqlite3
import hashlib

def get_file_hash(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

user_states = {
    "other_date": {},
    "login": {},
    "chose_role": {},
    "update_user_group": {},
    "delete_user": {},
    "profile_edit": {},
    "feedback": {},
    "check_schedule": {},
    "list_users": {},
    "check_another_group": {},
    "set_group_num": {},
    "other_date_another_group": {},
    "add_favorite_group": {}
}

profile_messages = {}

def init_db(db_name, schema):
    with sqlite3.connect(f"db/{db_name}.db") as conn:
        cursor = conn.cursor()
        cursor.execute(schema)
        conn.commit()


# Инициализация базы данных для пользователей
init_db("users", """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        value TEXT,
        is_teacher INTEGER DEFAULT 0,
        notifications_enabled INTEGER DEFAULT 1
    )""")

init_db("users", """
    CREATE TABLE IF NOT EXISTS favorite_groups (
    user_id INTEGER,
    group_name TEXT,
    PRIMARY KEY (user_id, group_name),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
    )""")

# Инициализация базы данных для админов
init_db("admins", """
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        role INTEGER,
        who_add TEXT
    )
""")

# Инициализация базы данных для уведомлений
init_db("notifications", """
    CREATE TABLE IF NOT EXISTS notifications (
        file_name TEXT PRIMARY KEY,
        notified BOOLEAN DEFAULT FALSE
    )
""")


def db_execute(db_name, query, params=()):
    with sqlite3.connect(f"db/{db_name}.db") as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()


def db_fetch(db_name, query, params=()):
    with sqlite3.connect(f"db/{db_name}.db") as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()


def add_admin(user_id: int, username: str, role: int, who_add: str):
    db_execute("admins", """
        INSERT OR REPLACE INTO admins (user_id, username, role, who_add)
        VALUES (?, ?, ?, ?)
    """, (user_id, username, role, who_add))


def get_admin_role(user_id: int) -> int:
    result = db_fetch("admins", "SELECT role FROM admins WHERE user_id = ?", (user_id,))
    return result[0][0] if result else 0


def update_admin_role(user_id: int, new_role: int):
    db_execute("admins", "UPDATE admins SET role = ? WHERE user_id = ?", (new_role, user_id))


def remove_admin_def(user_id: int):
    db_execute("admins", "DELETE FROM admins WHERE user_id = ?", (user_id,))


def remove_user_def(user_id: int):
    db_execute("users", "DELETE FROM users WHERE user_id = ?", (user_id,))


def get_all_admins():
    return db_fetch("admins", "SELECT user_id, username, role, who_add FROM admins")


def get_username_admin(user_id: int):
    result = db_fetch("admins", "SELECT username FROM admins WHERE user_id = ?", (user_id,))
    return result[0][0] if result else 0


def add_favorite_group(user_id, group_name):
    return db_execute("users", "INSERT OR IGNORE INTO favorite_groups (user_id, group_name) VALUES (?, ?)", (user_id, group_name))

def remove_favorite_group(user_id, group_name):
    return db_execute("users", "DELETE FROM favorite_groups WHERE user_id = ? AND group_name = ?", (user_id, group_name))

def get_favorite_groups(user_id):
    result = db_fetch("users", "SELECT group_name FROM favorite_groups WHERE user_id = ?", (user_id,))
    return [group[0] for group in result]

def get_all_users_id():
    result = db_fetch("users", "SELECT user_id FROM users")
    return [user_id for (user_id,) in result]

def get_all_users_data():
    return db_fetch("users", "SELECT user_id, username, value, is_teacher, notifications_enabled FROM users")

def enable_notify(user_id):
    db_execute("users", "UPDATE users SET notifications_enabled = 1 WHERE user_id = ?", (user_id,))


def disable_notify(user_id):
    db_execute("users", "UPDATE users SET notifications_enabled = 0 WHERE user_id = ?", (user_id,))
