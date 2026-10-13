/* Offline UI rendering and interaction checks. Install Playwright separately if re-rendering. */
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

async function main() {
  const root = path.resolve(__dirname,'..');
  const folder = path.join(root,'docs','showcase','v3');
  const browserArg = process.argv.indexOf('--browser');
  const browser = await chromium.launch({headless:true,...(browserArg >= 0 ? {executablePath:process.argv[browserArg+1]} : {})});
  const context = await browser.newContext({viewport:{width:1600,height:1000},deviceScaleFactor:1});
  const page = await context.newPage();
  const errors = [];
  const network = [];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if (/^https?:/.test(request.url())) network.push(request.url())});
  const out = path.join(folder,'效果图');
  fs.mkdirSync(out,{recursive:true});
  const screenshots = [];
  for (const [scene,name] of [['query','01-query.png'],['order','02-order.png'],['policy','03-policy.png'],['processing','04-processing.png']]) {
    await page.goto(pathToFileURL(path.join(folder,'index.html')).href+'?scene='+scene);
    await page.locator('#chat-content .assistant-label').waitFor();
    await page.screenshot({path:path.join(out,name),fullPage:true});
    screenshots.push(name);
    if (scene==='order') {
      if (await page.locator('.tool-row').count()!==3) throw new Error('Order tools missing');
      await page.locator('.tool-row').last().click();
      if (!(await page.locator('#tool-args').innerText()).includes('lock_id')) throw new Error('Tool detail did not change');
    }
    if (scene==='policy' && !(await page.locator('.source-link').innerText()).includes('#P11')) throw new Error('Policy source missing');
    if (scene==='processing' && await page.locator('.spinner').count()!==1) throw new Error('Processing spinner missing');
  }
  await page.locator('#nav-code').click();
  if (await page.locator('.code-item').count()!==4) throw new Error('Code excerpts missing');
  await page.screenshot({path:path.join(out,'05-code-tour.png'),fullPage:true});
  screenshots.push('05-code-tour.png');
  await page.locator('#nav-history').click();
  await page.locator('[data-replay="order"]').click();
  if (!(await page.locator('.order-card').innerText()).includes('pending')) throw new Error('History replay failed');
  await page.locator('#send-demo').click();
  await page.locator('.spinner').waitFor();
  await page.locator('.order-card').waitFor();
  await page.locator('[data-scene="query"]').click();
  await page.locator('.json-details summary').click();
  if (!(await page.locator('#trace-json').innerText()).includes('tool_sequence')) throw new Error('Trace JSON missing');
  await context.close();
  const mobile = await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1});
  const small = await mobile.newPage();
  await small.goto(pathToFileURL(path.join(folder,'index.html')).href);
  await small.locator('.ticket-card').first().waitFor();
  const dimensions = await small.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
  if (dimensions.scroll > dimensions.client+1) throw new Error('Mobile horizontal overflow');
  await small.screenshot({path:path.join(out,'06-mobile-query.png'),fullPage:true});
  screenshots.push('06-mobile-query.png');
  await mobile.close();
  if (errors.length) throw new Error(errors.join('; '));
  if (network.length) throw new Error('Preview attempted external requests');
  const result = {status:'passed',scope:'offline UI design, actual historical Mock data; not live Agent UI',
                  screenshots,desktop:{width:1600,height:1000},mobile:dimensions,
                  interactions:['scenario tabs','tool parameter selection','policy source','processing animation','code tour','history replay','full JSON'],
                  browser_version:browser.version(),playwright_version:require('playwright/package.json').version,
                  external_requests:network.length,javascript_errors:errors.length,real_model_tested:false};
  await browser.close();
  fs.writeFileSync(path.join(folder,'效果图验证.json'),JSON.stringify(result,null,2),'utf8');
  console.log(JSON.stringify(result));
}
main().catch(error=>{console.error(error.message);process.exitCode=1});
