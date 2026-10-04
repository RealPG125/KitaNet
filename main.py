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

# 1. 顧客一覧の取得（ごみ箱内も is_deleted で判定して取得可能）
@app.get("/api/users")
def get_all_users():
    with get_db() as conn:
        users = conn.execute("SELECT * FROM UserData").fetchall()
        result = {}
        for u in users:
            uid = u["id"]
            algs = conn.execute("""
                SELECT a.name FROM UserAllergy ua
                JOIN Allergy a ON ua.allergy_id = a.id
                WHERE ua.user_id = ?
            """, (uid,)).fetchall()
            favs = conn.execute("""
                SELECT m.name FROM UserMenuPreference ump
                JOIN Menu m ON ump.menu_id = m.id
                WHERE ump.user_id = ?
            """, (uid,)).fetchall()
            mem = conn.execute("""
                SELECT memory_content FROM UserMemory
                WHERE user_id = ? ORDER BY id DESC LIMIT 1
            """, (uid,)).fetchone()
            sess = conn.execute("""
                SELECT ts.id as sId, ts.table_id as tId, ts.start_datetime as [in], ts.end_datetime as [out]
                FROM TableSessionMembers tsm
                JOIN TableSession ts ON tsm.table_session_id = ts.id
                WHERE tsm.user_id = ?
                ORDER BY ts.start_datetime DESC
            """, (uid,)).fetchall()

            result[uid] = {
                "id": uid,
                "name": u["name"],
                "region": u["region"] or "未登録",
                "count": u["visit_count"] if "visit_count" in u.keys() else 1,
                "last": u["last_visit"] or "-",
                "is_deleted": bool(u["is_deleted"]) if "is_deleted" in u.keys() else False,
                "allergies": [a["name"] for a in algs],
                "favs": [f["name"] for f in favs],
                "hint": mem["memory_content"] if mem else "",
                "sessions": [dict(s) for s in sess]
            }
        return result

# 2. フロア全体の稼働状況
@app.get("/api/floor-status")
def get_floor_status():
    with get_db() as conn:
        active_sessions = conn.execute("""
            SELECT * FROM TableSession 
            WHERE end_datetime IS NULL OR end_datetime = '利用中' OR end_datetime = '予約中'
        """).fetchall()

        tables_data = {}
        for i in range(1, 11):
            tables_data[i] = {
                "sessionId": None,
                "type": "empty",
                "stayTime": None,
                "guestCount": 0,
                "userIds": [],
                "hasSpoken": False,
                "summary": ""
            }

        for s in active_sessions:
            t_id = s["table_id"]
            if t_id not in tables_data:
                continue

            members = conn.execute("""
                SELECT user_id FROM TableSessionMembers WHERE table_session_id = ?
            """, (s["id"],)).fetchall()
            u_ids = [m["user_id"] for m in members]

            conv = conn.execute("""
                SELECT memory_content FROM ConversationMemory 
                WHERE table_session_id = ? ORDER BY timestamp DESC LIMIT 1
            """, (s["id"],)).fetchone()
            summary_text = conv["memory_content"] if conv else ""

            is_reserved = (s["end_datetime"] == "予約中")
            is_speaking = bool(s["conversation_status"])

            s_type = "reserved" if is_reserved else ("speaking" if is_speaking else "active")

            tables_data[t_id] = {
                "sessionId": s["id"],
                "type": s_type,
                "stayTime": "利用中" if not is_reserved else None,
                "reserveTime": s["start_datetime"] if is_reserved else None,
                "guestCount": max(len(u_ids), 1),
                "userIds": u_ids,
                "hasSpoken": bool(summary_text) or is_speaking,
                "summary": summary_text
            }

        return tables_data

# 3. 新規受付
@app.post("/api/register-group")
def register_group(req: GroupRegisterRequest):
    created_user_ids = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_date = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        for idx, u in enumerate(req.users):
            if u.user_id:
                uid = u.user_id
                conn.execute("""
                    UPDATE UserData 
                    SET last_visit = ?, region = COALESCE(NULLIF(?, ''), region), is_deleted = 0
                    WHERE id = ?
                """, (now_str, u.region, uid))
            else:
                uid = f"u-{int(time.time()*1000)}-{idx+1}"
                conn.execute("""
                    INSERT INTO UserData (id, name, region, join_datetime, last_visit, is_deleted)
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (uid, u.name, u.region, now_str, now_str))

                for alg_name in u.allergies:
                    row = conn.execute("SELECT id FROM Allergy WHERE name = ?", (alg_name,)).fetchone()
                    if row:
                        alg_id = row["id"]
                    else:
                        cur = conn.execute("INSERT INTO Allergy (name) VALUES (?)", (alg_name,))
                        alg_id = cur.lastrowid
                    conn.execute("INSERT OR IGNORE INTO UserAllergy (user_id, allergy_id, info_date) VALUES (?, ?, ?)",
                                 (uid, alg_id, today_date))

                if u.hint:
                    conn.execute("""
                        INSERT INTO UserMemory (user_id, timestamp, memory_topic, memory_content)
                        VALUES (?, ?, '新規受付', ?)
                    """, (uid, now_str, u.hint))

            created_user_ids.append(uid)
        conn.commit()

    return {"status": "success", "user_ids": created_user_ids}

# 4. カルテ更新
@app.put("/api/users/{user_id}")
def update_user_profile(user_id: str, req: UserUpdateRequest):
    with get_db() as conn:
        conn.execute("UPDATE UserData SET name = ?, region = ? WHERE id = ?", (req.name, req.region, user_id))

        conn.execute("DELETE FROM UserAllergy WHERE user_id = ?", (user_id,))
        for alg_name in req.allergies:
            row = conn.execute("SELECT id FROM Allergy WHERE name = ?", (alg_name,)).fetchone()
            if row:
                alg_id = row["id"]
            else:
                cur = conn.execute("INSERT INTO Allergy (name) VALUES (?)", (alg_name,))
                alg_id = cur.lastrowid
            conn.execute("INSERT OR IGNORE INTO UserAllergy (user_id, allergy_id, info_date) VALUES (?, ?, date('now'))",
                         (user_id, alg_id))

        conn.execute("DELETE FROM UserMenuPreference WHERE user_id = ?", (user_id,))
        for fav_name in req.favs:
            row = conn.execute("SELECT id FROM Menu WHERE name = ?", (fav_name,)).fetchone()
            if row:
                menu_id = row["id"]
            else:
                cur = conn.execute("INSERT INTO Menu (name, price) VALUES (?, 1000)", (fav_name,))
                menu_id = cur.lastrowid
            conn.execute("INSERT OR IGNORE INTO UserMenuPreference (user_id, menu_id) VALUES (?, ?)",
                         (user_id, menu_id))

        if req.hint:
            conn.execute("""
                INSERT INTO UserMemory (user_id, timestamp, memory_topic, memory_content)
                VALUES (?, datetime('now'), '接客カルテ更新', ?)
            """, (user_id, req.hint))

        conn.commit()
    return {"status": "updated"}

# 5. ごみ箱に入れる（論理削除）
@app.put("/api/users/{user_id}/trash")
def trash_user(user_id: str):
    with get_db() as conn:
        conn.execute("UPDATE UserData SET is_deleted = 1 WHERE id = ?", (user_id,))
        conn.commit()
    return {"status": "trashed", "user_id": user_id}

# 6. ごみ箱から復元する
@app.put("/api/users/{user_id}/restore")
def restore_user(user_id: str):
    with get_db() as conn:
        conn.execute("UPDATE UserData SET is_deleted = 0 WHERE id = ?", (user_id,))
        conn.commit()
    return {"status": "restored", "user_id": user_id}

# 7. 本当の削除（物理削除：DBから完全消去）
@app.delete("/api/users/{user_id}/purge")
def purge_user(user_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM UserData WHERE id = ?", (user_id,))
        conn.commit()
    return {"status": "purged", "user_id": user_id}

# 8. 配席セッション作成
@app.post("/api/sessions/assign")
def assign_session(req: AssignRequest):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_db() as conn:
        conn.execute("""
            INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
            VALUES (?, ?, ?, ?, '利用中', 0)
        """, (req.session_id, now, req.table_id, now))
        
        for uid in req.user_ids:
            conn.execute("INSERT INTO TableSessionMembers (table_session_id, user_id) VALUES (?, ?)", (req.session_id, uid))
            conn.execute("UPDATE UserData SET last_visit = ? WHERE id = ?", (now, uid))
        conn.commit()
    return {"status": "assigned"}

# 9. 会計・退店処理
@app.post("/api/sessions/{session_id}/checkout")
def checkout_session(session_id: str):
    now = datetime.now().strftime("%H:%M 退店")
    with get_db() as conn:
        conn.execute("UPDATE TableSession SET end_datetime = ? WHERE id = ?", (now, session_id))
        conn.commit()
    return {"status": "checked_out"}

# ── 静的配信 ──
@app.get("/")
def serve_index():
    return FileResponse("index.html")

app.mount("/", StaticFiles(directory="."), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)