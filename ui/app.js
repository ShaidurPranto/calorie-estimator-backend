(() => {
  'use strict';

  /* =========================================================
     Config
  ========================================================= */
  const CONFIG = {
    INITIAL_DELAY_MS: 8000,     // wait after /process is fired before the first state check
    POLL_INTERVAL_MS: 10000,    // gap kept between every state check, whether or not it moved things forward
    MAX_POLL_ATTEMPTS: 70,      // ~2.5 min ceiling before giving up on the whole pipeline
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

  function basename(path) {
    return String(path).split(/[\\/]/).pop();
  }

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

  /** sleep() above is still used directly by the sequential pipeline below;
   *  no generic retry-poller is needed anymore since /result/state is
   *  checked in one single loop instead of per-stage. */

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
    segment:  { started: 0, done: 0, target: 1 },
    classify: { started: 0, done: 0, target: 1 },
    volume:   { started: 0, done: 0, target: 1 },
    report:   { started: 0, done: 0, target: 1 },
  };
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
     Kick-off: once both images are uploaded, fire /process, then
     drive one single sequential pipeline off of /result/state:

       segmentation top   -> fetch + draw top masks
       segmentation side  -> fetch + draw side masks
       classification top -> label the already-fetched top masks
       classification side-> label the already-fetched side masks
       volume             -> fetch the final report

     Each step only starts once the previous one has been handled, and a
     fixed gap (CONFIG.POLL_INTERVAL_MS) is kept between every check of
     /result/state, whether or not that check moved things forward.
  ========================================================= */
  let pipelineKicked = false;
  function maybeStartPipeline() {
    if (pipelineKicked) return;
    if (!views.top.uploaded || !views.side.uploaded) return;
    pipelineKicked = true;
    views.top.pipelineStarted = true;
    views.side.pipelineStarted = true;

    bumpStage('upload', 'start');
    bumpStage('upload', 'done');
    log('Both angles uploaded \u2014 starting pipeline.');

    runPipeline();
  }

  async function runPipeline() {
    bumpStage('process', 'start');
    try {
      const queued = await fetchJSON(`${apiBase()}/process`, { method: 'POST' });
      bumpStage('process', 'done');
      log(queued.message || 'Processing started on the server.', 'success');
    } catch (e) {
      log(`/process failed: ${e.message}`, 'error');
      showToast(`Processing failed to start: ${e.message}`);
      return;
    }

    log(`Waiting ${(CONFIG.INITIAL_DELAY_MS / 1000).toFixed(0)}s before checking pipeline state\u2026`);
    await sleep(CONFIG.INITIAL_DELAY_MS);

    // Tracks which stage-transitions we've already reacted to, so each one
    // fires exactly once, in order, as /result/state reports it complete.
    const seen = {
      segmentation_top: false,
      segmentation_side: false,
      classification_top: false,
      classification_side: false,
      volume: false,
    };

    setSweeping('top', true);
    bumpStage('segment', 'start');

    for (let attempt = 1; attempt <= CONFIG.MAX_POLL_ATTEMPTS; attempt++) {
      let state;
      try {
        state = await fetchJSON(`${apiBase()}/result/state`);
      } catch (e) {
        log(`State check failed (attempt ${attempt}): ${e.message}`, 'warn');
        await sleep(CONFIG.POLL_INTERVAL_MS);
        continue;
      }

      const stages = state.stages || {};
      let acted = false;

      // These used to be an if/else-if chain, which meant only ONE newly
      // -ready stage got handled per poll cycle even if the backend had
      // already raced ahead and finished several stages while we were
      // asleep. Each block is still gated on the previous stage's "seen"
      // flag (so order is preserved), but they're now independent ifs so
      // a single poll can walk through every stage that's already ready.
      if (!seen.segmentation_top && stages.segmentation_top) {
        seen.segmentation_top = true;
        acted = true;
        await handleSegmentationDone('top');
        setSweeping('side', true);
      }

      if (seen.segmentation_top && !seen.segmentation_side && stages.segmentation_side) {
        seen.segmentation_side = true;
        acted = true;
        await handleSegmentationDone('side');
        bumpStage('segment', 'done');
        bumpStage('classify', 'start');
      }

      if (seen.segmentation_side && !seen.classification_top && stages.classification_top) {
        seen.classification_top = true;
        acted = true;
        await handleClassificationDone('top');
      }

      if (seen.classification_top && !seen.classification_side && stages.classification_side) {
        seen.classification_side = true;
        acted = true;
        await handleClassificationDone('side');
        bumpStage('classify', 'done');
        bumpStage('volume', 'start');
      }

      if (seen.classification_side && !seen.volume && stages.volume) {
        seen.volume = true;
        acted = true;
        await handleVolumeDone();
        bumpStage('volume', 'done');
        return; // pipeline fully complete
      }

      if (!acted) {
        const doneList = state.completed_stages && state.completed_stages.length
          ? state.completed_stages.join(', ')
          : 'none yet';
        log(`Waiting on pipeline \u2014 completed so far: ${doneList} (attempt ${attempt})`, 'warn');
      }

      await sleep(CONFIG.POLL_INTERVAL_MS);
    }

    log('Timed out waiting for the pipeline to finish.', 'error');
    showToast('Timed out waiting for processing to finish.');
  }

  /* =========================================================
     Stage handlers
  ========================================================= */

  /** Segmentation for one view has completed: fetch the mask list, then
   *  fetch + draw each mask's content as it arrives. Masks start unlabeled;
   *  classification (once it completes) decides which of them get a label. */
  async function handleSegmentationDone(view) {
    const v = views[view];
    try {
      setStatus(view, 'Segmenting\u2026', 'active');
      log(`[${view}] segmentation complete \u2014 fetching masks\u2026`, 'success');

      const segList = await fetchJSON(`${apiBase()}/result/segmentation/${view}`);
      const filenames = segList.files || [];
      log(`[${view}] ${filenames.length} region(s) found.`, 'success');
      setStatus(view, `${filenames.length} region(s) found \u2014 loading masks\u2026`, 'active');

      let loadedCount = 0;
      await Promise.all(filenames.map(async (filename, i) => {
        const res = await fetchJSON(`${apiBase()}/result/segmentation/${view}/content/${encodeURIComponent(filename)}`);
        v.masks[filename] = {
          filename,
          data: res.mask,
          color: SEGMENT_COLORS[i % SEGMENT_COLORS.length],
          visible: true,
          label: null,
          centroidFrac: computeCentroidFrac(res.mask),
        };
        loadedCount++;
        drawMasks(view);
        renderLegend(view);
        setStatus(view, `Masking region ${loadedCount}/${filenames.length}\u2026`, 'active');
      }));

      setSweeping(view, false);
      setStatus(view, `${filenames.length} region(s) masked \u2014 waiting on classification\u2026`, 'active');
    } catch (e) {
      setSweeping(view, false);
      setStatus(view, `Failed: ${e.message}`, 'error');
      log(`[${view}] segmentation step failed: ${e.message}`, 'error');
      showToast(`${view} segmentation failed: ${e.message}`);
    }
  }

  /** Classification for one view has completed. We already have every mask
   *  for this view in memory from segmentation — this step only fetches the
   *  category listing and uses it to decide which already-fetched filename
   *  belongs to which category. No mask content is re-fetched here. Masks
   *  that don't appear in any category stay visible, just without a label. */
  async function handleClassificationDone(view) {
    const v = views[view];
    try {
      setStatus(view, 'Classifying\u2026', 'active');
      log(`[${view}] classification complete \u2014 applying labels\u2026`, 'success');

      const clsList = await fetchJSON(`${apiBase()}/result/classification/${view}`);
      const categories = clsList.categories || {};

      // filename -> category, built purely from the listing response.
      // We index every category filename under a few different keys so a
      // mask matches regardless of small formatting differences between
      // what segmentation handed us and what classification hands back:
      //   - the raw filename as given
      //   - its basename (in case classification includes a subfolder path)
      //   - a "normalized" form: lowercase, extension stripped, any
      //     non-alphanumeric run collapsed to a single underscore
      //   - the numeric id pulled out of the filename (handles zero-padding
      //     or prefix differences like "segment_4" vs "top_segment_004")
      function normalize(name) {
        return basename(name).toLowerCase().replace(/\.npy$/, '').replace(/[^a-z0-9]+/g, '_');
      }
      function numericId(name) {
        const m = basename(name).match(/(\d+)(?!.*\d)/); // last digit run
        return m ? String(parseInt(m[1], 10)) : null;
      }

      const byExact = {}, byBasename = {}, byNormalized = {}, byNumericId = {};
      Object.entries(categories).forEach(([category, files]) => {
        (files || []).forEach((filename) => {
          byExact[filename] = category;
          byBasename[basename(filename)] = category;
          byNormalized[normalize(filename)] = category;
          const id = numericId(filename);
          if (id !== null) {
            // Don't let an ambiguous numeric id silently overwrite a
            // different category — only keep it if it's unambiguous.
            byNumericId[id] = (id in byNumericId && byNumericId[id] !== category) ? '__AMBIGUOUS__' : category;
          }
        });
      });

      function resolveCategory(filename) {
        if (byExact[filename]) return byExact[filename];
        if (byBasename[basename(filename)]) return byBasename[basename(filename)];
        if (byNormalized[normalize(filename)]) return byNormalized[normalize(filename)];
        const id = numericId(filename);
        if (id !== null && byNumericId[id] && byNumericId[id] !== '__AMBIGUOUS__') return byNumericId[id];
        return null;
      }

      let labeledCount = 0;
      let removedCount = 0;
      const totalCount = Object.keys(v.masks).length;
      Object.values(v.masks).forEach((m) => {
        const category = resolveCategory(m.filename);
        if (category) {
          m.label = category;
          m.color = getCategoryColor(category); // same food category -> same color, shared across views/report
          m.visible = true;
          labeledCount++;
        } else {
          // Not under any predicted category — drop it from the display
          // entirely rather than leaving an unlabeled mask behind.
          m.label = null;
          m.visible = false;
          removedCount++;
        }
      });

      // Nothing matched at all even though the server reported categories
      // -> almost certainly a filename-format mismatch between the
      // segmentation and classification endpoints. Surface the raw values
      // so it's diagnosable from the activity log instead of failing silently.
      const categoryFileCount = Object.values(categories).reduce((n, files) => n + (files ? files.length : 0), 0);
      if (labeledCount === 0 && categoryFileCount > 0 && totalCount > 0) {
        const oursSample = Object.keys(v.masks).slice(0, 5).join(', ');
        const theirsSample = Object.values(categories).flat().slice(0, 5).join(', ');
        log(`[${view}] 0 matches despite ${categoryFileCount} categorized file(s) \u2014 filename mismatch? segmentation gave: [${oursSample}] vs classification gave: [${theirsSample}]`, 'error');
      }

      drawMasks(view);
      renderLegend(view);

      log(`[${view}] classification applied \u2014 ${labeledCount}/${totalCount} region(s) labeled, ${removedCount} unclassified region(s) removed.`, 'success');
      setStatus(view, `${labeledCount} food item(s) identified`, 'done');
    } catch (e) {
      setStatus(view, `Failed: ${e.message}`, 'error');
      log(`[${view}] classification step failed: ${e.message}`, 'error');
      showToast(`${view} classification failed: ${e.message}`);
    }
  }

  /** Volume estimation (the last stage) has completed: fetch and render
   *  the final nutrition report. */
  async function handleVolumeDone() {
    bumpStage('report', 'start');
    try {
      const res = await fetchJSON(`${apiBase()}/volume-estimation`);
      renderReport(res.data);
      bumpStage('report', 'done');
      log('Nutrition report ready.', 'success');
    } catch (e) {
      log(`Fetching the final report failed: ${e.message}`, 'error');
      showToast(`Fetching the final report failed: ${e.message}`);
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
    const h = 13 + padY * 2;
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