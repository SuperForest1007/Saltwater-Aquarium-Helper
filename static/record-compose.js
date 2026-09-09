// Small record forms use the existing endpoints and stay on the record tab.
let recordComposeBusy = false;
let recordComposeKind = '';
let recordComposeReturnFocus = null;
const recordComposeMask = document.createElement('div');
recordComposeMask.className = 'modal-mask';
recordComposeMask.id = 'recordComposeModal';
recordComposeMask.innerHTML = '<div class="modal-box record-compose-box" role="dialog" aria-modal="true" aria-labelledby="recordComposeTitle"><div class="record-compose-head"><h2 id="recordComposeTitle">记一笔</h2><button type="button" aria-label="关闭" onclick="closeRecordComposer()">×</button></div><div id="recordComposeBody"></div></div>';
document.body.appendChild(recordComposeMask);
recordComposeMask.addEventListener('click', event => { if (event.target === recordComposeMask) closeRecordComposer(); });
recordComposeMask.addEventListener('keydown', event => {
  if (event.key === 'Escape') { event.stopImmediatePropagation(); closeRecordComposer(); }
  if (event.key === 'Tab') {
    const items = [...recordComposeMask.querySelectorAll('button,input,textarea')].filter(el => !el.disabled && el.getClientRects().length);
    const first = items[0], last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
function closeRecordComposer(restore = true) {
  if (recordComposeBusy) return;
  recordComposeMask.classList.remove('open');
  document.body.classList.remove('lock-scroll');
  if (restore && recordComposeReturnFocus?.isConnected) recordComposeReturnFocus.focus({preventScroll:true});
}
function openRecordComposer() {
  if (recordComposeBusy) return;
  recordComposeReturnFocus = document.activeElement;
  recordComposeKind = '';
  document.getElementById('recordComposeTitle').textContent = '记一笔';
  document.getElementById('recordComposeBody').innerHTML = '<div class="record-compose-options">' +
    [['water','水质','填写实测读数'],['round','看一圈','记下生物和设备的状态'],['care','维护','记下今天完成的缸务'],['change','已换水','记录实际换水量']].map(item => '<button type="button" onclick="chooseRecordCompose(\''+item[0]+'\')"><strong>'+item[1]+'</strong><small>'+item[2]+'</small><span>›</span></button>').join('') +
    '</div><p class="record-compose-tools-label">需要计算或调整方案</p><div class="record-compose-tools"><button type="button" onclick="recordComposeTool(\'salt\',\'wcCalculator\')">打开配盐计算 ↗</button><button type="button" onclick="recordComposeTool(\'calc\',\'supplementCalc\')">打开补充计算 ↗</button><button type="button" onclick="recordComposeTool(\'dosing\',\'dosingCalc\')">调整滴定方案 ↗</button></div>';
  recordComposeMask.classList.add('open');
  document.body.classList.add('lock-scroll');
  recordComposeMask.querySelector('button').focus();
}
function recordComposeTool(tab, anchor) { closeRecordComposer(false); openRecordTool(tab, anchor); }
async function chooseRecordCompose(kind) {
  if (kind === 'round') { closeRecordComposer(false); openReefRound(); return; }
  recordComposeKind = kind;
  const root = document.getElementById('recordComposeBody');
  document.getElementById('recordComposeTitle').textContent = {water:'记录水质',care:'记录维护',change:'记录换水'}[kind];
  let fields = '';
  if (kind === 'water') fields = '<p>填写这次测过的项目，其他留空。</p>' + ['KH','Ca','Mg','NO3','PO4'].map((el,i) => '<label class="record-compose-field"><span>'+['KH · dKH','钙 · ppm','镁 · ppm','NO₃ · ppm','PO₄ · ppm'][i]+'</span><input name="'+el+'" type="number" inputmode="decimal" step="any" min="'+(i>2?'0':'0.000001')+'" placeholder="未测"></label>').join('');
  if (kind === 'change') fields = '<label class="record-compose-field">换水量 · L<input name="water_liters" type="number" inputmode="decimal" step="any" min="0.000001" required></label><label class="record-compose-field">海盐品牌 · 选填<input name="salt_brand" maxlength="80"></label><label class="record-compose-field">海盐克数 · 选填<input name="salt_grams" type="number" inputmode="decimal" step="any" min="0.000001"></label>';
  if (kind === 'care') {
    root.innerHTML = '<p>正在读取维护项目…</p>';
    try {
      const data = await api('/api/maintenance');
      if (!recordComposeMask.classList.contains('open') || recordComposeKind !== kind) return;
      fields = (data.rules || []).map(rule => '<label class="record-compose-care"><input required type="radio" name="task_key" value="'+escapeToday(rule.task_key)+'"><span>'+escapeToday(rule.title)+'</span></label>').join('');
      if (!fields) { root.innerHTML = '<p>暂无可记录的维护项目，可在“我的”中设置维护节奏。</p><button type="button" onclick="openRecordComposer()">返回</button>'; return; }
    } catch (_) { root.innerHTML = '<p>维护项目没读到。</p><button type="button" onclick="chooseRecordCompose(\'care\')">重新读取</button>'; return; }
  }
  root.innerHTML = '<form id="recordComposeForm">'+fields+'<label class="record-compose-field">备注 · 选填<textarea name="note" maxlength="200" rows="2"></textarea></label><p id="recordComposeError" role="alert"></p><div class="record-compose-footer"><button type="button" onclick="openRecordComposer()">返回</button><button type="submit">保存记录</button></div></form>';
  root.querySelector('form').addEventListener('submit', saveRecordCompose);
  root.querySelector('input')?.focus();
}
async function saveRecordCompose(event) {
  event.preventDefault();
  if (recordComposeBusy) return;
  const form = event.currentTarget, fields = new FormData(form), error = document.getElementById('recordComposeError');
  const note = String(fields.get('note') || '').trim();
  const jobs = [];
  if (recordComposeKind === 'water') {
    for (const element of ['KH','Ca','Mg','NO3','PO4']) {
      const raw = fields.get(element);
      if (!raw) continue;
      const value = Number(raw);
      if (!Number.isFinite(value) || value < 0 || (value === 0 && !['NO3','PO4'].includes(element))) { error.textContent = '读数格式不合适，请检查数值。'; return; }
      jobs.push({path:'/api/water/record',body:{element,value,note,recorded_at:''},field:element});
    }
    if (!jobs.length) { error.textContent = '至少填写一项实测读数。'; return; }
  } else if (recordComposeKind === 'change') {
    jobs.push({path:'/api/water-change',body:{water_liters:Number(fields.get('water_liters')),salt_grams:fields.get('salt_grams') ? Number(fields.get('salt_grams')) : null,salt_brand:String(fields.get('salt_brand') || ''),note,recorded_at:''}});
  } else jobs.push({path:'/api/maintenance/event',body:{task_key:fields.get('task_key'),action:'complete',note}});
  recordComposeBusy = true;
  error.textContent = '';
  form.querySelectorAll('button,input,textarea').forEach(el => el.disabled = true);
  let completed = 0;
  try {
    for (const job of jobs) {
      await api(job.path,{method:'POST',body:job.body});
      completed++;
      if (job.field) form.elements.namedItem(job.field).value = '';
    }
    recordComposeBusy = false;
    closeRecordComposer();
    toast('已记下 ✓','ok');
    await loadFormalRecordPage();
    await loadWater();
  } catch (_) {
    error.textContent = completed ? '已保存 '+completed+' 项，未保存的读数仍在这里，可以继续保存。' : '这次没有保存成功，填写内容已保留。';
    if (completed) await Promise.all([loadFormalRecordPage(), loadWater()]);
  } finally {
    recordComposeBusy = false;
    form.querySelectorAll('button,input,textarea').forEach(el => el.disabled = false);
  }
}
