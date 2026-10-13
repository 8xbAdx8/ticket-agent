/* Capture the real Streamlit application against an isolated Mock server. */
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

async function main(){
  const value=(flag)=>process.argv[process.argv.indexOf(flag)+1];
  const url=value('--url');
  if(new URL(url).hostname!=='127.0.0.1') throw new Error('Only the isolated localhost server is allowed');
  const out=path.resolve(__dirname,'../docs/showcase/v3/真实截图');
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:value('--browser')});
  const context=await browser.newContext({viewport:{width:1600,height:1120},deviceScaleFactor:1});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);
  await page.getByRole('textbox',{name:'输入消息'}).waitFor({timeout:45000});
  const inputs=[['查明天上海到杭州的高铁','01-actual-query.png','query_tickets'],
                ['订明天上海到杭州的高铁','02-actual-order.png','create_order'],
                ['锁座后多久必须完成支付？','03-actual-policy.png','P11']];
  for(const [input,name,expected] of inputs){
    await page.getByRole('textbox',{name:'输入消息'}).fill(input);
    await page.getByRole('button',{name:'发送',exact:true}).click();
    await page.waitForFunction(text=>document.body.innerText.includes(text),expected);
    await page.locator('.ticket-agent-processing').waitFor({state:'detached'});
    await page.getByText('最新一条 trace',{exact:true}).waitFor();
    const expectedCount=input.startsWith('订')?'3':'1';
    await page.waitForFunction(count=>{
      const values=document.querySelectorAll('[data-testid="stMetricValue"]');
      return values.length===3 && values[0].textContent.trim()===count;
    },expectedCount);
    await page.locator('[data-testid="stDataFrame"] canvas').first().waitFor();
    await page.waitForFunction(()=>document.querySelectorAll('[data-testid="stSkeleton"]').length===0);
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    await page.screenshot({path:path.join(out,name),fullPage:false});
  }
  const body=await page.locator('body').innerText();
  if(!body.includes('LangChain Mock')) throw new Error('Actual app engine is not LangChain Mock');
  if(errors.length) throw new Error(errors.join('; '));
  fs.writeFileSync(path.join(out,'browser_check.json'),JSON.stringify({status:'passed',
    source:'unmodified web/app.py real browser rendering',provider:'langchain_mock',real_model_tested:false,
    inputs:inputs.map(([message,screenshot])=>({message,screenshot})),viewport:{width:1600,height:1120},
    browser_version:browser.version(),javascript_errors:errors.length},null,2));
  await context.close();await browser.close();
  console.log(JSON.stringify({status:'passed',actual_screenshots:3,provider:'langchain_mock'}));
}
main().catch(error=>{console.error(error.message);process.exitCode=1});
