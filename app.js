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
const DEFAULT_ALLERGENS = [
  "卵", "乳", "小麦", "くるみ", "落花生（ピーナッツ）", "そば", "えび", "かに", "カシューナッツ",
  "大豆", "キウイフルーツ", "バナナ", "もも", "りんご", "オレンジ",
  "アーモンド", "ピスタチオ", "マカダミアナッツ", "さけ", "さば", "いくら", "いか",
  "あわび", "ごま", "牛肉", "豚肉", "鶏肉", "やまいも", "ゼラチン"
];
let allergenMaster = [...DEFAULT_ALLERGENS];
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
let waitingQueue = [];
let selectedTable = '1';
let selectedQueueId = null;
let dragItem = null;
let lastUndo = null;
let editingUserId = null;
let currentEditingFavs = [];
let deletePendingQueueId = null;
let currentLedgerTab = "active";
let confirmCallback = null;
async function initApp() {
  setupFloorGestures();
  try { waitingQueue = await (await fetch(`${API_BASE}/waiting-queue`)).json(); } catch (e) { console.error(e); }
  try { MENU = await (await fetch(`${API_BASE}/menu`)).json(); } catch (e) { console.error(e); }
  await loadDatabase();
  renderFloor();
  renderWaiting();
  showDetail('1');
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
const FLOORS = {
  '1F': {
    size: [1100, 1460],
    bounds: [30, 60, 1060, 1445],
    rooms: [
      ['事<br>務<br>所',58,493,110,207,'v'], ['WC',58,700,110,72,'s'], ['WC',58,772,180,63,'s'], ['階<br>段',238,670,72,165,'v'],
      ['厨房',700,585,330,80,'l bare'], ['テラス',330,1030,300,80,'l bare'], ['鉄板<br>カウンター',912,1150,120,110,'t bare']
    ],
    walls: 'M310 605L347 635L450 540L635 370L347 120L58 370L238 535V565H168M238 605V930M300 150L275 128L347 57L455 152L420 182M598 462H1030V960M450 540L705 770V898H815V960H1030M58 495V960L705 1365M58 960H745M705 960V1365H780V1428H1030V960',
    teppan: 'M950 1045L805 1195L925 1350H1030',
    pillars: [[288,296],[435,296],[285,420],[435,420]],
    dividers: [[240,260,78,32,45],[315,222,135,32,45],[470,262,58,7,-45],[480,455,85,32,45],[305,884,92,26,90]],
    tables: [
      ['3',150,372,118,78,{},45], ['4A',226,436,66,66,{},45], ['1',492,322,66,66,{},45], ['2',545,392,90,70,{},45],
      ['4B',405,556,70,70,{},45],
      ['A',342,752,62,76,{}], ['D',490,804,90,62,{}], ['C',652,833,100,66,{}],
      ['5',150,892,110,70,{}], ['B',501,915,86,84,{}],
      ['T1',902,1081,62,52,{},-46], ['T2',854,1131,62,52,{},-46], ['T3',806,1181,62,52,{},-46],
      ['T4',876,1195,54,54,{},0],
      ['T5',787,1265,62,52,{},52], ['T6',830,1318,62,52,{},52], ['T7',873,1371,62,52,{},52]
    ]
  },
  '2F': {
    size: [1100, 1085],
    bounds: [0, 0, 1100, 1085],
    rooms: [['WC',33,33,108,66,'s'],['階段',213,259,108,254,'v'],['パントリー',767,133,146,380,'s']],
    walls: 'M33 613V33H213V613H843V1053M321 513H437L547 419L657 513H767M915 513V613H1057',
    tables: [
      ['8',112,193,110,64,{r:1,bench:1}], ['9',112,303,110,64,{r:1,bench:1}],
      ['10',112,417,110,64,{r:1,bench:1}], ['11',112,545,110,64,{r:1,bench:1}],
      ['12',547,485,80,52,{l:1,r:1}], ['13',977,739,110,70,{t:2,b:2}],
      ['14A',887,819,80,60,{t:1,b:1}], ['14B',1037,923,80,60,{t:1,b:1}], ['15',909,957,110,70,{t:2,b:2}]
    ]
  }
};
Object.values(FLOORS).forEach(f => f.ids = f.tables.map(t => t[0]));
let currentFloor = '1F';
const ALLERGEN_FILES = {
  "卵": "egg", "乳": "milk", "小麦": "wheat", "くるみ": "walnut", "落花生（ピーナッツ）": "peanut",
  "そば": "buckwheat", "えび": "shrimp", "かに": "crab", "カシューナッツ": "cashew", "大豆": "soybean",
  "キウイフルーツ": "kiwi", "バナナ": "banana", "もも": "peach", "りんご": "apple", "オレンジ": "orange",
  "アーモンド": "almond", "ピスタチオ": "pistachio", "マカダミアナッツ": "macadamia", "さけ": "salmon",
  "さば": "mackerel", "いくら": "ikura", "いか": "squid", "あわび": "abalone", "ごま": "sesame",
  "牛肉": "beef", "豚肉": "pork", "鶏肉": "chicken", "やまいも": "yam", "ゼラチン": "gelatin"
};
const allergenImg = (name, cls = 'alg-ico') =>
  `<img class="${cls}" src="img/allergens/${ALLERGEN_FILES[name] || 'other'}.png" alt="${name}" title="${name}" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'chip chip-red',textContent:this.alt}))">`;
const tableNo = id => /^\d+$/.test(id) ? Number(id) : id;
function makeCard(id, style = '') {
  const div = document.createElement('div');
  div.id = `tbl-${id}`;
  div.style.cssText = style;
  div.onclick = () => {
    if (!TABLES[id]) return;
    const q = waitingQueue.find(x => x.queueId === selectedQueueId);
    if (q && TABLES[id].type === 'empty') assign(id, q);
    else showDetail(id);
  };
  div.addEventListener('dragover', e => {
    if (TABLES[id]?.type === 'empty') { e.preventDefault(); div.classList.add('drag-over'); }
  });
  div.addEventListener('dragleave', () => div.classList.remove('drag-over'));
  div.addEventListener('drop', e => {
    e.preventDefault();
    div.classList.remove('drag-over');
    if (dragItem && TABLES[id]?.type === 'empty') assign(id, dragItem);
  });
  return div;
}
function chairHtml(w, h, c) {
  const out = [];
  const line = (n, fn) => { for (let i = 0; i < n; i++) out.push(fn((i - (n - 1) / 2) * 40)); };
  line(c.t || 0, o => [o, -h / 2 - 16]); line(c.b || 0, o => [o, h / 2 + 16]);
  line(c.l || 0, o => [-w / 2 - 18, o]); line(c.r || 0, o => [w / 2 + 18, o]);
  const chairs = out.map(([x, y]) => `<i class="chair" style="left:${x - 12}px;top:${y - 12}px"></i>`);
  if (c.bench) chairs.push(`<i class="bench" style="left:${-w / 2 - 20}px;top:${-h / 2}px;height:${h}px"></i>`);
  return chairs.join('');
}
// 回転したテーブル内に収まる「水平な」表示領域のサイズ（左上=卓番/右上=人数/中央=状況/左下=アレルゲン）
function innerBox(w, h, rotDeg) {
  const r = rotDeg * Math.PI / 180, c = Math.abs(Math.cos(r)), s = Math.abs(Math.sin(r));
  const ratio = Math.min(1.6, Math.max(1.15, w / h));
  const a = Math.min((w / 2 - 3) / (c + s / ratio), (h / 2 - 3) / (s + c / ratio));
  return [2 * a, 2 * a / ratio];
}
function renderFloor() {
  const canvas = document.getElementById('floor-canvas');
  canvas.innerHTML = '';
  document.querySelectorAll('.floor-switch .tab-btn').forEach(b => b.classList.toggle('active', b.dataset.floor === currentFloor));
  const f = FLOORS[currentFloor];
  const plan = document.createElement('div');
  plan.className = 'plan';
  plan.style.cssText = `width:${f.size[0]}px;height:${f.size[1]}px`;
  plan.dataset.bounds = f.bounds.join(',');
  plan.innerHTML = `<svg class="plan-walls" viewBox="0 0 ${f.size.join(' ')}"><path d="${f.walls}"/>` +
    `${f.teppan ? `<path class="teppan" d="${f.teppan}"/>` : ''}` +
    `${(f.pillars || []).map(([x, y]) => `<circle class="plan-pillar" cx="${x}" cy="${y}" r="17"/>`).join('')}</svg>` +
    (f.dividers || []).map(([x, y, l, t, a]) => `<div class="divider" style="left:${x}px;top:${y}px;width:${l}px;height:${t}px;--a:${a}deg"></div>`).join('') +
    f.rooms.map(([n, x, y, w, h, t = '']) => `<div class="facility ${t}" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px">${n}</div>`).join('');
  f.tables.forEach(([id, cx, cy, w, h, c, rot = 0]) => {
    const holder = document.createElement('div');
    holder.className = 'tbl-holder';
    holder.style.cssText = `left:${cx}px;top:${cy}px;transform:rotate(${rot}deg)`;
    holder.innerHTML = chairHtml(w, h, c);
    const card = makeCard(id, `--w:${w}px;--h:${h}px;left:${-w / 2}px;top:${-h / 2}px;right:auto;bottom:auto`);
    const [iw, ih] = innerBox(w, h, rot);
    card.dataset.rot = rot; card.dataset.iw = iw.toFixed(1); card.dataset.ih = ih.toFixed(1);
    holder.appendChild(card);
    plan.appendChild(holder);
  });
  canvas.appendChild(plan);
  canvas.appendChild(buildZoomControls());
  fitPlan();
  refreshAllCards();
}
const ZOOM_MIN = 0.7, ZOOM_MAX = 4, ZOOM_STEP = 1.25, PAN_PAD = 24;
let view = { z: 1, x: 0, y: 0 };
let panDrag = null;
function planGeom() {
  const plan = document.querySelector('.plan');
  if (!plan) return null;
  const c = document.getElementById('floor-canvas');
  const [x0, y0, x1, y1] = plan.dataset.bounds.split(',').map(Number);
  const w = x1 - x0, h = y1 - y0;
  const base = Math.min(c.clientWidth / w, c.clientHeight / h) * 0.98;
  const origin = k => [(c.clientWidth - w * k) / 2 - x0 * k, (c.clientHeight - h * k) / 2 - y0 * k];
  return { plan, c, base, origin, x0, y0, x1, y1 };
}
// 平面図がキャンバスの外へ行き過ぎないように移動範囲を制限
function clampAxis(v, lo, hi, o, k, cs) {
  const s0 = o + lo * k, s1 = o + hi * k;
  if (s1 - s0 <= cs - 2 * PAN_PAD) return 0;
  return Math.min(Math.max(v, cs - PAN_PAD - s1), PAN_PAD - s0);
}
function fitPlan() {
  const g = planGeom();
  if (!g) return;
  const k = g.base * view.z;
  const [ox, oy] = g.origin(k);
  view.x = clampAxis(view.x, g.x0, g.x1, ox, k, g.c.clientWidth);
  view.y = clampAxis(view.y, g.y0, g.y1, oy, k, g.c.clientHeight);
  g.plan.style.transform = `scale(${k})`;
  g.plan.style.left = `${ox + view.x}px`;
  g.plan.style.top = `${oy + view.y}px`;
  const label = document.querySelector('.zoom-pct');
  if (label) label.textContent = `${Math.round(view.z * 100)}%`;
}
function zoomTo(z, px, py) {
  const g = planGeom();
  if (!g) return;
  const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
  const kOld = g.base * view.z, kNew = g.base * next;
  const [ox, oy] = g.origin(kOld);
  const qx = (px - ox - view.x) / kOld, qy = (py - oy - view.y) / kOld;
  const [nx, ny] = g.origin(kNew);
  view = { z: next, x: px - qx * kNew - nx, y: py - qy * kNew - ny };
  fitPlan();
}
function zoomBy(factor) {
  const c = document.getElementById('floor-canvas');
  zoomTo(view.z * factor, c.clientWidth / 2, c.clientHeight / 2);
}
function resetView() {
  view = { z: 1, x: 0, y: 0 };
  fitPlan();
}
function buildZoomControls() {
  const box = document.createElement('div');
  box.className = 'zoom-ctl';
  box.innerHTML = `<button type="button" data-zoom="in" title="拡大" aria-label="拡大">＋</button>` +
    `<button type="button" class="zoom-pct" data-zoom="reset" title="表示をリセット" aria-label="表示をリセット">100%</button>` +
    `<button type="button" data-zoom="out" title="縮小" aria-label="縮小">－</button>`;
  box.addEventListener('click', e => {
    const mode = e.target.closest('button')?.dataset.zoom;
    if (mode === 'in') zoomBy(ZOOM_STEP);
    else if (mode === 'out') zoomBy(1 / ZOOM_STEP);
    else if (mode === 'reset') resetView();
  });
  return box;
}
function setupFloorGestures() {
  const canvas = document.getElementById('floor-canvas');
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const r = canvas.getBoundingClientRect();
    zoomTo(view.z * (e.deltaY < 0 ? 1.12 : 1 / 1.12), e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  canvas.addEventListener('pointerdown', e => {
    if (e.target.closest('.seat-card, .zoom-ctl')) return;
    panDrag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    canvas.setPointerCapture(e.pointerId);
    canvas.classList.add('panning');
  });
  canvas.addEventListener('pointermove', e => {
    if (!panDrag) return;
    view.x = panDrag.vx + e.clientX - panDrag.x;
    view.y = panDrag.vy + e.clientY - panDrag.y;
    fitPlan();
  });
  const endPan = () => {
    panDrag = null;
    canvas.classList.remove('panning');
  };
  canvas.addEventListener('pointerup', endPan);
  canvas.addEventListener('pointercancel', endPan);
}
const PLAN_CSS = `
.plan .facility.bare { background: none; border: none; box-shadow: none; white-space: nowrap; }
.floor-canvas { min-width: 0; min-height: 0; touch-action: none; cursor: grab; }
.floor-canvas.panning { cursor: grabbing; }
.floor-canvas .seat-card { cursor: pointer; }
.zoom-ctl { position: absolute; right: 14px; top: 14px; z-index: 20; display: flex; flex-direction: column; gap: 6px; cursor: default; }
.zoom-ctl button { width: 46px; height: 46px; padding: 0; border: 2px solid var(--wood-d); border-radius: 8px; background: #fbf6e6; color: var(--sumi); font: 800 1.5rem/1 var(--f-sans); cursor: pointer; box-shadow: 0 2px 0 rgba(40, 30, 10, .3); }
.zoom-ctl button:hover { background: #fff; }
.zoom-ctl button:active { transform: translateY(1px); }
.zoom-ctl .zoom-pct { height: 30px; font-size: .78rem; }
`;
document.head.appendChild(Object.assign(document.createElement('style'), { textContent: PLAN_CSS }));
function switchFloor(floor) {
  currentFloor = floor;
  view = { z: 1, x: 0, y: 0 };
  renderFloor();
  showDetail(FLOORS[floor].ids[0]);
}
window.addEventListener('resize', fitPlan);
function refreshAllCards() {
  FLOORS[currentFloor].ids.forEach(refreshCard);
}
function refreshCard(id) {
  const t = TABLES[id];
  const el = document.getElementById(`tbl-${id}`);
  if (!el) return;
  const iw = el.dataset.iw, ih = el.dataset.ih, rot = Number(el.dataset.rot || 0);
  const wrap = inner => `<div class="s-in" style="width:${iw}px;height:${ih}px;--m:${ih}px;transform:translate(-50%,-50%) rotate(${-rot}deg)">${inner}</div>`;
  if (!t) {
    el.className = 'seat-card is-off';
    el.innerHTML = wrap(`<b class="c-tl">${id}</b>`);
    return;
  }
  const allAllergies = [...new Set(t.userIds.flatMap(uid => DB[uid]?.allergies ?? []).map(normalizeAllergenUI))];
  let cls = 'seat-card is-empty', status = '空席', count = '';
  if (t.type === 'reserved') {
    cls = 'seat-card is-reserved'; status = t.reserveTime || '予約';
  } else if (t.type === 'billing') {
    cls = 'seat-card is-billing'; status = '会計中'; count = `${t.guestCount}名`;
  } else if (t.type === 'speaking') {
    cls = 'seat-card speaking'; status = '接客中 🎙️'; count = `${t.guestCount}名`;
  } else if (t.type === 'active') {
    cls = allAllergies.length ? 'seat-card has-allergy' : 'seat-card no-ai';
    status = '利用中'; count = `${t.guestCount}名`;
  }
  const maxShow = Number(ih) >= 56 ? 4 : 3;
  const algs = allAllergies.slice(0, maxShow).map(a => allergenImg(a)).join('') +
    (allAllergies.length > maxShow ? `<span class="alg-more">+${allAllergies.length - maxShow}</span>` : '');
  el.className = cls + (selectedTable === id && selectedQueueId === null ? ' active' : '');
  el.innerHTML = wrap(`<b class="c-tl">${id}</b><span class="c-tr">${count}</span><span class="c-mid">${status}</span><span class="c-bl">${algs}</span>`);
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
    const groupTitle = repName;
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
    `「${guestName}」の受付を待合リストから削除しますか？`,
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
  document.getElementById('d-sub').innerText = `ご案内待ち（${item.guestsCount}名）`;
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
        ${alg ? `<div class="alg-list">${uniqueAlgs.map(a => `<span class="alg-item">${allergenImg(a, 'alg-ico-lg')}</span>`).join('')}</div>` : ''}
        ${u.favs.length ? `<div class="text-xs" style="color:#5c441b;">⭐ 好物: ${u.favs.join('、')}</div>` : ''}
        <div class="hint-box">
          <div class="hint-label">メモ</div>
          <div class="hint-text">${u.hint || 'タップして情報を追加・編集できます。'}</div>
        </div>
      </div>`;
  }).join('');
}
function onDragStart(e, queueId) {
  dragItem = waitingQueue.find(q => q.queueId === queueId) ?? null;
  e.dataTransfer.setData('text/plain', queueId);
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
        table_id: tableNo(tableId),
        user_ids: qItem.userIds,
        session_id: sessionId
      })
    });
  } catch (err) {
    console.error("配席APIエラー:", err);
  }
  const undoBtn = document.getElementById('undo-btn');
  const repName = DB[qItem.userIds[0]]?.name || 'お客様';
  document.getElementById('undo-desc').innerText = `${repName}の${tableId}番卓への案内を取り消す`;
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
        <button class="btn btn-primary" style="flex:1;" onclick="seatReserved('${id}')">✅ 着席する</button>
      </div>`;
    document.getElementById('d-sub').innerText = `事前予約席`;
    content.innerHTML = `<div class="hint-box">予約客の来店をお待ちしています。</div>`;
    return;
  }
  actions.style.display = 'none';
  document.getElementById('d-sub').innerText = `滞在：${t.stayTime || '利用中'}（${t.guestCount || t.userIds.length}名）`;
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
            ${alg ? `<div class="alg-list">${uniqueAlgs.map(a => `<span class="alg-item">${allergenImg(a, 'alg-ico-lg')}</span>`).join('')}</div>` : ''}
            ${u.favs.length ? `<div class="text-xs" style="color:#5c441b;">⭐ 好物: ${u.favs.join('、')}</div>` : ''}
            <div class="hint-box">
              <div class="hint-label">メモ</div>
              <div class="hint-text">${u.hint || 'タップして情報を編集できます。'}</div>
            </div>
            <div style="text-align:right; font-size:0.72rem; color:var(--c-primary); font-weight:700;">カルテを編集</div>
          </div>`;
      }).join('');
  const ordersHtml = `
    <div class="orders-box">
      <div class="orders-head"><span>注文の状況</span>
        ${t.type === 'billing' ? '' : `<button class="btn btn-secondary btn-xs" onclick="toggleMenuPicker()">＋ 注文を追加</button>`}
      </div>
      <div class="menu-grid" id="menu-picker" style="display:none;">
        ${MENU.map(m => `<button class="menu-btn" onclick="addOrder(${m.id}, '${id}')">${m.name}<small>${yen(taxIn(m.price))}</small></button>`).join('')}
      </div>
      <div id="orders-list"></div>
    </div>`;
  content.innerHTML = ordersHtml + summaryHtml + guestsHtml;
  if (ORDERS[t.sessionId]) renderOrders(id);
  refreshOrders(id);
}
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
  const tid = `'${tableId}'`;
  box.innerHTML = data.items.length ? data.items.map(i => {
    const pending = i.status !== '提供済';
    const qty = pending
      ? `<span class="qty-ctl"><button onclick="changeQty(${i.id}, ${i.menu_id}, ${i.qty - 1}, ${tid})">−</button>${i.qty}<button onclick="changeQty(${i.id}, ${i.menu_id}, ${i.qty + 1}, ${tid})">＋</button></span>`
      : `<span class="order-qty">×${i.qty}</span>`;
    return `
    <div class="order-row">
      <span class="order-name">${i.name}</span>
      ${qty}
      <span class="order-price">${yen(taxIn(i.unit_price * i.qty))}</span>
      ${pending
        ? `<button class="order-st pending" onclick="serveOrder(${i.id}, ${tid})">提供する</button>
           <button class="order-x" title="削除" onclick="cancelOrder(${i.id}, ${tid})">✕</button>`
        : `<span class="order-st served">提供済</span>`}
    </div>`;
  }).join('') : `<div class="order-empty">注文はまだありません</div>`;
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
    <button class="btn btn-primary df-btn" onclick="${billing ? `checkoutTable('${tableId}')` : `billTable('${tableId}')`}">${billing ? '会計完了・退店' : 'お会計へ'}</button>`;
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
async function changeQty(orderId, menuId, qty, tableId) {
  if (qty < 1) return cancelOrder(orderId, tableId);
  const t = TABLES[tableId];
  try {
    await fetch(`${API_BASE}/orders/${orderId}`, { method: "DELETE" });
    await fetch(`${API_BASE}/sessions/${t.sessionId}/orders`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ menu_id: menuId, qty })
    });
  } catch (e) { console.error(e); }
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
  document.getElementById('mg-name').innerText = u.name;
  renderUserForm(u, 'mg');
  document.getElementById('modal-guest').style.display = 'flex';
}
function editorBody(p, ph = '') {
  return `
    <div><div class="section-title">顧客基本情報</div><div class="er-grid" id="${p}-stats"></div></div>
    <div>
      <div class="section-title text-danger">アレルゲン登録・変更</div>
      <div class="allergy-editor" id="${p}-allergy"></div>
      <div class="custom-allergy-bar">
        <input type="text" id="${p}-custom" class="custom-allergy-input" placeholder="＋ 独自アレルゲン（例: キウイ）">
        <button class="btn btn-secondary" onclick="addAllergen('${p}-allergy','${p}-custom')">追加</button>
      </div>
    </div>
    <div>
      <div class="section-title">好物</div>
      <div id="${p}-favs-chips" class="fav-chips-wrap"></div>
      <div class="custom-allergy-bar" style="margin-top:6px;">
        <input type="text" id="${p}-fav-input" class="custom-allergy-input" placeholder="＋ 好物（例: 鯛めし）">
        <button class="btn btn-secondary" onclick="addFavMenu('${p}')">追加</button>
      </div>
    </div>
    <div><div class="section-title">注文傾向</div><div id="${p}-trend" class="note-line"></div></div>
    <div><div class="section-title">メモ</div><textarea id="${p}-hint" class="input-base" rows="3"${ph ? ` placeholder="${ph}"` : ''}></textarea></div>
    <div>
      <div class="section-title">履歴</div>
      <table class="tbl"><thead><tr><th>卓番</th><th>入店</th><th>退店</th></tr></thead><tbody id="${p}-sessions"></tbody></table>
    </div>`;
}
document.getElementById('mg-body').innerHTML = editorBody('mg', '話題、趣味、好みの味付けなど');
document.getElementById('lp-body').innerHTML = editorBody('lp');
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
  document.getElementById(`${prefix}-trend`).innerText = u.trend || '未集計';
  document.getElementById(`${prefix}-hint`).value = u.hint || '';
  document.getElementById(`${prefix}-sessions`).innerHTML = u.sessions?.length
    ? u.sessions.map(s => `<tr><td>${s.tId}番卓</td><td>${s.in}</td><td>${s.out}</td></tr>`).join('')
    : '<tr><td colspan="3" style="text-align:center;color:var(--text-dim)">履歴なし</td></tr>';
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
  const normSelected = selected.map(normalizeAllergenUI);
  document.getElementById(containerId).innerHTML = allergenMaster.map(item => {
    const isCustom = !DEFAULT_ALLERGENS.includes(item);
    return `
      <label class="allergy-label alg-tile">
        <input type="checkbox" value="${item}" ${normSelected.includes(item) ? 'checked' : ''}>
        ${allergenImg(item, 'alg-ico-lg')}
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
function removeCustomAllergen(event, allergenName) {
  event.preventDefault();
  event.stopPropagation();
  if (DEFAULT_ALLERGENS.includes(allergenName)) return;
  showConfirmModal(
    "アレルゲンの削除",
    `追加した「${allergenName}」を選択肢から削除しますか？`,
    "削除する",
    true,
    () => {
      allergenMaster = allergenMaster.filter(a => a !== allergenName);
      const strip = id => {
        const c = document.getElementById(id);
        if (c) renderAllergyEditor([...c.querySelectorAll('input:checked')].map(cb => cb.value).filter(a => a !== allergenName), id);
      };
      const isOpen = id => document.getElementById(id)?.style.display === 'flex';
      if (isOpen('modal-guest')) strip('mg-allergy');
      if (isOpen('modal-ledger')) strip('lp-allergy');
      if (isOpen('modal-add')) {
        const count = parseInt(document.getElementById('qa-count').value, 10) || 1;
        for (let i = 1; i <= count; i++) strip(`qa-allergy-${i}`);
      }
    }
  );
}
function closeGuest() {
  document.getElementById('modal-guest').style.display = 'none';
  editingUserId = null;
}
async function saveUser(prefix, close) {
  if (!editingUserId) return;
  const $ = id => document.getElementById(`${prefix}-${id}`);
  const region = $('region-val').value;
  const custom = $('region-custom').value.trim();
  const payload = {
    name: $('name-val').value.trim() || '無名のお客様',
    region: region === "その他" ? (custom || "その他") : region,
    count: parseInt($('count-val').value, 10) || 1,
    hint: $('hint').value.trim(),
    allergies: [...new Set([...document.querySelectorAll(`#${prefix}-allergy input:checked`)].map(cb => normalizeAllergenUI(cb.value)))],
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
  close();
  await loadDatabase();
  if (selectedTable) showDetail(selectedTable);
}
function saveGuest()  { return saveUser('mg', closeGuest); }
function saveLedger() { return saveUser('lp', closeLedger); }
function confirmMoveToTrash() {
  if (!editingUserId) return;
  const userName = userLabel(editingUserId);
  showConfirmModal(
    "カルテをごみ箱へ移動",
    `「${userName}」のカルテをごみ箱へ移動しますか？\n（台帳のごみ箱タブからいつでも復元できます）`,
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
function userLabel(userId) {
  return DB[userId]?.name || "この顧客";
}
async function ledgerCall(userId, path, method, errLabel) {
  try {
    await fetch(`${API_BASE}/users/${userId}/${path}`, { method });
    await loadDatabase();
    filterLedger();
  } catch (err) {
    console.error(errLabel, err);
  }
}
function restoreUser(userId) {
  showConfirmModal(
    "カルテの復元",
    `「${userLabel(userId)}」のカルテを台帳へ復元しますか？`,
    "復元する",
    false,
    () => ledgerCall(userId, 'restore', 'PUT', "復元エラー:")
  );
}
function purgeUser(userId) {
  showConfirmModal(
    "⚠️ 顧客カルテの完全削除",
    `「${userLabel(userId)}」の全データをデータベースから完全に削除しますか？\n※この操作は取り消せません。過去の来店メモ・好物・アレルギー履歴もすべて消去されます。`,
    "完全に削除する",
    true,
    () => ledgerCall(userId, 'purge', 'DELETE', "完全削除エラー:")
  );
}
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
          <label class="form-label">メモ</label>
          <textarea id="qa-hint-${i}" class="input-base" rows="2" placeholder="初回来店、お祝い利用、味の好み、話題など"></textarea>
        </div>
      </div>
    `;
  }
  container.innerHTML = html;
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
    subText.innerText = "";
  }
  backLedger();
}
function backLedger() {
  document.getElementById('lp-list').style.display = 'flex';
  document.getElementById('lp-edit').style.display = 'none';
  filterLedger();
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
        <td>${uAlgs.length ? uAlgs.map(a => allergenImg(a)).join(' ') : '<span class="text-muted">なし</span>'}</td>
        <td>
          <button class="btn btn-secondary" style="padding:3px 8px;font-size:.72rem;margin-right:6px;" onclick="restoreUser('${u.id}')">↩️ 復元</button>
          <button class="btn btn-checkout" style="padding:3px 8px;font-size:.72rem;" onclick="purgeUser('${u.id}')">⚠️ 本当の削除</button>
        </td>
      </tr>`;
    }).join('');
  } else {
    thead.innerHTML = `<tr><th>氏名</th><th>地域</th><th>来店回数</th><th>好物</th><th>アレルゲン</th><th>最終来店</th><th>操作</th></tr>`;
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
        <td>${uAlgs.length ? uAlgs.map(a => allergenImg(a)).join(' ') : '<span class="text-muted">なし</span>'}</td>
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
  document.getElementById('lp-edit-name').innerText = u.name;
  renderUserForm(u, 'lp');
}
window.addEventListener('DOMContentLoaded', initApp);