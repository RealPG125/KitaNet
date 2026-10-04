import sqlite3
import os

DB_FILE = "restaurant.db"

def create_database():
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"既存の {DB_FILE} を初期化削除しました。")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")

    # ── 1. テーブル定義 ──
    # is_deleted カラム（0: 有効, 1: ごみ箱内）
    cursor.execute("""
    CREATE TABLE UserData (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        birthday DATE,
        region TEXT,
        join_datetime DATETIME,
        last_visit DATETIME,
        is_deleted BOOLEAN DEFAULT 0
    );
    """)

    cursor.execute("""
    CREATE TABLE TableSession (
        id VARCHAR(64) PRIMARY KEY,
        datetime DATETIME,
        table_id INTEGER,
        start_datetime DATETIME,
        end_datetime DATETIME,
        conversation_status BOOLEAN DEFAULT 0
    );
    """)

    cursor.execute("""
    CREATE TABLE TableSessionMembers (
        table_session_id VARCHAR(64),
        user_id VARCHAR(64),
        PRIMARY KEY (table_session_id, user_id),
        FOREIGN KEY (table_session_id) REFERENCES TableSession(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES UserData(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE Menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(64) NOT NULL,
        price INTEGER,
        availability BOOLEAN DEFAULT 1,
        stock BOOLEAN DEFAULT 1,
        seasonal BOOLEAN DEFAULT 0,
        description TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE UserMenuPreference (
        user_id VARCHAR(64),
        menu_id INTEGER,
        from_llm BOOLEAN DEFAULT 0,
        PRIMARY KEY (user_id, menu_id),
        FOREIGN KEY (user_id) REFERENCES UserData(id) ON DELETE CASCADE,
        FOREIGN KEY (menu_id) REFERENCES Menu(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE UserMemory (
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

    cursor.execute("""
    CREATE TABLE Allergy (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(32) NOT NULL UNIQUE
    );
    """)

    cursor.execute("""
    CREATE TABLE UserAllergy (
        user_id VARCHAR(64),
        allergy_id INTEGER,
        info_date DATE,
        PRIMARY KEY (user_id, allergy_id),
        FOREIGN KEY (user_id) REFERENCES UserData(id) ON DELETE CASCADE,
        FOREIGN KEY (allergy_id) REFERENCES Allergy(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE Ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(32) NOT NULL,
        allergy BOOLEAN DEFAULT 0,
        stock BOOLEAN DEFAULT 1,
        seasonal BOOLEAN DEFAULT 0,
        description TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE MenuIngredients (
        menu_id INTEGER,
        ingredient_id INTEGER,
        PRIMARY KEY (menu_id, ingredient_id),
        FOREIGN KEY (menu_id) REFERENCES Menu(id) ON DELETE CASCADE,
        FOREIGN KEY (ingredient_id) REFERENCES Ingredients(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IngredientsAllergy (
        ingredients_id INTEGER,
        allergy_id INTEGER,
        PRIMARY KEY (ingredients_id, allergy_id),
        FOREIGN KEY (ingredients_id) REFERENCES Ingredients(id) ON DELETE CASCADE,
        FOREIGN KEY (allergy_id) REFERENCES Allergy(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE SeasonData (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        season_name VARCHAR(32) NOT NULL,
        season_start_month INTEGER,
        season_start_day INTEGER,
        season_end_month INTEGER,
        season_end_day INTEGER
    );
    """)

    cursor.execute("""
    CREATE TABLE ConversationMemory (
        table_session_id VARCHAR(64) PRIMARY KEY,
        timestamp DATETIME,
        memory_topic VARCHAR(64),
        memory_content TEXT,
        FOREIGN KEY (table_session_id) REFERENCES TableSession(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE WorkerData (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        region TEXT,
        status TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE WorkerMemory (
        id VARCHAR(64) PRIMARY KEY,
        worker_id VARCHAR(64),
        timestamp DATETIME,
        last_referred DATETIME,
        memory_topic VARCHAR(64),
        memory_content TEXT,
        FOREIGN KEY (worker_id) REFERENCES WorkerData(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE OthersData (
        id VARCHAR(64) PRIMARY KEY,
        category TEXT,
        last_referred DATETIME,
        memory_content TEXT
    );
    """)

    # ── 2. マスタデータ投入 ──
    allergies = [
        (1, "卵"), (2, "乳製品"), (3, "エビ"), (4, "カニ"),
        (5, "小麦"), (6, "そば"), (7, "落花生"), (8, "大豆"),
        (9, "キウイ"), (10, "青魚")
    ]
    cursor.executemany("INSERT INTO Allergy (id, name) VALUES (?, ?);", allergies)

    menus = [
        (1, "オリーブ牛バーガー", 1200, 1, 1, 0, "地元産オリーブ牛100%使用の特製バーガー"),
        (2, "はちみつピザ", 1100, 1, 1, 0, "弓削島産百花蜜とゴルゴンゾーラのピザ"),
        (3, "鯛めし", 1300, 1, 1, 0, "瀬戸内海産の天然真鯛を使った伝統の土鍋ご飯"),
        (4, "刺身盛り合わせ", 1800, 1, 1, 0, "近海で獲れた旬の白身魚を中心とした鮮魚盛"),
        (5, "地酒 辛口", 800, 1, 1, 0, "料理を引き立てる愛媛の辛口純米酒"),
        (6, "レモンシャーベット", 450, 1, 1, 1, "岩城島産青いレモンを使用したさっぱりデザート")
    ]
    cursor.executemany("INSERT INTO Menu (id, name, price, availability, stock, seasonal, description) VALUES (?, ?, ?, ?, ?, ?, ?);", menus)

    # ── 3. 顧客データ投入 ──
    users = [
        ("u-0001", "山田 太郎", "1988-04-12", "愛媛県", "2026-09-22 12:02", "2026-10-04 11:30", 0),
        ("u-0002", "佐藤 美咲", "1995-08-25", "広島県", "2026-09-28 14:15", "2026-10-04 12:10", 0),
        ("u-0003", "田中 花子", "1992-06-30", "愛媛県", "2026-10-01 11:20", "2026-10-04 12:20", 0),
        ("u-0004", "田中 陸", "2018-09-12", "愛媛県", "2026-10-01 11:20", "2026-10-04 12:20", 0),
        ("u-0005", "高橋 健一", "1972-11-03", "東京都", "2026-10-02 18:00", "2026-10-04 13:00", 0),
        ("u-0006", "エミリー・スミス", "1993-12-05", "その他", "2026-10-04 12:25", "2026-10-04 12:25", 0),
        ("u-0007", "ジョン・ドー", "1990-03-15", "その他", "2026-10-04 12:25", "2026-10-04 12:25", 0),
        ("u-0008", "鈴木 一郎", "1980-02-14", "香川県", "2026-10-03 16:00", "2026-10-04 12:30", 0),
        ("u-0009", "中村 陽介", "1985-09-18", "岡山県", "2026-10-04 10:00", "2026-10-04 10:00", 0)
    ]
    cursor.executemany("INSERT INTO UserData (id, name, birthday, region, join_datetime, last_visit, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?);", users)

    user_allergies = [
        ("u-0001", 3, "2026-09-22"),
        ("u-0001", 4, "2026-09-22"),
        ("u-0002", 5, "2026-09-28"),
        ("u-0004", 1, "2026-10-01"),
        ("u-0004", 2, "2026-10-01"),
        ("u-0006", 7, "2026-10-04"),
        ("u-0008", 6, "2026-10-04")
    ]
    cursor.executemany("INSERT INTO UserAllergy (user_id, allergy_id, info_date) VALUES (?, ?, ?);", user_allergies)

    user_favs = [
        ("u-0001", 1, 1),
        ("u-0002", 3, 1),
        ("u-0003", 2, 0),
        ("u-0004", 6, 1),
        ("u-0005", 4, 0),
        ("u-0005", 5, 0),
        ("u-0008", 2, 1)
    ]
    cursor.executemany("INSERT INTO UserMenuPreference (user_id, menu_id, from_llm) VALUES (?, ?, ?);", user_favs)

    user_mems = [
        ("u-0001", "2026-10-04 11:30", 8, "趣味・話題", "釣りが趣味で毎週弓削港へ来ている。甲殻類アレルギーに注意。オリーブ牛バーガーがお気に入り。"),
        ("u-0002", "2026-10-04 12:10", 3, "食事の好み", "尾道からしまなみ海道をサイクリングで来訪。グルテンフリー希望のため鯛めしを中心にご案内。"),
        ("u-0003", "2026-10-04 12:20", 4, "利用傾向", "お子様連れで来店。ピザを好む。"),
        ("u-0004", "2026-10-04 12:20", 4, "アレルギー", "卵・乳アレルギーのためデザートはレモンシャーベットを注文。"),
        ("u-0005", "2026-10-04 13:00", 2, "事前予約", "接待・会食利用。静かな奥の席を希望。辛口の日本酒と地魚の刺身を好む。"),
        ("u-0006", "2026-10-04 12:25", 1, "インバウンド", "英語対応。ピーナッツアレルギーあり。"),
        ("u-0007", "2026-10-04 12:25", 1, "インバウンド", "柑橘系のドリンクを希望。"),
        ("u-0008", "2026-10-04 12:30", 2, "アレルギー注意", "重度のそばアレルギー。茹で釜の共用不可を徹底すること。"),
        ("u-0009", "2026-10-04 10:00", 1, "旅行", "フェリー待ちの合間にカフェ利用。")
    ]
    cursor.executemany("""
    INSERT INTO UserMemory (user_id, timestamp, visit_count, memory_topic, memory_content, from_llm)
    VALUES (?, ?, ?, ?, ?, 1);
    """, user_mems)

    # ── 4. 卓セッション ──
    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('session-0001', '2026-10-04 11:30', 1, '2026-10-04 11:30', '利用中', 1);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('session-0001', 'u-0001');")
    cursor.execute("""
    INSERT INTO ConversationMemory VALUES ('session-0001', '2026-10-04 11:45', '釣果自慢', '山田様が今朝の弓削港でのアジの釣果を嬉しそうに話され、AIスタッフが「次は佐島ですね！」と盛り上がった。');
    """)

    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('session-0002', '2026-10-04 12:15', 2, '2026-10-04 12:15', '利用中', 0);
    """)

    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('session-0003', '2026-10-04 12:10', 3, '2026-10-04 12:10', '利用中', 1);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('session-0003', 'u-0002');")
    cursor.execute("""
    INSERT INTO ConversationMemory VALUES ('session-0003', '2026-10-04 12:20', '観光ルート', 'しまなみ・ゆめしま海道の観光スポット（積善山の展望台）をご案内中。');
    """)

    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('session-0004', '2026-10-04 12:20', 5, '2026-10-04 12:20', '利用中', 0);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('session-0004', 'u-0003');")
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('session-0004', 'u-0004');")

    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('session-0005', '2026-10-04 13:00', 8, '2026-10-04 13:30', '予約中', 0);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('session-0005', 'u-0005');")

    conn.commit()
    conn.close()
    print("実務テスト用サンプルデータの初期化投入が完了しました。")

if __name__ == "__main__":
    create_database()