const $ = (selector, root = document) => root.querySelector(selector);
const app = $('#app');
const state = {
  orders: [], view: 'home', draft: null, contractor: '全部', search: '',
  year: new Date().getFullYear(), busy: false, workspaceId: null, csrf: '', canWrite: false, trash: [],
};
const text = value => String(value ?? '');
const esc = value => text(value).replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const dateToday = () => new Date().toLocaleDateString('sv-SE');
const sum = order => order.items.reduce((n, item) => n + Number(item.quantity || 0), 0);
const categories = ['篮球', '跑鞋', '训练', '休闲', '户外', '童鞋', '其他'];
const makers = ['杨祖锐', '徐亮', '张宇昂', '隋晗', '庄旭宏', '延领'];
const itemUnits = order => [...new Set(order.items.map(item => item.contractor || (order.contractor !== '混合' ? order.contractor : '')).filter(Boolean))];

function route(suffix = '') { return `/api/workspaces/${state.workspaceId}/sample-orders${suffix}`; }
async function api(path, options = {}) {
  const headers = {'Content-Type':'application/json'};
  if (options.method && options.method !== 'GET') headers['X-CSRF-Token'] = state.csrf;
  const response = await fetch(path, {credentials:'same-origin', headers, ...options});
  let data;
  try { data = await response.json(); } catch { data = null; }
  if (!response.ok) throw new Error(data?.error?.message || `请求失败（${response.status}）`);
  return data;
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove('show'), 4200);
}

function newItem() {
  return {id: crypto.randomUUID(), style:'', category:'', contractor:'', sole:'', gender:'男', photo_file:'', color:'', quantity:1, size:'', purpose:'', due_date:'', remark:''};
}

function newOrder() {
  const today = dateToday();
  const prefix = today.replaceAll('-', '');
  const existing = state.orders.filter(order => order.number.startsWith(prefix + '-')).map(order => Number(order.number.slice(prefix.length + 1)) || 0);
  state.draft = {number:`${prefix}-${Math.max(0, ...existing) + 1}`, order_date:today, status:'待签字', contractor:'', handover_status:'未接收', receiver:'', requester:'', department:'科技中心', note:'', scan_file:'', items:[newItem()]};
  state.view = 'form';
  render();
}

function editOrder(id) {
  const order = state.orders.find(value => value.id === id);
  if (!order) return;
  state.draft = structuredClone(order);
  state.view = 'form';
  render();
}

function setView(view) {
  state.view = view;
  if (view === 'trash') api(route('/trash')).then(rows => {state.trash = rows; render();}).catch(error => toast(error.message));
  render();
}

function labelForStatus(value) {
  return `<span class="pill ${value === '已下单' ? 'green' : value === '已签字' ? 'blue' : 'neutral'}">${esc(value)}</span>`;
}

function labelForHandover(value) {
  return `<span class="pill ${value === '完全接收' ? 'green' : value === '部分接收' ? 'orange' : 'neutral'}">${esc(value)}</span>`;
}

function header(title, subtitle, action = '') {
  return `<div class="page-head"><div><div class="eyebrow">SAMPLE ORDER WORKSPACE</div><h1>${title}</h1><p>${subtitle}</p></div>${action}</div>`;
}

function renderHome() {
  const currentYear = new Date().getFullYear();
  const placed = state.orders.filter(order => order.status === '已下单' && order.order_date.startsWith(String(currentYear)));
  const metric = (title, value, unit) => `<div class="metric"><span>${title}</span><strong>${value}<small>${unit}</small></strong></div>`;
  const recent = state.orders.slice(0, 5).map(order => `<button class="recent" data-action="edit" data-id="${esc(order.id)}"><span class="recent-icon">▤</span><span class="recent-main"><strong>${esc(order.number)}</strong><small>${order.items.length} 款鞋 · ${sum(order)} 双 · ${esc(order.order_date)} · ${esc(itemUnits(order).join('、') || '未分配')}</small><small>交接：${esc(order.handover_status)} · 接收人：${esc(order.receiver || '—')}</small></span>${labelForStatus(order.status)}</button>`).join('');
  return header('样鞋需求，一目了然', '录入鞋款，生成签字表，留存每一笔样品下单记录。', '<div class="actions"><a class="btn" href="/">← 返回 Flowboard</a><button class="btn primary write-action" data-action="new">＋ 新建需求单</button></div>') +
    `<div class="metrics">${metric('需求单总数', state.orders.length, '份')}${metric('待签字', state.orders.filter(order => order.status === '待签字').length, '份')}${metric(`${currentYear} 年已下单`, placed.length, '份')}${metric(`${currentYear} 年样鞋数量`, placed.reduce((n, order) => n + sum(order), 0), '双')}</div>` +
    `<div class="home-grid"><section class="panel"><div class="panel-head"><div><h2>最近的需求单</h2><p>按申请日期排序</p></div><button class="btn ghost" data-action="list">查看全部 ›</button></div>${recent || '<div class="empty">尚无需求单，点击右上角开始录入。</div>'}</section><section class="panel"><div class="panel-head"><div><h2>下单流程</h2><p>沿用签批和扫描留档流程</p></div></div><div class="flow"><div class="flow-step"><span>01</span><div><strong>录入鞋款信息</strong><p>填写款号、底模号、数量、图片和承接单位。</p></div></div><div class="flow-step"><span>02</span><div><strong>导出 Excel 签字</strong><p>使用原始模板生成签字单。</p></div></div><div class="flow-step"><span>03</span><div><strong>扫描并标记已下单</strong><p>上传扫描件，记录交接情况，进入年度统计。</p></div></div></div></section></div>`;
}

function visibleOrders() {
  const needle = state.search.trim().toLowerCase();
  return state.orders.filter(order => (state.contractor === '全部' || itemUnits(order).includes(state.contractor)) && (!needle || `${order.number} ${order.requester} ${order.items.map(item => `${item.style} ${item.category} ${item.sole}`).join(' ')}`.toLowerCase().includes(needle)));
}

function tableRows() {
  const rows = visibleOrders();
  if (!rows.length) return '<tr><td colspan="9" class="empty">没有匹配的需求单</td></tr>';
  return rows.map(order => `<tr data-action="edit" data-id="${esc(order.id)}"><td><strong>${esc(order.number)}</strong></td><td>${esc(order.order_date)}</td><td>${esc(order.items.slice(0, 2).map(item => item.style).join('、'))}${order.items.length > 2 ? ` 等 ${order.items.length} 款` : ''}<small>${esc([...new Set(order.items.map(item => item.category))].join(' / '))}</small></td><td><span class="contractor-pill">${esc(itemUnits(order).join('、') || '未分配')}</span></td><td>${sum(order)} 双</td><td>${labelForStatus(order.status)}</td><td>${labelForHandover(order.handover_status)}</td><td>${esc(order.receiver || '—')}</td><td>›</td></tr>`).join('');
}

function renderOrders() {
  const tabs = ['全部', '先锋', '外协', '大货'].map(name => `<button class="${state.contractor === name ? 'active' : ''}" data-action="filter" data-name="${name}">${name}${name !== '全部' ? `<small>${state.orders.filter(order => itemUnits(order).includes(name)).length}</small>` : ''}</button>`).join('');
  return header('需求单', '按承接单位查看需求单，并跟踪交接情况。', '<button class="btn primary write-action" data-action="new">＋ 新建需求单</button>') +
    `<section class="panel"><div class="tabs">${tabs}</div><div class="toolbar"><input id="search" class="search" placeholder="搜索编号、款号、品类或底模号" value="${esc(state.search)}" aria-label="搜索需求单"><span class="muted">共 <b id="result-count">${visibleOrders().length}</b> 份</span></div><div class="table-scroll"><table class="records"><thead><tr><th>需求单编号</th><th>申请日期</th><th>鞋款 / 品类</th><th>承接单位</th><th>数量</th><th>流程状态</th><th>交接状态</th><th>接收人</th><th></th></tr></thead><tbody id="orders-body">${tableRows()}</tbody></table></div></section>`;
}

function field(label, name, value, type = 'text', required = false, extra = '') {
  return `<div class="field"><label for="field-${name}">${label}${required ? ' *' : ''}</label><input id="field-${name}" name="${name}" type="${type}" value="${esc(value)}" ${required ? 'required' : ''} ${extra}></div>`;
}

function selectField(label, name, value, options) {
  return `<div class="field"><label for="field-${name}">${label}</label><select id="field-${name}" name="${name}">${options.map(option => `<option value="${esc(option)}" ${option === value ? 'selected' : ''}>${esc(option)}</option>`).join('')}</select></div>`;
}

function itemField(label, name, value, type = 'text', required = false, extra = '') {
  return `<div class="field"><label>${label}${required ? ' *' : ''}</label><input data-item-field="${name}" type="${type}" value="${esc(value)}" ${required ? 'required' : ''} ${extra}></div>`;
}

function itemCard(item, index) {
  const categoryOptions = [...new Set([...categories, item.category].filter(Boolean))];
  const preview = item.photo_file ? `<img src="${route(`/files/${encodeURIComponent(item.photo_file)}`)}" alt="鞋款图片">` : '<span>＋ 上传鞋款图片</span><small>JPG / PNG，≤ 10 MB</small>';
  const units = ['先锋','外协','大货'].map(name => `<label class="unit-choice"><input type="radio" name="item-contractor-${index}" value="${name}" ${(item.contractor || state.draft.contractor) === name ? 'checked' : ''}><span>${name}</span></label>`).join('');
  return `<div class="item-card" data-item-index="${index}"><div class="item-head"><strong>鞋款 ${index + 1}</strong><div class="item-actions"><button class="btn" type="button" data-action="copy-item" data-index="${index}">复制该款明细</button><button class="btn danger" type="button" data-action="remove-item" data-index="${index}" ${state.draft.items.length === 1 ? 'disabled' : ''}>删除</button></div></div><div class="item-layout"><label class="photo-box">${preview}<input class="photo-input" type="file" accept="image/png,image/jpeg" data-index="${index}" aria-label="上传第 ${index + 1} 款鞋图片"></label><div class="item-fields"><div class="fields">${itemField('款号', 'style', item.style, 'text', true)}<div class="field"><label>品类 *</label><input data-item-field="category" list="categories" value="${esc(item.category)}" required></div>${itemField('底模号', 'sole', item.sole)}<div class="field"><label>性别</label><select data-item-field="gender">${['男','女','中性','童'].map(value => `<option ${item.gender === value ? 'selected' : ''}>${value}</option>`).join('')}</select></div></div><div class="fields">${itemField('配色', 'color', item.color)}${itemField('数量（双）', 'quantity', item.quantity, 'number', true, 'min="1" max="9999"')}${itemField('号码', 'size', item.size)}${itemField('需求时间', 'due_date', item.due_date, 'date')}</div><div class="fields two"><div class="field"><label>用途说明</label><textarea data-item-field="purpose" rows="2">${esc(item.purpose)}</textarea></div><div class="field"><label>备注</label><textarea data-item-field="remark" rows="2">${esc(item.remark)}</textarea></div></div><div class="item-contractor"><span class="field-label">承接单位 *</span><div class="item-units">${units}</div></div></div></div></div>`;
}

function section(number, title, subtitle, body) {
  return `<section class="panel section"><div class="section-title"><span>${number}</span><div><h2>${title}</h2><p>${subtitle}</p></div></div>${body}</section>`;
}

function renderForm() {
  const order = state.draft;
  if (!order) return '';
  const makerChoices = makers.map(name => `<label class="maker-choice"><input type="radio" name="requester" value="${name}" ${order.requester === name ? 'checked' : ''}><span>${name}</span></label>`).join('');
  const scan = order.scan_file ? `已上传扫描件` : '点击上传签字扫描件（PDF，≤ 30 MB）';
  const scanLink = order.scan_file ? `<a class="scan-link" href="${route(`/files/${encodeURIComponent(order.scan_file)}`)}" target="_blank">查看扫描件 ›</a>` : '';
  const exportButton = order.id ? `<a class="btn" href="${route(`/${encodeURIComponent(order.id)}/signed.xlsx`)}">↓ 导出签字 Excel</a>` : '';
  return `<div class="page-head"><div><div class="eyebrow">SAMPLE ORDER FORM</div><h1>${order.id ? '编辑需求单' : '新建需求单'}</h1><p>按原签字表字段录入，保存后可随时导出 Excel。合计 ${sum(order)} 双</p></div><div class="actions"><button class="btn" data-action="list">返回列表</button>${exportButton}<button class="btn primary" type="submit" form="order-form" ${state.busy ? 'disabled' : ''}>保存需求单</button></div></div><form id="order-form"><datalist id="categories">${categories.map(value => `<option value="${value}"></option>`).join('')}</datalist>` +
    section('01','需求单信息','编号、申请日期、制表人和流程状态', `<div class="fields">${field('需求单编号','number',order.number,'text',true)}${field('申请日期','order_date',order.order_date,'date',true)}${selectField('状态','status',order.status,['待签字','已签字','已下单'])}</div><div class="maker-block"><span class="field-label">制表人</span><div class="maker-options">${makerChoices}</div></div>`) +
    section('02','鞋款明细','一行对应一个鞋款、配色与需求数量', `<div id="item-list">${order.items.map(itemCard).join('')}</div><button type="button" class="add-item" data-action="add-item">＋ 添加一行鞋款</button>`) +
    section('03','签字与留档','导出签字表后，可上传已签字的 PDF 扫描件', `<div class="fields two"><div class="field"><label for="field-note">需求单备注</label><textarea id="field-note" name="note" rows="3">${esc(order.note)}</textarea></div><div><span class="field-label">签字扫描件（PDF）</span><label class="scan-box">${scan}<input id="scan-input" type="file" accept="application/pdf" aria-label="上传签字扫描件"></label>${scanLink}</div></div>`) +
    section('04','交接记录','记录承接后的接收情况', `<div class="fields two">${selectField('交接状态','handover_status',order.handover_status,['未接收','部分接收','完全接收'])}${field('接收人','receiver',order.receiver)}</div><p class="hint">选择“部分接收”或“完全接收”时，请填写接收人。</p>`) +
    `<div class="footer-actions"><small>签字 Excel 沿用原始模板；承接单位和交接记录仅保存在系统中。</small><div class="actions">${order.id ? `<button type="button" class="btn danger" data-action="delete">删除</button>${exportButton}` : ''}<button class="btn primary" type="submit" ${state.busy ? 'disabled' : ''}>保存需求单</button></div></div></form>`;
}

function statsData() {
  const orders = state.orders.filter(order => order.status === '已下单' && order.order_date.startsWith(String(state.year)));
  const groups = new Map();
  for (const order of orders) for (const item of order.items) {
    const category = item.category || '未分类';
    if (!groups.has(category)) groups.set(category, {styles:new Set(), pairs:0});
    groups.get(category).styles.add(item.style);
    groups.get(category).pairs += Number(item.quantity || 0);
  }
  return {orders, groups:[...groups].sort((a,b) => b[1].pairs - a[1].pairs)};
}

function renderStats() {
  const years = [...new Set([new Date().getFullYear(), state.year, ...state.orders.map(order => Number(order.order_date.slice(0,4)))] )].sort((a,b) => b-a);
  const {orders,groups} = statsData();
  const styles = new Set(orders.flatMap(order => order.items.map(item => item.style))).size;
  const pairs = orders.reduce((n,order) => n+sum(order),0);
  const rows = groups.map(([name,data]) => `<tr><td>${esc(name)}</td><td>${data.styles.size}</td><td>${data.pairs}</td></tr>`).join('');
  return header('年度统计', '按申请日期统计已下单的样鞋品类、款号和数量。', `<div class="actions"><select id="year-select" class="stats-year" aria-label="统计年份">${years.map(year => `<option ${year === state.year ? 'selected' : ''}>${year}</option>`).join('')}</select><a class="btn primary" href="${route(`/annual.xlsx?year=${state.year}`)}">↓ 导出年度 Excel</a></div>`) +
    `<div class="metrics three"><div class="metric"><span>已下单需求单</span><strong>${orders.length}<small>份</small></strong></div><div class="metric"><span>不同款号</span><strong>${styles}<small>款</small></strong></div><div class="metric"><span>样鞋总数量</span><strong>${pairs}<small>双</small></strong></div></div><div class="stats-layout"><section class="panel"><div class="panel-head"><div><h2>品类汇总</h2><p>${state.year} 年 · 已下单记录</p></div></div><table class="stats-table"><thead><tr><th>品类</th><th>不同款号（款）</th><th>数量（双）</th></tr></thead><tbody>${rows || '<tr><td colspan="3" class="empty">该年份暂无已下单记录</td></tr>'}</tbody></table></section><section class="panel"><div class="panel-head"><div><h2>统计口径与数据备份</h2><p>由 Flowboard 服务器保存</p></div></div><div class="stats-note"><strong>统计口径</strong><ul><li>按需求单申请日期归属年份，仅计入“已下单”的记录。</li><li>不同款号按款号文字去重，数量按每一行鞋款的双数求和。</li><li>承接单位、交接状态及接收人包含在年度明细 Excel 中。</li></ul><strong>数据位置</strong><p>需求记录和附件保存在 Flowboard 服务器，由部门统一备份。</p></div></section></div>`;
}

function render() {
  const title = {home:'工作总览',orders:'需求单列表',stats:'年度统计',trash:'回收站',form:state.draft?.id ? '编辑需求单' : '新建需求单'}[state.view];
  $('#crumb').textContent = title;
  document.querySelectorAll('.nav button').forEach(button => button.classList.toggle('active', button.dataset.view === (state.view === 'form' ? 'orders' : state.view)));
  app.innerHTML = state.view === 'home' ? renderHome() : state.view === 'orders' ? renderOrders() : state.view === 'stats' ? renderStats() : state.view === 'trash' ? renderTrash() : renderForm();
  if (!state.canWrite) app.querySelectorAll('.write-action, #order-form input, #order-form select, #order-form textarea, #order-form button').forEach(node => node.disabled = true);
}

function collectForm() {
  const form = $('#order-form');
  if (!form) return;
  const previous = state.draft;
  const value = name => form.elements.namedItem(name)?.value || '';
  const items = [...form.querySelectorAll('.item-card')].map((card,index) => {
    const item = {...previous.items[index]};
    card.querySelectorAll('[data-item-field]').forEach(input => item[input.dataset.itemField] = input.value);
    item.contractor = card.querySelector(`input[name="item-contractor-${index}"]:checked`)?.value || '';
    item.quantity = Number(item.quantity);
    return item;
  });
  state.draft = {...previous, number:value('number').trim(), order_date:value('order_date'), requester:form.querySelector('[name="requester"]:checked')?.value || '', status:value('status'), note:value('note').trim(), handover_status:value('handover_status'), receiver:value('receiver').trim(), items};
}

async function refreshOrders() {
  state.orders = await api(route());
  state.orders.sort((a,b) => b.order_date.localeCompare(a.order_date) || b.created_at.localeCompare(a.created_at));
}

async function saveOrder() {
  if (state.busy) return;
  collectForm();
  const order = state.draft;
  if (order.items.some(item => !item.contractor)) { toast('请为每一款鞋选择承接单位'); return; }
  if (order.handover_status !== '未接收' && !order.receiver) { toast('请填写接收人'); return; }
  state.busy = true;
  try {
    const path = order.id ? route(`/${encodeURIComponent(order.id)}`) : route();
    await api(path, {method:order.id ? 'PUT' : 'POST',body:JSON.stringify(order)});
    await refreshOrders();
    state.view = 'orders';
    render();
    toast('需求单已保存到共享工作区');
  } catch (error) { toast(error.message); }
  finally { state.busy = false; }
}

async function deleteOrder() {
  if (!state.draft?.id || !confirm(`确定删除需求单 ${state.draft.number} 吗？可在回收站恢复。`)) return;
  try {
    await api(route(`/${encodeURIComponent(state.draft.id)}`), {method:'DELETE',body:JSON.stringify({version:state.draft.version})});
    await refreshOrders();
    state.view = 'orders';
    render();
    toast('需求单已删除');
  } catch (error) { toast(error.message); }
}

function base64FromFile(file) {
  return new Promise((resolve,reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('读取附件失败'));
    reader.readAsDataURL(file);
  });
}

async function upload(file, kind, index) {
  if (!file) return;
  const limit = kind === 'photo' ? 10 : 30;
  if (file.size > limit * 1024 * 1024) { toast(`附件不能超过 ${limit} MB`); return; }
  collectForm();
  try {
    toast('正在上传附件…');
    const result = await api(route('/upload'), {method:'POST',body:JSON.stringify({kind,data:await base64FromFile(file)})});
    if (kind === 'photo') state.draft.items[index].photo_file = result.file;
    else state.draft.scan_file = result.file;
    render();
    toast('附件已上传；请再保存需求单');
  } catch (error) { toast(error.message); }
}

document.querySelectorAll('.nav button').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
app.addEventListener('click', event => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  if (action === 'new') newOrder();
  else if (action === 'list') setView('orders');
  else if (action === 'edit') editOrder(button.dataset.id);
  else if (action === 'filter') { state.contractor = button.dataset.name; render(); }
  else if (action === 'add-item') { collectForm(); if (state.draft.items.length >= 50) return toast('每张需求单最多 50 行鞋款'); state.draft.items.push(newItem()); render(); }
  else if (action === 'copy-item') { collectForm(); if (state.draft.items.length >= 50) return toast('每张需求单最多 50 行鞋款'); const index = Number(button.dataset.index); state.draft.items.splice(index + 1, 0, {...state.draft.items[index], id:crypto.randomUUID()}); render(); toast('已复制该款明细，请核对配色和数量'); }
  else if (action === 'remove-item') { collectForm(); state.draft.items.splice(Number(button.dataset.index),1); render(); }
  else if (action === 'delete') void deleteOrder();
  else if (action === 'restore') void restoreOrder(button.dataset.id);
});
app.addEventListener('submit', event => {
  if (event.target.id === 'order-form') { event.preventDefault(); void saveOrder(); }
});
app.addEventListener('change', event => {
  if (event.target.id === 'year-select') { state.year = Number(event.target.value); render(); }
  if (event.target.classList.contains('photo-input')) void upload(event.target.files?.[0], 'photo', Number(event.target.dataset.index));
  if (event.target.id === 'scan-input') void upload(event.target.files?.[0], 'scan');
});
app.addEventListener('input', event => {
  if (event.target.id === 'search') {
    state.search = event.target.value;
    $('#orders-body').innerHTML = tableRows();
    $('#result-count').textContent = visibleOrders().length;
  }
});

async function boot() {
  try {
    const session = await api('/api/session');
    state.csrf = session.csrf_token;
    const bootstrap = await api('/api/bootstrap');
    state.workspaceId = bootstrap.workspace_id;
    state.canWrite = bootstrap.capabilities.write;
    $('#local-label').textContent = bootstrap.current_user.name || bootstrap.current_user.username;
    $('#mode-label').textContent = 'Flowboard 共享工作区';
    await refreshOrders();
    render();
  } catch (error) {
    app.innerHTML = `<div class="error">${esc(error.message)}。<a href="/">返回 Flowboard 登录</a></div>`;
  }
}
boot();

function renderTrash() {
  const rows = state.trash.map(order => `<tr><td>${esc(order.number)}</td><td>${esc(order.order_date)}</td><td>${order.items.length} 款 / ${sum(order)} 双</td><td>${esc(order.deleted_at)}</td><td><button class="btn write-action" data-action="restore" data-id="${esc(order.id)}">恢复</button></td></tr>`).join('');
  return header('回收站','删除的需求单可恢复。') + `<section class="panel"><div class="table-scroll"><table class="records"><thead><tr><th>需求单编号</th><th>申请日期</th><th>鞋款</th><th>删除时间</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="empty">回收站为空</td></tr>'}</tbody></table></div></section>`;
}
async function restoreOrder(id) {
  const order = state.trash.find(row => row.id === id);
  if (!order || !confirm(`恢复需求单 ${order.number}？`)) return;
  try { await api(route(`/${id}/restore`), {method:'POST',body:JSON.stringify({version:order.version})}); await refreshOrders(); state.trash = await api(route('/trash')); render(); toast('需求单已恢复'); }
  catch (error) { toast(error.message); }
}
