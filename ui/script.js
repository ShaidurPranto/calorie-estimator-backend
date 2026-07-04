// ==========================================
// CONFIGURATION
// ==========================================
const BASE_URL = 'http://localhost:8000';
// When deployed, change this to something like 'https://your-api-domain.com'

const CIRCUMFERENCE = 2 * Math.PI * 52; // matches r=52 in the SVG ring

const state = {
  top: null,
  side: null,
};

const els = {
  tray: document.getElementById('tray'),
  slotTop: document.getElementById('slot-top'),
  slotSide: document.getElementById('slot-side'),
  fileTop: document.getElementById('file-top'),
  fileSide: document.getElementById('file-side'),
  previewTop: document.getElementById('preview-top'),
  previewSide: document.getElementById('preview-side'),
  filenameTop: document.getElementById('filename-top'),
  filenameSide: document.getElementById('filename-side'),
  scan: document.getElementById('scan'),
  scanRingFill: document.getElementById('scan-ring-fill'),
  scanStage: document.getElementById('scan-stage'),
  scanSubstage: document.getElementById('scan-substage'),
  errorBanner: document.getElementById('error-banner'),
  errorText: document.getElementById('error-text'),
  errorRetry: document.getElementById('error-retry'),
  ticketWrap: document.getElementById('ticket-wrap'),
  ticketItems: document.getElementById('ticket-items'),
  ticketTotals: document.getElementById('ticket-totals'),
  ticketTimestamp: document.getElementById('ticket-timestamp'),
  rescanBtn: document.getElementById('rescan-btn'),
};

els.scanRingFill.style.strokeDasharray = `${CIRCUMFERENCE}`;
els.scanRingFill.style.strokeDashoffset = `${CIRCUMFERENCE}`;

// ----------------------------------------------------------------
// Upload handling
// ----------------------------------------------------------------

function setupSlot(view, fileInput, slotEl, previewEl, filenameEl) {
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;

    // Local preview immediately
    previewEl.src = URL.createObjectURL(file);
    slotEl.dataset.filled = 'true';
    filenameEl.textContent = file.name;

    try {
      await uploadFile(view, file);
      state[view] = true;
      maybeStartProcessing();
    } catch (err) {
      slotEl.dataset.filled = 'false';
      filenameEl.textContent = 'Upload failed — try again';
      showError(`Couldn't upload the ${view} image. ${err.message || ''}`.trim());
    }
  });
}

async function uploadFile(view, file) {
  const form = new FormData();
  form.append('file', file, file.name);
  const resp = await fetch(`${BASE_URL}/upload/${view}`, { method: 'POST', body: form });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(text || `Server responded ${resp.status}`);
  }
  return resp.json();
}

setupSlot('top', els.fileTop, els.slotTop, els.previewTop, els.filenameTop);
setupSlot('side', els.fileSide, els.slotSide, els.previewSide, els.filenameSide);

// ----------------------------------------------------------------
// Auto-trigger processing once both images are in
// ----------------------------------------------------------------

let processing = false;

function maybeStartProcessing() {
  if (state.top && state.side && !processing) {
    startProcessing();
  }
}

const SCAN_STAGES = [
  { pct: 18, stage: 'Segmenting plate…', sub: 'isolating food regions from the tray' },
  { pct: 42, stage: 'Aligning views…', sub: 'matching top and side silhouettes' },
  { pct: 66, stage: 'Classifying items…', sub: 'naming each thing on the plate' },
  { pct: 86, stage: 'Estimating volume…', sub: 'converting shape into cubic centimetres' },
  { pct: 96, stage: 'Portioning nutrition…', sub: 'weighing macros, minerals and vitamins' },
];

async function startProcessing() {
  processing = true;
  hideError();
  els.tray.style.opacity = '0.45';
  els.tray.style.pointerEvents = 'none';
  els.scan.hidden = false;

  let stageIndex = 0;
  setRing(0);
  const timer = setInterval(() => {
    if (stageIndex < SCAN_STAGES.length) {
      const s = SCAN_STAGES[stageIndex];
      setRing(s.pct);
      els.scanStage.textContent = s.stage;
      els.scanSubstage.textContent = s.sub;
      stageIndex++;
    }
  }, 900);

  try {
    const resp = await fetch(`${BASE_URL}/process`, { method: 'POST' });
    const data = await resp.json().catch(() => ({}));

    clearInterval(timer);
    setRing(100);
    els.scanStage.textContent = 'Done';
    els.scanSubstage.textContent = 'printing your receipt';

    if (!resp.ok) {
      throw new Error(data.detail || `Server responded ${resp.status}`);
    }

    setTimeout(() => {
      els.scan.hidden = true;
      renderTicket(data.data);
    }, 500);

  } catch (err) {
    clearInterval(timer);
    els.scan.hidden = true;
    els.tray.style.opacity = '1';
    els.tray.style.pointerEvents = 'auto';
    processing = false;
    showError(err.message || 'Processing failed. Please try again.');
  }
}

function setRing(pct) {
  const offset = CIRCUMFERENCE - (pct / 100) * CIRCUMFERENCE;
  els.scanRingFill.style.strokeDashoffset = `${offset}`;
}

function showError(message) {
  els.errorText.textContent = message;
  els.errorBanner.hidden = false;
}
function hideError() {
  els.errorBanner.hidden = true;
}

els.errorRetry.addEventListener('click', () => {
  hideError();
  els.tray.style.opacity = '1';
  els.tray.style.pointerEvents = 'auto';
  processing = false;
  maybeStartProcessing();
});

els.rescanBtn.addEventListener('click', () => {
  // Reset everything for a fresh scan
  state.top = null;
  state.side = null;
  processing = false;
  els.fileTop.value = '';
  els.fileSide.value = '';
  els.slotTop.dataset.filled = 'false';
  els.slotSide.dataset.filled = 'false';
  els.filenameTop.textContent = 'No file selected';
  els.filenameSide.textContent = 'No file selected';
  els.tray.style.opacity = '1';
  els.tray.style.pointerEvents = 'auto';
  els.ticketWrap.hidden = true;
  els.ticketItems.innerHTML = '';
  els.ticketTotals.innerHTML = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// ----------------------------------------------------------------
// Ticket rendering
// ----------------------------------------------------------------

function renderTicket(data) {
  if (!data || !data.per_food_breakdown) {
    showError('The scan finished but returned no nutrition data.');
    return;
  }

  const foods = data.per_food_breakdown;
  const totals = data.meal_totals || {};

  els.ticketTimestamp.textContent = new Date().toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });

  els.ticketItems.innerHTML = '';
  Object.entries(foods).forEach(([name, item], idx) => {
    els.ticketItems.appendChild(buildItemRow(name, item, idx));
  });

  els.ticketTotals.innerHTML = '';
  const totalRows = [
    ['Calories', `${fmt(totals.calories_kcal)} kcal`, true],
    ['Carbohydrates', `${fmt(totals.carbohydrates_g)} g`],
    ['Protein', `${fmt(totals.protein_g)} g`],
    ['Fat', `${fmt(totals.fat_g)} g`],
    ['Fiber', `${fmt(totals.fiber_g)} g`],
    ['Sodium', `${fmt(totals.sodium_mg)} mg`],
    ['Calcium', `${fmt(totals.calcium_mg)} mg`],
    ['Iron', `${fmt(totals.iron_mg)} mg`],
    ['Vitamin A', `${fmt(totals.vit_a_ug)} µg`],
    ['Vitamin C', `${fmt(totals.vit_c_mg)} mg`],
    ['Vitamin D', `${fmt(totals.vit_d_ug)} µg`],
  ];
  totalRows.forEach(([label, value, grand]) => {
    const row = document.createElement('div');
    row.className = 'ticket__totals-row' + (grand ? ' grand' : '');
    row.innerHTML = `<span class="ticket__totals-label">${label}</span><span class="ticket__totals-value">${value}</span>`;
    els.ticketTotals.appendChild(row);
  });

  els.ticketWrap.hidden = false;
  els.ticketWrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function buildItemRow(name, item, idx) {
  const wrap = document.createElement('div');
  wrap.className = 'ticket__item';
  wrap.id = `ticket-item-${idx}`;

  const split = item['macro_split_%'] || {};
  const macros = item.macros || {};
  const minerals = item.minerals || {};
  const vitamins = item.vitamins || {};

  const displayName = name.replace(/_/g, ' ');

  wrap.innerHTML = `
    <div class="ticket__item-head">
      <span class="ticket__item-name">${displayName} <span class="ticket__item-vol">${fmt(item.volume_cm3, 0)} cm³</span></span>
      <span class="ticket__item-cal">${fmt(item.calories_kcal)} kcal</span>
    </div>
    <div class="ticket__item-bars">
      <span class="bar-c" style="flex:${split.carbs || 0}"></span>
      <span class="bar-p" style="flex:${split.protein || 0}"></span>
      <span class="bar-f" style="flex:${split.fat || 0}"></span>
    </div>
    <div class="ticket__item-legend">
      <span class="legend-c"><em>●</em> Carbs ${split.carbs || 0}%</span>
      <span class="legend-p"><em>●</em> Protein ${split.protein || 0}%</span>
      <span class="legend-f"><em>●</em> Fat ${split.fat || 0}%</span>
    </div>
    <div class="ticket__item-detail">
      <div class="ticket__item-detail-inner">
        <div><span>Carbs</span><span>${fmt(macros.carbohydrates_g)} g</span></div>
        <div><span>Protein</span><span>${fmt(macros.protein_g)} g</span></div>
        <div><span>Fat</span><span>${fmt(macros.fat_g)} g</span></div>
        <div><span>Fiber</span><span>${fmt(macros.fiber_g)} g</span></div>
        <div><span>Sodium</span><span>${fmt(minerals.sodium_mg)} mg</span></div>
        <div><span>Calcium</span><span>${fmt(minerals.calcium_mg)} mg</span></div>
        <div><span>Iron</span><span>${fmt(minerals.iron_mg)} mg</span></div>
        <div><span>Vit A</span><span>${fmt(vitamins.vit_a_ug)} µg</span></div>
        <div><span>Vit C</span><span>${fmt(vitamins.vit_c_mg)} mg</span></div>
        <div><span>Vit D</span><span>${fmt(vitamins.vit_d_ug)} µg</span></div>
      </div>
    </div>
  `;

  wrap.querySelector('.ticket__item-head').addEventListener('click', () => {
    wrap.classList.toggle('open');
  });

  return wrap;
}

function fmt(val, decimals = 1) {
  if (val === undefined || val === null || Number.isNaN(val)) return '—';
  return Number(val).toFixed(decimals).replace(/\.0$/, '');
}
