// Render architecture-report.html -> PDF using Playwright's bundled Chromium.
// Same pipeline as Source/augura-brand-identity/render.js.
const fs = require('fs');
const path = require('path');

const PW_CANDIDATES = [
  '/Users/quentin/.npm/_npx/e41f203b7505f1fb/node_modules/playwright',
  '/Users/quentin/Desktop/Augure/lucis-dashboard/node_modules/playwright',
];
const PW = PW_CANDIDATES.find((p) => fs.existsSync(p));
if (!PW) { console.error('Playwright introuvable'); process.exit(1); }
const { chromium } = require(PW);

(async () => {
  const htmlPath = path.resolve(__dirname, 'architecture-report.html');
  const out = path.resolve(__dirname, 'Augura-Architecture-Backend.pdf');

  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' });
  await page.evaluate(async () => { await document.fonts.ready; });
  // settle a beat so masks/images paint
  await page.waitForTimeout(400);
  await page.pdf({
    path: out,
    preferCSSPageSize: true,
    printBackground: true,
  });
  await browser.close();
  console.log('WROTE ' + out);
})().catch((e) => { console.error(e); process.exit(1); });
