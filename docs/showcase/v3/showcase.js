(() => {
  const data = window.TICKET_DEMO;
  const byId = (id) => document.getElementById(id);
  const esc = (value) => String(value).replace(/[&<>"']/g, (x) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
  const labels = {query_tickets:'查询余票', lock_seat:'锁定座位', create_order:'创建订单', search_policy:'检索政策'};
  let scene = 'query';
  let view = 'chat';
  let pending = false;
  let timer = null;
  function current() { return data.scenes[scene === 'processing' ? 'query' : scene]; }
  function setTool(index) {
    const event = current().tools[index];
    byId('selected-tool').textContent = event.tool;
    byId('tool-args').textContent = JSON.stringify(event.tool === 'create_order' ? {...current().trace.steps.flatMap(s => s.calls).find(c => c.tool === event.tool).args, contact:'138****0001（虚构号码已遮蔽）'} : current().trace.steps.flatMap(s => s.calls).find(c => c.tool === event.tool).args, null, 2);
    document.querySelectorAll('.tool-row').forEach((button, i) => button.setAttribute('aria-pressed', String(i === index)));
  }
  function renderTrace() {
    const {trace, tools} = current();
    const busy = pending || scene === 'processing';
    byId('trace-state').textContent = busy ? '等待返回' : '已结束';
    byId('trace-state').classList.toggle('busy', busy);
    byId('call-count').textContent = busy ? '—' : trace.tool_sequence.length;
    byId('latency').textContent = busy ? '—' : trace.total_latency_ms;
    byId('finish').textContent = busy ? '—' : trace.finish_reason;
    byId('trace-json').textContent = busy ? '执行记录将在请求结束后显示。' : JSON.stringify(trace, null, 2);
    if (busy) {
      byId('tool-list').innerHTML = '<div class="waiting-tools">请求处理中…<br>返回后展示真实工具调用和结果。</div>';
      byId('selected-tool').textContent = '等待记录';
      byId('tool-args').textContent = '本页为处理动画设计演示。\n尚未发起实际 Agent 请求。';
      return;
    }
    byId('tool-list').innerHTML = tools.map((event, i) => `<button class="tool-row" aria-pressed="${i === 0}" data-tool-index="${i}"><span class="tool-number">${i+1}</span><div class="tool-info"><div class="tool-name">${esc(event.tool)}</div><p>${esc(labels[event.tool] || event.tool)} · ${event.ok ? '执行成功' : '返回错误'}</p></div><span class="tool-time">${event.latency_ms} ms</span></button>`).join('');
    byId('tool-list').querySelectorAll('button').forEach((button) => button.addEventListener('click', () => setTool(Number(button.dataset.toolIndex))));
    setTool(0);
  }
  function renderChat() {
    const {trace, tools} = current();
    const busy = pending || scene === 'processing';
    let content = '';
    if (busy) {
      content = '<div class="processing-box"><span class="spinner" aria-hidden="true"></span><h3 role="status">正在处理请求…</h3><p>这里只展示通用等待状态。<br>不显示或推测模型内部思维链。</p></div><div class="record-caption">效果稿中的动画为演示；不代表 Agent 正在联网执行。</div>';
    } else if (scene === 'query') {
      content = `<p class="assistant-lead">${esc('查询记录显示以下班次有余票。具体价格和库存来自模拟工具结果。')}</p><div class="ticket-list">${tools[0].result.trains.map(t => `<div class="ticket-card"><div><div class="train-no">${esc(t.train_no)}</div><div class="ticket-meta">${esc(t.seat_type)} · ${esc(t.date)}</div></div><div class="ticket-route"><div class="route-times">${esc(t.depart)}<span>→</span>${esc(t.arrive)}</div><div class="route-label">${esc(t.from_city)} — ${esc(t.to_city)}</div></div><div class="ticket-price">¥${t.price}<small>/人</small><div class="ticket-stock">余票 ${t.seats_left} 张</div></div></div>`).join('')}</div><div class="record-caption">读取历史 Mock 结果 · 不代表当前日期或真实票务库存</div>`;
    } else if (scene === 'order') {
      const order = tools.find(e => e.tool === 'create_order').result;
      const train = tools.find(e => e.tool === 'query_tickets').result.trains.find(t => t.train_no === order.train_no);
      content = `<p class="assistant-lead">工具已按顺序完成余票查询、锁座与创建订单。当前订单待支付。</p><div class="order-card"><div class="order-top">模拟订单已创建<span>待支付 · pending</span></div><div class="order-route">${esc(train.from_city)}<span>→</span>${esc(train.to_city)}</div><div class="order-tags"><span>${esc(order.train_no)}</span><span>${esc(order.date)}</span><span>${esc(order.seat_type)}</span></div><div class="order-money"><span>模拟订单金额</span><strong>¥${order.amount}</strong></div><div class="order-id">${esc(order.order_id)}</div></div><div class="safety-note"><span>✓</span><span>订票不默认支付。支付操作需要用户明确授权。</span></div><div class="record-caption">本页只回放已保存的订单记录，不创建新订单。</div>`;
    } else if (scene === 'policy') {
      const hit = tools[0].result.hits.find(h => h.doc_id === 'P11');
      content = `<p class="assistant-lead">${esc(trace.reply)}</p><div class="policy-card"><div class="policy-label"><span>${esc(hit.doc_id)}</span><span>虚构政策 · 检索来源</span></div><h3>${esc(hit.title)}</h3><p>${esc(hit.content)}</p></div><div class="source-link">来源：${esc(hit.source)}</div><div class="record-caption">本轮调用 search_policy，没有执行支付操作。</div>`;
    }
    byId('chat-content').innerHTML = `<div class="user-message"><p>${esc(trace.user_msg)}</p><span class="user-avatar">你</span></div><div class="assistant-label"><span class="assistant-mark">T</span> Ticket Agent <span class="quiet-badge">LangChain Mock</span></div>${content}`;
    byId('message-input').value = trace.user_msg;
    byId('send-demo').disabled = busy;
    renderTrace();
  }
  function setView(next) {
    view = next;
    byId('conversation-view').hidden = next !== 'chat';
    byId('history-view').hidden = next !== 'history';
    byId('code-view').hidden = next !== 'code';
    document.querySelector('.scenario-tabs').hidden = next !== 'chat';
    ['chat','history','code'].forEach(v => byId('nav-'+v).classList.toggle('selected', v === next));
    const titles = {chat:['把每一步出行，都变得清晰。','从余票查询到模拟订票，让工具结果成为回答的依据。','出行对话'],history:['回看每一次执行，保留每一份依据。','历史记录来自 V3 已保存的 Mock 验证附件。','历史回放'],code:['从一条消息，到一条可检查的工具链。','真实源码摘录，理解框架、工具与业务授权如何协作。','核心代码']};
    byId('page-title').textContent=titles[next][0];byId('page-subtitle').textContent=titles[next][1];byId('breadcrumb-page').textContent=titles[next][2];
  }
  function choose(next) {
    if (timer) clearTimeout(timer);
    pending = false; scene = next;
    document.querySelectorAll('[data-scene]').forEach(b => b.setAttribute('aria-selected',String(b.dataset.scene === next)));
    setView('chat');renderChat();
  }
  document.querySelectorAll('[data-scene]').forEach(b => b.addEventListener('click',()=>choose(b.dataset.scene)));
  byId('reset-demo').addEventListener('click',()=>choose('query'));
  ['chat','history','code'].forEach(v=>byId('nav-'+v).addEventListener('click',()=>setView(v)));
  byId('send-demo').addEventListener('click',()=>{
    if (byId('message-input').value.trim() !== current().trace.user_msg) {
      byId('message-input').value=current().trace.user_msg;
      byId('page-subtitle').textContent='离线效果稿仅回放所选场景；新消息请在真实 Streamlit 应用中发送。';
      return;
    }
    pending=true;renderChat();timer=setTimeout(()=>{pending=false;renderChat()},1300);
  });
  byId('history-list').innerHTML = Object.entries(data.scenes).map(([key,{trace}])=>`<div class="history-item"><span class="history-mode">langchain_mock</span><span>${esc(trace.user_msg)}</span><span class="history-tools">${esc(trace.tool_sequence.join(' → '))}</span><button class="primary-button" data-replay="${key}">查看</button></div>`).join('');
  document.querySelectorAll('[data-replay]').forEach(b=>b.addEventListener('click',()=>choose(b.dataset.replay)));
  byId('code-list').innerHTML = data.code.map(item=>`<article class="code-item"><div class="code-item-header"><div><h3>${esc(item.title)}</h3><p>${esc(item.purpose)}</p></div><span class="code-location">${esc(item.path)}:${item.line}</span></div><pre>${esc(item.code)}</pre></article>`).join('');
  const requested = new URLSearchParams(location.search).get('scene');
  choose(['query','order','policy','processing'].includes(requested) ? requested : 'query');
  window.TICKET_PREVIEW = {choose, setView, getState:()=>({scene,view,pending})};
})();
