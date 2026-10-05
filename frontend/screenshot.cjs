const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  // Wait for the app to be ready
  await page.goto('http://localhost:5173');
  await page.waitForTimeout(2000);

  // Navigate to queue
  await page.screenshot({ path: path.join(__dirname, 'queue.png') });

  // Wait for cv_0011 to appear or just directly click it
  await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('td')).find(e => e.textContent === 'cv_0011');
    if (el) el.click();
  });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(__dirname, 'cv_0011.png') });

  // Navigate back to queue
  await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('.sidebar-dot')).find(e => e.getAttribute('title') === 'Handoff Queue');
    if (el) el.click();
  });
  await page.waitForTimeout(1000);

  // Click cv_0009
  await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('td')).find(e => e.textContent === 'cv_0009');
    if (el) el.click();
  });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(__dirname, 'cv_0009.png') });

  await browser.close();
})();
