let DATA = __DATA__;

function toggleTheme() {
  document.documentElement.classList.toggle('dark');
  localStorage.setItem('scriba-theme', document.documentElement.classList.contains('dark') ? 'dark' : 'light');
}
if (localStorage.getItem('scriba-theme') === 'dark' || (!localStorage.getItem('scriba-theme') && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
  document.documentElement.classList.add('dark');
}

function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }
function fmtSec(s) { if (s == null) return '—'; const m = Math.floor(s / 60); return m ? `${m}:${String(Math.round(s % 60)).padStart(2, '0')}` : `${s.toFixed(1)}s`; }

// hashルーティング: クリック等は location.hash を更新するだけで、
// 実際の描画は hashchange リスナー(router)経由に一本化する（hash変更→描画の一方向）。
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(t => t.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  const nav = document.querySelector('.nav-link[data-view="' + name + '"]');
  if (nav) nav.classList.add('active');
  if (name === 'settings') showSubTab('dict');
}

function showSubTab(name) {
  document.querySelectorAll('.sub-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.sub-nav-link').forEach(t => t.classList.remove('active'));
  document.getElementById('sub-' + name).classList.add('active');
  const btn = document.querySelector('.sub-nav-link[data-sub="' + name + '"]');
  if (btn) btn.classList.add('active');
  if (name === 'dict') renderDict();
  if (name === 'enrich') renderEnrich();
}

// location.hash を解釈して描画する。存在しないセッションIDは一覧へフォールバック。
function router() {
  const raw = location.hash.replace(/^#/, '');
  if (raw.startsWith('session=')) {
    const id = decodeURIComponent(raw.slice('session='.length));
    const i = DATA.sessions.findIndex(s => s.id === id);
    if (i < 0) { location.hash = 'sessions'; return; }
    showView('sessions');
    showDetail(i);
    return;
  }
  const name = ['sessions', 'performance', 'settings'].includes(raw) ? raw : (raw === 'dictionary' || raw === 'enrich' ? 'settings' : 'sessions');
  showView(name);
  if (name === 'sessions') backToList();
}

// ===== Dictionary =====
function dictRow(kind, a, b) {
  const del = `<button class="row-del" onclick="this.closest('.dict-row').remove(); onDictInput()">×</button>`;
  if (kind === 'term') {
    return `<div class="dict-row"><input class="term-word" value="${esc(a)}" placeholder="用語（例: 山田）" oninput="onDictInput()">${del}</div>`;
  }
  if (kind === 'filter') {
    return `<div class="dict-row"><input class="filter-value" value="${esc(a)}" placeholder="除去する発話（例: ありがとうございました）">${del}</div>`;
  }
  return `<div class="dict-row"><input class="repl-from" value="${esc(a)}" placeholder="誤（例: バックローリー）" oninput="onDictInput()"><span class="dict-arrow">→</span><input class="repl-to" value="${esc(b)}" placeholder="正（例: バックログ）" oninput="onDictInput()">${del}</div>`;
}

function renderDict() {
  const editable = IS_HTTP;
  document.getElementById('dict-readonly-note').style.display = editable ? 'none' : 'block';
  document.getElementById('dict-editor').style.display = editable ? 'block' : 'none';
  if (!editable) return;
  const d = DATA.dict || { terms: [], replacements: [], filters: [] };
  document.getElementById('terms-list').innerHTML = (d.terms.length ? d.terms : [{ word: '' }]).map(t => dictRow('term', t.word)).join('');
  document.getElementById('repl-list').innerHTML = (d.replacements.length ? d.replacements : [{ from: '', to: '' }]).map(r => dictRow('repl', r.from, r.to)).join('');
  const defaults = d.default_filters || [];
  document.getElementById('filter-default-list').innerHTML = defaults.length
    ? defaults.map(f => `<span class="dict-default-item">${esc(f)}</span>`).join('')
    : '<span class="dict-default-item">なし</span>';
  const filters = d.filters || [];
  document.getElementById('filter-list').innerHTML = (filters.length ? filters : [{ value: '' }]).map(f => dictRow('filter', f.value)).join('');
  document.getElementById('dict-path').textContent = d.path || '';
  document.getElementById('dict-save-status').textContent = '';
  onDictInput();
}

function addTerm() { document.getElementById('terms-list').insertAdjacentHTML('beforeend', dictRow('term', '')); }
function addRepl() { document.getElementById('repl-list').insertAdjacentHTML('beforeend', dictRow('repl', '', '')); }
function addFilter() { document.getElementById('filter-list').insertAdjacentHTML('beforeend', dictRow('filter', '')); }

function collectDict() {
  const terms = [...document.querySelectorAll('.term-word')].map(i => i.value.trim()).filter(Boolean).map(w => ({ word: w }));
  const replacements = [...document.querySelectorAll('#repl-list .dict-row')].map(row => ({
    from: row.querySelector('.repl-from').value.trim(),
    to: row.querySelector('.repl-to').value.trim(),
  })).filter(r => r.from);
  const filters = [...document.querySelectorAll('.filter-value')].map(i => i.value.trim()).filter(Boolean).map(v => ({ value: v }));
  return { terms, replacements, filters };
}

// 保存前のプレビュー: 文字数ベースで概算警告（正確なトークン判定は保存時にサーバーが返す）
function onDictInput() {
  const words = [...document.querySelectorAll('.term-word')].map(i => i.value.trim()).filter(Boolean);
  const haas = DATA.model.startsWith('haas-');
  const prompt = haas ? words.join('\n') : (words.length ? '会議の用語: ' + words.join('、') : '');
  const n = prompt.length;
  const st = document.getElementById('dict-prompt-status');
  document.getElementById('dict-prompt-preview').textContent = prompt;
  if (haas) { st.className = 'dict-status ok'; st.textContent = `${words.length}語`; return; }
  if (n === 0) { st.className = 'dict-status ok'; st.textContent = ''; return; }
  if (n > 150) { st.className = 'dict-status block'; st.textContent = `${n}文字（上限超の恐れ、減らしてください）`; }
  else if (n > 120) { st.className = 'dict-status warn'; st.textContent = `${n}文字（上限に接近）`; }
  else { st.className = 'dict-status ok'; st.textContent = `${n}文字`; }
}

async function saveDict() {
  const status = document.getElementById('dict-save-status');
  status.className = 'dict-status ok';
  status.textContent = '保存中...';
  try {
    const res = await fetch('/dict', { method: 'POST', body: JSON.stringify(collectDict()) });
    if (!res.ok) { status.className = 'dict-status block'; status.textContent = '保存失敗: ' + await res.text(); return; }
    DATA.dict = await res.json();
    const v = DATA.dict.verdict;
    status.className = 'dict-status ' + (v === 'block' ? 'block' : v === 'warn' ? 'warn' : 'ok');
    status.textContent = (v === 'ok' ? '保存しました · ' : '保存（警告あり）· ') + DATA.dict.message;
  } catch (e) {
    status.className = 'dict-status block'; status.textContent = '保存失敗: ' + e;
  }
}

// ===== Enrich =====
function enrichOrgRow(domain, name) {
  const del = `<button class="row-del" onclick="this.closest('.dict-row').remove()">×</button>`;
  return `<div class="dict-row"><input class="enrich-org-domain" value="${esc(domain)}" placeholder="ドメイン（例: example.com）"><span class="dict-arrow">→</span><input class="enrich-org-name" value="${esc(name)}" placeholder="組織名（例: Example 社）">${del}</div>`;
}

function enrichProjectRow(alias, keywords) {
  const del = `<button class="row-del" onclick="this.closest('.dict-row').remove()">×</button>`;
  const up = `<button class="order-btn" onclick="moveEnrichRow(this, -1)">↑</button>`;
  const dn = `<button class="order-btn" onclick="moveEnrichRow(this, 1)">↓</button>`;
  const kw = Array.isArray(keywords) ? keywords.join(', ') : (keywords || '');
  return `<div class="dict-row"><input class="enrich-proj-alias" value="${esc(alias)}" placeholder="エイリアス（例: acme）" style="flex:0.6"><input class="enrich-proj-keywords" value="${esc(kw)}" placeholder="キーワード（カンマ区切り）" style="flex:1">${up}${dn}${del}</div>`;
}

function moveEnrichRow(btn, dir) {
  const row = btn.closest('.dict-row');
  const parent = row.parentNode;
  const rows = [...parent.querySelectorAll('.dict-row')];
  const idx = rows.indexOf(row);
  const target = idx + dir;
  if (target < 0 || target >= rows.length) return;
  if (dir < 0) parent.insertBefore(row, rows[target]);
  else parent.insertBefore(rows[target], row);
}

function renderEnrich() {
  const editable = IS_HTTP;
  document.getElementById('enrich-readonly-note').style.display = editable ? 'none' : 'block';
  document.getElementById('enrich-editor').style.display = editable ? 'block' : 'none';
  if (!editable) return;
  const e = DATA.enrich || { calendar_path: '', organizations: {}, projects: [] };
  document.getElementById('enrich-calendar-path').value = e.calendar_path || '';
  const orgs = e.organizations || {};
  const orgEntries = Object.entries(orgs);
  document.getElementById('enrich-orgs-list').innerHTML = (orgEntries.length ? orgEntries : [['', '']]).map(([d, n]) => enrichOrgRow(d, n)).join('');
  const projects = e.projects || [];
  document.getElementById('enrich-projects-list').innerHTML = (projects.length ? projects : [{ alias: '', keywords: [] }]).map(p => enrichProjectRow(p.alias, p.keywords)).join('');
}

function addEnrichOrg() { document.getElementById('enrich-orgs-list').insertAdjacentHTML('beforeend', enrichOrgRow('', '')); }
function addEnrichProject() { document.getElementById('enrich-projects-list').insertAdjacentHTML('beforeend', enrichProjectRow('', '')); }

function collectEnrich() {
  const organizations = {};
  document.querySelectorAll('#enrich-orgs-list .dict-row').forEach(row => {
    const domain = row.querySelector('.enrich-org-domain').value.trim();
    const name = row.querySelector('.enrich-org-name').value.trim();
    if (domain) organizations[domain] = name;
  });
  const projects = [];
  document.querySelectorAll('#enrich-projects-list .dict-row').forEach(row => {
    const alias = row.querySelector('.enrich-proj-alias').value.trim();
    const kw = row.querySelector('.enrich-proj-keywords').value.trim();
    if (alias) {
      projects.push({ alias, keywords: kw ? kw.split(/[,、]/).map(s => s.trim()).filter(Boolean) : [] });
    }
  });
  return { organizations, projects };
}

async function saveEnrich() {
  const status = document.getElementById('enrich-save-status');
  status.className = 'dict-status ok';
  status.textContent = '保存中...';
  try {
    const res = await fetch('/enrich', { method: 'POST', body: JSON.stringify(collectEnrich()) });
    if (!res.ok) { status.className = 'dict-status block'; status.textContent = '保存失敗: ' + await res.text(); return; }
    DATA.enrich = await res.json();
    status.className = 'dict-status ok';
    status.textContent = '保存しました';
  } catch (e) {
    status.className = 'dict-status block'; status.textContent = '保存失敗: ' + e;
  }
}

function renderList() {
  const root = document.getElementById('session-list');
  if (!DATA.sessions.length) { root.innerHTML = '<div class="empty">セッションがありません。scriba start で録音を開始してください。</div>'; return; }
  root.innerHTML = DATA.sessions.map((s, i) => `
    <div class="session-list-item" onclick="location.hash='session=' + encodeURIComponent('${s.id}')">
      <div class="sl-top">
        <div><span class="sl-date">${esc(s.date)}</span><span class="sl-time">${esc(s.time_range)}${s.duration_display !== '—' ? ' · ' + s.duration_display : ''}</span>${s.title ? `<span class="sl-time">${esc(s.title)}</span>` : ''}</div>
        <div class="sl-stats">${s.chunks} chunks${s.chars ? ' · ' + s.chars.toLocaleString() + ' 字' : ''}</div>
      </div>
      <div class="sl-preview">${esc(s.preview)}</div>
    </div>`).join('');
}

function showDetail(i) {
  const s = DATA.sessions[i];
  currentSessionId = s.id;
  document.getElementById('session-list').style.display = 'none';
  document.getElementById('session-detail').style.display = 'block';
  renderDetail(s);
  showDetailView('transcript', document.querySelector('.detail-tab[data-dv="transcript"]'));
}

function renderDetail(s) {
  document.getElementById('d-date').textContent = s.date;
  document.getElementById('d-title').value = s.title || '';
  document.getElementById('d-time').textContent = s.time_range + (s.duration_min != null ? ` · ${s.duration_min} min` : '');
  document.getElementById('d-filename').textContent = s.filename ? `sessions/${s.id}/transcripts/${s.filename}` : '';
  document.getElementById('d-chunks').textContent = s.chunks;
  document.getElementById('d-chars').textContent = s.chars.toLocaleString();
  document.getElementById('d-ptime').textContent = fmtSec(s.process_time_sec);
  document.getElementById('d-rtf').textContent = s.rtf ?? '—';

  // combined を [時刻] [話者] ブロック単位で表示
  const blocks = s.transcript.split(/\n(?=\[\d)/).filter(b => b.trim());
  document.getElementById('detail-transcript').innerHTML = blocks.length
    ? blocks.map(b => {
        const lines = b.trim().split('\n');
        return `<div class="t-chunk"><div class="t-time">${esc(lines[0])}</div><p class="t-text">${esc(lines.slice(1).join(''))}</p></div>`;
      }).join('')
    : '<div class="empty">文字起こし結果がまだありません。</div>';

  const perf = document.getElementById('detail-session-perf');
  if (s.per_chunk.length) {
    const max = Math.max(...s.per_chunk.map(c => c.sec || 0));
    const secs = s.per_chunk.map(c => c.sec || 0);
    perf.innerHTML = `<div class="sparkline-row">${s.per_chunk.map(c =>
      `<div class="spark" style="height:${max ? Math.round((c.sec || 0) / max * 100) : 0}%" data-label="${esc(c.chunk)}: ${(c.sec || 0).toFixed(1)}s"></div>`).join('')}</div>
      <div class="perf-stats">
        <span>Avg: <strong>${(secs.reduce((a, b) => a + b, 0) / secs.length).toFixed(1)}s</strong></span>
        <span>Min: <strong>${Math.min(...secs).toFixed(1)}s</strong></span>
        <span>Max: <strong>${Math.max(...secs).toFixed(1)}s</strong></span>
        <span>RTF: <strong>${s.rtf ?? '—'}</strong></span>
      </div>`;
  } else {
    perf.innerHTML = '<div class="empty">パフォーマンスログがありません。</div>';
  }
}

function backToList() {
  document.getElementById('session-list').style.display = 'block';
  document.getElementById('session-detail').style.display = 'none';
}

let currentSessionId = null;
const IS_HTTP = location.protocol.startsWith('http');

async function copyDiscard() {
  const btn = document.getElementById('discard-btn');
  if (IS_HTTP) {
    // serveモード: サーバー経由でワンクリック削除
    if (!confirm(`${currentSessionId} を削除します。よろしいですか？`)) return;
    const res = await fetch(`/discard?id=${encodeURIComponent(currentSessionId)}`, { method: 'POST' });
    if (!res.ok) { alert('削除に失敗: ' + await res.text()); return; }
    location.hash = 'sessions';
    await refresh();
    return;
  }
  // 静的HTMLからは直接削除できないため、破棄コマンドをコピーして案内する
  const cmd = `scriba discard ${currentSessionId} -y`;
  try {
    await navigator.clipboard.writeText(cmd);
    btn.textContent = 'コマンドをコピーしました — ターミナルで実行してください';
  } catch {
    prompt('このコマンドをターミナルで実行してください:', cmd);
  }
  setTimeout(() => { btn.textContent = 'Discard…'; }, 4000);
}

async function saveTitle() {
  const title = document.getElementById('d-title').value.trim();
  const btn = document.getElementById('d-title-save');
  if (IS_HTTP) {
    const res = await fetch(`/title?id=${encodeURIComponent(currentSessionId)}`, {
      method: 'POST', body: JSON.stringify({ title })
    });
    if (!res.ok) { btn.textContent = '失敗'; setTimeout(() => { btn.textContent = '保存'; }, 2000); return; }
    const s = DATA.sessions.find(x => x.id === currentSessionId);
    if (s) s.title = title;
    renderList();
    btn.textContent = '保存しました'; setTimeout(() => { btn.textContent = '保存'; }, 2000);
    return;
  }
  const cmd = `scriba title ${currentSessionId} "${title.replace(/"/g, '\\"')}"`;
  try {
    await navigator.clipboard.writeText(cmd);
    btn.textContent = 'コマンドをコピーしました'; setTimeout(() => { btn.textContent = '保存'; }, 4000);
  } catch {
    prompt('このコマンドをターミナルで実行してください:', cmd);
  }
}

async function refresh() {
  try {
    const res = await fetch('/data.json');
    if (!res.ok) return;
    DATA = await res.json();
  } catch { return; }
  document.getElementById('generated-at').textContent = DATA.generated_at;
  renderList();
  renderPerformance();
  // 詳細表示中は同じセッションを追従更新（liveモードで文字起こしが伸びていく）
  if (document.getElementById('session-detail').style.display === 'block') {
    const s = DATA.sessions.find(x => x.id === currentSessionId);
    if (s) renderDetail(s); else location.hash = 'sessions';
  }
}
if (IS_HTTP) setInterval(refresh, 5000);

function showDetailView(name, el) {
  document.querySelectorAll('.detail-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('detail-' + name).classList.add('active');
  el.classList.add('active');
}

function renderPerformance() {
  const k = DATA.kpi;
  document.getElementById('kpi-row').innerHTML = `
    <div class="kpi"><div class="kpi-label">Sessions</div><div class="kpi-value">${k.sessions}</div><div class="kpi-sub">total</div></div>
    <div class="kpi"><div class="kpi-label">Duration</div><div class="kpi-value">${k.hours}h</div><div class="kpi-sub">recorded</div></div>
    <div class="kpi"><div class="kpi-label">Characters</div><div class="kpi-value">${k.chars >= 1000 ? (k.chars / 1000).toFixed(1) + 'k' : k.chars}</div><div class="kpi-sub">transcribed</div></div>
    <div class="kpi"><div class="kpi-label">Avg RTF</div><div class="kpi-value">${k.avg_rtf ?? '—'}</div><div class="kpi-sub">process / audio</div></div>`;

  const trend = DATA.trend.filter(t => t.sec != null);
  const max = Math.max(1, ...trend.map(t => t.sec));
  document.getElementById('trend').innerHTML = trend.length
    ? trend.map(t => `<div class="spark" style="height:${Math.round(t.sec / max * 100)}%" data-label="${esc(t.label)}: ${t.sec.toFixed(1)}s"></div>`).join('')
    : '<div class="empty">まだデータがありません。</div>';
  document.getElementById('trend-stats').innerHTML = `
    <span>Model: <strong>${esc(DATA.model)}</strong></span>
    <span>Chunk: <strong>${DATA.chunk_duration}s</strong></span>
    <span>Sample Rate: <strong>${DATA.sample_rate / 1000}kHz</strong></span>`;

  document.getElementById('history').innerHTML =
    '<tr><th>Date</th><th>Time</th><th class="num">Duration</th><th class="num">Chunks</th><th class="num">RTF</th><th class="num">Chars</th></tr>' +
    DATA.sessions.map(s => `<tr>
      <td>${esc(s.date)}</td><td>${esc(s.time_range)}</td>
      <td class="num">${s.duration_min != null ? s.duration_min + ' min' : '—'}</td>
      <td class="num">${s.chunks}</td><td class="num">${s.rtf ?? '—'}</td>
      <td class="num">${s.chars ? s.chars.toLocaleString() : '—'}</td></tr>`).join('');
}

document.getElementById('generated-at').textContent = DATA.generated_at;
renderList();
renderPerformance();
// 初期表示: hash があれば復元、なければ sessions
window.addEventListener('hashchange', router);
if (!location.hash) location.hash = 'sessions';
router();
