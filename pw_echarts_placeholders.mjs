import { chromium } from 'playwright';
import { readFileSync } from 'fs';
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome-stable' });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
const echartsSrc = readFileSync('/home/zbox/projects/quantmind/node_modules/echarts/dist/echarts.js', 'utf8');
await page.setContent('<div id="c" style="width:600px;height:400px"></div>');
await page.addScriptTag({ content: echartsSrc });

async function run(name, kdata) {
  const res = await page.evaluate((kdata) => {
    try {
      const el = document.getElementById('c');
      const chart = echarts.init(el);
      chart.setOption({
        xAxis: { type: 'category', data: ['d1','d2','d3'] },
        yAxis: { type: 'value' },
        series: [{ type: 'candlestick', data: kdata }]
      });
      return 'OK';
    } catch (e) { return 'CRASH: ' + e.message; }
  }, kdata);
  console.log(name + ': ' + res);
}

await run("dash '-' placeholder", [[10.1,10.5,9.9,10.7],[10.5,10.2,10.0,10.8],'-']);
await run("empty-array [] placeholder", [[10.1,10.5,9.9,10.7],[10.5,10.2,10.0,10.8],[]]);
await run("array-of-null placeholder", [[10.1,10.5,9.9,10.7],[10.5,10.2,10.0,10.8],[null,null,null,null]]);
await run("undefined placeholder", [[10.1,10.5,9.9,10.7],[10.5,10.2,10.0,10.8],undefined]);
await run("omit last (shorter)", [[10.1,10.5,9.9,10.7],[10.5,10.2,10.0,10.8]]);
console.log('PAGE ERRORS:', errors.length ? errors.join('\n') : 'NONE');
await browser.close();
