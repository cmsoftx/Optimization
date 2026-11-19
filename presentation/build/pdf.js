const { chromium } = require('playwright');
(async () => { const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + __dirname + '/cheatsheet.html'); await p.pdf({ path: process.argv[2], format: 'A4', printBackground: true });
  await b.close(); })();
