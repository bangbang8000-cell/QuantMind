import { chromium } from 'playwright';
const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMDAwMDAwMSIsInRlbmFudF9pZCI6ImRlZmF1bHQiLCJ1c2VybmFtZSI6ImFkbWluIiwiZW1haWwiOiJhZG1pbkBleGFtcGxlLmNvbSIsInJvbGVzIjpbXSwiaXNfYWRtaW4iOnRydWUsImp0aSI6IjQzYjQ0Y2NjLTEzY2MtNGNmZS05NGJjLTIxZjc3NWViZTI2ZCIsImlhdCI6MTc4NjAyMjI4OCwiZXhwIjoxNzg2MTk1MDg4LCJ0eXBlIjoiYWNjZXNzIn0.yUL_TvsYGLrnvIxfd6AyOQLfMThWkejgXLN3Nl6gdBw';
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome-stable' });
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } });
await page.addInitScript((tok) => {
  localStorage.setItem('access_token', tok);
  localStorage.setItem('refresh_token', '');
  localStorage.setItem('tenant_id', 'default');
  localStorage.setItem('remember_login', 'true');
}, TOKEN);
await page.goto('http://localhost:3080/#/model-registry', { waitUntil: 'networkidle', timeout: 40000 });
await page.waitForTimeout(5000);
// List all buttons/tabs visible
const btns = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll('button, [role=tab], .ant-tabs-tab').forEach(el => {
    const t = (el.textContent || '').trim().slice(0, 30);
    if (t) out.push(t);
  });
  return [...new Set(out)].slice(0, 40);
});
console.log('BUTTONS/TABS:', JSON.stringify(btns, null, 1));
await browser.close();
