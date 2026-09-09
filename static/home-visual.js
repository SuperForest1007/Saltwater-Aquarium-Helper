// Homepage presentation uses the existing analysis and recording flows.
function homeValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(Number(number.toFixed(6))) : '—';
}
function homeSeries(item) {
  return (item?.records || []).filter(r => r.value != null && r.ts != null && Number.isFinite(Number(r.value)) && Number.isFinite(Number(r.ts)))
    .slice().sort((a, b) => Number(a.ts) - Number(b.ts)).slice(-3);
}

function homeTrendModel(item) {
  const records = homeSeries(item);
  if (!records.length) return null;
  const values = records.map(r => Number(r.value));
  const low = Math.min(...values), high = Math.max(...values);
  const idealSpan = Number(item.ideal?.high) - Number(item.ideal?.low);
  const padding = Math.max((high - low) * .3, Number.isFinite(idealSpan) ? idealSpan * .08 : 0, Math.abs(high) * .01, .001);
  const min = low - padding, max = high + padding;
  const first = Number(records[0].ts), last = Number(records[records.length - 1].ts);
  return { records, delta: values[values.length - 1] - values[0], min, max,
    points: records.map(r => [last === first ? 84 : 20 + (Number(r.ts) - first) / (last - first) * 128, 72 - (Number(r.value) - min) / (max - min) * 50]) };
}

function homeRecordDate(record) {
  const date = new Date(Number(record.ts));
  return Number.isNaN(date.getTime()) ? '日期未知' : (date.getMonth() + 1) + '.' + date.getDate();
}

function renderHomePulseChart(item, element, stale) {
  document.querySelectorAll('.home-reading').forEach(button => button.classList.toggle('is-focus', button.dataset.element === element));
  const model = homeTrendModel(item);
  if (!model) return;
  const { records, points, delta } = model;
  const unit = escapeToday(item.ideal?.unit || '');
  document.getElementById('homePulseChange').innerHTML = records.length > 1
    ? escapeToday((delta > 0 ? '+' : '') + homeValue(delta)) + '<small>' + unit + ' · 最近 ' + records.length + ' 次' + (stale ? ' · 待复测' : '') + '</small>'
    : '<small>只有一次读数，暂不判断走势</small>';
  const coordinates = points.map(p => p.join(',')).join(' L');
  const path = records.length > 1 ? '<path class="home-trend-area" d="M' + coordinates + ' L' + points[points.length - 1][0] + ',72 L' + points[0][0] + ',72 Z"/><path d="M' + coordinates + '"/>' : '';
  const labels = points.map((p, i) => '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="3"/>' +
    (i > 0 && i < points.length - 1 && (p[0] - points[i-1][0] < 35 || points[i+1][0] - p[0] < 35) ? '' : '<text x="' + p[0] + '" y="' + (p[1] - 10) + '" text-anchor="middle">' + escapeToday(homeValue(records[i].value)) + '</text>')).join('');
  // Closely spaced timestamps retain their true positions; only endpoints get date labels.
  const dates = '<text class="home-chart-date" x="20" y="96">' + escapeToday(homeRecordDate(records[0])) + '</text>' +
    (records.length > 1 ? '<text class="home-chart-date" x="148" y="96" text-anchor="end">' + escapeToday(homeRecordDate(records[records.length - 1])) + '</text>' : '');
  const range = item.ideal ? '本缸参考 ' + item.ideal.low + '–' + item.ideal.high + ' ' + item.ideal.unit : '参考范围未设置';
  document.getElementById('homePulseChart').innerHTML = '<svg viewBox="0 0 168 104" role="img" aria-label="' + escapeToday(element + ' 最近读数 ' + records.map(r => r.value).join('、') + '；纵轴局部放大，' + range) + '"><line x1="10" y1="72" x2="158" y2="72"/>' + path + labels + dates + '</svg><small>局部走势 · ' + escapeToday(range) + '</small>';
}

function renderHomeReadings(analysis, evidence) {
  const names = { KH: 'KH', '钙': '钙', '镁': '镁', NO3: 'NO₃', PO4: 'PO₄' };
  document.getElementById('homeReadings').innerHTML = Object.entries(names).map(([key, name], index) => {
    const item = analysis[key], records = homeSeries(item), hasValue = records.length && item.current != null;
    const direction = records.length > 1 ? item.signals?.direction : '';
    const trend = { rising: ['↗', '上升'], falling: ['↘', '下降'], stable: ['→', '基本持平'] }[direction] || ['·', '趋势不足'];
    const state = evidence.find(e => e.element === key);
    const status = !hasValue ? '未测' : ({low:'偏低',high:'偏高'}[item.status] || (['stale','missing'].includes(state?.state) ? '待复测' : ''));
    return '<button class="home-reading element-' + index + '" data-element="' + key + '" type="button" onclick="openHomeReading(\'' + key + '\')"><span>' + name + '</span><b>' + (hasValue ? escapeToday(homeValue(records[records.length - 1].value)) : '—') + '</b><small>' + escapeToday(item?.ideal?.unit || (index === 0 ? 'dKH' : 'ppm')) + ' <i class="home-trend ' + direction + '" aria-label="' + trend[1] + '">' + trend[0] + '</i></small><em>' + escapeToday(status || homeRecordDate(records[records.length - 1])) + '</em></button>';
  }).join('');
}

function openHomeReading(element) {
  showTab('water');
  jumpToTrend(element);
  const select = document.getElementById('wqChartEl');
  if (select) syncChoiceTrigger(select);
  requestAnimationFrame(() => document.getElementById('wqPro').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',block:'start'}));
}

function openHomeWaterEntry() {
  openRecordComposer();
  chooseRecordCompose('water');
}
