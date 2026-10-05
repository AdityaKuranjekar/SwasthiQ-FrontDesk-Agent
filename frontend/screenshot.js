import { chromium } from 'playwright';
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const ids = ['cv_0007', 'cv_0009', 'cv_0010', 'cv_0011'];
  for (const id of ids) {
    console.log('Capturing ' + id);
    await page.goto('http://localhost:5173/?id=' + id, { waitUntil: 'networkidle' });
    await page.screenshot({ path: id + '.png' });
  }
  await browser.close();
})();