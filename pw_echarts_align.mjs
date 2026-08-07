import { chromium } from 'playwright';
import { readFileSync } from 'fs';
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome-stable' });
const page = await browser.newPage();
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
      // inspect where each candle landed via layout
      const data = chart.getModel().getSeriesByIndex(0).getData();
      const out = [];
      for (let i = 0; i < data.count(); i++) {
        const l = data.getItemLayout(i);
        out.push({ i, sign: data.getItemLayout(i)?.sign, x: l && l.brushRect ? l.brushRect.x.toFixed(1) : 'n/a' });
      }
      return JSON.stringify(out);
    } catch (e) { return 'CRASH: ' + e.message; }
  }, kdata);
  console.log(name + ': ' + res);
}

await run('shorter(2 candles / 3 cats)', [[10.1,10.5,9.9,10.7],[10.5,10.2,10.0,10.8]]);
await run('dash placeholder', [[10.1,10.5,9.9,10.7],[10.5,10.2,10.0,10.8],'-']);
await run('empty-array placeholder', [[10.1,10.5,9.9,10.7],[10.5,10.2,10.0,10.8],[]]);
await browser.close();
