// Render scene.html frame-by-frame with Playwright/Chromium and export the page's SFX cue list.
// Usage: NODE_PATH=$(npm root -g) node render.cjs <scene.html> <framesDir> <fps> <seconds> [workers]
const fs = require('fs'), path = require('path');
const { chromium } = require('playwright');

(async () => {
  const [html, out, fps, secs, nw = '4'] = process.argv.slice(2);
  const N = Math.round(+secs * +fps), W = +nw;
  const browser = await chromium.launch({ args: ['--force-color-profile=srgb', '--font-render-hinting=none', '--hide-scrollbars'] });
  let sfx = null, done = 0;
  await Promise.all(Array.from({ length: W }, async (_, k) => {
    const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
    page.on('pageerror', e => { console.error('page error:', e.message); process.exit(1); });
    await page.goto('file://' + path.resolve(html));
    const s = await page.evaluate(() => window.build());
    if (k === 0) sfx = s;
    for (let i = k; i < N; i += W) {  // workers interleave frames
      await page.evaluate(t => window.seek(t), i / +fps);
      await page.screenshot({ path: path.join(out, `f_${String(i).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 92 });
      if (++done % 150 === 0) console.log(`${done}/${N} frames`);
    }
  }));
  fs.writeFileSync(path.join(out, '..', 'sfx.json'), JSON.stringify(sfx));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
