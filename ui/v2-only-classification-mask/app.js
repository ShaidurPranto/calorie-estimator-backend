(() => {
  'use strict';

  /* =========================================================
     Config
  ========================================================= */
  const CONFIG = {
    INITIAL_DELAY_MS: 5000,     // wait after /process is fired before first classification check
    POLL_INTERVAL_MS: 3500,     // gap between "not ready yet" retries
    MAX_POLL_ATTEMPTS: 40,      // ~2.5 min ceiling per stage before giving up
  };

  const SEGMENT_COLORS = ['#3DD6C4', '#F2A93B', '#8E7CE0', '#E88AB0', '#6FBF6A', '#4FA3D1', '#E07A5F', '#B5CC5C'];
  let colorCursor = 0;
  const categoryColors = new Map(); // category name -> hex, shared across top/side/report

  function getCategoryColor(category) {
    if (!categoryColors.has(category)) {
      categoryColors.set(category, SEGMENT_COLORS[colorCursor % SEGMENT_COLORS.length]);
      colorCursor++;
    }
    return categoryColors.get(category);
  }

  const apiBase = () => document.getElementById('apiBase').value.replace(/\/+$/, '');

  /* =========================================================
     Small utilities
  ========================================================= */
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function hexToRgb(hex) {
    const m = hex.replace('#', '');
    return [parseInt(m.slice(0, 2), 16), parseInt(m.slice(2, 4), 16), parseInt(m.slice(4, 6), 16)];
  }

  async function fetchJSON(url, opts) {
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      throw new Error(`Network error reaching ${url} (${e.message})`);
    }
    let body = null;
    try { body = await res.json(); } catch (_e) { /* no body */ }
    if (!res.ok) {
      const detail = (body && body.detail) ? body.detail : `HTTP ${res.status}`;
      throw new Error(detail);
    }
    return body;
  }

  /** Poll fn() until it resolves without throwing, retrying on failure. */
  async function pollUntilOk(fn, { intervalMs, maxAttempts, onRetry }) {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        return await fn();
      } catch (e) {
        if (attempt >= maxAttempts) throw e;
        if (onRetry) onRetry(attempt, e);
        await sleep(intervalMs);
      }
    }
  }

  /* =========================================================
     Logging + toast
  ========================================================= */
  const logList = document.getElementById('logList');
  function log(msg, level = 'info') {
    const li = document.createElement('li');
    li.dataset.level = level;
    const time = document.createElement('time');
    time.textContent = new Date().toLocaleTimeString([], { hour12: false });
    const span = document.createElement('span');
    span.className = 'log-card__msg';
    span.textContent = msg;
    li.append(time, span);
    logList.prepend(li);
  }
  document.getElementById('clearLog').addEventListener('click', () => { logList.innerHTML = ''; });

  let toastTimer = null;
  function showToast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 4500);
  }

  /* =========================================================
     Pipeline rail
  ========================================================= */
  const stageTracker = {
    upload:   { started: 0, done: 0, target: 1 },
    process:  { started: 0, done: 0, target: 1 },
    classify: { started: 0, done: 0, target: 2 },
    report:   { started: 0, done: 0, target: 1 },
  };
  function resetStageTracker() {
    Object.values(stageTracker).forEach((t) => { t.started = 0; t.done = 0; });
    document.querySelectorAll('.pipeline-rail__stage').forEach((li) => li.classList.remove('is-active', 'is-done'));
  }
  function setStageVisual(name, state) {
    const li = document.querySelector(`.pipeline-rail__stage[data-stage="${name}"]`);
    if (!li) return;
    if (state === 'active') { li.classList.add('is-active'); li.classList.remove('is-done'); }
    if (state === 'done') { li.classList.remove('is-active'); li.classList.add('is-done'); }
  }
  function bumpStage(name, type) {
    const t = stageTracker[name];
    if (!t) return;
    if (type === 'start') { t.started++; if (t.started >= 1) setStageVisual(name, 'active'); }
    if (type === 'done') { t.done++; if (t.done >= t.target) setStageVisual(name, 'done'); }
  }

  /* =========================================================
     Per-view state
  ========================================================= */
  const views = ['top', 'side'].reduce((acc, view) => {
    const root = document.getElementById(`panel-${view}`);
    acc[view] = {
      view,
      root,
      statusEl: root.querySelector('[data-role="status"]'),
      emptyEl: root.querySelector('[data-role="empty"]'),
      dropzone: root.querySelector('[data-role="dropzone"]'),
      fileInput: root.querySelector('[data-role="file-input"]'),
      canvasWrap: root.querySelector('[data-role="canvas-wrap"]'),
      imgEl: root.querySelector('[data-role="base-image"]'),
      canvas: root.querySelector('[data-role="mask-canvas"]'),
      sweepEl: root.querySelector('[data-role="sweep"]'),
      replaceBtn: root.querySelector('[data-role="replace"]'),
      legendEl: root.querySelector('[data-role="legend"]'),
      uploaded: false,
      pipelineStarted: false,
      masks: {}, // filename -> { filename, data, color, visible, label, rows, cols, centroidFrac }
    };
    return acc;
  }, {});

  function setStatus(view, text, tone) {
    const v = views[view];
    v.statusEl.textContent = text;
    if (tone) v.statusEl.dataset.tone = tone; else delete v.statusEl.dataset.tone;
  }

  function setSweeping(view, on) {
    views[view].sweepEl.classList.toggle('is-sweeping', !!on);
  }

  /* =========================================================
     Upload handling
  ========================================================= */
  function wireUpload(view) {
    const v = views[view];

    // The <label> wraps the hidden <input type="file">, so a plain click on
    // the label already opens the native picker — no JS needed for that,
    // and manually calling fileInput.click() here would re-bubble a click
    // back up to the label and fight itself. We only need the change handler.
    v.fileInput.addEventListener('change', () => {
      const file = v.fileInput.files[0];
      if (file) handleFile(view, file);
    });

    ['dragover', 'dragenter'].forEach((evt) =>
      v.dropzone.addEventListener(evt, (e) => { e.preventDefault(); v.dropzone.classList.add('is-dragover'); })
    );
    ['dragleave', 'drop'].forEach((evt) =>
      v.dropzone.addEventListener(evt, (e) => { e.preventDefault(); v.dropzone.classList.remove('is-dragover'); })
    );
    v.dropzone.addEventListener('drop', (e) => {
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) handleFile(view, file);
    });

    v.replaceBtn.addEventListener('click', () => {
      if (v.pipelineStarted) {
        showToast('This image is already part of a running pipeline and can\u2019t be swapped mid-run.');
        return;
      }
      v.canvasWrap.hidden = true;
      v.emptyEl.hidden = false;
      v.uploaded = false;
      v.fileInput.value = '';
      setStatus(view, 'Waiting for image');
    });
  }

  async function handleFile(view, file) {
    const v = views[view];

    // Instant local preview
    const objectUrl = URL.createObjectURL(file);
    v.imgEl.onload = () => {
      v.canvas.width = v.imgEl.naturalWidth;
      v.canvas.height = v.imgEl.naturalHeight;
      v.ctx = v.canvas.getContext('2d');
    };
    v.imgEl.src = objectUrl;
    v.emptyEl.hidden = true;
    v.canvasWrap.hidden = false;

    setStatus(view, 'Uploading\u2026', 'active');
    const form = new FormData();
    form.append('file', file);

    try {
      await fetchJSON(`${apiBase()}/upload/${view}`, { method: 'POST', body: form });
      v.uploaded = true;
      setStatus(view, 'Uploaded \u2014 waiting on the other angle', 'active');
      log(`[${view}] uploaded ${file.name}`, 'success');
      maybeStartPipeline();
    } catch (e) {
      setStatus(view, `Upload failed: ${e.message}`, 'error');
      log(`[${view}] upload failed: ${e.message}`, 'error');
      showToast(`${view} image failed to upload: ${e.message}`);
    }
  }

  /* =========================================================
     Kick-off: once both images are uploaded, fire three
     independent, concurrent processes:
       1) POST /process           (the slow final report)
       2) top classification poll + redraw loop
       3) side classification poll + redraw loop
  ========================================================= */
  let pipelineKicked = false;
  let settledCount = 0; // counts runProcessPipeline + runViewPipeline(top) + runViewPipeline(side) finishing, success or fail

  function maybeStartPipeline() {
    if (pipelineKicked) return;
    if (!views.top.uploaded || !views.side.uploaded) return;
    pipelineKicked = true;
    views.top.pipelineStarted = true;
    views.side.pipelineStarted = true;
    settledCount = 0;

    bumpStage('upload', 'start');
    bumpStage('upload', 'done');
    log('Both angles uploaded \u2014 starting pipeline (process + top scan + side scan, in parallel).');

    runProcessPipeline();     // not awaited: runs independently
    runViewPipeline('top');   // not awaited: runs independently
    runViewPipeline('side');  // not awaited: runs independently
  }

  function markSettled() {
    settledCount++;
    if (settledCount >= 3) {
      document.getElementById('sessionActions').hidden = false;
      log('Scan finished \u2014 ready for another pair of images.');
    }
  }

  function resetSession() {
    pipelineKicked = false;
    settledCount = 0;
    document.getElementById('sessionActions').hidden = true;

    resetStageTracker();

    const reportCard = document.getElementById('reportCard');
    reportCard.hidden = true;
    reportCard.querySelector('[data-role="report-body"]').innerHTML = '';
    reportCard.querySelector('[data-role="report-total"]').textContent = '';

    ['top', 'side'].forEach((view) => {
      const v = views[view];
      v.uploaded = false;
      v.pipelineStarted = false;
      v.masks = {};
      if (v.ctx) v.ctx.clearRect(0, 0, v.canvas.width, v.canvas.height);
      v.canvasWrap.hidden = true;
      v.emptyEl.hidden = false;
      v.fileInput.value = '';
      v.imgEl.src = '';
      v.legendEl.innerHTML = '';
      setSweeping(view, false);
      setStatus(view, 'Waiting for image');
    });

    log('Session reset \u2014 upload a new top view and side view to start again.');
  }
  document.getElementById('startOverBtn').addEventListener('click', resetSession);

  /* =========================================================
     Process pipeline: the slow, single source of truth report
  ========================================================= */
  async function runProcessPipeline() {
    bumpStage('process', 'start');
    try {
      const res = await fetchJSON(`${apiBase()}/process`, { method: 'POST' });
      bumpStage('process', 'done');
      bumpStage('report', 'start');
      renderReport(res.data);
      bumpStage('report', 'done');
      log('Nutrition report ready.', 'success');
    } catch (e) {
      log(`/process failed: ${e.message}`, 'error');
      showToast(`Processing failed: ${e.message}`);
    } finally {
      markSettled();
    }
  }

  /* =========================================================
     Per-view scan pipeline — classification-only.
     We never call the segmentation endpoints: the classification
     listing is the sole source of truth for what's on the plate,
     and its own content endpoint gives us the mask data directly.
  ========================================================= */
  async function runViewPipeline(view) {
    const v = views[view];
    try {
      log(`[${view}] waiting ${(CONFIG.INITIAL_DELAY_MS / 1000).toFixed(0)}s before checking for classification output\u2026`);
      await sleep(CONFIG.INITIAL_DELAY_MS);

      setStatus(view, 'Classifying\u2026', 'active');
      setSweeping(view, true);
      bumpStage('classify', 'start');

      const clsList = await pollUntilOk(
        () => fetchJSON(`${apiBase()}/result/classification/${view}`),
        {
          intervalMs: CONFIG.POLL_INTERVAL_MS,
          maxAttempts: CONFIG.MAX_POLL_ATTEMPTS,
          onRetry: (attempt) => log(`[${view}] classification not ready yet (attempt ${attempt}) \u2014 retrying\u2026`, 'warn'),
        }
      );
      setSweeping(view, false);

      const categories = clsList.categories || {};
      const catEntries = Object.entries(categories);
      const foodCount = catEntries.reduce((n, [, files]) => n + (files ? files.length : 0), 0);
      log(`[${view}] classification complete \u2014 ${catEntries.length} food item(s), ${foodCount} region(s).`, 'success');

      // Fetch each classified mask directly by category and paint it onto
      // the image the instant it arrives — non-food regions are simply
      // never fetched, so they're never on the image to begin with.
      let placedCount = 0;
      await Promise.all(catEntries.flatMap(([category, files]) =>
        (files || []).map(async (filename) => {
          const res = await fetchJSON(
            `${apiBase()}/result/classification/${view}/content/${encodeURIComponent(category)}/${encodeURIComponent(filename)}`
          );
          const key = `${category}/${filename}`;
          v.masks[key] = {
            filename: key,
            data: res.mask,
            color: getCategoryColor(category),   // same food category -> same color, shared across views/report
            visible: true,
            label: category,
            centroidFrac: computeCentroidFrac(res.mask),
          };
          placedCount++;
          drawMasks(view);
          renderLegend(view);
          setStatus(view, `Labeling food ${placedCount}/${foodCount}\u2026`, 'active');
        })
      ));

      bumpStage('classify', 'done');
      const itemCount = catEntries.length;
      setStatus(view, `${itemCount} food item(s) identified`, 'done');
    } catch (e) {
      setSweeping(view, false);
      setStatus(view, `Failed: ${e.message}`, 'error');
      log(`[${view}] pipeline failed: ${e.message}`, 'error');
      showToast(`${view} scan failed: ${e.message}`);
    } finally {
      markSettled();
    }
  }

  /* =========================================================
     Mask math + canvas rendering
  ========================================================= */
  function computeCentroidFrac(mask) {
    const rows = mask.length;
    const cols = rows ? mask[0].length : 0;
    let sx = 0, sy = 0, count = 0;
    for (let y = 0; y < rows; y++) {
      const row = mask[y];
      for (let x = 0; x < cols; x++) {
        if (row[x]) { sx += x; sy += y; count++; }
      }
    }
    if (!count) return { x: 0.5, y: 0.5 };
    return { x: (sx / count + 0.5) / cols, y: (sy / count + 0.5) / rows };
  }

  function maskToOffscreenCanvas(mask, colorHex) {
    const rows = mask.length;
    const cols = rows ? mask[0].length : 0;
    const off = document.createElement('canvas');
    off.width = cols || 1;
    off.height = rows || 1;
    const octx = off.getContext('2d');
    if (!rows || !cols) return off;
    const imgData = octx.createImageData(cols, rows);
    const [r, g, b] = hexToRgb(colorHex);
    const alpha = Math.round(0.40 * 255);
    for (let y = 0; y < rows; y++) {
      const row = mask[y];
      for (let x = 0; x < cols; x++) {
        const idx = (y * cols + x) * 4;
        if (row[x]) {
          imgData.data[idx] = r;
          imgData.data[idx + 1] = g;
          imgData.data[idx + 2] = b;
          imgData.data[idx + 3] = alpha;
        }
      }
    }
    octx.putImageData(imgData, 0, 0);
    return off;
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawLabel(ctx, text, x, y, color) {
    ctx.font = "600 13px 'IBM Plex Mono', monospace";
    const padX = 9, padY = 6;
    const w = ctx.measureText(text).width + padX * 2;
    const h = 22;
    ctx.fillStyle = 'rgba(15,17,20,0.82)';
    roundRect(ctx, x - w / 2, y - h / 2, w, h, h / 2);
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = color;
    ctx.stroke();
    ctx.fillStyle = '#EDEDEE';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, x, y + 0.5);
  }

  function drawMasks(view) {
    const v = views[view];
    if (!v.ctx) return;
    const { width, height } = v.canvas;
    v.ctx.clearRect(0, 0, width, height);

    const visibleMasks = Object.values(v.masks).filter((m) => m.visible);
    visibleMasks.forEach((m) => {
      const off = maskToOffscreenCanvas(m.data, m.color);
      v.ctx.drawImage(off, 0, 0, width, height);
    });
    visibleMasks.forEach((m) => {
      if (!m.label) return;
      const x = m.centroidFrac.x * width;
      const y = m.centroidFrac.y * height;
      drawLabel(v.ctx, m.label, x, y, m.color);
    });
  }

  function renderLegend(view) {
    const v = views[view];
    v.legendEl.innerHTML = '';
    const visibleMasks = Object.values(v.masks).filter((m) => m.visible);

    // Dedupe: multiple regions of the same food share one legend entry.
    // Pre-classification, masks are unlabeled, so each raw region gets its
    // own entry instead (using the mask filename as the grouping key).
    const seen = new Map(); // key -> { color, text }
    visibleMasks.forEach((m) => {
      const key = m.label || m.filename;
      if (!seen.has(key)) {
        seen.set(key, { color: m.color, text: m.label ? capitalize(m.label) : m.filename.replace(/\.npy$/, '') });
      }
    });

    seen.forEach(({ color, text }) => {
      const li = document.createElement('li');
      const dot = document.createElement('span');
      dot.className = 'swatch';
      dot.style.background = color;
      li.appendChild(dot);
      li.append(text);
      v.legendEl.appendChild(li);
    });
  }

  function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  /* =========================================================
     Report rendering
  ========================================================= */
  function renderReport(data) {
    const card = document.getElementById('reportCard');
    const body = card.querySelector('[data-role="report-body"]');
    const totalEl = card.querySelector('[data-role="report-total"]');
    body.innerHTML = '';

    const totals = data.meal_totals || {};
    totalEl.textContent = `${Math.round(totals.calories_kcal || 0)} kcal total`;

    const breakdown = data.per_food_breakdown || {};
    Object.entries(breakdown).forEach(([name, info]) => {
      const row = document.createElement('div');
      row.className = 'food-row';

      const nameWrap = document.createElement('div');
      nameWrap.className = 'food-row__name';
      const swatch = document.createElement('span');
      swatch.className = 'food-row__swatch';
      swatch.style.background = getCategoryColor(name);
      nameWrap.append(swatch, name);

      const meta = document.createElement('div');
      meta.className = 'food-row__meta';
      const cal = Math.round(info.calories_kcal || 0);
      const vol = info.volume_cm3 != null ? `${info.volume_cm3} cm\u00B3` : '';
      meta.innerHTML = `<b>${cal} kcal</b> &middot; ${vol}`;

      row.append(nameWrap, meta);
      body.appendChild(row);
    });

    card.hidden = false;
  }

  /* =========================================================
     Init
  ========================================================= */
  wireUpload('top');
  wireUpload('side');
  log('Ready. Upload a top view and a side view to begin.');
})();
