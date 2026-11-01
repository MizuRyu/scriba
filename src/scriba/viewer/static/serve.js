// Serve-mode JS helpers (loaded once in layout.html, used by HTMX partials)

function showSubTab(name) {
  document.querySelectorAll('.sub-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.sub-nav-link').forEach(t => t.classList.remove('active'));
  document.getElementById('sub-' + name).classList.add('active');
  event.target.classList.add('active');
}

function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }

function addRow(listId, kind) {
  const list = document.getElementById(listId);
  const del = '<button class="row-del" onclick="this.closest(\'.dict-row\').remove(); onDictInput()">×</button>';
  if (kind === 'term') {
    list.insertAdjacentHTML('beforeend', '<div class="dict-row"><input class="term-word" value="" placeholder="用語（例: 山田）" oninput="onDictInput()">' + del + '</div>');
  } else if (kind === 'repl') {
    list.insertAdjacentHTML('beforeend', '<div class="dict-row"><input class="repl-from" value="" placeholder="誤（例: バックローリー）" oninput="onDictInput()"><span class="dict-arrow">→</span><input class="repl-to" value="" placeholder="正（例: バックログ）" oninput="onDictInput()">' + del + '</div>');
  } else if (kind === 'filter') {
    const fdel = '<button class="row-del" onclick="this.closest(\'.dict-row\').remove()">×</button>';
    list.insertAdjacentHTML('beforeend', '<div class="dict-row"><input class="filter-value" value="" placeholder="除去する発話（例: ありがとうございました）">' + fdel + '</div>');
  }
}

function addEnrichOrg() {
  const del = '<button class="row-del" onclick="this.closest(\'.dict-row\').remove()">×</button>';
  document.getElementById('enrich-orgs-list').insertAdjacentHTML('beforeend',
    '<div class="dict-row"><input class="enrich-org-domain" value="" placeholder="ドメイン（例: example.com）"><span class="dict-arrow">→</span><input class="enrich-org-name" value="" placeholder="組織名（例: Example 社）">' + del + '</div>');
}

function addEnrichProject() {
  const del = '<button class="row-del" onclick="this.closest(\'.dict-row\').remove()">×</button>';
  const up = '<button class="order-btn" onclick="moveEnrichRow(this, -1)">↑</button>';
  const dn = '<button class="order-btn" onclick="moveEnrichRow(this, 1)">↓</button>';
  document.getElementById('enrich-projects-list').insertAdjacentHTML('beforeend',
    '<div class="dict-row"><input class="enrich-proj-alias" value="" placeholder="エイリアス（例: acme）" style="flex:0.6"><input class="enrich-proj-keywords" value="" placeholder="キーワード（カンマ区切り）" style="flex:1">' + up + dn + del + '</div>');
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

function onDictInput() {
  const words = [...document.querySelectorAll('.term-word')].map(i => i.value.trim()).filter(Boolean);
  const haas = document.getElementById('dict-editor').dataset.engine === 'haas';
  const prompt = haas ? words.join('\n') : (words.length ? '会議の用語: ' + words.join('、') : '');
  const n = prompt.length;
  const st = document.getElementById('dict-prompt-status');
  document.getElementById('dict-prompt-preview').textContent = prompt;
  if (haas) { st.className = 'dict-status ok'; st.textContent = `${words.length}語`; return; }
  if (n === 0) { st.className = 'dict-status ok'; st.textContent = ''; return; }
  if (n > 150) { st.className = 'dict-status block'; st.textContent = n + '文字（上限超の恐れ、減らしてください）'; }
  else if (n > 120) { st.className = 'dict-status warn'; st.textContent = n + '文字（上限に接近）'; }
  else { st.className = 'dict-status ok'; st.textContent = n + '文字'; }
}

function collectDict() {
  const terms = [...document.querySelectorAll('.term-word')].map(i => i.value.trim()).filter(Boolean).map(w => ({ word: w }));
  const replacements = [...document.querySelectorAll('#repl-list .dict-row')].map(row => ({
    from: row.querySelector('.repl-from').value.trim(),
    to: row.querySelector('.repl-to').value.trim(),
  })).filter(r => r.from);
  const filters = [...document.querySelectorAll('.filter-value')].map(i => i.value.trim()).filter(Boolean).map(v => ({ value: v }));
  return { terms, replacements, filters };
}

async function saveDict() {
  const status = document.getElementById('dict-save-status');
  status.className = 'dict-status ok';
  status.textContent = '保存中...';
  try {
    const res = await fetch('/dict', { method: 'POST', body: JSON.stringify(collectDict()) });
    if (!res.ok) { status.className = 'dict-status block'; status.textContent = '保存失敗: ' + await res.text(); return; }
    const data = await res.json();
    const v = data.verdict;
    status.className = 'dict-status ' + (v === 'block' ? 'block' : v === 'warn' ? 'warn' : 'ok');
    status.textContent = (v === 'ok' ? '保存しました · ' : '保存（警告あり）· ') + data.message;
  } catch (e) {
    status.className = 'dict-status block'; status.textContent = '保存失敗: ' + e;
  }
}

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
    status.className = 'dict-status ok';
    status.textContent = '保存しました';
  } catch (e) {
    status.className = 'dict-status block'; status.textContent = '保存失敗: ' + e;
  }
}

// Session detail helpers (used by HTMX partials)
function showDetailView(name, el) {
  document.querySelectorAll('.detail-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('detail-' + name).classList.add('active');
  el.classList.add('active');
}

async function discardSession(sid) {
  if (!confirm(sid + ' を削除します。よろしいですか？')) return;
  const res = await fetch('/discard?id=' + encodeURIComponent(sid), { method: 'POST' });
  if (!res.ok) { alert('削除に失敗: ' + await res.text()); return; }
  htmx.ajax('GET', '/partial/sessions', '#content');
}

async function saveTitle(sid) {
  const title = document.getElementById('d-title').value.trim();
  const res = await fetch('/title?id=' + encodeURIComponent(sid), {
    method: 'POST', body: JSON.stringify({ title })
  });
  const btn = event.target;
  if (!res.ok) { btn.textContent = '失敗'; setTimeout(() => { btn.textContent = '保存'; }, 2000); return; }
  btn.textContent = '保存しました'; setTimeout(() => { btn.textContent = '保存'; }, 2000);
}

async function exportSession(sid) {
  const res = await fetch('/export?id=' + encodeURIComponent(sid), { method: 'POST' });
  if (!res.ok) { alert('転送失敗: ' + await res.text()); return; }
  const data = await res.json();
  if (data.skipped) { alert('スキップ: ' + data.reason); return; }
  alert('転送完了: ' + data.path);
  htmx.ajax('GET', '/partial/session/' + encodeURIComponent(sid), '#content');
}

async function remerge(sid, track) {
  const res = await fetch('/merge?id=' + encodeURIComponent(sid) + '&track=' + track, { method: 'POST' });
  if (!res.ok) { alert('再生成失敗: ' + await res.text()); return; }
  htmx.ajax('GET', '/partial/session/' + encodeURIComponent(sid), '#content');
}

async function exportWithProject(sid) {
  const sel = document.getElementById('export-proj-' + sid);
  const proj = sel ? sel.value : '';
  const url = '/export?id=' + encodeURIComponent(sid) + (proj ? '&project=' + encodeURIComponent(proj) : '');
  const res = await fetch(url, { method: 'POST' });
  if (!res.ok) { alert('転送失敗: ' + await res.text()); return; }
  const data = await res.json();
  if (data.skipped) { alert('スキップ: ' + data.reason); return; }
  alert('転送完了: ' + data.path);
  htmx.ajax('GET', '/partial/session/' + encodeURIComponent(sid), '#content');
}
