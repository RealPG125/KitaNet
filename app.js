/* ═══════════════════════════════════════════
   店舗接客フロントエンド（追加アレルゲンの削除対応版）
═══════════════════════════════════════════ */
const API_BASE = "http://127.0.0.1:8000/api";

const PREFECTURES = [
  "愛媛県", "広島県", "香川県", "徳島県", "高知県", "岡山県", "山口県",
  "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
  "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
  "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
  "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
  "奈良県", "和歌山県", "鳥取県", "島根県", "福岡県", "佐賀県", "長崎県",
  "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県", "その他"
];

// 初期基本マスター（削除不可の保護対象）
const DEFAULT_ALLERGENS = [
  // 義務：特定原材料（9品目）
  "卵", "乳", "小麦", "くるみ", "落花生（ピーナッツ）", "そば", "えび", "かに", "カシューナッツ",
  // 推奨：特定原材料に準ずるもの（20品目）
  "大豆", "キウイフルーツ", "バナナ", "もも", "りんご", "オレンジ",
  "アーモンド", "ピスタチオ", "マカダミアナッツ", "さけ", "さば", "いくら", "いか",
  "あわび", "ごま", "牛肉", "豚肉", "鶏肉", "やまいも", "ゼラチン"
];

let allergenMaster = [...DEFAULT_ALLERGENS];

// 表記ゆれマッピング
const ALLERGEN_MAP = {
  "エビ": "えび", "海老": "えび",
  "カニ": "かに", "蟹": "かに",
  "ソバ": "そば", "蕎麦": "そば",
  "コムギ": "小麦",
  "たまご": "卵", "タマゴ": "卵", "玉子": "卵", "鶏卵": "卵",
  "乳製品": "乳", "ミルク": "乳", "牛乳": "乳",
  "落花生": "落花生（ピーナッツ）", "ピーナッツ": "落花生（ピーナッツ）",
  "クルミ": "くるみ", "胡桃": "くるみ",
  "サケ": "さけ", "鮭": "さけ", "サーモン": "さけ",
  "サバ": "さば", "鯖": "さば",
  "イカ": "いか", "烏賊": "いか",
  "アワビ": "あわび", "鮑": "あわび",
  "ゴマ": "ごま", "胡麻": "ごま",
  "ヤマイモ": "やまいも", "山芋": "やまいも",
  "キウイ": "キウイフルーツ"
};

function normalizeAllergenUI(name) {
  const clean = name.trim();
  return ALLERGEN_MAP[clean] || clean;
}

let DB = {};
let MENU = [];
let ORDERS = {};
window.pickerOpen = false;
let TABLES = {};

// 待合リストを賑やかに（3組待ち）
let waitingQueue = [];

let selectedTable = 1;
let selectedQueueId = null;
let dragItem = null;
let lastUndo = null;
let editingUserId = null;
let currentEditingFavs = [];
let deletePendingQueueId = null;
let currentLedgerTab = "active";
let confirmCallback = null;

async function initApp() {
  buildSeatCards();
  setupDrop();
  initResizers();
  try { waitingQueue = await (await fetch(`${API_BASE}/waiting-queue`)).json(); } catch (e) { console.error(e); }
  try { MENU = await (await fetch(`${API_BASE}/menu`)).json(); } catch (e) { console.error(e); }
  await loadDatabase();
  renderWaiting();
  showDetail(1);

  setInterval(async () => {
    if (editingUserId || window.pickerOpen) return;
    await loadDatabase();
    if (selectedTable) showDetail(selectedTable);
  }, 10000);
}

async function loadDatabase() {
  try {
    const [resUsers, resFloor] = await Promise.all([
      fetch(`${API_BASE}/users`),
      fetch(`${API_BASE}/floor-status`)
    ]);

    DB = await resUsers.json();
    TABLES = await resFloor.json();

    Object.values(DB).forEach(u => {
      u.allergies.forEach(a => {
        const norm = normalizeAllergenUI(a);
        if (!allergenMaster.includes(norm)) allergenMaster.push(norm);
      });
    });

    updateTrashBadge();
    refreshAllCards();
    renderWaiting();
  } catch (err) {
    console.error("データベース同期エラー:", err);
  }
}

function updateTrashBadge() {
  const count = Object.values(DB).filter(u => u.is_deleted).length;
  const badge = document.getElementById("trash-count");
  if (badge) badge.innerText = count;
}

/* ═══════════════════════════════════════════
   カスタム確認モーダル
═══════════════════════════════════════════ */
function showConfirmModal(title, message, actionBtnText, isDanger, onConfirm) {
  document.getElementById("confirm-dialog-title").innerText = title;
  document.getElementById("confirm-dialog-message").innerText = message;
  const btn = document.getElementById("confirm-dialog-action-btn");
  btn.innerText = actionBtnText;
  btn.className = isDanger ? "btn btn-checkout" : "btn btn-primary";
  confirmCallback = onConfirm;
  document.getElementById("modal-confirm").style.display = "flex";
}

function closeConfirmModal(result) {
  document.getElementById("modal-confirm").style.display = "none";
  if (result && typeof confirmCallback === "function") {
    confirmCallback();
  }
  confirmCallback = null;
}

function handleRegionChange(selectEl, customInputId) {
  const customInput = document.getElementById(customInputId);
  if (!customInput) return;
  if (selectEl.value === "その他") {
    customInput.style.display = "block";
    customInput.focus();
  } else {
    customInput.style.display = "none";
    customInput.value = "";
  }
}

function buildSeatCards() {
  const canvas = document.getElementById('floor-canvas');
  for (let i = 1; i <= 10; i++) {
    const div = document.createElement('div');
    div.id = `tbl-${i}`;
    div.className = 'seat-card';
    div.onclick = () => {
      const q = waitingQueue.find(x => x.queueId === selectedQueueId);
      if (q && TABLES[i]?.type === 'empty') assign(i, q);   // 待合カード選択中に空席をタップ → 配席
      else showDetail(i);
    };
    canvas.appendChild(div);
  }
}

function refreshAllCards() {
  for (let i = 1; i <= 10; i++) refreshCard(i);
}

function refreshCard(id) {
  const t = TABLES[id];
  const el = document.getElementById(`tbl-${id}`);
  if (!el || !t) return;

  const allAllergies = t.userIds.flatMap(uid => DB[uid]?.allergies ?? []);
  let cls = 'seat-card is-empty';

  if (t.type === 'active') {
    cls = allAllergies.length ? 'seat-card has-allergy' : 'seat-card no-ai';
  } else if (t.type === 'speaking') {
    cls = 'seat-card speaking';
  } else if (t.type === 'reserved') {
    cls = 'seat-card is-reserved';
  } else if (t.type === 'billing') {
    cls = 'seat-card is-billing';
  }

  el.className = cls + (selectedTable === id && selectedQueueId === null ? ' active' : '');

  let guestLabel = `<span style="font-size:.72rem;color:var(--text-dim);font-weight:700;">空席</span>`;
  let bodyHtml = '';
  let footHtml = `<span style="color:var(--text-dim);">案内可能</span>`;

  if (t.type === 'reserved') {
    guestLabel = `${t.guestCount}名予約`;
    bodyHtml = `<span class="chip chip-amber">${t.reserveTime || '予約席'}</span>`;
    footHtml = `<span class="text-reserved">${DB[t.userIds[0]]?.name || '予約席'}</span>`;
  } else if (t.type !== 'empty') {
    guestLabel = `${t.guestCount}名`;
    if (t.type === 'billing') {
      bodyHtml = `<span class="chip chip-amber">会計中</span>`;
    } else if (t.type === 'speaking') {
      bodyHtml = `<span class="chip chip-green">🎙️ 対話中</span>`;
    } else {
      const uniqueAlgs = [...new Set(allAllergies.map(normalizeAllergenUI))];
      bodyHtml = uniqueAlgs.map(a => `<span class="chip chip-red">${a}</span>`).join('');
    }
    footHtml = `<span>${t.stayTime || '利用中'}</span>`;
  }

  el.innerHTML = `
    <div class="flex justify-between items-center">
      <span class="s-num">${id}番</span>
      <span class="s-guests">${guestLabel}</span>
    </div>
    <div class="s-body">${bodyHtml}</div>
    <div class="s-foot">${footHtml}</div>
  `;
}

function renderWaiting() {
  const container = document.getElementById('waiting-list');
  document.getElementById('wait-count').innerText = `${waitingQueue.length}組`;

  let active = 0, empty = 0, reserved = 0;
  Object.values(TABLES).forEach(t => {
    if (['active','speaking','billing'].includes(t.type)) active++;
    if (t.type === 'empty') empty++;
    if (t.type === 'reserved') reserved++;
  });
  document.getElementById('active-badge').innerText = `稼働：${active}卓`;
  document.getElementById('reserved-badge').innerText = `予約：${reserved}卓`;
  document.getElementById('empty-badge').innerText  = `空席：${empty}卓`;

  if (!waitingQueue.length) {
    container.innerHTML = `<div style="text-align:center;padding:30px 0;color:var(--text-dim);font-size:.8rem;">待機中のお客様はいません</div>`;
    return;
  }

  container.innerHTML = waitingQueue.map(item => {
    const users = item.userIds.map(uid => DB[uid]).filter(Boolean);
    const allAllergies = [...new Set(users.flatMap(u => u.allergies).map(normalizeAllergenUI))];
    const alg = allAllergies.length > 0;
    const isSelected = selectedQueueId === item.queueId;

    const repName = users[0]?.name || 'お客様';
    const groupTitle = `${repName} 様`;

    return `
      <div class="waiting-card ${alg ? 'has-allergy' : ''} ${isSelected ? 'active' : ''}"
           draggable="true" 
           ondragstart="onDragStart(event,'${item.queueId}')"
           onclick="showWaitingDetail('${item.queueId}')">
        <div class="waiting-card-head">
          <span class="waiting-card-name">${groupTitle}</span>
          <div class="flex items-center gap-2">
            <span class="chip chip-blue">${item.guestsCount}名</span>
            <button class="btn-delete-queue" 
                    title="待合から削除"
                    onclick="handleDeleteQueue(event, '${item.queueId}', '${repName}')">
              ✕
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

function handleDeleteQueue(event, queueId, guestName) {
  event.stopPropagation();
  showConfirmModal(
    "待合受付の取り消し",
    `本当に「${guestName} 様」の受付を待合リストから除外しますか？`,
    "待合から削除",
    true,
    () => {
      waitingQueue = waitingQueue.filter(q => q.queueId !== queueId);
      if (selectedQueueId === queueId) {
        selectedQueueId = null;
        document.getElementById('d-title').innerText = "選択なし";
        document.getElementById('d-sub').innerText = "卓番または待合を選択してください";
        document.getElementById('d-content').innerHTML = "";
      }
      renderWaiting();
    }
  );
}

function showWaitingDetail(queueId) {
  selectedQueueId = queueId;
  selectedTable = null;
  hideFooter();

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
  content.innerHTML = users.map((u, index) => {
    const uniqueAlgs = [...new Set(u.allergies.map(normalizeAllergenUI))];
    const alg = uniqueAlgs.length > 0;
    return `
      <div class="guest-card ${alg ? 'danger' : ''}" onclick="openGuest('${u.id}')">
        <div class="flex justify-between items-center">
          <span style="font-weight:800;">👤 ${u.name} ${index === 0 && users.length > 1 ? '<span class="chip chip-blue">代表</span>' : ''}</span>
          <span class="chip chip-sub">来店 ${u.count}回目</span>
        </div>
        ${alg ? `<div>${uniqueAlgs.map(a => `<span class="chip chip-red">${a}</span>`).join(' ')}</div>` : ''}
        ${u.favs.length ? `<div class="text-xs" style="color:#5c441b;">⭐ 好物: ${u.favs.join('、')}</div>` : ''}
        <div class="hint-box">
          <div class="hint-label">💡 接客メモ</div>
          <div class="hint-text">${u.hint || 'タップして情報を追加・編集できます。'}</div>
        </div>
      </div>`;
  }).join('');
}

function onDragStart(e, queueId) {
  dragItem = waitingQueue.find(q => q.queueId === queueId) ?? null;
  e.dataTransfer.setData('text/plain', queueId);
}

function setupDrop() {
  for (let i = 1; i <= 10; i++) {
    const el = document.getElementById(`tbl-${i}`);
    el.addEventListener('dragover', e => {
      if (TABLES[i] && TABLES[i].type === 'empty') { e.preventDefault(); el.classList.add('drag-over'); }
    });
    el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
    el.addEventListener('drop', e => {
      e.preventDefault();
      el.classList.remove('drag-over');
      if (dragItem && TABLES[i].type === 'empty') assign(i, dragItem);
    });
  }
}

async function assign(tableId, qItem) {
  const sessionId = `sess-${Date.now()}`;
  lastUndo = { tableId, sessionId, queueItem: { ...qItem } };
  waitingQueue = waitingQueue.filter(q => q.queueId !== qItem.queueId);

  try {
    await fetch(`${API_BASE}/sessions/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        table_id: tableId,
        user_ids: qItem.userIds,
        session_id: sessionId
      })
    });
  } catch (err) {
    console.error("配席APIエラー:", err);
  }

  const undoBtn = document.getElementById('undo-btn');
  const repName = DB[qItem.userIds[0]]?.name || 'お客様';
  document.getElementById('undo-desc').innerText = `${tableId}番卓 → ${repName}`;
  undoBtn.style.display = 'inline-flex';

  selectedQueueId = null;
  await loadDatabase();
  showDetail(tableId);
}

async function undoLast() {
  if (!lastUndo) return;
  const { sessionId, tableId, queueItem } = lastUndo;
  try { await fetch(`${API_BASE}/sessions/${sessionId}`, { method: "DELETE" }); } catch (e) { console.error("取消APIエラー:", e); }
  waitingQueue.unshift(queueItem);
  lastUndo = null;
  document.getElementById('undo-btn').style.display = 'none';
  await loadDatabase();
  showDetail(tableId);
}

async function billTable(tableId) {
  const t = TABLES[tableId];
  if (!t?.sessionId) return;
  const doBill = async () => {
    try { await fetch(`${API_BASE}/sessions/${t.sessionId}/bill`, { method: "POST" }); } catch (e) { console.error(e); }
    await loadDatabase();
    showDetail(tableId);
  };
  const pending = (ORDERS[t.sessionId]?.items || []).filter(i => i.status === '注文中').length;
  if (pending > 0) {
    showConfirmModal("未提供の注文があります", `「注文中」のまま ${pending} 品が残っています。このままお会計に進みますか？`, "お会計へ", false, doBill);
  } else {
    await doBill();
  }
}

async function seatReserved(tableId) {
  const t = TABLES[tableId];
  if (!t?.sessionId) return;
  try { await fetch(`${API_BASE}/sessions/${t.sessionId}/seat`, { method: "POST" }); } catch (e) { console.error(e); }
  await loadDatabase();
  showDetail(tableId);
}

async function checkoutTable(tableId) {
  const t = TABLES[tableId];
  if (!t || t.type === 'empty') return;

  showConfirmModal(
    "お会計・退店処理",
    `${tableId}番テーブルのお会計（${yen(ORDERS[t.sessionId]?.total ?? 0)}）を完了し、空席に戻しますか？`,
    "お会計を完了",
    false,
    async () => {
      if (t.sessionId) {
        try {
          await fetch(`${API_BASE}/sessions/${t.sessionId}/checkout`, { method: "POST" });
        } catch (err) {
          console.error("退店APIエラー:", err);
        }
      }
      await loadDatabase();
      showDetail(tableId);
    }
  );
}

function showDetail(id) {
  selectedTable = id;
  selectedQueueId = null;
  window.pickerOpen = false;
  hideFooter();

  document.querySelectorAll('.seat-card').forEach(el => el.classList.remove('active'));
  document.getElementById(`tbl-${id}`)?.classList.add('active');

  const t = TABLES[id];
  const actions = document.getElementById('d-actions');
  const content = document.getElementById('d-content');
  document.getElementById('d-title').innerText = `${id}番テーブル`;

  if (!t || t.type === 'empty') {
    actions.style.display = 'none';
    document.getElementById('d-sub').innerText = '空席（即時案内可能）';
    content.innerHTML = `
      <div style="text-align:center;padding:50px 0;color:var(--text-dim);">
        <div style="font-size:2.5rem;">🪑</div>
        <div style="font-weight:800;font-size:1rem;color:var(--text-sub);margin-top:8px;">現在空席です</div>
        <div class="text-sm" style="margin-top:4px;">左の待合カードを選んでこの席をタップ（ドラッグでも配席できます）</div>
      </div>`;
    return;
  }

  if (t.type === 'reserved') {
    actions.style.display = 'flex';
    actions.innerHTML = `
      <div class="action-btn-row">
        <button class="btn btn-primary" style="flex:1;" onclick="seatReserved(${id})">✅ 着席する</button>
      </div>`;
    document.getElementById('d-sub').innerText = `事前予約席`;
    content.innerHTML = `<div class="hint-box">予約客の来店をお待ちしています。</div>`;
    return;
  }

  actions.style.display = 'none';

  document.getElementById('d-sub').innerText = `滞在：${t.stayTime || '利用中'}（${t.guestCount || t.userIds.length}名様）`;

  const summaryHtml = t.summary ? `
    <div class="ai-box">
      <div class="ai-box-head">🎙️ 接客・対話まとめ</div>
      <div class="ai-box-body">${t.summary}</div>
    </div>` : '';

  const guestsHtml = t.userIds.length === 0
    ? `<div style="padding:15px;background:var(--surface-sub);border:1.5px dashed var(--border-dark);border-radius:var(--radius-md);text-align:center;color:var(--text-sub);font-size:.85rem;">
        <strong>一般のお客様（カルテ未登録）</strong>
       </div>`
    : t.userIds.map((uid, index) => {
        const u = DB[uid];
        if (!u) return '';
        const uniqueAlgs = [...new Set(u.allergies.map(normalizeAllergenUI))];
        const alg = uniqueAlgs.length > 0;
        return `
          <div class="guest-card ${alg ? 'danger' : ''}" onclick="openGuest('${u.id}')">
            <div class="flex justify-between items-center">
              <span style="font-weight:800;">👤 ${u.name} ${index === 0 && t.userIds.length > 1 ? '<span class="chip chip-blue">代表</span>' : ''}</span>
              <span class="chip chip-sub">来店 ${u.count}回目</span>
            </div>
            ${alg ? `<div>${uniqueAlgs.map(a => `<span class="chip chip-red">${a}</span>`).join(' ')}</div>` : ''}
            ${u.favs.length ? `<div class="text-xs" style="color:#5c441b;">⭐ 好物: ${u.favs.join('、')}</div>` : ''}
            <div class="hint-box">
              <div class="hint-label">💡 接客メモ</div>
              <div class="hint-text">${u.hint || 'タップして情報を編集できます。'}</div>
            </div>
            <div style="text-align:right; font-size:0.72rem; color:var(--c-primary); font-weight:700;">👉 カルテを編集</div>
          </div>`;
      }).join('');

  const ordersHtml = `
    <div class="orders-box">
      <div class="orders-head"><span>注文の状況</span>
        ${t.type === 'billing' ? '' : `<button class="btn btn-secondary btn-xs" onclick="toggleMenuPicker()">＋ 追加</button>`}
      </div>
      <div class="menu-grid" id="menu-picker" style="display:none;">
        ${MENU.map(m => `<button class="menu-btn" onclick="addOrder(${m.id}, ${id})">${m.name}<small>${yen(taxIn(m.price))}</small></button>`).join('')}
      </div>
      <div id="orders-list"></div>
    </div>`;

  content.innerHTML = ordersHtml + summaryHtml + guestsHtml;
  if (ORDERS[t.sessionId]) renderOrders(id);
  refreshOrders(id);
}

/* ── 注文・会計 ── */
const yen = n => `¥${Number(n).toLocaleString('ja-JP')}`;
const taxIn = p => Math.round(p * 1.1);

function hideFooter() {
  const f = document.getElementById('d-footer');
  f.style.display = 'none';
  f.innerHTML = '';
}

async function refreshOrders(tableId) {
  const t = TABLES[tableId];
  if (!t?.sessionId) return;
  try {
    ORDERS[t.sessionId] = await (await fetch(`${API_BASE}/sessions/${t.sessionId}/orders`)).json();
    if (selectedTable === tableId) renderOrders(tableId);
  } catch (e) { console.error("注文取得エラー:", e); }
}

function renderOrders(tableId) {
  const t = TABLES[tableId];
  const data = ORDERS[t?.sessionId];
  const box = document.getElementById('orders-list');
  if (!data || !box) return;
  box.innerHTML = data.items.length ? data.items.map(i => `
    <div class="order-row">
      <span class="order-name">${i.name}</span>
      <span class="order-qty">×${i.qty}</span>
      <span class="order-price">${yen(taxIn(i.unit_price * i.qty))}</span>
      ${i.status === '提供済'
        ? `<span class="order-st served">提供済</span>`
        : `<button class="order-st pending" onclick="serveOrder(${i.id}, ${tableId})">注文中 → 提供</button>
           <button class="order-x" title="取り消し" onclick="cancelOrder(${i.id}, ${tableId})">✕</button>`}
    </div>`).join('') : `<div class="order-empty">注文はまだありません</div>`;
  renderFooter(tableId);
}

function renderFooter(tableId) {
  const t = TABLES[tableId];
  const d = ORDERS[t?.sessionId];
  const f = document.getElementById('d-footer');
  if (!d || !t || t.type === 'empty' || t.type === 'reserved') { hideFooter(); return; }
  const billing = t.type === 'billing';
  f.style.display = 'flex';
  f.innerHTML = `
    <div class="df-total">
      <div class="df-label">合計金額 <small>(税込)</small></div>
      <div class="df-sum">${yen(d.total)}</div>
      <div class="df-tax">うち消費税 ${yen(d.tax)}</div>
    </div>
    <button class="btn btn-primary df-btn" onclick="${billing ? `checkoutTable(${tableId})` : `billTable(${tableId})`}">${billing ? '会計完了・退店' : 'お会計へ'}</button>`;
}

function toggleMenuPicker() {
  const el = document.getElementById('menu-picker');
  const open = el.style.display === 'none';
  el.style.display = open ? 'grid' : 'none';
  window.pickerOpen = open;
}

async function addOrder(menuId, tableId) {
  const t = TABLES[tableId];
  if (!t?.sessionId) return;
  try {
    await fetch(`${API_BASE}/sessions/${t.sessionId}/orders`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ menu_id: menuId, qty: 1 })
    });
  } catch (e) { console.error(e); }
  await refreshOrders(tableId);
}

async function serveOrder(orderId, tableId) {
  try { await fetch(`${API_BASE}/orders/${orderId}/serve`, { method: "PUT" }); } catch (e) { console.error(e); }
  await refreshOrders(tableId);
}

async function cancelOrder(orderId, tableId) {
  try { await fetch(`${API_BASE}/orders/${orderId}`, { method: "DELETE" }); } catch (e) { console.error(e); }
  await refreshOrders(tableId);
}

function openGuest(userId) {
  editingUserId = userId;
  const u = DB[userId];
  if (!u) return;

  document.getElementById('mg-name').innerText = `${u.name} 様のカルテ`;
  document.getElementById('mg-id').innerText   = `顧客識別番号: ${u.id}`;
  renderUserForm(u, 'mg');
  document.getElementById('modal-guest').style.display = 'flex';
}

function renderUserForm(u, prefix) {
  const currentRegion = u.region || "未登録";
  const isPrefecture = PREFECTURES.filter(p => p !== "その他").includes(currentRegion);
  const selectValue = isPrefecture ? currentRegion : "その他";
  const customRegionValue = isPrefecture ? "" : (currentRegion === "その他" || currentRegion === "未登録" ? "" : currentRegion);

  const regionOptions = PREFECTURES.map(p => 
    `<option value="${p}" ${selectValue === p ? 'selected' : ''}>${p}</option>`
  ).join('');

  document.getElementById(`${prefix}-stats`).innerHTML = `
    <div class="er-item"><div class="er-label">お名前</div><input id="${prefix}-name-val" class="input-base" value="${u.name}"></div>
    <div class="er-item">
      <div class="er-label">居住地域</div>
      <select id="${prefix}-region-val" class="input-base" onchange="handleRegionChange(this, '${prefix}-region-custom')">
        ${regionOptions}
      </select>
      <input type="text" id="${prefix}-region-custom" class="input-base" 
             style="margin-top:4px; display:${selectValue === 'その他' ? 'block' : 'none'};" 
             placeholder="市区町村や海外名を入力" 
             value="${customRegionValue}">
    </div>
    <div class="er-item"><div class="er-label">累計来店回数</div><input id="${prefix}-count-val" class="input-base" type="number" value="${u.count || 1}" min="1"></div>
    <div class="er-item"><div class="er-label">最終来店</div><div style="font-size:0.8rem; font-weight:700; margin-top:4px;">${u.last || '-'}</div></div>
  `;

  renderAllergyEditor(u.allergies.map(normalizeAllergenUI), `${prefix}-allergy`);
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
    container.innerHTML = `<span class="text-muted text-xs">登録なし</span>`;
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
  if (val && !currentEditingFavs.includes(val)) {
    currentEditingFavs.push(val);
    renderFavChips(prefix);
  }
  input.value = '';
}

function removeFavMenu(prefix, index) {
  currentEditingFavs.splice(index, 1);
  renderFavChips(prefix);
}

/* ═══════════════════════════════════════════
   アレルゲンUI描画（追加品目のみ削除ボタンを表示）
═══════════════════════════════════════════ */
function renderAllergyEditor(selected, containerId) {
  const normSelected = selected.map(normalizeAllergenUI);
  document.getElementById(containerId).innerHTML = allergenMaster.map(item => {
    const isCustom = !DEFAULT_ALLERGENS.includes(item);
    return `
      <label class="allergy-label">
        <input type="checkbox" value="${item}" ${normSelected.includes(item) ? 'checked' : ''}>
        <span>${item}</span>
        ${isCustom ? `<button type="button" class="allergy-del-btn" title="マスターから削除" onclick="removeCustomAllergen(event, '${item}')">✕</button>` : ''}
      </label>`;
  }).join('');
}

function addAllergen(editorId, inputId) {
  const input = document.getElementById(inputId);
  const rawVal = input.value.trim();
  if (!rawVal) return;
  const val = normalizeAllergenUI(rawVal);

  if (!allergenMaster.includes(val)) {
    allergenMaster.push(val);
  }
  const checked = [...document.querySelectorAll(`#${editorId} input:checked`)].map(cb => normalizeAllergenUI(cb.value));
  if (!checked.includes(val)) checked.push(val);
  renderAllergyEditor(checked, editorId);
  input.value = '';
}

// ユーザーが新しく追加したアレルゲンだけを削除する処理
function removeCustomAllergen(event, allergenName) {
  event.preventDefault();
  event.stopPropagation();

  // 基本アレルゲンは削除対象外
  if (DEFAULT_ALLERGENS.includes(allergenName)) return;

  showConfirmModal(
    "アレルゲンの削除",
    `追加した「${allergenName}」を選択肢から削除しますか？`,
    "削除する",
    true,
    () => {
      allergenMaster = allergenMaster.filter(a => a !== allergenName);

      // 開いているモーダルのアレルゲン欄を即時再描画
      const guestAllergyContainer = document.getElementById('mg-allergy');
      if (guestAllergyContainer && document.getElementById('modal-guest').style.display === 'flex') {
        const checked = [...guestAllergyContainer.querySelectorAll('input:checked')].map(cb => cb.value).filter(a => a !== allergenName);
        renderAllergyEditor(checked, 'mg-allergy');
      }

      const ledgerAllergyContainer = document.getElementById('lp-allergy');
      if (ledgerAllergyContainer && document.getElementById('modal-ledger').style.display === 'flex') {
        const checked = [...ledgerAllergyContainer.querySelectorAll('input:checked')].map(cb => cb.value).filter(a => a !== allergenName);
        renderAllergyEditor(checked, 'lp-allergy');
      }

      const quickAddModal = document.getElementById('modal-add');
      if (quickAddModal && quickAddModal.style.display === 'flex') {
        const count = parseInt(document.getElementById('qa-count').value, 10) || 1;
        for (let i = 1; i <= count; i++) {
          const c = document.getElementById(`qa-allergy-${i}`);
          if (c) {
            const checked = [...c.querySelectorAll('input:checked')].map(cb => cb.value).filter(a => a !== allergenName);
            renderAllergyEditor(checked, `qa-allergy-${i}`);
          }
        }
      }
    }
  );
}

function closeGuest() {
  document.getElementById('modal-guest').style.display = 'none';
  editingUserId = null;
}

async function saveGuest() {
  if (!editingUserId) return;
  const regionSelect = document.getElementById('mg-region-val').value;
  const customRegion = document.getElementById('mg-region-custom').value.trim();
  const finalRegion = (regionSelect === "その他") ? (customRegion || "その他") : regionSelect;

  const rawAllergies = [...document.querySelectorAll('#mg-allergy input:checked')].map(cb => cb.value);
  const normalizedAllergies = [...new Set(rawAllergies.map(normalizeAllergenUI))];

  const payload = {
    name: document.getElementById('mg-name-val').value.trim() || '無名のお客様',
    region: finalRegion,
    count: parseInt(document.getElementById('mg-count-val').value, 10) || 1,
    hint: document.getElementById('mg-hint').value.trim(),
    allergies: normalizedAllergies,
    favs: [...currentEditingFavs]
  };

  try {
    await fetch(`${API_BASE}/users/${editingUserId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (err) {
    console.error("更新APIエラー:", err);
  }

  closeGuest();
  await loadDatabase();
  if (selectedTable) showDetail(selectedTable);
}

/* ═══════════════════════════════════════════
   ごみ箱・復元・完全削除の操作処理
═══════════════════════════════════════════ */
function confirmMoveToTrash() {
  if (!editingUserId) return;
  const targetUser = DB[editingUserId];
  const userName = targetUser?.name || "この顧客";

  showConfirmModal(
    "カルテをごみ箱へ移動",
    `「${userName} 様」のカルテをごみ箱へ移動しますか？\n（台帳のごみ箱タブからいつでも復元できます）`,
    "ごみ箱へ入れる",
    true,
    async () => {
      try {
        await fetch(`${API_BASE}/users/${editingUserId}/trash`, { method: "PUT" });
        waitingQueue.forEach(item => {
          item.userIds = item.userIds.filter(uid => uid !== editingUserId);
        });
        waitingQueue = waitingQueue.filter(item => item.userIds.length > 0);

        closeGuest();
        closeLedger();
        await loadDatabase();
        if (selectedTable) showDetail(selectedTable);
      } catch (err) {
        console.error("ごみ箱移動エラー:", err);
      }
    }
  );
}

function restoreUser(userId) {
  const targetUser = DB[userId];
  const userName = targetUser?.name || "この顧客";

  showConfirmModal(
    "カルテの復元",
    `「${userName} 様」のカルテをごみ箱から通常台帳へ復元しますか？`,
    "復元する",
    false,
    async () => {
      try {
        await fetch(`${API_BASE}/users/${userId}/restore`, { method: "PUT" });
        await loadDatabase();
        renderLedger(document.getElementById('lp-search').value);
      } catch (err) {
        console.error("復元エラー:", err);
      }
    }
  );
}

function purgeUser(userId) {
  const targetUser = DB[userId];
  const userName = targetUser?.name || "この顧客";

  showConfirmModal(
    "⚠️ 顧客カルテの完全削除",
    `本当に「${userName} 様」の全データをデータベースから完全に削除しますか？\n※この操作は取り消せません。過去の来店メモ・好物・アレルギー履歴もすべて消去されます。`,
    "完全に削除する",
    true,
    async () => {
      try {
        await fetch(`${API_BASE}/users/${userId}/purge`, { method: "DELETE" });
        await loadDatabase();
        renderLedger(document.getElementById('lp-search').value);
      } catch (err) {
        console.error("完全削除エラー:", err);
      }
    }
  );
}

/* ═══════════════════════════════════════════
   新規受付モーダルの開閉処理
═══════════════════════════════════════════ */
function openQuickAdd() {
  const modal = document.getElementById('modal-add');
  if (!modal) return;
  document.getElementById('qa-count').value = 2;
  renderQuickAddForms();
  modal.style.display = 'flex';
}

function closeAdd() {
  const modal = document.getElementById('modal-add');
  if (modal) {
    modal.style.display = 'none';
  }
}

function renderQuickAddForms() {
  const count = parseInt(document.getElementById('qa-count').value, 10) || 1;
  const container = document.getElementById('qa-forms-container');
  let html = '';

  const prefOpts = PREFECTURES.map(p => `<option value="${p}">${p}</option>`).join('');

  for (let i = 1; i <= count; i++) {
    const defaultPlaceholder = i === 1 ? '代表のお客様' : `お連れ様 ${i}`;

    html += `
      <div class="qa-person-card">
        <div class="flex justify-between items-center">
          <span style="font-weight:900; font-size:0.85rem;">👤 ${i}人目のお客様 ${i === 1 ? '(代表)' : ''}</span>
          <input type="text" placeholder="🔍 過去カルテ検索" style="font-size:0.75rem; padding:2px 6px;" oninput="searchExistingUser(this, ${i})">
        </div>
        <input type="hidden" id="qa-user-id-${i}" value="">
        <div style="display:grid; grid-template-columns: 1.5fr 1fr; gap:6px;">
          <div>
            <label class="form-label">お名前</label>
            <input id="qa-pname-${i}" class="input-base" type="text" placeholder="${defaultPlaceholder}">
          </div>
          <div>
            <label class="form-label">居住地域</label>
            <select id="qa-pregion-${i}" class="input-base" onchange="handleRegionChange(this, 'qa-pregion-custom-${i}')">
              ${prefOpts}
            </select>
            <input type="text" id="qa-pregion-custom-${i}" class="input-base" 
                   style="margin-top:4px; display:none;" 
                   placeholder="市区町村や海外名を入力">
          </div>
        </div>

        <div>
          <label class="form-label text-danger">アレルゲン（重要度順）</label>
          <div class="allergy-editor" id="qa-allergy-${i}"></div>
          <div class="custom-allergy-bar" style="margin-top: 6px;">
            <input type="text" id="qa-custom-allergy-${i}" class="custom-allergy-input" placeholder="＋ 表記ゆれ自動統一（例: エビ、ピーナッツ）">
            <button type="button" class="btn btn-secondary" onclick="addCustomAllergenToQuick(${i})">追加</button>
          </div>
        </div>

        <div>
          <label class="form-label">接客メモ・ノート</label>
          <textarea id="qa-hint-${i}" class="input-base" rows="2" placeholder="初回来店、お祝い利用、味の好み、話題など"></textarea>
        </div>
      </div>
    `;
  }
  container.innerHTML = html;

  // 各フォームのアレルゲンチェックボックスを描画
  for (let i = 1; i <= count; i++) {
    renderAllergyEditor([], `qa-allergy-${i}`);
  }
}

function addCustomAllergenToQuick(formIdx) {
  const input = document.getElementById(`qa-custom-allergy-${formIdx}`);
  const rawVal = input.value.trim();
  if (!rawVal) return;
  const val = normalizeAllergenUI(rawVal);

  if (!allergenMaster.includes(val)) {
    allergenMaster.push(val);
  }

  // 全フォームのアレルゲン欄を再描画（現在チェックされている状態を維持）
  const count = parseInt(document.getElementById('qa-count').value, 10) || 1;
  for (let i = 1; i <= count; i++) {
    const c = document.getElementById(`qa-allergy-${i}`);
    if (c) {
      const checked = [...c.querySelectorAll('input:checked')].map(cb => normalizeAllergenUI(cb.value));
      if (i === formIdx && !checked.includes(val)) {
        checked.push(val);
      }
      renderAllergyEditor(checked, `qa-allergy-${i}`);
    }
  }

  input.value = '';
}

function searchExistingUser(inputEl, formIdx) {
  const query = inputEl.value.trim().toLowerCase();
  if (!query) return;

  const matched = Object.values(DB).find(u => !u.is_deleted && u.name.toLowerCase().includes(query));
  if (matched) {
    document.getElementById(`qa-user-id-${formIdx}`).value = matched.id;
    document.getElementById(`qa-pname-${formIdx}`).value = matched.name;

    const isPref = PREFECTURES.filter(p => p !== "その他").includes(matched.region);
    const selectEl = document.getElementById(`qa-pregion-${formIdx}`);
    const customInput = document.getElementById(`qa-pregion-custom-${formIdx}`);

    if (isPref) {
      selectEl.value = matched.region;
      customInput.style.display = "none";
      customInput.value = "";
    } else {
      selectEl.value = "その他";
      customInput.style.display = "block";
      customInput.value = matched.region === "未登録" ? "" : matched.region;
    }

    const normUserAllergies = matched.allergies.map(normalizeAllergenUI);
    normUserAllergies.forEach(a => {
      if (!allergenMaster.includes(a)) allergenMaster.push(a);
    });
    renderAllergyEditor(normUserAllergies, `qa-allergy-${formIdx}`);
  }
}

async function submitAdd() {
  const count = parseInt(document.getElementById('qa-count').value, 10) || 1;
  const usersPayload = [];

  for (let i = 1; i <= count; i++) {
    const existingId = document.getElementById(`qa-user-id-${i}`).value || null;
    const inputEl = document.getElementById(`qa-pname-${i}`);
    const name = inputEl.value.trim() || (i === 1 ? '代表のお客様' : `お連れ様 ${i}`);

    const regionSelect = document.getElementById(`qa-pregion-${i}`).value;
    const customRegion = document.getElementById(`qa-pregion-custom-${i}`).value.trim();
    const finalRegion = (regionSelect === "その他") ? (customRegion || "その他") : regionSelect;

    const rawChecked = [...document.querySelectorAll(`#qa-allergy-${i} input:checked`)].map(cb => cb.value);
    const checked = [...new Set(rawChecked.map(normalizeAllergenUI))];

    const hintVal = document.getElementById(`qa-hint-${i}`).value.trim();
    const defaultHint = existingId ? "" : "初来店の組。";
    const finalHint = hintVal || defaultHint;

    usersPayload.push({
      user_id: existingId,
      name: name,
      region: finalRegion,
      allergies: checked,
      hint: finalHint
    });
  }

  try {
    const res = await fetch(`${API_BASE}/register-group`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ users: usersPayload })
    });
    const data = await res.json();

    waitingQueue.push({
      queueId: `q-${Date.now()}`,
      userIds: data.user_ids,
      guestsCount: count
    });
  } catch (err) {
    console.error("新規登録エラー:", err);
  }

  await loadDatabase();
  closeAdd();
  renderWaiting();
}

/* ═══════════════════════════════════════════
   顧客台帳（通常台帳 & ごみ箱管理）
═══════════════════════════════════════════ */
function openLedger() {
  document.getElementById('modal-ledger').style.display = 'flex';
  switchLedgerTab('active');
}

function closeLedger() {
  document.getElementById('modal-ledger').style.display = 'none';
  editingUserId = null;
}

function switchLedgerTab(tab) {
  currentLedgerTab = tab;
  document.getElementById('tab-active-btn').className = tab === 'active' ? 'tab-btn active' : 'tab-btn';
  document.getElementById('tab-trash-btn').className  = tab === 'trash'  ? 'tab-btn active' : 'tab-btn';

  const titleText = document.getElementById('ledger-title-text');
  const subText = document.getElementById('ledger-sub-text');

  if (tab === 'trash') {
    titleText.innerText = "🗑️ ごみ箱（削除保留中のカルテ）";
    subText.innerText = "復元、またはデータベースからの完全削除が行えます";
  } else {
    titleText.innerText = "顧客台帳";
    subText.innerText = "行をクリックするとカルテ編集へ進みます";
  }

  backLedger();
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
  const thead = document.getElementById('lp-thead');
  const tbody = document.getElementById('lp-tbody');
  const lower = kw.toLowerCase().trim();

  const isTrash = currentLedgerTab === 'trash';
  const list = Object.values(DB).filter(u => {
    if (isTrash ? !u.is_deleted : u.is_deleted) return false;
    if (!lower) return true;
    const algStr = u.allergies.map(normalizeAllergenUI).join(' ');
    return `${u.name} ${u.region} ${algStr} ${u.favs.join(' ')} ${u.hint}`.toLowerCase().includes(lower);
  });

  if (isTrash) {
    thead.innerHTML = `<tr><th>氏名</th><th>地域</th><th>来店回数</th><th>アレルゲン</th><th>操作（復元・完全削除）</th></tr>`;
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-dim);">ごみ箱は空です</td></tr>`;
      return;
    }
    tbody.innerHTML = list.map(u => {
      const uAlgs = [...new Set(u.allergies.map(normalizeAllergenUI))];
      return `
      <tr>
        <td><strong>${u.name}</strong></td>
        <td>${u.region || '未登録'}</td>
        <td>${u.count || 1}回</td>
        <td>${uAlgs.length ? uAlgs.map(a => `<span class="chip chip-red">${a}</span>`).join(' ') : '<span class="text-muted">なし</span>'}</td>
        <td>
          <button class="btn btn-secondary" style="padding:3px 8px;font-size:.72rem;margin-right:6px;" onclick="restoreUser('${u.id}')">↩️ 復元</button>
          <button class="btn btn-checkout" style="padding:3px 8px;font-size:.72rem;" onclick="purgeUser('${u.id}')">⚠️ 本当の削除</button>
        </td>
      </tr>`;
    }).join('');
  } else {
    thead.innerHTML = `<tr><th>氏名</th><th>地域</th><th>来店回数</th><th>好物・注文傾向</th><th>アレルゲン</th><th>最終来店</th><th>操作</th></tr>`;
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--text-dim);">該当する顧客は見つかりませんでした</td></tr>`;
      return;
    }
    tbody.innerHTML = list.map(u => {
      const uAlgs = [...new Set(u.allergies.map(normalizeAllergenUI))];
      return `
      <tr class="row-click" onclick="openLedgerEdit('${u.id}')">
        <td><strong>${u.name}</strong></td>
        <td>${u.region || '未登録'}</td>
        <td>${u.count || 1}回</td>
        <td>${u.favs.length ? u.favs.map(f => `⭐${f}`).join('、') : '<span class="text-muted">なし</span>'}</td>
        <td>${uAlgs.length ? uAlgs.map(a => `<span class="chip chip-red">${a}</span>`).join(' ') : '<span class="text-muted">なし</span>'}</td>
        <td>${u.last || '-'}</td>
        <td><button class="btn btn-secondary" style="padding:3px 8px;font-size:.72rem;" onclick="event.stopPropagation();openLedgerEdit('${u.id}')">編集</button></td>
      </tr>`;
    }).join('');
  }
}

function openLedgerEdit(userId) {
  editingUserId = userId;
  const u = DB[userId];
  document.getElementById('lp-list').style.display = 'none';
  document.getElementById('lp-edit').style.display = 'flex';
  document.getElementById('lp-edit-name').innerText = `${u.name} 様のカルテ編集`;
  renderUserForm(u, 'lp');
}

async function saveLedger() {
  if (!editingUserId) return;
  const regionSelect = document.getElementById('lp-region-val').value;
  const customRegion = document.getElementById('lp-region-custom').value.trim();
  const finalRegion = (regionSelect === "その他") ? (customRegion || "その他") : regionSelect;

  const rawAllergies = [...document.querySelectorAll('#lp-allergy input:checked')].map(cb => cb.value);
  const normalizedAllergies = [...new Set(rawAllergies.map(normalizeAllergenUI))];

  const payload = {
    name: document.getElementById('lp-name-val').value.trim() || '無名のお客様',
    region: finalRegion,
    count: parseInt(document.getElementById('lp-count-val').value, 10) || 1,
    hint: document.getElementById('lp-hint').value.trim(),
    allergies: normalizedAllergies,
    favs: [...currentEditingFavs]
  };

  try {
    await fetch(`${API_BASE}/users/${editingUserId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (err) {
    console.error("更新APIエラー:", err);
  }

  closeLedger();
  await loadDatabase();
  if (selectedTable) showDetail(selectedTable);
}

function initResizers() {
  const layout = document.getElementById('app-layout');
  let active = null;

  ['res-left', 'res-right'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
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

window.addEventListener('DOMContentLoaded', initApp);