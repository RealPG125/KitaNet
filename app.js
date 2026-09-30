/* ═══════════════════════════════════════════
   データストア (ER図準拠・スリム化)[cite: 1]
═══════════════════════════════════════════ */
let allergenMaster = ["エビ", "カニ", "小麦", "そば", "卵", "乳製品", "落花生", "大豆"];

const DB = {
  "u-001": {
    id: "u-001",
    name: "山田 太郎",
    region: "愛媛県上島町",
    last: "2026-09-22 12:02",
    count: 8,
    allergies: ["エビ", "カニ"], // UserAllergy[cite: 1]
    favs: ["オリーブ牛バーガー", "地酒 辛口"], // UserMenuPreference[cite: 1]
    hint: "【釣り・地元】先週末も弓削港で黒鯛を釣り上げたそう。「次は佐島側の岩場に行きたい」と話していました。オリーブ牛バーガーが好物。", // UserMemory[cite: 1]
    sessions: [
      { sId: "0001", tId: 1, in: "2026-09-08 18:00", out: "2026-09-08 20:15" },
      { sId: "0002", tId: 1, in: "2026-09-22 12:02", out: "利用中" }
    ]
  },
  "u-002": {
    id: "u-002",
    name: "佐藤 次郎",
    region: "広島県因島",
    last: "2026-09-22 12:02",
    count: 3,
    allergies: ["小麦"],
    favs: ["若鶏の唐揚げ"],
    hint: "【サイクリング】因島からフェリーで来島。クロスバイクでゆめしま海道を走るのが趣味。本日のおすすめ焼き魚を提案推奨。",
    sessions: [
      { sId: "0002", tId: 1, in: "2026-09-22 12:02", out: "利用中" }
    ]
  },
  "u-003": {
    id: "u-003",
    name: "鈴木 一郎",
    region: "愛媛県松山市",
    last: "2026-09-22 12:02",
    count: 1,
    allergies: [],
    favs: ["はちみつピザ"],
    hint: "【学生時代の思い出】弓削商船の機関科OB。今年の商船祭の展示や部活の後輩の話題で盛り上がりました。",
    sessions: [
      { sId: "0002", tId: 1, in: "2026-09-22 12:02", out: "利用中" }
    ]
  },
  "u-004": {
    id: "u-004",
    name: "木村 達也",
    region: "東京都",
    last: "2026-09-22 12:10",
    count: 4,
    allergies: ["そば", "落花生"],
    favs: ["海鮮丼"],
    hint: "【カメラ・出張】東京からの出張で来島。夕暮れ時の島の風景写真を撮るのが楽しみ。そば・落花生の器具共用に注意。",
    sessions: [
      { sId: "0021", tId: 5, in: "2026-09-22 12:10", out: "利用中" }
    ]
  },
  "u-005": {
    id: "u-005",
    name: "田中 健一",
    region: "愛媛県今治市",
    last: "2026-08-30",
    count: 12,
    allergies: [],
    favs: ["刺身盛り合わせ"],
    hint: "【ドライブ・温泉】今治から友人達と車で来島。食後はフェスパの温浴施設に立ち寄る計画。13:00〜4名で事前予約中。",
    sessions: []
  },
  "u-wait-1": {
    id: "u-wait-1",
    name: "渡辺 航平",
    region: "愛媛県上島町",
    last: "2026-07-15",
    count: 5,
    allergies: ["卵"],
    favs: ["鯛めし"],
    hint: "【家庭菜園・柑橘】近所でレモンやみかんを栽培されている常連様。卵アレルギーに注意。",
    sessions: []
  },
  "u-wait-1-guest": {
    id: "u-wait-1-guest",
    name: "渡辺様のお連れ様",
    region: "愛媛県上島町",
    last: "2026-09-28",
    count: 1,
    allergies: [],
    favs: [],
    hint: "【同席者】渡辺様のご友人。",
    sessions: []
  },
  "u-wait-other-1": {
    id: "u-wait-other-1",
    name: "観光客A",
    region: "未登録",
    last: "2026-09-28",
    count: 1,
    allergies: [],
    favs: [],
    hint: "【初来店】しまなみサイクリングで来島されたグループの代表者様。",
    sessions: []
  },
  "u-wait-other-2": {
    id: "u-wait-other-2",
    name: "観光客B",
    region: "未登録",
    last: "2026-09-28",
    count: 1,
    allergies: ["乳製品"],
    favs: [],
    hint: "【初来店】乳製品アレルギー申告あり。",
    sessions: []
  },
  "u-seated-9": {
    id: "u-seated-9",
    name: "一般来店の2名様",
    region: "未登録",
    last: "2026-09-28 15:30",
    count: 1,
    allergies: [],
    favs: [],
    hint: "ふらっと入店された2名様。Wi-Fiと本日限定デザートについて質問中。",
    sessions: [{ sId: "0091", tId: 9, in: "2026-09-28 15:30", out: "利用中" }]
  }
};

let waitingQueue = [
  { queueId: "q-1", userIds: ["u-wait-1", "u-wait-1-guest"], guestsCount: 2 },
  { queueId: "q-2", userIds: ["u-wait-other-1", "u-wait-other-2"], guestsCount: 2 }
];

const TABLES = {
  1:  { type: "active",   stayTime: "25分", guestCount: 3, userIds: ["u-001", "u-002", "u-003"], hasSpoken: true, summary: "山田様が今朝の弓削港での釣果（黒鯛30cm）を話され、お連れの佐藤様（小麦アレルギー）向けに本日のおすすめ焼き魚を案内しました。" },
  2:  { type: "active",   stayTime: "10分", guestCount: 2, userIds: [], hasSpoken: false, summary: "" },
  3:  { type: "speaking", stayTime: "15分", guestCount: 4, userIds: [], hasSpoken: true, summary: "観光で来島された4名様。島内で見晴らしの良い場所を相談され、積善山展望台をご案内中です。" },
  4:  { type: "reserved", reserveTime: "13:00", guestCount: 4, userIds: ["u-005"], hasSpoken: false, summary: "事前予約席（田中健一様・4名）。" },
  5:  { type: "active",   stayTime: "18分", guestCount: 1, userIds: ["u-004"], hasSpoken: true, summary: "木村様が夕暮れの弓削大橋を撮影したいとお話し中。そば・落花生アレルギーの器具交差防止を確認済みです。" },
  6:  { type: "active",   stayTime: "50分", guestCount: 4, userIds: [], hasSpoken: false, summary: "" },
  7:  { type: "empty",    guestCount: 0, userIds: [], hasSpoken: false, summary: "" },
  8:  { type: "reserved", reserveTime: "13:30", guestCount: 2, userIds: [], hasSpoken: false, summary: "事前予約席（高橋様・2名）。" },
  9:  { type: "speaking", stayTime: "5分", guestCount: 2, userIds: ["u-seated-9"], hasSpoken: true, summary: "2名様。卓上AIマイクを通じてFree Wi-Fi接続と地元レモン特製パフェをご案内しました。" },
  10: { type: "empty",    guestCount: 0, userIds: [], hasSpoken: false, summary: "" }
};

let selectedTable = 1;
let selectedQueueId = null;
let dragItem = null;
let lastUndo = null;
let editingUserId = null;
let currentEditingFavs = [];
let deletePendingQueueId = null; // 削除確認待機中のqueueId

/* ═══════════════════════════════════════════
   卓番カード描画
═══════════════════════════════════════════ */
function buildSeatCards() {
  const canvas = document.getElementById('floor-canvas');
  for (let i = 1; i <= 10; i++) {
    const div = document.createElement('div');
    div.id = `tbl-${i}`;
    div.className = 'seat-card';
    div.onclick = () => showDetail(i);
    canvas.appendChild(div);
  }
  refreshAllCards();
}

function refreshAllCards() {
  for (let i = 1; i <= 10; i++) refreshCard(i);
}

function refreshCard(id) {
  const t = TABLES[id];
  const el = document.getElementById(`tbl-${id}`);
  if (!el) return;

  const cls = {
    empty:    'seat-card is-empty',
    reserved: 'seat-card is-reserved',
    speaking: 'seat-card speaking',
    active:   (() => {
      const allAllergies = t.userIds.flatMap(uid => DB[uid]?.allergies ?? []);
      return allAllergies.length ? 'seat-card has-allergy' : 'seat-card no-ai';
    })()
  }[t.type] ?? 'seat-card';

  el.className = cls + (selectedTable === id && selectedQueueId === null ? ' active' : '');

  let numLabel = `${id}番`;
  let guestLabel = '';
  let bodyHtml = '';
  let footHtml = '';

  if (t.type === 'empty') {
    guestLabel = `<span style="font-size:.72rem;color:var(--text-dim);font-weight:700;">空席</span>`;
    footHtml   = `<span style="color:var(--text-dim);">案内可能</span>`;
  } else if (t.type === 'reserved') {
    guestLabel = `${t.guestCount}名予約`;
    bodyHtml   = `<span class="chip chip-amber">${t.reserveTime} 予約</span>`;
    const rep  = t.userIds[0] ? DB[t.userIds[0]]?.name : '';
    footHtml   = rep ? `<span class="text-reserved">${rep}</span>` : '';
  } else {
    guestLabel = `${t.guestCount}名`;
    if (t.type === 'speaking') {
      bodyHtml = `<span class="chip chip-green">🎙️ 対話中</span>`;
    } else {
      const allAllergies = [...new Set(t.userIds.flatMap(uid => DB[uid]?.allergies ?? []))];
      bodyHtml = allAllergies.map(a => `<span class="chip chip-red">${a}</span>`).join('');
    }
    footHtml = `<span>滞在 ${t.stayTime}</span>`;
  }

  el.innerHTML = `
    <div class="flex justify-between items-center">
      <span class="s-num">${numLabel}</span>
      <span class="s-guests">${guestLabel}</span>
    </div>
    <div class="s-body">${bodyHtml}</div>
    <div class="s-foot">${footHtml}</div>
  `;
}

/* ═══════════════════════════════════════════
   待合リスト（ごー行の誤字修正 ＆ 2段階安全削除）
═══════════════════════════════════════════ */
function renderWaiting() {
  const container = document.getElementById('waiting-list');
  document.getElementById('wait-count').innerText = `${waitingQueue.length}組`;

  let active = 0, empty = 0;
  Object.values(TABLES).forEach(t => {
    if (t.type === 'active' || t.type === 'speaking') active++;
    if (t.type === 'empty') empty++;
  });
  document.getElementById('active-badge').innerText = `稼働：${active}卓`;
  document.getElementById('empty-badge').innerText  = `空席：${empty}卓`;

  if (!waitingQueue.length) {
    container.innerHTML = `<div style="text-align:center;padding:30px 0;color:var(--text-dim);font-size:.8rem;">待機中のお客様はいません</div>`;
    return;
  }

  container.innerHTML = waitingQueue.map(item => {
    const users = item.userIds.map(uid => DB[uid]).filter(Boolean);
    const allAllergies = [...new Set(users.flatMap(u => u.allergies))];
    const alg = allAllergies.length > 0;
    const isSelected = selectedQueueId === item.queueId;
    const isPendingDelete = deletePendingQueueId === item.queueId;

    // 「ご一行」に修正（「ごー行」などのタイポを完全排除）
    const groupTitle = `${users[0]?.name || 'お客様'} ご一行`;

    return `
      <div class="waiting-card ${alg ? 'has-allergy' : ''} ${isSelected ? 'active' : ''}"
           draggable="true" 
           ondragstart="onDragStart(event,'${item.queueId}')"
           onclick="showWaitingDetail('${item.queueId}')">
        <div class="waiting-card-head">
          <span class="waiting-card-name">${groupTitle}</span>
          <div class="flex items-center gap-2">
            <span class="chip chip-blue">${item.guestsCount}名</span>
            <button class="btn-delete-queue ${isPendingDelete ? 'confirming' : ''}" 
                    title="待合から削除"
                    onclick="handleDeleteQueue(event, '${item.queueId}', '${users[0]?.name || 'お客様'}')">
              ${isPendingDelete ? '確認削除' : '✕'}
            </button>
          </div>
        </div>
        <div class="flex gap-2 text-xs text-sub" style="margin-top:4px; flex-wrap:wrap;">
          ${users.map(u => `<span>👤 ${u.name}</span>`).join(' ')}
        </div>
        ${alg ? `<div style="margin-top:4px;">${allAllergies.map(a => `<span class="chip chip-red">${a}</span>`).join(' ')}</div>` : ''}
      </div>`;
  }).join('');
}

/* ═══════════════════════════════════════════
   2段階安全削除ロジック（遊び防止）
═══════════════════════════════════════════ */
function handleDeleteQueue(event, queueId, guestName) {
  event.stopPropagation(); // 詳細パネル切り替えイベントの連動を防止

  if (deletePendingQueueId === queueId) {
    // 2度目のクリック：確認ダイアログ（ポップアップウィンドウ）を表示
    if (confirm(`本当に ${guestName} 様（ご一行）を待合リストから削除しますか？`)) {
      waitingQueue = waitingQueue.filter(q => q.queueId !== queueId);
      deletePendingQueueId = null;

      // 削除対象が右側パネルに表示されていたら詳細をクリア
      if (selectedQueueId === queueId) {
        selectedQueueId = null;
        document.getElementById('d-title').innerText = "選択なし";
        document.getElementById('d-sub').innerText = "卓番または待合を選択してください";
        document.getElementById('d-content').innerHTML = "";
      }

      renderWaiting();
    } else {
      deletePendingQueueId = null;
      renderWaiting();
    }
  } else {
    // 1度目のクリック：「確認削除」ボタン状態へ変化
    deletePendingQueueId = queueId;
    renderWaiting();

    // 4秒間何もしなければ自動的に通常状態へリセット
    setTimeout(() => {
      if (deletePendingQueueId === queueId) {
        deletePendingQueueId = null;
        renderWaiting();
      }
    }, 4000);
  }
}

/* ═══════════════════════════════════════════
   待合受付クリック時の右側詳細表示
═══════════════════════════════════════════ */
function showWaitingDetail(queueId) {
  selectedQueueId = queueId;
  selectedTable = null;

  document.querySelectorAll('.seat-card').forEach(el => el.classList.remove('active'));
  renderWaiting();

  const item = waitingQueue.find(q => q.queueId === queueId);
  if (!item) return;

  const actions = document.getElementById('d-actions');
  const content = document.getElementById('d-content');
  
  document.getElementById('d-title').innerText = `待合受付`;
  document.getElementById('d-sub').innerText = `ご案内待ち（${item.guestsCount}名様）`;
  actions.style.display = 'none';

  const users = item.userIds.map(uid => DB[uid]).filter(Boolean);
  const guestsHtml = users.map((u, index) => {
    const alg = u.allergies.length > 0;
    return `
      <div class="guest-card ${alg ? 'danger' : ''}" onclick="openGuest('${u.id}')">
        <div class="flex justify-between items-center">
          <span style="font-weight:800;">
            👤 ${u.name} ${index === 0 && users.length > 1 ? '<span class="chip chip-blue" style="margin-left:4px;">代表</span>' : ''}
          </span>
          <span class="chip chip-sub">来店 ${u.count}回目</span>
        </div>
        ${alg ? `<div>${u.allergies.map(a => `<span class="chip chip-red">${a}</span>`).join(' ')}</div>` : ''}
        ${u.favs.length ? `<div class="text-xs" style="color:#5c441b;">⭐ 好物: ${u.favs.join('、')}</div>` : ''}
        <div class="hint-box">
          <div class="hint-label">💡 接客メモ (UserMemory)[cite: 1]</div>
          <div class="hint-text">${u.hint || 'タップして情報を追加・編集できます。'}</div>
        </div>
        <div style="text-align:right; font-size:0.72rem; color:var(--c-primary); font-weight:700;">👉 カルテを編集</div>
      </div>`;
  }).join('');

  content.innerHTML = guestsHtml;
}

/* ═══════════════════════════════════════════
   ドラッグ＆ドロップ配席
═══════════════════════════════════════════ */
function onDragStart(e, queueId) {
  dragItem = waitingQueue.find(q => q.queueId === queueId) ?? null;
  e.dataTransfer.setData('text/plain', queueId);
}

function setupDrop() {
  for (let i = 1; i <= 10; i++) {
    const el = document.getElementById(`tbl-${i}`);
    el.addEventListener('dragover', e => {
      if (TABLES[i].type === 'empty') { e.preventDefault(); el.classList.add('drag-over'); }
    });
    el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
    el.addEventListener('drop', e => {
      e.preventDefault();
      el.classList.remove('drag-over');
      if (dragItem && TABLES[i].type === 'empty') assign(i, dragItem);
    });
  }
}

function assign(tableId, qItem) {
  lastUndo = { tableId, queueItem: { ...qItem } };
  waitingQueue = waitingQueue.filter(q => q.queueId !== qItem.queueId);

  const t = TABLES[tableId];
  Object.assign(t, {
    type: 'active',
    stayTime: '1分',
    guestCount: qItem.guestsCount,
    userIds: [...qItem.userIds], // TableSessionMember[cite: 1]
    assignedQueue: qItem,
    hasSpoken: false,
    summary: ""
  });

  const undoBtn = document.getElementById('undo-btn');
  const repName = DB[qItem.userIds[0]]?.name || 'お客様';
  document.getElementById('undo-desc').innerText = `${tableId}番卓 → ${repName}`;
  undoBtn.style.display = 'inline-flex';

  selectedQueueId = null;
  refreshCard(tableId);
  renderWaiting();
  showDetail(tableId);
}

function returnToWaiting(tableId) {
  const t = TABLES[tableId];
  if (!t || t.type === 'empty' || t.type === 'reserved') return;

  if (t.type === 'speaking' || t.hasSpoken) {
    alert("対話中、または会話を開始済みのお客様は待合リストへ戻せません。\n退店時は「お会計・退店処理」を行ってください。");
    return;
  }

  if (t.assignedQueue) {
    waitingQueue.unshift(t.assignedQueue);
  } else if (t.userIds.length) {
    waitingQueue.unshift({
      queueId: `q-restored-${Date.now()}`,
      userIds: [...t.userIds],
      guestsCount: t.guestCount || t.userIds.length
    });
  }

  Object.assign(t, {
    type: 'empty',
    stayTime: null,
    guestCount: 0,
    userIds: [],
    assignedQueue: null,
    hasSpoken: false,
    summary: ""
  });

  if (lastUndo?.tableId === tableId) {
    document.getElementById('undo-btn').style.display = 'none';
    lastUndo = null;
  }
  refreshCard(tableId);
  renderWaiting();
  showDetail(tableId);
}

function undoLast() {
  if (lastUndo) returnToWaiting(lastUndo.tableId);
}

/* ═══════════════════════════════════════════
   会計・退店・予約案内
═══════════════════════════════════════════ */
function checkoutTable(tableId) {
  const t = TABLES[tableId];
  if (!t || t.type === 'empty') return;

  if (!confirm(`${tableId}番テーブルのお会計を完了し、空席（清掃済み）にしますか？`)) return;

  const nowStr = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
  t.userIds.forEach(uid => {
    const u = DB[uid];
    if (u && u.sessions) {
      const activeSess = u.sessions.find(s => s.tId === tableId && s.out === "利用中");
      if (activeSess) activeSess.out = `${nowStr} 退店`;
    }
  });

  Object.assign(t, {
    type: 'empty',
    stayTime: null,
    guestCount: 0,
    userIds: [],
    assignedQueue: null,
    hasSpoken: false,
    summary: ""
  });

  if (lastUndo?.tableId === tableId) {
    document.getElementById('undo-btn').style.display = 'none';
    lastUndo = null;
  }

  refreshCard(tableId);
  renderWaiting();
  showDetail(tableId);
}

function seatReservedTable(tableId) {
  const t = TABLES[tableId];
  if (!t || t.type !== 'reserved') return;

  t.type = 'active';
  t.stayTime = '1分';
  t.hasSpoken = false;

  refreshCard(tableId);
  renderWaiting();
  showDetail(tableId);
}

/* ═══════════════════════════════════════════
   卓番詳細パネル表示
═══════════════════════════════════════════ */
function showDetail(id) {
  selectedTable = id;
  selectedQueueId = null;

  document.querySelectorAll('.seat-card').forEach(el => el.classList.remove('active'));
  document.getElementById(`tbl-${id}`)?.classList.add('active');
  renderWaiting();

  const t = TABLES[id];
  const actions = document.getElementById('d-actions');
  const content = document.getElementById('d-content');
  document.getElementById('d-title').innerText = `${id}番テーブル`;

  if (t.type === 'empty') {
    actions.style.display = 'none';
    document.getElementById('d-sub').innerText = '空席（即時案内可能）';
    content.innerHTML = `
      <div style="text-align:center;padding:50px 0;color:var(--text-dim);">
        <div style="font-size:2.5rem;">🪑</div>
        <div style="font-weight:800;font-size:1rem;color:var(--text-sub);margin-top:8px;">現在空席です</div>
        <div class="text-sm" style="margin-top:4px;">左の待合リストからドラッグ＆ドロップして配席してください</div>
      </div>`;
    return;
  }

  if (t.type === 'reserved') {
    actions.style.display = 'flex';
    actions.innerHTML = `
      <div class="action-btn-row">
        <button class="btn btn-primary" style="flex:1;" onclick="seatReservedTable(${id})">✅ ご来店・着席を開始する</button>
      </div>
    `;
    document.getElementById('d-sub').innerText = `事前予約席（${t.reserveTime} ご来店予定）`;
    content.innerHTML = t.userIds.map(uid => {
      const u = DB[uid];
      return `
        <div class="guest-card" onclick="openGuest('${u.id}')">
          <div class="flex justify-between items-center">
            <span style="font-weight:800;">👤 ${u.name} (代表予約)</span>
            <span class="chip chip-sub">来店 ${u.count}回目</span>
          </div>
          ${u.favs.length ? `<div class="text-xs" style="color:#5c441b;">⭐ 好物: ${u.favs.join('、')}</div>` : ''}
          <div class="hint-box">
            <div class="hint-label">💡 予約情報・カルテ</div>
            <div class="hint-text">${u.hint}</div>
          </div>
        </div>`;
    }).join('');
    return;
  }

  actions.style.display = 'flex';
  const isLocked = t.type === 'speaking' || t.hasSpoken;

  actions.innerHTML = `
    <div class="action-btn-row">
      ${isLocked 
        ? `<button class="btn btn-cannot-return" disabled>✕ 配席取消不可（対話中）</button>`
        : `<button class="btn btn-return-wait" onclick="returnToWaiting(${id})">↩️ 待合リストへ戻す</button>`
      }
      <button class="btn btn-checkout" onclick="checkoutTable(${id})">
        🧾 会計・退店処理
      </button>
    </div>
  `;

  document.getElementById('d-sub').innerText = `滞在：${t.stayTime}（${t.guestCount || t.userIds.length}名様）`;

  const summaryHtml = t.summary ? `
    <div class="ai-box">
      <div class="ai-box-head flex justify-between">
        <span>🎙️ 接客・対話まとめ</span>
      </div>
      <div class="ai-box-body">${t.summary}</div>
    </div>` : '';

  const guestsHtml = t.userIds.length === 0
    ? `<div style="padding:15px;background:var(--surface-sub);border:1.5px dashed var(--border-dark);border-radius:var(--radius-md);text-align:center;color:var(--text-sub);font-size:.85rem;">
        <strong>一般のお客様（カルテ未登録）</strong>
       </div>`
    : t.userIds.map((uid, index) => {
        const u = DB[uid];
        if (!u) return '';
        const alg = u.allergies.length > 0;
        return `
          <div class="guest-card ${alg ? 'danger' : ''}" onclick="openGuest('${u.id}')">
            <div class="flex justify-between items-center">
              <span style="font-weight:800;">
                👤 ${u.name} ${index === 0 && t.userIds.length > 1 ? '<span class="chip chip-blue" style="margin-left:4px;">代表</span>' : ''}
              </span>
              <span class="chip chip-sub">来店 ${u.count}回目</span>
            </div>
            ${alg ? `<div>${u.allergies.map(a => `<span class="chip chip-red">${a}</span>`).join(' ')}</div>` : ''}
            ${u.favs.length ? `<div class="text-xs" style="color:#5c441b;">⭐ 好物: ${u.favs.join('、')}</div>` : ''}
            <div class="hint-box">
              <div class="hint-label">💡 接客メモ (UserMemory)[cite: 1]</div>
              <div class="hint-text">${u.hint || 'タップして情報を追加・編集できます。'}</div>
            </div>
            <div style="text-align:right; font-size:0.72rem; color:var(--c-primary); font-weight:700;">👉 カルテを編集</div>
          </div>`;
      }).join('');

  content.innerHTML = summaryHtml + guestsHtml;
}

/* ═══════════════════════════════════════════
   顧客カルテ編集（スリム化・好物編集対応）
═══════════════════════════════════════════ */
function renderUserForm(u, prefix) {
  document.getElementById(`${prefix}-stats`).innerHTML = `
    <div class="er-item"><div class="er-label">お名前 (name)</div><input id="${prefix}-name-val" class="input-base" value="${u.name}"></div>
    <div class="er-item"><div class="er-label">居住地域 (region)</div><input id="${prefix}-region-val" class="input-base" value="${u.region || ''}" placeholder="未登録"></div>
    <div class="er-item"><div class="er-label">累計来店回数</div><input id="${prefix}-count-val" class="input-base" type="number" value="${u.count || 1}" min="1"></div>
    <div class="er-item"><div class="er-label">最終来店</div><div style="font-size:0.8rem; font-weight:700; margin-top:4px;">${u.last || '-'}</div></div>
  `;

  renderAllergyEditor(u.allergies, `${prefix}-allergy`);

  currentEditingFavs = [...(u.favs || [])];
  renderFavChips(prefix);

  document.getElementById(`${prefix}-hint`).value = u.hint || '';

  document.getElementById(`${prefix}-sessions`).innerHTML = u.sessions?.length
    ? u.sessions.map(s => `<tr><td>${s.sId}</td><td>${s.tId}番卓</td><td>${s.in}</td><td>${s.out}</td></tr>`).join('')
    : '<tr><td colspan="4" style="text-align:center;color:var(--text-dim)">履歴なし</td></tr>';
}

function renderFavChips(prefix) {
  const container = document.getElementById(`${prefix}-favs-chips`);
  if (!container) return;
  if (!currentEditingFavs.length) {
    container.innerHTML = `<span class="text-muted text-xs">登録なし（下の入力欄から追加できます）</span>`;
    return;
  }
  container.innerHTML = currentEditingFavs.map((fav, index) => `
    <span class="fav-tag">
      ⭐ ${fav}
      <button type="button" class="fav-del-btn" onclick="removeFavMenu('${prefix}', ${index})">✕</button>
    </span>
  `).join('');
}

function addFavMenu(prefix) {
  const input = document.getElementById(`${prefix}-fav-input`);
  const val = input.value.trim();
  if (!val) return;
  if (!currentEditingFavs.includes(val)) {
    currentEditingFavs.push(val);
    renderFavChips(prefix);
  }
  input.value = '';
}

function removeFavMenu(prefix, index) {
  currentEditingFavs.splice(index, 1);
  renderFavChips(prefix);
}

function collectUserForm(prefix) {
  return {
    name:      document.getElementById(`${prefix}-name-val`).value.trim() || '無名のお客様',
    region:    document.getElementById(`${prefix}-region-val`).value.trim() || '未登録',
    count:     parseInt(document.getElementById(`${prefix}-count-val`).value, 10) || 1,
    hint:      document.getElementById(`${prefix}-hint`).value.trim(),
    allergies: [...document.querySelectorAll(`#${prefix}-allergy input:checked`)].map(cb => cb.value),
    favs:      [...currentEditingFavs]
  };
}

function renderAllergyEditor(selected, containerId) {
  document.getElementById(containerId).innerHTML = allergenMaster.map(item => `
    <label class="allergy-label">
      <input type="checkbox" value="${item}" ${selected.includes(item) ? 'checked' : ''}>
      <span>${item}</span>
    </label>`
  ).join('');
}

function addAllergen(editorId, inputId) {
  const input = document.getElementById(inputId);
  const val = input.value.trim();
  if (!val) return;
  if (!allergenMaster.includes(val)) allergenMaster.push(val);
  const checked = [...document.querySelectorAll(`#${editorId} input:checked`)].map(cb => cb.value);
  if (!checked.includes(val)) checked.push(val);
  renderAllergyEditor(checked, editorId);
  input.value = '';
}

function openGuest(userId) {
  editingUserId = userId;
  const u = DB[userId];
  document.getElementById('mg-name').innerText = `${u.name} 様のカルテ`;
  document.getElementById('mg-id').innerText   = `顧客識別番号 (uuid): ${u.id}`;
  renderUserForm(u, 'mg');
  document.getElementById('modal-guest').style.display = 'flex';
}

function closeGuest() {
  document.getElementById('modal-guest').style.display = 'none';
  editingUserId = null;
}

function saveGuest() {
  if (!editingUserId) return;
  Object.assign(DB[editingUserId], collectUserForm('mg'));
  
  if (selectedTable) {
    refreshCard(selectedTable);
    showDetail(selectedTable);
  } else if (selectedQueueId) {
    showWaitingDetail(selectedQueueId);
  }
  
  closeGuest();
  renderWaiting();
}

/* ═══════════════════════════════════════════
   新規受付（placeholder化 ＆ 空欄時自動フォールバック）
═══════════════════════════════════════════ */
function openQuickAdd() {
  renderQuickAddForms();
  document.getElementById('modal-add').style.display = 'flex';
}
function closeAdd() {
  document.getElementById('modal-add').style.display = 'none';
}

function renderQuickAddForms() {
  const count = parseInt(document.getElementById('qa-count').value, 10) || 1;
  const container = document.getElementById('qa-forms-container');
  let html = '';

  for (let i = 1; i <= count; i++) {
    const defaultPlaceholder = i === 1 ? '代表のお客様' : `お連れ様 ${i}`;

    html += `
      <div class="qa-person-card">
        <div class="flex justify-between items-center">
          <span style="font-weight:900; font-size:0.85rem;">👤 ${i}人目のお客様 ${i === 1 ? '(代表)' : ''}</span>
        </div>
        <div>
          <label class="form-label">お名前・呼称（未入力の場合はプレースホルダー名が反映されます）</label>
          <input id="qa-pname-${i}" 
                 class="input-base" 
                 type="text" 
                 value="" 
                 placeholder="${defaultPlaceholder}" 
                 data-default-name="${defaultPlaceholder}">
        </div>
        <div>
          <label class="form-label text-danger">アレルゲン選択</label>
          <div class="allergy-editor" id="qa-allergy-${i}">
            ${allergenMaster.map(item => `
              <label class="allergy-label">
                <input type="checkbox" value="${item}">
                <span>${item}</span>
              </label>
            `).join('')}
          </div>
          <div class="custom-allergy-bar">
            <input type="text" id="qa-custom-${i}" class="custom-allergy-input" placeholder="＋ 独自アレルゲン（例: キウイ）">
            <button class="btn btn-secondary" style="font-size:0.75rem; padding:4px 8px;" onclick="addAllergen('qa-allergy-${i}','qa-custom-${i}')">追加</button>
          </div>
        </div>
      </div>
    `;
  }
  container.innerHTML = html;
}

function submitAdd() {
  const count = parseInt(document.getElementById('qa-count').value, 10) || 1;
  const createdUserIds = [];

  for (let i = 1; i <= count; i++) {
    const inputEl = document.getElementById(`qa-pname-${i}`);
    const enteredVal = inputEl.value.trim();
    const defaultVal = inputEl.getAttribute('data-default-name') || `お客様 (${i})`;
    const finalName = enteredVal !== '' ? enteredVal : defaultVal;

    const checked = [...document.querySelectorAll(`#qa-allergy-${i} input:checked`)].map(cb => cb.value);

    const newId = `u-reg-${Date.now()}-${i}`;
    DB[newId] = {
      id: newId,
      name: finalName,
      region: "未登録",
      last: "2026-09-28",
      count: 1,
      allergies: checked,
      favs: [],
      hint: `初来店の組（同席者）。`,
      sessions: []
    };
    createdUserIds.push(newId);
  }

  waitingQueue.push({
    queueId: `q-${Date.now()}`,
    userIds: createdUserIds,
    guestsCount: count
  });

  closeAdd();
  renderWaiting();
}

/* ═══════════════════════════════════════════
   顧客台帳
═══════════════════════════════════════════ */
function openLedger() {
  document.getElementById('modal-ledger').style.display = 'flex';
  backLedger();
}

function closeLedger() {
  document.getElementById('modal-ledger').style.display = 'none';
  editingUserId = null;
}

function backLedger() {
  document.getElementById('lp-list').style.display = 'flex';
  document.getElementById('lp-edit').style.display = 'none';
  renderLedger(document.getElementById('lp-search').value);
}

function filterLedger() {
  renderLedger(document.getElementById('lp-search').value);
}

function renderLedger(kw = '') {
  const tbody = document.getElementById('lp-tbody');
  const lower = kw.toLowerCase().trim();
  const list = Object.values(DB).filter(u => {
    if (!lower) return true;
    return `${u.name} ${u.region} ${u.allergies.join(' ')} ${u.favs.join(' ')} ${u.hint}`.toLowerCase().includes(lower);
  });

  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--text-dim);">該当する顧客は見つかりませんでした</td></tr>`;
    return;
  }

  tbody.innerHTML = list.map(u => `
    <tr class="row-click" onclick="openLedgerEdit('${u.id}')">
      <td><strong>${u.name}</strong></td>
      <td>${u.region || '未登録'}</td>
      <td>${u.count || 1}回</td>
      <td>${u.favs.length ? u.favs.map(f => `⭐${f}`).join('、') : '<span class="text-muted">なし</span>'}</td>
      <td>${u.allergies.length ? u.allergies.map(a => `<span class="chip chip-red">${a}</span>`).join(' ') : '<span class="text-muted">なし</span>'}</td>
      <td>${u.last || '-'}</td>
      <td><button class="btn btn-secondary" style="padding:3px 8px;font-size:.72rem;" onclick="event.stopPropagation();openLedgerEdit('${u.id}')">編集</button></td>
    </tr>`).join('');
}

function openLedgerEdit(userId) {
  editingUserId = userId;
  const u = DB[userId];
  document.getElementById('lp-list').style.display = 'none';
  document.getElementById('lp-edit').style.display = 'flex';
  document.getElementById('lp-edit-name').innerText = `${u.name} 様のカルテ編集`;
  renderUserForm(u, 'lp');
  document.querySelector('#lp-edit .modal-body').scrollTop = 0;
}

function saveLedger() {
  if (!editingUserId) return;
  Object.assign(DB[editingUserId], collectUserForm('lp'));
  if (selectedTable) refreshCard(selectedTable);
  renderWaiting();
  backLedger();
}

/* ═══════════════════════════════════════════
   リサイザー & 座席図スケール切り替え
═══════════════════════════════════════════ */
function initResizers() {
  const layout = document.getElementById('app-layout');
  let active = null;

  ['res-left', 'res-right'].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('mousedown', () => {
      active = id;
      el.classList.add('dragging');
      document.body.style.cursor = 'col-resize';
    });
  });

  window.addEventListener('mousemove', e => {
    if (!active) return;
    const r = layout.getBoundingClientRect();
    if (active === 'res-left') {
      const w = Math.min(440, Math.max(170, e.clientX - r.left));
      document.documentElement.style.setProperty('--panel-left', `${w}px`);
    } else {
      const w = Math.min(560, Math.max(240, r.right - e.clientX));
      document.documentElement.style.setProperty('--panel-right', `${w}px`);
    }
  });

  window.addEventListener('mouseup', () => {
    if (!active) return;
    document.getElementById(active).classList.remove('dragging');
    document.body.style.cursor = '';
    active = null;
  });
}

function setW(side, w) {
  document.documentElement.style.setProperty(side === 'left' ? '--panel-left' : '--panel-right', `${w}px`);
}

function setFloorScale(scale) {
  if (scale === 'small') {
    setW('left', 340);
    setW('right', 460);
  } else if (scale === 'medium') {
    setW('left', 260);
    setW('right', 380);
  } else if (scale === 'large') {
    setW('left', 180);
    setW('right', 260);
  }
}

/* ═══════════════════════════════════════════
   初期起動
═══════════════════════════════════════════ */
buildSeatCards();
setupDrop();
initResizers();
renderWaiting();
showDetail(1);