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

    # ── 2. マスタデータ投入（アレルゲン重要度順） ──
    allergies = [
        (1, "卵"), (2, "乳"), (3, "小麦"), (4, "くるみ"), (5, "落花生（ピーナッツ）"),
        (6, "そば"), (7, "えび"), (8, "かに"), (9, "カシューナッツ"),
        (10, "大豆"), (11, "キウイフルーツ"), (12, "バナナ"), (13, "もも"), (14, "りんご"),
        (15, "オレンジ"), (16, "アーモンド"), (17, "ピスタチオ"), (18, "マカダミアナッツ"),
        (19, "さけ"), (20, "さば"), (21, "いくら"), (22, "いか"), (23, "あわび"),
        (24, "ごま"), (25, "牛肉"), (26, "豚肉"), (27, "鶏肉"), (28, "やまいも"), (29, "ゼラチン")
    ]
    cursor.executemany("INSERT INTO Allergy (id, name) VALUES (?, ?);", allergies)

    menus = [
        (1, "オリーブ牛バーガー", 1200, 1, 1, 0, "地元産オリーブ牛100%使用の特製バーガー"),
        (2, "はちみつピザ", 1100, 1, 1, 0, "弓削島産百花蜜とゴルゴンゾーラのピザ"),
        (3, "鯛めし土鍋ご飯", 1300, 1, 1, 0, "瀬戸内海産の天然真鯛を使った伝統の土鍋ご飯"),
        (4, "地魚刺身盛り合わせ", 1800, 1, 1, 0, "近海で獲れた旬の白身魚を中心とした鮮魚盛"),
        (5, "地酒 辛口純米", 800, 1, 1, 0, "料理を引き立てる愛媛の辛口純米酒"),
        (6, "青いレモンシャーベット", 450, 1, 1, 1, "岩城島産青いレモンを使用したさっぱりデザート"),
        (7, "タコの唐揚げ", 750, 1, 1, 0, "瀬戸内の地ダコをカラッと揚げたおつまみ"),
        (8, "しまなみ柑橘エール", 900, 1, 1, 0, "柑橘の香りが爽やかなクラフトビール")
    ]
    cursor.executemany("INSERT INTO Menu (id, name, price, availability, stock, seasonal, description) VALUES (?, ?, ?, ?, ?, ?, ?);", menus)

    # ── 3. 賑やかな顧客データ（16名） ──
    users = [
        ("u-0001", "山田 太郎", "1988-04-12", "愛媛県", "2026-09-22 12:00", "2026-10-16 19:10", 0),
        ("u-0002", "佐藤 美咲", "1995-08-25", "広島県", "2026-09-28 14:00", "2026-10-16 19:25", 0),
        ("u-0003", "田中 花子", "1992-06-30", "愛媛県", "2026-10-01 11:20", "2026-10-16 19:15", 0),
        ("u-0004", "田中 陸", "2018-09-12", "愛媛県", "2026-10-01 11:20", "2026-10-16 19:15", 0),
        ("u-0005", "高橋 健一", "1972-11-03", "東京都", "2026-10-02 18:00", "2026-10-16 20:30", 0),
        ("u-0006", "エミリー・スミス", "1993-12-05", "その他", "2026-10-16 19:40", "2026-10-16 19:40", 0),
        ("u-0007", "ジョン・ドー", "1990-03-15", "その他", "2026-10-16 19:40", "2026-10-16 19:40", 0),
        ("u-0008", "鈴木 一郎", "1980-02-14", "香川県", "2026-10-03 16:00", "2026-10-16 19:30", 0),
        ("u-0009", "中村 陽介", "1985-09-18", "岡山県", "2026-10-04 10:00", "2026-10-16 18:50", 0),
        ("u-0010", "小林 真央", "1998-05-20", "愛媛県", "2026-10-16 19:35", "2026-10-16 19:35", 0),
        ("u-0011", "ワン・ウェイ (王偉)", "1994-07-11", "その他", "2026-10-16 19:50", "2026-10-16 19:50", 0),
        ("u-0012", "リー・ナ (李娜)", "1996-01-28", "その他", "2026-10-16 19:50", "2026-10-16 19:50", 0),
        ("u-0013", "渡辺 大輔", "1983-12-01", "愛媛県", "2026-10-10 18:30", "2026-10-16 19:00", 0),
        ("u-0014", "木村 さくら", "2001-03-14", "大阪府", "2026-10-16 19:55", "2026-10-16 19:55", 0),
        ("u-0015", "マルコ・ロッシ", "1989-11-23", "その他", "2026-10-16 20:00", "2026-10-16 20:00", 0),
        ("u-0016", "井上 拓海", "1991-09-05", "福岡県", "2026-10-16 20:10", "2026-10-16 20:10", 0)
    ]
    cursor.executemany("INSERT INTO UserData (id, name, birthday, region, join_datetime, last_visit, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?);", users)

    # 顧客アレルゲン（えび、かに、そば、ピーナッツ、乳、小麦などバラバラに）
    user_allergies = [
        ("u-0001", 7, "2026-09-22"),  # えび
        ("u-0001", 8, "2026-09-22"),  # かに
        ("u-0002", 3, "2026-09-28"),  # 小麦 (グルテンフリー)
        ("u-0004", 1, "2026-10-01"),  # 卵
        ("u-0004", 2, "2026-10-01"),  # 乳
        ("u-0006", 5, "2026-10-16"),  # 落花生（ピーナッツ）
        ("u-0008", 6, "2026-10-03"),  # そば (重度)
        ("u-0011", 7, "2026-10-16"),  # えび
        ("u-0014", 11, "2026-10-16"), # キウイフルーツ
        ("u-0015", 24, "2026-10-16"), # ごま
    ]
    cursor.executemany("INSERT INTO UserAllergy (user_id, allergy_id, info_date) VALUES (?, ?, ?);", user_allergies)

    # 好物
    user_favs = [
        ("u-0001", 1, 1), ("u-0001", 4, 1),
        ("u-0002", 3, 1),
        ("u-0003", 2, 0),
        ("u-0004", 6, 1),
        ("u-0005", 4, 0), ("u-0005", 5, 0),
        ("u-0007", 8, 1),
        ("u-0008", 2, 1), ("u-0008", 7, 1),
        ("u-0009", 5, 0),
        ("u-0010", 6, 1),
        ("u-0013", 4, 1), ("u-0013", 5, 1),
    ]
    cursor.executemany("INSERT INTO UserMenuPreference (user_id, menu_id, from_llm) VALUES (?, ?, ?);", user_favs)

    # 顧客カルテ・メモ
    user_mems = [
        ("u-0001", "2026-10-16 19:10", 12, "常連・話題", "毎週弓削港で釣り。甲殻類NG。本日は太刀魚の話題で盛り上がっている。"),
        ("u-0002", "2026-10-16 19:25", 4, "観光・食事", "尾道からクロスバイクで来訪。グルテンフリー希望のため鯛めしをおすすめ。"),
        ("u-0003", "2026-10-16 19:15", 5, "家族利用", "お子様（陸くん）連れ。ピザをカットしてシェア。"),
        ("u-0004", "2026-10-16 19:15", 5, "アレルギー", "卵・乳アレルギー。レモンシャーベットを気に入っている。"),
        ("u-0005", "2026-10-16 20:30", 3, "接待予約", "奥の静かな席を希望。愛媛の辛口地酒と鮮魚刺身を事前オーダー。"),
        ("u-0006", "2026-10-16 19:40", 1, "インバウンド", "米国より。英語対応希望。ピーナッツ完全不使用を確認。"),
        ("u-0007", "2026-10-16 19:40", 1, "ドリンク", "地元の柑橘クラフトビールがお気に入り。"),
        ("u-0008", "2026-10-16 19:30", 3, "厳重注意", "重度のそばアレルギー。調理器具や茹で釜の分離を徹底。"),
        ("u-0009", "2026-10-16 18:50", 2, "出張", "フェリー最終便までの時間調整。お会計準備中。"),
        ("u-0010", "2026-10-16 19:35", 1, "地元若者", "スイーツ巡り。レモンシャーベットをご注文。"),
        ("u-0011", "2026-10-16 19:50", 1, "インバウンド", "中国・上海より観光。えびアレルギー。中国語メニュー対応。"),
        ("u-0012", "2026-10-16 19:50", 1, "観光", "瀬戸内の絶景スポット（積善山）の行き方を質問中。"),
        ("u-0013", "2026-10-16 19:00", 8, "地元役場", "刺身と日本酒。いつもカウンター寄りの席。"),
        ("u-0014", "2026-10-16 19:55", 1, "女子旅", "キウイアレルギーあり。デザート選択時要確認。"),
        ("u-0015", "2026-10-16 20:00", 1, "サイクリスト", "イタリアより。ごまアレルギー。ピザの生地について質問あり。"),
        ("u-0016", "2026-10-16 20:10", 1, "一人旅", "地魚と地酒のペアリングをAIと相談中。")
    ]
    cursor.executemany("""
    INSERT INTO UserMemory (user_id, timestamp, visit_count, memory_topic, memory_content, from_llm)
    VALUES (?, ?, ?, ?, ?, 1);
    """, user_mems)

    # ── 4. 卓セッション（全10卓中7卓が稼働中！） ──
    # 1番卓：利用中 ＆ AI対話中 🎙️（山田様・常連釣り自慢）
    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('sess-001', '2026-10-16 19:10', 1, '19:10 入店 (滞在40分)', '利用中', 1);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-001', 'u-0001');")
    cursor.execute("""
    INSERT INTO ConversationMemory VALUES ('sess-001', '2026-10-16 19:42', '釣果自慢と酒の肴', 
    '山田様「今朝弓削港で40cmの太刀魚が上がったよ！」→ AI「お見事です！その白身の脂なら、今夜は辛口純米酒とタコの唐揚げが合いますよ」と提案しご注文成立。');
    """)

    # 2番卓：利用中（小林様・カフェ利用）
    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('sess-002', '2026-10-16 19:35', 2, '19:35 入店 (滞在15分)', '利用中', 0);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-002', 'u-0010');")

    # 3番卓：利用中 ＆ AI対話中 🎙️（佐藤様・サイクリング案内）
    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('sess-003', '2026-10-16 19:25', 3, '19:25 入店 (滞在25分)', '利用中', 1);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-003', 'u-0002');")
    cursor.execute("""
    INSERT INTO ConversationMemory VALUES ('sess-003', '2026-10-16 19:40', 'ゆめしま海道案内', 
    '佐藤様「明日尾道へ戻る前に寄れる絶景スポットは？」→ AI「積善山（せきぜんざん）の展望台がおすすめです！360度パノラマで芸予諸島が見渡せます」とルートを案内。');
    """)

    # 4番卓：会計中 🧾（中村様・フェリー待ち）
    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('sess-004', '2026-10-16 18:50', 4, '18:50 入店 (滞在60分)', '会計中', 0);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-004', 'u-0009');")
    cursor.execute("""
    INSERT INTO ConversationMemory VALUES ('sess-004', '2026-10-16 19:45', 'お会計対応', 
    '20:10発の今治行き最終フェリーに合わせてお会計を要請。帳場へ通知済み。');
    """)

    # 5番卓：利用中 ⚠️アレルギー注意（田中様ファミリー 2名）
    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('sess-005', '2026-10-16 19:15', 5, '19:15 入店 (滞在35分)', '利用中', 0);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-005', 'u-0003');")
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-005', 'u-0004');")
    cursor.execute("""
    INSERT INTO ConversationMemory VALUES ('sess-005', '2026-10-16 19:20', 'キッズアレルギー対応', 
    '陸くん（卵・乳アレルギー）。ピザの代わりにアレルゲンフリーの鯛めしとレモンシャーベットを配膳完了。');
    """)

    # 6番卓：利用中 ＆ AI対話中 🎙️（インバウンド英語対応 2名）
    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('sess-006', '2026-10-16 19:40', 6, '19:40 入店 (滞在10分)', '利用中', 1);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-006', 'u-0006');")
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-006', 'u-0007');")
    cursor.execute("""
    INSERT INTO ConversationMemory VALUES ('sess-006', '2026-10-16 19:48', 'English Pairing', 
    'Emily & John: AI explained local citrus craft beer and olive beef burger in English. Peanut allergy cross-check completed with kitchen.');
    """)

    # 8番卓：予約中 📅（高橋様・接待20:30〜）
    cursor.execute("""
    INSERT INTO TableSession (id, datetime, table_id, start_datetime, end_datetime, conversation_status)
    VALUES ('sess-008', '2026-10-16 20:30', 8, '20:30 予約', '予約中', 0);
    """)
    cursor.execute("INSERT INTO TableSessionMembers VALUES ('sess-008', 'u-0005');")

    # 7番、9番、10番卓は空席（即時案内可能）

    conn.commit()
    conn.close()
    print("✨ 店舗フロアが満席近くの賑やかな初期状態にセットアップされました！")

if __name__ == "__main__":
    create_database()