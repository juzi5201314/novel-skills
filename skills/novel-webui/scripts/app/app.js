/* 墨稿 · 写作台前端。零依赖，直接与 webui.py 的 JSON API 交互。 */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const state = {
  tab: 'chapters',        // 'chapters' | 'lore'
  chapters: null,         // {volumes:[{name,chapters:[...]}], next:{volume,number}}
  lore: null,             // [{name, items:[...]}]
  loreCat: null,          // 当前展开的设定分类
  doc: null,              // {kind:'chapter', id} | {kind:'lore', cat, file}
  dirty: false,
  saveTimer: null,
  filter: '',
};

/* ---------------- 基础 ---------------- */

const api = {
  async get(path) {
    const r = await fetch(path);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    return d;
  },
  async send(method, path, data) {
    const r = await fetch(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    return d;
  },
};

const esc = s => s.replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const wc = s => s.replace(/\s/g, '').length;
const fmtN = n => n.toLocaleString('zh-Hans-CN');

const CN_D = '零一二三四五六七八九';
function cnNum(n) {
  if (n <= 0 || n > 999) return String(n);
  if (n < 10) return CN_D[n];
  if (n < 20) return '十' + (n % 10 ? CN_D[n % 10] : '');
  if (n < 100) return CN_D[Math.floor(n / 10)] + '十' + (n % 10 ? CN_D[n % 10] : '');
  const h = Math.floor(n / 100), r = n % 100;
  return CN_D[h] + '百' + (r === 0 ? '' : r < 10 ? '零' + CN_D[r] : cnNum(r));
}

const volLabel = name => {
  const m = /^vol(\d+)$/i.exec(name);
  return m ? `第${cnNum(+m[1])}卷` : name;
};

function toast(msg, isErr) {
  const t = document.createElement('div');
  t.className = 'toast' + (isErr ? ' err' : '');
  t.textContent = msg;
  $('#toast-root').append(t);
  setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 350); }, 2400);
}

function setStatus(left, right) {
  $('#status-left').textContent = left;
  $('#status-right').textContent = right || '';
}

function setSaveState(mode, time) {
  const el = $('#save-state');
  el.className = mode === 'dirty' ? 'dirty' : '';
  el.textContent = { dirty: '未保存', saving: '保存中…', saved: `已存 ${time}`, '': '' }[mode];
}

/* ---------------- 模态框 ---------------- */

function modal({ title, body, okText = '确定', danger = false, onOk }) {
  const root = $('#modal-root');
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <h3>${esc(title)}</h3>
      <div class="modal-body">${body}</div>
      <div class="modal-actions">
        <button class="btn btn-ghost" data-act="cancel">取消</button>
        <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" data-act="ok">${esc(okText)}</button>
      </div>
    </div>`;
  root.append(overlay);
  const close = () => overlay.remove();
  overlay.addEventListener('mousedown', e => { if (e.target === overlay) close(); });
  $('[data-act="cancel"]', overlay).onclick = close;
  $('[data-act="ok"]', overlay).onclick = async () => {
    try {
      if (await onOk(overlay) !== false) close();
    } catch (e) { toast(e.message, true); }
  };
  const first = $('input, select', overlay);
  if (first) first.focus();
  return close;
}

const confirmDanger = (title, msgHtml, onOk) =>
  modal({ title, body: `<p class="modal-msg">${msgHtml}</p>`, okText: '删除', danger: true, onOk });

/* ---------------- 文档打开 / 保存 ---------------- */

const quill = () => $('.quill');

function markDirty() {
  if (!state.doc) return;
  state.dirty = true;
  setSaveState('dirty');
  updateStatusCounts();
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(save, 1200);
}

async function save() {
  clearTimeout(state.saveTimer);
  const d = state.doc;
  if (!d || !state.dirty || !quill()) return;
  setSaveState('saving');
  const content = quill().value;
  try {
    if (d.kind === 'chapter') {
      await api.send('POST', '/api/chapter-save', { id: d.id, content });
      const ch = findChapter(d.id);
      if (ch) { ch.words = wc(content); paintChapterItem(d.id, ch); updateBookMeta(); }
    } else {
      const r = await api.send('POST', '/api/lore-item-save',
        { category: d.cat, filename: d.file, content });
      const cat = state.lore?.find(c => c.name === d.cat);
      const item = cat?.items.find(i => i.filename === d.file);
      if (item && r.meta) Object.assign(item, r.meta);
    }
    state.dirty = false;
    setSaveState('saved', new Date().toTimeString().slice(0, 5));
  } catch (e) {
    setSaveState('dirty');
    toast('保存失败：' + e.message, true);
  }
}

async function flushSave() {
  clearTimeout(state.saveTimer);
  if (state.dirty) await save();
}

function updateStatusCounts() {
  if (!state.doc || !quill()) return;
  const text = quill().value;
  const paras = text.split('\n').filter(l => l.trim()).length;
  setStatus(`字数 ${fmtN(wc(text))}　·　${paras} 段`, docPath());
}

function docPath() {
  const d = state.doc;
  return d.kind === 'chapter' ? `chapters/${d.id}` : `lore/${d.cat}/${d.file}`;
}

async function openChapter(id) {
  await flushSave();
  const { content } = await api.get(`/api/chapter/${encodeURIComponent(id)}`);
  state.doc = { kind: 'chapter', id };
  state.dirty = false;
  const ch = findChapter(id);
  $('#doc-kind').textContent = ch ? `第${+ch.number || ch.number}章` : '章节';
  $('#doc-title').textContent = ch ? ch.title : id;
  $('#doc-actions').innerHTML = '<button class="btn btn-ghost" id="btn-save">保存</button>';
  $('#btn-save').onclick = save;
  $('#desk').innerHTML = `
    <div class="sheet">
      <div class="folio"><span>${esc(id.toUpperCase())}</span><span>墨稿</span></div>
      <textarea class="quill chapter" spellcheck="false"
        placeholder="　　　正文……"></textarea>
    </div>`;
  quill().value = content;
  quill().addEventListener('input', markDirty);
  quill().focus();
  quill().setSelectionRange(0, 0);
  quill().scrollTop = 0;
  setSaveState('');
  updateStatusCounts();
  $$('.chapter-item').forEach(el => el.classList.toggle('is-active', el.dataset.id === id));
}

async function openLoreItem(cat, file) {
  await flushSave();
  const { content } = await api.get(`/api/lore-item/${encodeURIComponent(cat)}/${encodeURIComponent(file)}`);
  state.doc = { kind: 'lore', cat, file };
  state.dirty = false;
  $('#doc-kind').textContent = '设定';
  $('#doc-title').textContent = file.replace(/\.md$/, '');
  $('#doc-actions').innerHTML = `
    <button class="btn btn-ghost" id="btn-back">‹ 返回</button>
    <button class="btn btn-ghost" id="btn-save">保存</button>`;
  $('#btn-back').onclick = () => openShelf(cat);
  $('#btn-save').onclick = save;
  $('#desk').innerHTML = `
    <div class="sheet">
      <div class="folio"><span>LORE / ${esc(cat.toUpperCase())}</span><span>墨稿</span></div>
      <textarea class="quill lore" spellcheck="false" placeholder="---&#10;name: …&#10;---"></textarea>
    </div>`;
  quill().value = content;
  quill().addEventListener('input', markDirty);
  quill().focus();
  quill().setSelectionRange(0, 0);
  quill().scrollTop = 0;
  setSaveState('');
  updateStatusCounts();
}

function openShelf(cat) {
  state.doc = null;
  state.loreCat = cat;
  state.dirty = false;
  clearTimeout(state.saveTimer);
  const catObj = (state.lore || []).find(c => c.name === cat);
  const label = catObj?.label || cat;
  const items = (catObj ? catObj.items : []).filter(i =>
    !state.filter || i.name.includes(state.filter) || i.filename.includes(state.filter));
  $('#doc-kind').textContent = '设定';
  $('#doc-title').textContent = label;
  $('#doc-actions').innerHTML =
    (catObj?.schema ? '<button class="btn btn-ghost" id="btn-schema">分类模板</button>' : '') +
    '<button class="btn btn-primary" id="btn-new-item">＋ 新建设定</button>';
  if (catObj?.schema) $('#btn-schema').onclick = () => openLoreItem(cat, '_schema.md');
  $('#btn-new-item').onclick = showNewLoreItemModal;
  $('#desk').innerHTML = `
    <div class="shelf">
      <div class="shelf-title"><h3>${esc(label)}</h3><span class="n">${items.length} 项</span></div>
      <div class="card-grid" id="card-grid"></div>
    </div>`;
  const grid = $('#card-grid');
  if (!items.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1;min-height:300px">
      <div class="empty-seal">空</div><p>这个分类还没有设定</p>
      <p class="hint">点右上角「＋ 新建设定」创建第一条</p></div>`;
  }
  for (const it of items) {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <h4>${esc(it.name)}</h4>
      ${it.tags.length ? `<div class="tags">${it.tags.map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : ''}
      <p class="preview">${esc(it.preview || '（空文件）')}</p>
      <div class="card-actions">
        <button class="btn btn-ghost" data-act="edit">编辑</button>
        <button class="btn btn-danger" data-act="del">删除</button>
      </div>`;
    $('[data-act="edit"]', card).onclick = () => openLoreItem(cat, it.filename);
    $('[data-act="del"]', card).onclick = () =>
      confirmDanger('删除设定', `确定删除 <strong>${esc(it.name)}</strong>（${esc(it.filename)}）？此操作不可撤销。`, async () => {
        await api.send('POST', '/api/lore-item-delete', { category: cat, filename: it.filename });
        toast('已删除');
        await loadLore();
        openShelf(cat);
      });
    grid.append(card);
  }
  setStatus(`${cat} · ${items.length} 项`, `lore/${cat}/`);
  setSaveState('');
  $$('.cat-item').forEach(el => el.classList.toggle('is-active', el.dataset.cat === cat));
}

function showEmpty(msg, hint) {
  $('#doc-kind').textContent = '';
  $('#doc-title').textContent = '';
  $('#doc-actions').innerHTML = '';
  $('#desk').innerHTML = `
    <div class="empty">
      <div class="empty-seal">墨</div>
      <p>${esc(msg)}</p>
      ${hint ? `<p class="hint">${esc(hint)}</p>` : ''}
    </div>`;
  setSaveState('');
}

/* ---------------- 面板渲染 ---------------- */

function findChapter(id) {
  for (const v of state.chapters?.volumes || [])
    for (const c of v.chapters) if (c.id === id) return c;
  return null;
}

function paintChapterItem(id, ch) {
  const el = $(`.chapter-item[data-id="${CSS.escape(id)}"] .wc`);
  if (el) el.textContent = fmtN(ch.words);
}

function skeleton() {
  $('#panel-list').innerHTML =
    `<div class="skel">${'<div class="skel-line"></div>'.repeat(9)}</div>`;
}

function renderChaptersPanel() {
  const box = $('#panel-list');
  box.innerHTML = '';
  const vols = state.chapters?.volumes || [];
  const q = state.filter;
  let shown = 0;

  for (const vol of vols) {
    const items = vol.chapters.filter(c =>
      !q || c.title.includes(q) || c.number.includes(q));
    if (!items.length && q) continue;
    const head = document.createElement('div');
    head.className = 'vol-head';
    head.innerHTML = `
      <span class="vol-name">${esc(volLabel(vol.name))}</span>
      <span class="vol-latin">${esc(vol.name.toUpperCase())}</span>
      <span class="vol-count">${items.length}</span>`;
    box.append(head);

    for (const c of items) {
      shown++;
      const el = document.createElement('div');
      el.className = 'chapter-item' + (state.doc?.id === c.id ? ' is-active' : '');
      el.dataset.id = c.id;
      el.innerHTML = `
        <button class="pick" title="打开本章">
          <span class="num">${esc(c.number || '—')}</span>
          <span class="title">${esc(c.title)}</span>
          <span class="wc">${fmtN(c.words)}</span>
        </button>
        <button class="del" title="删除本章" data-del>×</button>`;
      $('.pick', el).onclick = () =>
        openChapter(c.id).catch(e => toast(e.message, true));
      $('[data-del]', el).onclick = () =>
        confirmDanger('删除章节', `确定删除 <strong>${esc(volLabel(c.id.split('/')[0]))} · ${esc(c.title)}</strong>？文件将从磁盘移除。`, async () => {
          await api.send('POST', '/api/chapter-delete', { id: c.id });
          toast('已删除');
          if (state.doc?.id === c.id) { state.doc = null; showEmpty('选择一章开始写作', '左侧是章节树，按卷分组'); }
          await loadChapters(false);
        });
      box.append(el);
    }
  }
  if (!shown) {
    box.innerHTML = `<div class="panel-empty">${q ? '没有匹配的章节' : '还没有章节<br>点击下方按钮写下第一章'}</div>`;
  }
}

function renderLorePanel() {
  const box = $('#panel-list');
  box.innerHTML = '';
  const cats = (state.lore || []).filter(c =>
    !state.filter || c.name.includes(state.filter) || (c.label || '').includes(state.filter));
  for (const c of cats) {
    const el = document.createElement('div');
    el.className = 'cat-item' + (state.loreCat === c.name && state.doc?.kind !== 'lore' ? ' is-active' : '');
    el.dataset.cat = c.name;
    el.innerHTML = `
      <button class="pick" title="查看该分类">
        <span class="cat-name">${esc(c.label || c.name)}</span>
        <span class="cat-count">${c.items.length}</span>
      </button>
      <button class="del" title="删除分类（须为空）" data-del>×</button>`;
    $('.pick', el).onclick = () => flushSave().then(() => openShelf(c.name));
    $('[data-del]', el).onclick = () =>
      confirmDanger('删除分类', `确定删除分类 <strong>${esc(c.label || c.name)}</strong>？仅当分类为空时可删除。`, async () => {
        try {
          await api.send('DELETE', `/api/lore-category/${encodeURIComponent(c.name)}`);
        } catch (e) { toast(e.message, true); return false; }
        toast('已删除');
        if (state.loreCat === c.name) { state.loreCat = null; showEmpty('选择一个分类', '或新建一个分类'); }
        await loadLore();
      });
    box.append(el);
  }
  if (!cats.length) {
    box.innerHTML = `<div class="panel-empty">还没有设定分类<br>下方新建一个，如 characters / locations</div>`;
  }
}

function updateBookMeta() {
  const vols = state.chapters?.volumes || [];
  const n = vols.reduce((a, v) => a + v.chapters.length, 0);
  const w = vols.reduce((a, v) => a + v.chapters.reduce((x, c) => x + c.words, 0), 0);
  $('#book-meta').textContent = n ? `${vols.length} 卷 · ${n} 章 · ${fmtN(w)} 字` : '尚未开卷';
}

/* ---------------- 新建 ---------------- */

function showNewChapterModal() {
  const next = state.chapters?.next || { volume: 'vol01', number: '0001' };
  const vols = (state.chapters?.volumes || []).map(v => v.name);
  const opts = [...vols, '__new__'].map(v =>
    v === '__new__' ? '<option value="__new__">＋ 新卷…</option>'
      : `<option value="${esc(v)}" ${v === next.volume ? 'selected' : ''}>${esc(v)}（${esc(volLabel(v))}）</option>`);
  modal({
    title: '新章节',
    body: `
      <div class="field"><label>卷</label>
        <select id="f-vol">${opts.join('')}</select>
        <input id="f-vol-new" style="display:none;margin-top:8px" placeholder="新卷目录名，如 vol02">
      </div>
      <div class="field"><label>章号</label>
        <input id="f-num" value="${esc(next.number)}" inputmode="numeric">
      </div>
      <div class="field"><label>标题</label>
        <input id="f-title" placeholder="章名，如 道童惊梦">
      </div>`,
    okText: '创建',
    onOk: async ov => {
      let volume = $('#f-vol', ov).value;
      if (volume === '__new__') {
        volume = $('#f-vol-new', ov).value.trim();
        if (!volume) { toast('请填写新卷名', true); return false; }
      }
      const number = $('#f-num', ov).value.trim();
      const title = $('#f-title', ov).value.trim();
      if (!number || !title) { toast('章号和标题必填', true); return false; }
      const d = await api.send('POST', '/api/chapter-create', { volume, number, title });
      toast('已创建');
      await loadChapters(false);
      await openChapter(d.id);
    },
  });
  const sel = $('#modal-root select#f-vol');
  sel.addEventListener('change', () => {
    $('#f-vol-new').style.display = sel.value === '__new__' ? '' : 'none';
  });
}

function showNewCategoryModal() {
  modal({
    title: '新建设定分类',
    body: `
      <div class="field"><label>分类目录名</label>
        <input id="f-cat" placeholder="如 characters、sects，嵌套用 orgs/churches">
        <p class="field-hint">建议英文小写，可嵌套子目录；文件名仍可用中文，如 characters/鸿钧.md</p>
      </div>`,
    okText: '创建',
    onOk: async ov => {
      const name = $('#f-cat', ov).value.trim();
      if (!name) { toast('请输入分类名', true); return false; }
      await api.send('POST', '/api/lore-category-create', { name });
      toast('已创建');
      await loadLore();
      openShelf(name);
    },
  });
}

function showNewLoreItemModal() {
  modal({
    title: `新建设定 · ${state.loreCat}`,
    body: `
      <div class="field"><label>名称</label>
        <input id="f-name" placeholder="实体名，如 鸿钧、紫霄宫">
        <p class="field-hint">自动添加 .md 后缀，并写入 name/aliases/type/tags frontmatter</p>
      </div>`,
    okText: '创建',
    onOk: async ov => {
      const name = $('#f-name', ov).value.trim();
      if (!name) { toast('请输入名称', true); return false; }
      const d = await api.send('POST', '/api/lore-item-create',
        { category: state.loreCat, name });
      toast('已创建');
      await loadLore();
      await openLoreItem(state.loreCat, d.filename);
    },
  });
}

/* ---------------- 加载与切换 ---------------- */

async function loadProject() {
  const info = await api.get('/api/project');
  document.title = `${info.name} · 墨稿`;
  $('#book-name').textContent = info.name;
  $('#rail-book').innerHTML = [...info.name].map(c => `<span>${esc(c)}</span>`).join('');
  $('#rail-book').title = info.root;
}

async function loadChapters(keepEmpty = true) {
  state.chapters = await api.get('/api/chapters');
  renderChaptersPanel();
  updateBookMeta();
  if (keepEmpty && !state.doc) showEmpty('选择一章开始写作', '左侧是章节树，按卷分组');
}

async function loadLore() {
  state.lore = await api.get('/api/lore/tree');
  renderLorePanel();
}

function switchTab(tab) {
  if (state.tab === tab) return;
  state.tab = tab;
  flushSave();
  state.filter = '';
  $('#filter').value = '';
  $$('.rail-item').forEach(b => b.classList.toggle('is-active', b.dataset.tab === tab));
  $('#btn-new').textContent = tab === 'chapters' ? '＋ 新章节' : '＋ 新分类';
  skeleton();
  if (tab === 'chapters') {
    renderChaptersPanel();
    if (!state.doc) showEmpty('选择一章开始写作', '左侧是章节树，按卷分组');
  } else {
    renderLorePanel();
    if (state.loreCat) openShelf(state.loreCat);
    else showEmpty('选择一个分类查看设定', '分类由你自定义，如 characters、items');
  }
}

/* ---------------- 启动 ---------------- */

async function init() {
  $$('.rail-item').forEach(b => b.onclick = () => switchTab(b.dataset.tab));
  $('#btn-new').onclick = () =>
    state.tab === 'chapters' ? showNewChapterModal() : showNewCategoryModal();
  $('#filter').addEventListener('input', e => {
    state.filter = e.target.value.trim();
    (state.tab === 'chapters' ? renderChaptersPanel : renderLorePanel)();
  });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); }
    if (e.key === 'Escape') $('.overlay')?.remove();
  });
  window.addEventListener('beforeunload', () => {
    if (state.dirty && state.doc && quill()) {
      const d = state.doc;
      const payload = d.kind === 'chapter'
        ? { id: d.id, content: quill().value }
        : { category: d.cat, filename: d.file, content: quill().value };
      navigator.sendBeacon(
        d.kind === 'chapter' ? '/api/chapter-save' : '/api/lore-item-save',
        new Blob([JSON.stringify(payload)], { type: 'application/json' }));
    }
  });

  skeleton();
  try {
    await Promise.all([loadProject(), loadChapters(), loadLore()]);
    renderChaptersPanel();
  } catch (e) {
    toast('加载失败：' + e.message, true);
    showEmpty('无法连接服务', e.message);
  }
}

init();
