import sqlite3
import os

DB_FILE = "restaurant.db"

def create_database():
    # 既存のDBを削除して再作成する場合はコメントアウトを外してください
    # if os.path.exists(DB_FILE):
    #     os.remove(DB_FILE)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 外部キー制約を有効化
    cursor.execute("PRAGMA foreign_keys = ON;")

    # ── 1. 顧客情報 (UserData) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS UserData (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        birthday DATE,
        region TEXT,
        join_datetime DATETIME,
        last_visit DATETIME
    );
    """)

    # ── 2. 卓セッション (TableSession) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TableSession (
        id VARCHAR(64) PRIMARY KEY,
        datetime DATETIME,
        table_id INTEGER,
        start_datetime DATETIME,
        end_datetime DATETIME,
        conversation_status BOOLEAN DEFAULT 0
    );
    """)

    # ── 3. セッション所属顧客 (TableSessionMembers) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TableSessionMembers (
        table_session_id VARCHAR(64),
        user_id VARCHAR(64),
        PRIMARY KEY (table_session_id, user_id),
        FOREIGN KEY (table_session_id) REFERENCES TableSession(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES UserData(id) ON DELETE CASCADE
    );
    """)

    # ── 4. メニューマスタ (Menu) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(64) NOT NULL,
        price INTEGER,
        availability BOOLEAN DEFAULT 1,
        stock BOOLEAN DEFAULT 1,
        seasonal BOOLEAN DEFAULT 0,
        description TEXT
    );
    """)

    # ── 5. 顧客お気に入りメニュー (UserMenuPreference) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS UserMenuPreference (
        user_id VARCHAR(64),
        menu_id INTEGER,
        from_llm BOOLEAN DEFAULT 0,
        PRIMARY KEY (user_id, menu_id),
        FOREIGN KEY (user_id) REFERENCES UserData(id) ON DELETE CASCADE,
        FOREIGN KEY (menu_id) REFERENCES Menu(id) ON DELETE CASCADE
    );
    """)

    # ── 6. 顧客メモ (UserMemory) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS UserMemory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id VARCHAR(64),
        table_session_id VARCHAR(64),
        timestamp DATETIME,
        expiration_datetime DATETIME,
        last_update DATETIME,
        visit_count INTEGER DEFAULT 1,
        memory_topic VARCHAR(64),
        memory_content TEXT,
        from_llm BOOLEAN DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES UserData(id) ON DELETE CASCADE,
        FOREIGN KEY (table_session_id) REFERENCES TableSession(id) ON DELETE SET NULL
    );
    """)

    # ── 7. アレルギーマスタ (Allergy) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Allergy (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(32) NOT NULL UNIQUE
    );
    """)

    # ── 8. 顧客アレルギー (UserAllergy) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS UserAllergy (
        user_id VARCHAR(64),
        allergy_id INTEGER,
        info_date DATE,
        PRIMARY KEY (user_id, allergy_id),
        FOREIGN KEY (user_id) REFERENCES UserData(id) ON DELETE CASCADE,
        FOREIGN KEY (allergy_id) REFERENCES Allergy(id) ON DELETE CASCADE
    );
    """)

    # ── 9. 食材・仕込み原料 (Ingredients) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(32) NOT NULL,
        allergy BOOLEAN DEFAULT 0,
        stock BOOLEAN DEFAULT 1,
        seasonal BOOLEAN DEFAULT 0,
        description TEXT
    );
    """)

    # ── 10. メニューと原材料の紐付け (MenuIngredients) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS MenuIngredients (
        menu_id INTEGER,
        ingredient_id INTEGER,
        PRIMARY KEY (menu_id, ingredient_id),
        FOREIGN KEY (menu_id) REFERENCES Menu(id) ON DELETE CASCADE,
        FOREIGN KEY (ingredient_id) REFERENCES Ingredients(id) ON DELETE CASCADE
    );
    """)

    # ── 11. 食材に含まれるアレルゲン (IngredientsAllergy) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS IngredientsAllergy (
        ingredients_id INTEGER,
        allergy_id INTEGER,
        PRIMARY KEY (ingredients_id, allergy_id),
        FOREIGN KEY (ingredients_id) REFERENCES Ingredients(id) ON DELETE CASCADE,
        FOREIGN KEY (allergy_id) REFERENCES Allergy(id) ON DELETE CASCADE
    );
    """)

    # ── 12. 旬・季節情報 (SeasonData) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS SeasonData (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        season_name VARCHAR(32) NOT NULL,
        season_start_month INTEGER,
        season_start_day INTEGER,
        season_end_month INTEGER,
        season_end_day INTEGER
    );
    """)

    # ── 13. セッション対話ログ・要約 (ConversationMemory) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ConversationMemory (
        table_session_id VARCHAR(64) PRIMARY KEY,
        timestamp DATETIME,
        memory_topic VARCHAR(64),
        memory_content TEXT,
        FOREIGN KEY (table_session_id) REFERENCES TableSession(id) ON DELETE CASCADE
    );
    """)

    # ── 14. 店員情報 (WorkerData) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS WorkerData (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        region TEXT,
        status TEXT
    );
    """)

    # ── 15. 店員メモ (WorkerMemory) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS WorkerMemory (
        id VARCHAR(64) PRIMARY KEY,
        worker_id VARCHAR(64),
        timestamp DATETIME,
        last_referred DATETIME,
        memory_topic VARCHAR(64),
        memory_content TEXT,
        FOREIGN KEY (worker_id) REFERENCES WorkerData(id) ON DELETE CASCADE
    );
    """)

    # ── 16. 地域イベント・その他データ (OthersData) ──
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS OthersData (
        id VARCHAR(64) PRIMARY KEY,
        category TEXT,
        last_referred DATETIME,
        memory_content TEXT
    );
    """)

    # ════════════════════════════════════════════════
    # 初期マスタデータ & ER図のサンプルデータを投入
    # ════════════════════════════════════════════════

    # アレルゲンマスタ（画像内の allergy_id: 3 = エビ を含む）
    allergies = [
        (1, "卵"),
        (2, "乳製品"),
        (3, "エビ"),      # 図中の allergy_id: 3
        (4, "カニ"),
        (5, "小麦"),
        (6, "そば"),
        (7, "落花生"),
        (8, "大豆")
    ]
    cursor.executemany("INSERT OR IGNORE INTO Allergy (id, name) VALUES (?, ?);", allergies)

    # メニューマスタ（オリーブ牛バーガー、はちみつピザ、鯛めし等）
    menus = [
        (1, "オリーブ牛バーガー", 1200, 1, 1, 0, "地元産オリーブ牛100%使用の特製バーガー"),
        (2, "はちみつピザ", 1100, 1, 1, 0, "弓削島産百花蜜とゴルゴンゾーラのピザ"),
        (3, "鯛めし", 1300, 1, 1, 0, "瀬戸内海産の天然真鯛を使った伝統の土鍋ご飯"),
        (4, "刺身盛り合わせ", 1800, 1, 1, 0, "近海で獲れた旬の白身魚を中心とした鮮魚盛"),
        (5, "地酒 辛口", 800, 1, 1, 0, "料理を引き立てる愛媛の辛口純米酒")
    ]
    cursor.executemany("INSERT OR IGNORE INTO Menu (id, name, price, availability, stock, seasonal, description) VALUES (?, ?, ?, ?, ?, ?, ?);", menus)

    # ER図サンプル1: 山田 太郎 様 (9月22日に登録、愛媛県上島町、エビ・カニアレルギー)
    cursor.execute("""
    INSERT OR IGNORE INTO UserData (id, name, birthday, region, join_datetime, last_visit)
    VALUES ('u-0001', '山田 太郎', '1988-04-12', '愛媛県上島町', '2026-09-22 12:02', '2026-09-22 12:02');
    """)

    # アレルギー登録（エビ: 3, カニ: 4）
    cursor.execute("INSERT OR IGNORE INTO UserAllergy (user_id, allergy_id, info_date) VALUES ('u-0001', 3, '2026-09-22');")
    cursor.execute("INSERT OR IGNORE INTO UserAllergy (user_id, allergy_id, info_date) VALUES ('u-0001', 4, '2026-09-22');")

    # お気に入りメニュー（オリーブ牛バーガー: 1）
    cursor.execute("INSERT OR IGNORE INTO UserMenuPreference (user_id, menu_id, from_llm) VALUES ('u-0001', 1, 1);")

    # ER図サンプル2: テーブルセッション 0002 (テーブル4番 または 1番で開始)
    cursor.execute("""
    INSERT OR IGNORE INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('session-0002', '2026-09-22 13:00', 1, '2026-09-22 13:00', '利用中', 1);
    """)
    cursor.execute("INSERT OR IGNORE INTO TableSessionMembers (table_session_id, user_id) VALUES ('session-0002', 'u-0001');")

    # UserMemory (釣りが趣味で毎週弓削港で釣りしている)
    cursor.execute("""
    INSERT OR IGNORE INTO UserMemory (user_id, table_session_id, timestamp, expiration_datetime, last_update, visit_count, memory_topic, memory_content, from_llm)
    VALUES ('u-0001', 'session-0002', '2026-09-22 13:10', '2027-09-22', '2026-09-22 13:10', 8, '釣り・アウトドア', '釣りが趣味で毎週弓削島で釣りしている。オリーブ牛バーガーが大好物。', 1);
    """)

    # ConversationMemory (セッション対話ログ)
    cursor.execute("""
    INSERT OR IGNORE INTO ConversationMemory (table_session_id, timestamp, memory_topic, memory_content)
    VALUES ('session-0002', '2026-09-22 13:15', '釣り談義', '山田様が今朝の弓削港での釣果を自慢され、AIが『次は佐島ですね！』と返答。');
    """)

    conn.commit()
    conn.close()
    print(" データベースファイル (restaurant.db) の作成および初期化が完了しました！")

if __name__ == "__main__":
    create_database()