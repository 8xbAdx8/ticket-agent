/* Real browser verification of the integrated frontend against an isolated server. */
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

async function main() {
  const arg = flag => process.argv[process.argv.indexOf(flag)+1];
  const url = arg('--url');
  if (new URL(url).hostname !== '127.0.0.1') throw new Error('Isolated localhost required');
  const out = path.resolve(arg('--out'));
  const browser = await chromium.launch({headless:true, executablePath:arg('--browser')});
  try {
    const context = await browser.newContext({viewport:{width:1600,height:1120},deviceScaleFactor:1});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(url);
    await page.getByRole('textbox',{name:'输入消息'}).waitFor({timeout:45000});
    const scenarios = [
      ['查明天上海到杭州的高铁','01-query.png',['query_tickets'],'.ticket-card'],
      ['订明天上海到杭州的高铁','02-order.png',['query_tickets','lock_seat','create_order'],'.order-card'],
      ['锁座后多久必须完成支付？','03-policy.png',['search_policy'],'.policy-card'],
      ['支付我刚才的订单','04-payment.png',['pay_order'],'.order-card'],
      ['支付我刚才的订单','05-duplicate-payment.png',['pay_order'],'.order-card'],
    ];
    let mobileOverflow;
    for (let i=0;i<scenarios.length;i++) {
      const [input, image, sequence, card] = scenarios[i];
      await page.getByRole('textbox',{name:'输入消息'}).fill(input);
      await page.getByRole('button',{name:'发送',exact:true}).click();
      // Wait for this turn's actual trace rather than an earlier tool name in hidden history.
      try { await page.waitForFunction(({input,sequence}) => {
        const messages = document.querySelectorAll('[data-testid="stChatMessage"]');
        const rows = [...document.querySelectorAll('.tool-row .tool-info b')].map(e=>e.textContent);
        return messages.length===2 && messages[0].textContent.includes(input) &&
               JSON.stringify(rows)===JSON.stringify(sequence) &&
               !document.querySelector('.ticket-agent-processing') &&
               document.querySelectorAll('[data-testid="stMetricValue"]').length===3;
      },{input,sequence}); } catch(e) {
        await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});
        fs.writeFileSync(path.join(out,'failure_state.json'),JSON.stringify(await page.evaluate(()=>({
          messages:[...document.querySelectorAll('[data-testid="stChatMessage"]')].map(e=>e.textContent),
          tools:[...document.querySelectorAll('.tool-row .tool-info b')].map(e=>e.textContent),
          metrics:[...document.querySelectorAll('[data-testid="stMetricValue"]')].map(e=>e.textContent),
          body:document.body.innerText})),null,2));
        throw e;
      }
      await page.locator(card).first().waitFor();
      try { await page.waitForFunction(expected=>document.querySelector('input[aria-label="工具参数与结果"]')?.value===expected,'1. '+sequence[0],{timeout:5000}); }
      catch(e) {
        await page.screenshot({path:path.join(out,'label-failure.png'),fullPage:true});
        fs.writeFileSync(path.join(out,'label-failure.txt'),await page.locator('body').innerText());
        fs.writeFileSync(path.join(out,'select-debug.json'),JSON.stringify(await page.locator('input,[role="combobox"]').evaluateAll(nodes=>nodes.map(e=>({html:e.outerHTML,value:e.value}))),null,2));
        throw e;
      }
      if(i===4) await page.getByText('订单已支付，本次没有重复扣款。',{exact:true}).waitFor();
      await page.waitForFunction(()=>document.querySelectorAll('[data-testid="stSkeleton"]').length===0);
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      await page.evaluate(()=>document.querySelector('[data-testid="stMain"]')?.scrollTo(0,0));
      await page.screenshot({path:path.join(out,image),fullPage:true});
      if(i===0) {
        fs.writeFileSync(path.join(out,'layout_inspection.json'),JSON.stringify(await page.locator('.ticket-card').first().evaluate(e=>({
          ancestors:[e,e.parentElement,e.parentElement.parentElement,e.parentElement.parentElement.parentElement,
                     e.parentElement.parentElement.parentElement.parentElement,
                     e.parentElement.parentElement.parentElement.parentElement.parentElement].map(n=>n.outerHTML.slice(0,600)),
          buttons:[...document.querySelectorAll('button')].map(n=>({label:n.getAttribute('aria-label'),title:n.getAttribute('title'),text:n.textContent}))})),null,2));
        await page.setViewportSize({width:390,height:844});
        await page.waitForFunction(()=>document.querySelector('[data-testid="stSidebar"]')?.getAttribute('aria-expanded')==='false',null,{timeout:3000}).catch(async()=>{
          await page.getByRole('button',{name:'keyboard_double_arrow_left',exact:true}).click();
          await page.waitForFunction(()=>document.querySelector('[data-testid="stSidebar"]')?.getAttribute('aria-expanded')==='false');
        });
        await page.waitForFunction(()=>document.querySelector('[data-testid="stSidebar"]').getBoundingClientRect().right<=0);
        await page.evaluate(()=>document.querySelector('[data-testid="stMain"]')?.scrollTo(0,0));
        await page.screenshot({path:path.join(out,'06-mobile-query.png'),fullPage:true});
        mobileOverflow = await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
        if(mobileOverflow) throw new Error('Mobile horizontal overflow');
        await page.setViewportSize({width:1600,height:1120});
        if(await page.locator('[data-testid="stSidebar"]').getAttribute('aria-expanded')==='false')
          await page.getByRole('button',{name:'keyboard_double_arrow_right',exact:true}).click();
      }
    }
    await page.getByText('完整 JSON',{exact:true}).click();
    await page.getByRole('button',{name:'下载本轮 Trace',exact:true}).scrollIntoViewIfNeeded();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button',{name:'下载本轮 Trace',exact:true}).click();
    await (await downloadPromise).saveAs(path.join(out,'downloaded-trace.json'));
    await page.getByRole('tab',{name:'历史记录回放',exact:true}).click();
    await page.getByText('原始记录回放，不执行新的业务操作，也不恢复旧会话记忆。',{exact:true}).waitFor();
    await page.getByRole('tab',{name:'核心代码导览',exact:true}).click();
    await page.getByText('统一入口：校验输入并选择执行引擎',{exact:true}).click();
    await page.getByText('target/agent.py:61',{exact:true}).waitFor();
    await page.getByRole('button',{name:'清空会话',exact:true}).click();
    await page.getByRole('tab',{name:'对话与工具',exact:true}).click();
    await page.getByText('一段旅程，从一句话开始。',{exact:true}).waitFor();
    if(await page.locator('.ticket-card,.order-card,.policy-card').count()) throw new Error('Stale business card after clear');
    if(errors.length) throw new Error(errors.join('; '));
    const report = {status:'passed',source:'integrated web/app.py real browser',provider:'langchain_mock',
      real_model_tested:false,scenarios:scenarios.map(([message,screenshot,tools])=>({message,screenshot,tools})),
      browser_version:browser.version(),javascript_errors:errors.length,mobile_horizontal_overflow:mobileOverflow,
      trace_download:true,history_replay:true,code_navigation:true,session_reset:true};
    fs.writeFileSync(path.join(out,'browser_check.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
}
main().catch(e=>{console.error(e.stack);process.exitCode=1});
