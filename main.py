import sqlite3
import time
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
app = FastAPI(title="店舗接客フロア管理システム")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
DB_FILE = "restaurant.db"
ALLERGEN_SYNONYMS = {
    "エビ": "えび", "海老": "えび", "カニ": "かに", "蟹": "かに",
    "ソバ": "そば", "蕎麦": "そば", "コムギ": "小麦", "たまご": "卵",
    "タマゴ": "卵", "玉子": "卵", "乳製品": "乳", "ミルク": "乳",
    "牛乳": "乳", "落花生": "落花生（ピーナッツ）", "ピーナッツ": "落花生（ピーナッツ）",
    "キウイ": "キウイフルーツ", "ゴマ": "ごま", "胡麻": "ごま"
}
def normalize_allergen(name: str) -> str:
    cleaned = name.strip()
    return ALLERGEN_SYNONYMS.get(cleaned, cleaned)
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
class SingleUserPayload(BaseModel):
    user_id: Optional[str] = None
    name: str
    region: Optional[str] = "未登録"
    allergies: List[str] = []
    hint: Optional[str] = ""
class GroupRegisterRequest(BaseModel):
    users: List[SingleUserPayload]
class UserUpdateRequest(BaseModel):
    name: str
    region: Optional[str] = "未登録"
    count: int = 1
    hint: Optional[str] = ""
    allergies: List[str] = []
    favs: List[str] = []
class AssignRequest(BaseModel):
    table_id: int
    user_ids: List[str]
    session_id: str
@app.get("/api/waiting-queue")
def get_waiting_queue():
    return [
        {"queueId": "q-01", "guestsCount": 1, "userIds": ["u-0008"]},  # 鈴木様（そばアレルギー）
        {"queueId": "q-02", "guestsCount": 1, "userIds": ["u-0009"]},  # 渡辺様（常連）
        {"queueId": "q-03", "guestsCount": 1, "userIds": ["u-0010"]}   # 木村様（旅行）
    ]
@app.get("/api/users")
def get_all_users():
    with get_db() as conn:
        users = conn.execute("SELECT * FROM UserData").fetchall()
        result = {}
        for u in users:
            uid = u["id"]
            algs = conn.execute("SELECT a.name FROM UserAllergy ua JOIN Allergy a ON ua.allergy_id = a.id WHERE ua.user_id = ?", (uid,)).fetchall()
            favs = conn.execute("SELECT m.name FROM UserMenuPreference ump JOIN Menu m ON ump.menu_id = m.id WHERE ump.user_id = ?", (uid,)).fetchall()
            mem = conn.execute("SELECT memory_content FROM UserMemory WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
            sess = conn.execute("""
                SELECT ts.id as sId, ts.table_id as tId, ts.start_datetime as [in], ts.end_datetime as [out]
                FROM TableSessionMembers tsm JOIN TableSession ts ON tsm.table_session_id = ts.id
                WHERE tsm.user_id = ? ORDER BY ts.start_datetime DESC
            """, (uid,)).fetchall()
            result[uid] = {
                "id": uid,
                "name": u["name"],
                "region": u["region"] or "未登録",
                "count": max(len(sess), 1),
                "last": u["last_visit"] or "-",
                "is_deleted": bool(u["is_deleted"]),
                "allergies": [a["name"] for a in algs],
                "favs": [f["name"] for f in favs],
                "hint": mem["memory_content"] if mem else "",
                "sessions": [dict(s) for s in sess]
            }
        return result
@app.get("/api/floor-status")
def get_floor_status():
    with get_db() as conn:
        active_sessions = conn.execute("""
            SELECT * FROM TableSession
            WHERE end_datetime IN ('利用中', '会計中', '予約中')
        """).fetchall()
        tables_data = {}
        for i in range(1, 11):
            tables_data[i] = {
                "sessionId": None, "type": "empty", "status": "empty",
                "stayTime": None, "guestCount": 0, "userIds": [], "hasSpoken": False, "summary": ""
            }
        for s in active_sessions:
            t_id = s["table_id"]
            if t_id not in tables_data:
                continue
            members = conn.execute("SELECT user_id FROM TableSessionMembers WHERE table_session_id = ?", (s["id"],)).fetchall()
            u_ids = [m["user_id"] for m in members]
            conv = conn.execute("SELECT memory_content FROM ConversationMemory WHERE table_session_id = ? ORDER BY timestamp DESC LIMIT 1", (s["id"],)).fetchone()
            summary_text = conv["memory_content"] if conv else ""
            is_reserved = (s["end_datetime"] == "予約中")
            is_billing = (s["end_datetime"] == "会計中")
            is_speaking = bool(s["conversation_status"])
            if is_reserved:
                s_type = "reserved"
            elif is_billing:
                s_type = "billing"
            elif is_speaking:
                s_type = "speaking"
            else:
                s_type = "active"
            tables_data[t_id] = {
                "sessionId": s["id"],
                "type": s_type,
                "status": s["end_datetime"],
                "stayTime": s["start_datetime"] if not is_reserved else None,
                "reserveTime": s["start_datetime"] if is_reserved else None,
                "guestCount": max(len(u_ids), 1),
                "userIds": u_ids,
                "hasSpoken": bool(summary_text) or is_speaking,
                "summary": summary_text
            }
        return tables_data
@app.post("/api/register-group")
def register_group(req: GroupRegisterRequest):
    created_user_ids = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_date = datetime.now().strftime("%Y-%m-%d")
    with get_db() as conn:
        for idx, u in enumerate(req.users):
            if u.user_id:
                uid = u.user_id
                conn.execute("UPDATE UserData SET last_visit = ?, region = COALESCE(NULLIF(?, ''), region), is_deleted = 0 WHERE id = ?", (now_str, u.region, uid))
            else:
                uid = f"u-{int(time.time()*1000)}-{idx+1}"
                conn.execute("INSERT INTO UserData (id, name, region, join_datetime, last_visit, is_deleted) VALUES (?, ?, ?, ?, ?, 0)",
                             (uid, u.name, u.region, now_str, now_str))
                normalized_algs = list(dict.fromkeys([normalize_allergen(a) for a in u.allergies if a.strip()]))
                for alg_name in normalized_algs:
                    row = conn.execute("SELECT id FROM Allergy WHERE name = ?", (alg_name,)).fetchone()
                    alg_id = row["id"] if row else conn.execute("INSERT INTO Allergy (name) VALUES (?)", (alg_name,)).lastrowid
                    conn.execute("INSERT OR IGNORE INTO UserAllergy (user_id, allergy_id, info_date) VALUES (?, ?, ?)", (uid, alg_id, today_date))
                if u.hint:
                    conn.execute("INSERT INTO UserMemory (user_id, timestamp, memory_topic, memory_content) VALUES (?, ?, '新規受付', ?)", (uid, now_str, u.hint))
            created_user_ids.append(uid)
        conn.commit()
    return {"status": "success", "user_ids": created_user_ids}
@app.put("/api/users/{user_id}")
def update_user_profile(user_id: str, req: UserUpdateRequest):
    with get_db() as conn:
        conn.execute("UPDATE UserData SET name = ?, region = ? WHERE id = ?", (req.name, req.region, user_id))
        conn.execute("DELETE FROM UserAllergy WHERE user_id = ?", (user_id,))
        for alg_name in list(dict.fromkeys([normalize_allergen(a) for a in req.allergies if a.strip()])):
            row = conn.execute("SELECT id FROM Allergy WHERE name = ?", (alg_name,)).fetchone()
            alg_id = row["id"] if row else conn.execute("INSERT INTO Allergy (name) VALUES (?)", (alg_name,)).lastrowid
            conn.execute("INSERT OR IGNORE INTO UserAllergy (user_id, allergy_id, info_date) VALUES (?, ?, date('now'))", (user_id, alg_id))
        conn.execute("DELETE FROM UserMenuPreference WHERE user_id = ?", (user_id,))
        for fav_name in req.favs:
            clean_fav = fav_name.strip()
            if not clean_fav:
                continue
            row = conn.execute("SELECT id FROM Menu WHERE name = ?", (clean_fav,)).fetchone()
            menu_id = row["id"] if row else conn.execute("INSERT INTO Menu (name, price) VALUES (?, 0)", (clean_fav,)).lastrowid
            conn.execute("INSERT OR IGNORE INTO UserMenuPreference (user_id, menu_id) VALUES (?, ?)", (user_id, menu_id))
        if req.hint:
            conn.execute("INSERT INTO UserMemory (user_id, timestamp, memory_topic, memory_content) VALUES (?, datetime('now'), 'カルテ更新', ?)", (user_id, req.hint))
        conn.commit()
    return {"status": "updated"}
@app.put("/api/users/{user_id}/trash")
def trash_user(user_id: str):
    with get_db() as conn:
        conn.execute("UPDATE UserData SET is_deleted = 1 WHERE id = ?", (user_id,))
        conn.commit()
    return {"status": "trashed"}
@app.put("/api/users/{user_id}/restore")
def restore_user(user_id: str):
    with get_db() as conn:
        conn.execute("UPDATE UserData SET is_deleted = 0 WHERE id = ?", (user_id,))
        conn.commit()
    return {"status": "restored"}
@app.delete("/api/users/{user_id}/purge")
def purge_user(user_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM UserData WHERE id = ?", (user_id,))
        conn.commit()
    return {"status": "purged"}
@app.post("/api/sessions/assign")
def assign_session(req: AssignRequest):
    now = datetime.now().strftime("%H:%M")
    start_label = f"{now} 入店"
    with get_db() as conn:
        conn.execute("INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status) VALUES (?, ?, ?, ?, '利用中', 0)",
                     (req.session_id, now, req.table_id, start_label))
        for uid in req.user_ids:
            conn.execute("INSERT INTO TableSessionMembers (table_session_id, user_id) VALUES (?, ?)", (req.session_id, uid))
            conn.execute("UPDATE UserData SET last_visit = datetime('now') WHERE id = ?", (uid,))
        conn.commit()
    return {"status": "assigned"}
@app.delete("/api/sessions/{session_id}")
def cancel_session(session_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM TableSession WHERE id = ?", (session_id,))
        conn.commit()
    return {"status": "cancelled"}
@app.post("/api/sessions/{session_id}/seat")
def seat_reserved(session_id: str):
    start_label = datetime.now().strftime("%H:%M 入店")
    with get_db() as conn:
        conn.execute("UPDATE TableSession SET end_datetime = '利用中', start_datetime = ? WHERE id = ?", (start_label, session_id))
        conn.commit()
    return {"status": "seated"}
@app.post("/api/sessions/{session_id}/bill")
def bill_session(session_id: str):
    with get_db() as conn:
        conn.execute("UPDATE TableSession SET end_datetime = '会計中' WHERE id = ?", (session_id,))
        conn.commit()
    return {"status": "billing"}
@app.post("/api/sessions/{session_id}/checkout")
def checkout_session(session_id: str):
    now_label = datetime.now().strftime("%H:%M 退店")
    with get_db() as conn:
        conn.execute("UPDATE TableSession SET end_datetime = ? WHERE id = ?", (now_label, session_id))
        conn.commit()
    return {"status": "checked_out"}
TAX_RATE = 0.10  # Menu.price は税抜価格として扱う
class OrderAddRequest(BaseModel):
    menu_id: int
    qty: int = 1
def ensure_order_table():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS OrderItem (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(64) NOT NULL,
                menu_id INTEGER,
                name VARCHAR(64) NOT NULL,
                unit_price INTEGER NOT NULL,
                qty INTEGER NOT NULL DEFAULT 1,
                status VARCHAR(8) NOT NULL DEFAULT '注文中',
                created_at DATETIME,
                FOREIGN KEY (session_id) REFERENCES TableSession(id) ON DELETE CASCADE
            )""")
        if conn.execute("SELECT COUNT(*) FROM OrderItem").fetchone()[0] == 0:
            demo = {"sess-001": [(4, 1, "提供済"), (1, 1, "提供済"), (5, 1, "注文中")],
                    "sess-002": [(6, 1, "提供済")],
                    "sess-003": [(3, 1, "提供済"), (4, 1, "注文中")],
                    "sess-004": [(1, 1, "提供済"), (2, 1, "提供済"), (5, 2, "提供済")],
                    "sess-005": [(2, 1, "提供済"), (6, 1, "提供済")]}
            for sid, rows in demo.items():
                if not conn.execute("SELECT 1 FROM TableSession WHERE id = ?", (sid,)).fetchone():
                    continue
                for mid, qty, st in rows:
                    m = conn.execute("SELECT name, price FROM Menu WHERE id = ?", (mid,)).fetchone()
                    if m:
                        conn.execute("INSERT INTO OrderItem (session_id, menu_id, name, unit_price, qty, status, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
                                     (sid, mid, m["name"], m["price"], qty, st))
        conn.commit()
ensure_order_table()
def order_summary(conn, session_id: str):
    items = [dict(r) for r in conn.execute("SELECT * FROM OrderItem WHERE session_id = ? ORDER BY id", (session_id,)).fetchall()]
    subtotal = sum(i["unit_price"] * i["qty"] for i in items)
    total = round(subtotal * (1 + TAX_RATE))
    return {"items": items, "subtotal": subtotal, "tax": total - subtotal, "total": total}
@app.get("/api/menu")
def get_menu():
    with get_db() as conn:
        rows = conn.execute("SELECT id, name, price FROM Menu WHERE availability = 1 AND stock = 1 AND price > 0 ORDER BY id").fetchall()
        return [dict(r) for r in rows]
@app.get("/api/sessions/{session_id}/orders")
def get_orders(session_id: str):
    with get_db() as conn:
        return order_summary(conn, session_id)
@app.post("/api/sessions/{session_id}/orders")
def add_order(session_id: str, req: OrderAddRequest):
    with get_db() as conn:
        m = conn.execute("SELECT name, price FROM Menu WHERE id = ?", (req.menu_id,)).fetchone()
        if not m:
            raise HTTPException(status_code=404, detail="menu not found")
        conn.execute("INSERT INTO OrderItem (session_id, menu_id, name, unit_price, qty, status, created_at) VALUES (?,?,?,?,?,'注文中',datetime('now'))",
                     (session_id, req.menu_id, m["name"], m["price"], max(req.qty, 1)))
        conn.commit()
        return order_summary(conn, session_id)
@app.put("/api/orders/{order_id}/serve")
def serve_order(order_id: int):
    with get_db() as conn:
        conn.execute("UPDATE OrderItem SET status = '提供済' WHERE id = ?", (order_id,))
        conn.commit()
    return {"status": "served"}
@app.delete("/api/orders/{order_id}")
def cancel_order(order_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM OrderItem WHERE id = ? AND status = '注文中'", (order_id,))
        conn.commit()
    return {"status": "cancelled"}
@app.get("/")
def serve_index():
    return FileResponse("index.html")
app.mount("/", StaticFiles(directory="."), name="static")
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)