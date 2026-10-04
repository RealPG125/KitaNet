/* ═══════════════════════════════════════════
   店舗接客フロントエンド（ごみ箱＆カスタムUI統合版）
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

let allergenMaster = ["エビ", "カニ", "小麦", "そば", "卵", "乳製品", "落花生", "大豆"];
let DB = {};
let TABLES = {};

let waitingQueue = [
  { queueId: "q-init-01", guestsCount: 2, userIds: ["u-0006", "u-0007"] },
  { queueId: "q-init-02", guestsCount: 1, userIds: ["u-0008"] }
];

let selectedTable = 1;
let selectedQueueId = null;
let dragItem = null;
let lastUndo = null;
let editingUserId = null;
let currentEditingFavs = [];
let deletePendingQueueId = null;
let currentLedgerTab = "active"; // "active" または "trash"
let confirmCallback = null;

async function initApp() {
  buildSeatCards();
  setupDrop();
  initResizers();
  await loadDatabase();
  renderWaiting();
  showDetail(1);

  setInterval(async () => {
    if (editingUserId) return;
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
        if (!allergenMaster.includes(a)) allergenMaster.push(a);
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
   カスタム確認モーダル（標準ポップアップ代替）
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
    div.onclick = () => showDetail(i);
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
    if (t.type === 'speaking') {
      bodyHtml = `<span class="chip chip-green">🎙️ 対話中</span>`;
    } else {
      const uniqueAlgs = [...new Set(allAllergies)];
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
    const alg = u.allergies.length > 0;
    return `
      <div class="guest-card ${alg ? 'danger' : ''}" onclick="openGuest('${u.id}')">
        <div class="flex justify-between items-center">
          <span style="font-weight:800;">👤 ${u.name} ${index === 0 && users.length > 1 ? '<span class="chip chip-blue">代表</span>' : ''}</span>
          <span class="chip chip-sub">来店 ${u.count}回目</span>
        </div>
        ${alg ? `<div>${u.allergies.map(a => `<span class="chip chip-red">${a}</span>`).join(' ')}</div>` : ''}
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
  lastUndo = { tableId, queueItem: { ...qItem } };
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

async function checkoutTable(tableId) {
  const t = TABLES[tableId];
  if (!t || t.type === 'empty') return;

  showConfirmModal(
    "お会計・退店処理",
    `${tableId}番テーブルのお会計を完了し、空席に戻しますか？`,
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
        <div class="text-sm" style="margin-top:4px;">左の待合リストからドラッグ＆ドロップして配席してください</div>
      </div>`;
    return;
  }

  if (t.type === 'reserved') {
    actions.style.display = 'flex';
    actions.innerHTML = `
      <div class="action-btn-row">
        <button class="btn btn-primary" style="flex:1;" onclick="checkoutTable(${id})">✅ 予約解除・着席完了</button>
      </div>`;
    document.getElementById('d-sub').innerText = `事前予約席`;
    content.innerHTML = `<div class="hint-box">予約客の来店をお待ちしています。</div>`;
    return;
  }

  actions.style.display = 'flex';
  actions.innerHTML = `
    <div class="action-btn-row">
      <button class="btn btn-checkout" onclick="checkoutTable(${id})">🧾 会計・退店処理</button>
    </div>`;

  document.getElementById('d-sub').innerText = `滞在：${t.stayTime || '利用中'}（${t.guestCount || t.userIds.length}名様）`;

  const summaryHtml = t.summary ? `
    <div class="ai-box">
      <div class="ai-box-head">🎙️ 接客・対話まとめ (ConversationMemory)</div>
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
              <span style="font-weight:800;">👤 ${u.name} ${index === 0 && t.userIds.length > 1 ? '<span class="chip chip-blue">代表</span>' : ''}</span>
              <span class="chip chip-sub">来店 ${u.count}回目</span>
            </div>
            ${alg ? `<div>${u.allergies.map(a => `<span class="chip chip-red">${a}</span>`).join(' ')}</div>` : ''}
            ${u.favs.length ? `<div class="text-xs" style="color:#5c441b;">⭐ 好物: ${u.favs.join('、')}</div>` : ''}
            <div class="hint-box">
              <div class="hint-label">💡 接客メモ (UserMemory)</div>
              <div class="hint-text">${u.hint || 'タップして情報を編集できます。'}</div>
            </div>
            <div style="text-align:right; font-size:0.72rem; color:var(--c-primary); font-weight:700;">👉 カルテを編集</div>
          </div>`;
      }).join('');

  content.innerHTML = summaryHtml + guestsHtml;
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

function closeGuest() {
  document.getElementById('modal-guest').style.display = 'none';
  editingUserId = null;
}

async function saveGuest() {
  if (!editingUserId) return;
  const regionSelect = document.getElementById('mg-region-val').value;
  const customRegion = document.getElementById('mg-region-custom').value.trim();
  const finalRegion = (regionSelect === "その他") ? (customRegion || "その他") : regionSelect;

  const payload = {
    name: document.getElementById('mg-name-val').value.trim() || '無名のお客様',
    region: finalRegion,
    count: parseInt(document.getElementById('mg-count-val').value, 10) || 1,
    hint: document.getElementById('mg-hint').value.trim(),
    allergies: [...document.querySelectorAll('#mg-allergy input:checked')].map(cb => cb.value),
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
// 1. ごみ箱に入れる（論理削除）
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

// 2. ごみ箱から復元する
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

// 3. 本当の削除（完全抹消・物理削除）
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
                   placeholder="手動入力">
          </div>
        </div>
        <div>
          <label class="form-label text-danger">アレルゲン</label>
          <div class="allergy-editor" id="qa-allergy-${i}">
            ${allergenMaster.map(item => `
              <label class="allergy-label">
                <input type="checkbox" value="${item}">
                <span>${item}</span>
              </label>
            `).join('')}
          </div>
        </div>
      </div>
    `;
  }
  container.innerHTML = html;
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

    const cbs = document.querySelectorAll(`#qa-allergy-${formIdx} input`);
    cbs.forEach(cb => {
      cb.checked = matched.allergies.includes(cb.value);
    });
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

    const checked = [...document.querySelectorAll(`#qa-allergy-${i} input:checked`)].map(cb => cb.value);

    usersPayload.push({
      user_id: existingId,
      name: name,
      region: finalRegion,
      allergies: checked,
      hint: existingId ? "" : "初来店の組。"
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

  // タブに応じて通常顧客かごみ箱顧客かをフィルタ
  const isTrash = currentLedgerTab === 'trash';
  const list = Object.values(DB).filter(u => {
    if (isTrash ? !u.is_deleted : u.is_deleted) return false;
    if (!lower) return true;
    return `${u.name} ${u.region} ${u.allergies.join(' ')} ${u.favs.join(' ')} ${u.hint}`.toLowerCase().includes(lower);
  });

  if (isTrash) {
    thead.innerHTML = `<tr><th>氏名</th><th>地域</th><th>来店回数</th><th>アレルゲン</th><th>操作（復元・完全削除）</th></tr>`;
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-dim);">ごみ箱は空です</td></tr>`;
      return;
    }
    tbody.innerHTML = list.map(u => `
      <tr>
        <td><strong>${u.name}</strong></td>
        <td>${u.region || '未登録'}</td>
        <td>${u.count || 1}回</td>
        <td>${u.allergies.length ? u.allergies.map(a => `<span class="chip chip-red">${a}</span>`).join(' ') : '<span class="text-muted">なし</span>'}</td>
        <td>
          <button class="btn btn-secondary" style="padding:3px 8px;font-size:.72rem;margin-right:6px;" onclick="restoreUser('${u.id}')">↩️ 復元</button>
          <button class="btn btn-checkout" style="padding:3px 8px;font-size:.72rem;" onclick="purgeUser('${u.id}')">⚠️ 本当の削除</button>
        </td>
      </tr>`).join('');
  } else {
    thead.innerHTML = `<tr><th>氏名</th><th>地域</th><th>来店回数</th><th>好物・注文傾向</th><th>アレルゲン</th><th>最終来店</th><th>操作</th></tr>`;
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

  const payload = {
    name: document.getElementById('lp-name-val').value.trim() || '無名のお客様',
    region: finalRegion,
    count: parseInt(document.getElementById('lp-count-val').value, 10) || 1,
    hint: document.getElementById('lp-hint').value.trim(),
    allergies: [...document.querySelectorAll('#lp-allergy input:checked')].map(cb => cb.value),
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