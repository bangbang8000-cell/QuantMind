import { chromium } from 'playwright';
const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMSIsInRlbmFudF9pZCI6ImRlZmF1bHQiLCJ1c2VybmFtZSI6ImFkbWluIiwiZW1haWwiOiJhZG1pbkBleGFtcGxlLmNvbSIsInJvbGVzIjpbXSwiaXNfYWRtaW4iOnRydWUsImp0aSI6IjQzYjQ0Y2NjLTEzY2MtNGNmZS05NGJjLTIxZjc3NWViZTI2ZCIsImlhdCI6MTc4NjAyMjI4OCwiZXhwIjoxNzg2MTk1MDg4LCJ0eXBlIjoiYWNjZXNzIn0.yUL_TvsYGLrnvIxfd6AyOQLfMThWkejgXLN3Nl6gdBw';
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome-stable' });
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
page.on('response', r => { if (r.url().includes('market/kline')) console.log('KLINE RESP', r.status(), r.url().slice(0,80)); });

await page.addInitScript((tok) => {
  localStorage.setItem('access_token', tok);
  localStorage.setItem('refresh_token', '');
  localStorage.setItem('tenant_id', 'default');
  localStorage.setItem('remember_login', 'true');
}, TOKEN);

await page.goto('http://localhost:3080/#/model-registry', { waitUntil: 'networkidle', timeout: 40000 });
await page.waitForTimeout(6000);
console.log('URL:', page.url());

// 点第一个模型卡片
try {
  await page.locator('div.cursor-pointer.rounded-2xl').first().click({ timeout: 12000 });
  console.log('CLICKED model');
} catch { console.log('model click fail'); }
await page.waitForTimeout(4000);

// 推理历史 tab
try {
  await page.locator('button:has-text("推理历史")').first().click({ timeout: 10000 });
  console.log('CLICKED history');
} catch { console.log('history tab fail'); }
await page.waitForTimeout(4000);

// 点表格第一行(打开股票详情)
try {
  await page.locator('.ant-table-tbody > tr').first().click({ timeout: 10000 });
  console.log('CLICKED stock row');
} catch { console.log('row fail'); }
await page.waitForTimeout(8000);

// 检查 echarts canvas 是否存在
const canvasCount = await page.locator('canvas').count();
console.log('canvas count:', canvasCount);
const hasEcharts = await page.evaluate(() => !!document.querySelector('[class*="echarts"]'));
console.log('has echarts container:', hasEcharts);

console.log('=== ERRORS ===');
console.log(errors.filter(e => !e.includes('WebSocket')).join('\n') || 'NONE');
await page.screenshot({ path: '/tmp/qm_kline_issue.png' });
await browser.close();
