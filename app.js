const $ = (s, p=document) => p.querySelector(s);
const $$ = (s, p=document) => [...p.querySelectorAll(s)];
let me = null, settings = {}, dash = null, currentPage = 'dashboard';
let ownerWelcomeDisplayed = false;
const nf = new Intl.NumberFormat('en-IN', {maximumFractionDigits: 0});
const nf2 = new Intl.NumberFormat('en-IN', {maximumFractionDigits: 2});
const money = v => 'NPR ' + nf.format(Number(v||0));
const qty = v => nf2.format(Number(v||0));
const esc = s => String(s??'').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

function injectEnhancementStyles(){
  if($('#v9EnhancementStyles')) return;
  const style=document.createElement('style');
  style.id='v9EnhancementStyles';
  style.textContent=`
    .management-highlights{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
    .management-highlight{position:relative;display:flex;gap:12px;align-items:flex-start;padding:15px 16px;border:1px solid #ececec;border-radius:14px;background:#fff;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
    .management-highlight:hover{transform:translateY(-2px);border-color:#d90819;box-shadow:0 10px 28px rgba(0,0,0,.07)}
    .management-highlight .highlight-mark{width:9px;min-width:9px;height:9px;border-radius:999px;margin-top:6px;background:#111}
    .management-highlight .highlight-text{color:#111;font-size:14px;line-height:1.55;font-weight:600}
    .management-highlight.success{border-color:#b9e6c6;background:#f5fff8}
    .management-highlight.success .highlight-mark{background:#138a3d}
    .management-highlight.success .highlight-text{color:#0c6b2e}
    .management-highlight.positive{border-color:#cce8d4;background:#f8fff9}
    .management-highlight.positive .highlight-mark{background:#138a3d}
    .management-highlight.warning{border-color:#f0d5ad;background:#fffaf3}
    .management-highlight.warning .highlight-mark{background:#b46b00}
    .management-highlight.danger{border-color:#f2bcc2;background:#fff7f8}
    .management-highlight.danger .highlight-mark{background:#d90819}
    .management-highlight.danger .highlight-text{color:#b60716}
    .owner-welcome-overlay{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(10,10,10,.52);backdrop-filter:blur(7px);animation:welcomeFade .18s ease-out}
    .owner-welcome-card{width:min(760px,100%);max-height:90vh;overflow:auto;background:#fff;border-radius:24px;border:1px solid rgba(217,8,25,.16);box-shadow:0 28px 80px rgba(0,0,0,.22);padding:28px;position:relative;animation:welcomeUp .24s ease-out}
    .owner-welcome-accent{height:5px;position:absolute;left:0;right:0;top:0;background:#d90819;border-radius:24px 24px 0 0}
    .owner-welcome-close{position:absolute;right:18px;top:18px;width:36px;height:36px;border:1px solid #e7e7e7;border-radius:50%;background:#fff;color:#111;font-size:22px;line-height:1;cursor:pointer;transition:.18s ease}
    .owner-welcome-close:hover{color:#fff;background:#d90819;border-color:#d90819;transform:rotate(4deg)}
    .owner-welcome-kicker{font-size:12px;font-weight:800;letter-spacing:.13em;text-transform:uppercase;color:#d90819;margin-bottom:8px}
    .owner-welcome-title{font-size:30px;line-height:1.1;color:#111;margin:0 50px 7px 0;font-weight:850}
    .owner-welcome-sub{margin:0 0 22px;color:#666;font-size:14px}
    .owner-welcome-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
    .owner-summary-card{border:1px solid #ededed;border-radius:16px;padding:17px;background:#fff;transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease}
    .owner-summary-card:hover{transform:translateY(-3px);border-color:#d90819;box-shadow:0 12px 28px rgba(0,0,0,.07)}
    .owner-summary-card .summary-label{font-size:12px;color:#6b6b6b;text-transform:uppercase;letter-spacing:.07em;font-weight:750;margin-bottom:7px}
    .owner-summary-card .summary-value{font-size:23px;color:#111;font-weight:850;line-height:1.2}
    .owner-order-card{grid-column:1/-1;border-color:#f1c2c7;background:#fff8f9}
    .owner-order-card .summary-value{font-size:15px;color:#a90614;line-height:1.55}
    .owner-order-chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
    .owner-order-chip{display:inline-flex;padding:7px 10px;border-radius:999px;background:#fff;border:1px solid #efc0c5;color:#9e0714;font-size:12px;font-weight:750}
    .owner-date-card{grid-column:1/-1;background:#fff;border-color:#f0c6ca}
    .owner-date-card .owner-date-value{font-size:19px;color:#d90819}
    .owner-welcome-note{margin:14px 0 0;padding:11px 13px;border-radius:12px;background:#fafafa;border:1px solid #ececec;color:#666;font-size:13px;line-height:1.45}
    .owner-welcome-actions{display:flex;justify-content:flex-end;margin-top:22px}
    .owner-dashboard-btn{border:1px solid #d90819;background:#d90819;color:#fff;border-radius:12px;padding:12px 22px;font-size:14px;font-weight:800;cursor:pointer;transition:transform .18s ease,box-shadow .18s ease,background .18s ease}
    .owner-dashboard-btn:hover{background:#b80615;box-shadow:0 9px 24px rgba(217,8,25,.25);transform:translateY(-2px)}
    @keyframes welcomeFade{from{opacity:0}to{opacity:1}}
    @keyframes welcomeUp{from{opacity:0;transform:translateY(14px) scale(.985)}to{opacity:1;transform:none}}
    @media(max-width:760px){
      .management-highlights{grid-template-columns:1fr}
      .owner-welcome-overlay{padding:12px;align-items:flex-end}
      .owner-welcome-card{border-radius:22px 22px 0 0;padding:24px 18px 20px;max-height:92vh}
      .owner-welcome-title{font-size:26px}
      .owner-welcome-grid{grid-template-columns:1fr}
      .owner-order-card{grid-column:auto}
      .owner-dashboard-btn{width:100%}
    }
  `;
  document.head.appendChild(style);
}
injectEnhancementStyles();

function managementHighlights(items){
  if(!items?.length) return empty('No management highlights are available for this period.');
  return `<div class="management-highlights">${items.slice(0,8).map(item=>{
    const obj=typeof item==='string'?{text:item,tone:'neutral'}:item;
    const tone=['success','positive','warning','danger','neutral'].includes(obj.tone)?obj.tone:'neutral';
    return `<div class="management-highlight ${tone}"><span class="highlight-mark"></span><div class="highlight-text">${esc(obj.text||'')}</div></div>`;
  }).join('')}</div>`;
}

function closeOwnerWelcome(){
  const overlay=$('#ownerWelcomeOverlay');
  if(overlay) overlay.remove();
}

async function showOwnerWelcome(force=false){
  if(me?.role!=='owner') return;
  if(ownerWelcomeDisplayed && !force) return;

  closeOwnerWelcome();

  let info=null;
  try{
    info=await api('/api/owner-welcome');
  }catch(err){
    console.warn('Owner welcome API unavailable:',err);
    const now=new Date();
    const dateLabel=new Intl.DateTimeFormat('en-GB',{
      timeZone:'Asia/Kathmandu',weekday:'long',day:'numeric',month:'long',year:'numeric'
    }).format(now);
    info={
      date_label:dateLabel,
      pizza_qty:0,
      total_sales:0,
      highest_sold_item:null,
      has_data:false
    };
  }

  ownerWelcomeDisplayed=true;
  const best=info?.highest_sold_item;
  const dateLabel=info?.date_label||info?.date||'Today';
  const noDataNote=info?.has_data===false
    ? `<p class="owner-welcome-note">No restaurant data has been uploaded for this date yet.</p>`
    : '';

  document.body.insertAdjacentHTML('beforeend',`
    <div class="owner-welcome-overlay" id="ownerWelcomeOverlay" role="dialog" aria-modal="true" aria-labelledby="ownerWelcomeTitle">
      <div class="owner-welcome-card">
        <div class="owner-welcome-accent"></div>
        <button class="owner-welcome-close" id="ownerWelcomeClose" type="button" aria-label="Close welcome summary">×</button>
        <div class="owner-welcome-kicker">Today's restaurant snapshot</div>
        <h2 class="owner-welcome-title" id="ownerWelcomeTitle">Welcome back!</h2>
        <p class="owner-welcome-sub">Here is the restaurant performance recorded for today across both branches.</p>
        <div class="owner-welcome-grid">
          <div class="owner-summary-card owner-date-card">
            <div class="summary-label">Today's date</div>
            <div class="summary-value owner-date-value">${esc(dateLabel)}</div>
          </div>
          <div class="owner-summary-card">
            <div class="summary-label">Pizzas sold today</div>
            <div class="summary-value">${nf.format(Number(info?.pizza_qty||0))}</div>
          </div>
          <div class="owner-summary-card">
            <div class="summary-label">Total sales today</div>
            <div class="summary-value">${money(info?.total_sales||0)}</div>
          </div>
          <div class="owner-summary-card">
            <div class="summary-label">Highest-selling item today</div>
            <div class="summary-value">${best?`${esc(best.name)} · ${nf.format(Number(best.qty||0))} sold`:'No sold-item data yet'}</div>
          </div>
        </div>
        ${noDataNote}
        <div class="owner-welcome-actions">
          <button class="owner-dashboard-btn" id="ownerDashboardBtn" type="button">Dashboard</button>
        </div>
      </div>
    </div>
  `);

  const overlay=$('#ownerWelcomeOverlay');
  const closeBtn=$('#ownerWelcomeClose');
  const dashboardBtn=$('#ownerDashboardBtn');
  if(closeBtn) closeBtn.onclick=closeOwnerWelcome;
  if(dashboardBtn) dashboardBtn.onclick=()=>{closeOwnerWelcome();navTo('dashboard')};
  if(overlay){
    overlay.addEventListener('click',e=>{if(e.target===overlay)closeOwnerWelcome()});
  }
  setTimeout(()=>closeBtn?.focus(),0);
}
async function api(url, options={}) {
  const res = await fetch(url, options);
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) {
    if (res.status === 401 && !url.includes('/login')) showLogin();
    throw new Error(data.detail || 'Request failed');
  }
  return data;
}
function toast(msg, bad=false){const t=$('#toast');t.textContent=msg;t.className='toast show'+(bad?' bad':'');setTimeout(()=>t.className='toast',2800)}
function showLogin(){ $('#loginView').classList.remove('hidden'); $('#appView').classList.add('hidden'); }
function showApp(){ $('#loginView').classList.add('hidden'); $('#appView').classList.remove('hidden'); }

$('#loginForm').addEventListener('submit', async e => {
  e.preventDefault(); $('#loginError').textContent='';
  try {
    await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('#loginUsername').value,password:$('#loginPassword').value})});
    ownerWelcomeDisplayed=false;
    await bootstrap(true);
  } catch(err){ $('#loginError').textContent=err.message; }
});
$('#logoutBtn').addEventListener('click', async()=>{try{await api('/api/logout',{method:'POST'})}catch(_){} ownerWelcomeDisplayed=false; closeOwnerWelcome(); showLogin()});

async function bootstrap(showWelcome=false){
  try {
    const r=await api('/api/me'); me=r.user; settings=r.settings; showApp();
    $('#restaurantName').textContent=settings.restaurant_name||'Restaurant';
    $('#userName').textContent=me.display_name; $('#userRole').textContent=roleLabel(me.role);
    $('#avatar').textContent=(me.display_name||'U').trim().charAt(0).toUpperCase();
    $$('.owner-only').forEach(el=>el.classList.toggle('hidden-role',me.role!=='owner'));
    buildBranchFilter(); await navTo('dashboard');
    if(me.role==='owner') await showOwnerWelcome(showWelcome);
  } catch(_){showLogin()}
}
function roleLabel(r){return r==='owner'?'Owner / Admin':r==='manager'?'Manager':'Head Employee'}
function buildBranchFilter(){
  const f=$('#branchFilter');
  if(me.role==='owner') f.innerHTML=`<option value="all">All branches</option><option value="1">${esc(settings.branch_1_name)}</option><option value="2">${esc(settings.branch_2_name)}</option>`;
  else f.innerHTML=`<option value="${me.branch_id}">${esc(settings['branch_'+me.branch_id+'_name'])}</option>`;
}
function branchName(id){return settings['branch_'+id+'_name']||('Branch '+id)}

$('#nav').addEventListener('click', e=>{const b=e.target.closest('[data-page]');if(b) navTo(b.dataset.page)});
$('#refreshBtn').addEventListener('click',()=>navTo(currentPage));
$('#branchFilter').addEventListener('change',()=>{if(!['upload','users','settings'].includes(currentPage)) navTo(currentPage)});
$('#startDate').addEventListener('change',()=>{if(!['upload','users','settings'].includes(currentPage)) navTo(currentPage)});
$('#endDate').addEventListener('change',()=>{if(!['upload','users','settings'].includes(currentPage)) navTo(currentPage)});

async function navTo(page){
  if(me.role!=='owner' && ['users','settings'].includes(page)) page='dashboard';
  currentPage=page; $$('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.page===page));
  const titles={dashboard:['OVERVIEW','Dashboard'],upload:['DAILY OPERATIONS','Daily Data Upload'],sales:['REVENUE','Sales Analysis'],purchase:['COST CONTROL','Purchase / Expense'],daybook:['FINANCE','Daybook'],inventory:['STOCK','Inventory'],compare:['PERFORMANCE','Branch Comparison'],history:['DATA','Upload History'],users:['ACCESS CONTROL','Users'],settings:['CONFIGURATION','Settings']};
  $('#pageTitle').textContent=titles[page][1];
  const filterOn=!['upload','users','settings'].includes(page); $('.filters').style.opacity=filterOn?'1':'.55';
  try{
    if(page==='upload') return renderUpload();
    if(page==='history') return renderHistory();
    if(page==='users') return renderUsers();
    if(page==='settings') return renderSettings();
    dash=await getDashboard();
    if(page==='dashboard') renderDashboard();
    if(page==='sales') renderSales();
    if(page==='purchase') renderPurchase();
    if(page==='daybook') renderDaybook();
    if(page==='inventory') renderInventory();
    if(page==='compare') renderCompare();
  }catch(err){$('#content').innerHTML=`<div class="empty">${esc(err.message)}</div>`}
}
async function getDashboard(){
  const q=new URLSearchParams({branch:$('#branchFilter').value}); if($('#startDate').value)q.set('start',$('#startDate').value);if($('#endDate').value)q.set('end',$('#endDate').value);
  return api('/api/dashboard?'+q.toString());
}
function kpi(label,value,sub=''){return `<div class="kpi"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div><div class="sub">${esc(sub)}</div></div>`}
function panel(title,sub,body){return `<section class="panel"><div class="panel-head"><h3>${esc(title)}</h3></div>${body}</section>`}
function bars(items, formatter=money, limit=8){
  if(!items?.length)return `<div class="empty">No data available</div>`;
  const arr=items.slice(0,limit), max=Math.max(...arr.map(x=>Number(x.value)||0),1);
  return `<div class="bar-list">${arr.map(x=>`<div class="bar-row"><span title="${esc(x.label)}">${esc(x.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.max(2,(Number(x.value)||0)/max*100)}%"></div></div><span class="bar-val">${esc(formatter(x.value))}</span></div>`).join('')}</div>`;
}
function empty(msg){return `<div class="empty">${esc(msg)}</div>`}

function renderDashboard(){
  const s=dash.sales,p=dash.purchase,inv=dash.inventory,m=dash.management||{};
  const topDishes=(s.dishes||[]).slice(0,8).map(x=>({label:x.name,value:Number(x.qty)||0}));
  const paymentData=(s.payment_modes||[]).slice(0,7);
  const best=m.highest_selling_item||s.dishes?.[0];
  const topOutlet=m.highest_sales_branch;
  const combinedLabel=(dash.branches||[]).length===2?'Both Branch Sales':'Total Sales';
  const orderBody=inv.order_list?.length?orderListTable(inv.order_list):empty('No items currently need ordering.');

  $('#content').innerHTML=`
    <div class="kpi-grid">
      ${kpi(combinedLabel,m.combined_sales!=null?money(m.combined_sales):money(s.total))}
      ${kpi('Items Sold',nf.format(s.dish_qty_total||0))}
      ${kpi('Best Seller',best?best.name:'—',best?`${nf.format(best.qty)} sold`:``)}
      ${kpi('Estimated Cheese Used',`${qty(m.cheese_used_kg||0)} kg`,m.pizza_qty?`${nf.format(m.pizza_qty)} pizzas × 100 g`:'')}
      ${kpi('Order List',nf.format(inv.order_count||0),'Low / out-of-stock items')}
      ${kpi('Bills',nf.format(s.bills))}
    </div>

    ${panel('Management Highlights','',managementHighlights(dash.insights||[]))}

    <div class="grid-2 equal dashboard-graphs">
      <section class="panel graph-panel"><div class="panel-head"><h3>Sales Trend</h3></div><div class="chart-wrap"><canvas id="salesTrend"></canvas></div></section>
      <section class="panel graph-panel"><div class="panel-head"><h3>Sales vs Purchase / Expense</h3></div><div class="chart-wrap"><canvas id="salesPurchaseTrend"></canvas></div></section>
    </div>

    <div class="grid-2 equal dashboard-graphs">
      <section class="panel graph-panel"><div class="panel-head"><h3>Top Selling Items</h3></div><div class="chart-wrap chart-wrap-bars"><canvas id="topDishesChart"></canvas></div></section>
      <section class="panel graph-panel"><div class="panel-head"><h3>Sales by Payment Mode</h3></div><div class="chart-wrap chart-wrap-bars"><canvas id="paymentChart"></canvas></div></section>
    </div>

    <div class="grid-2 equal">
      ${panel('Outlet Performance','',topOutlet?`<div class="metric-row"><span>Highest-sales outlet</span><strong>${esc(topOutlet.branch_name)}</strong></div><div class="metric-row"><span>Outlet sales</span><strong>${money(topOutlet.sales)}</strong></div><div class="metric-row"><span>Top item</span><strong>${esc(topOutlet.top_item?.name||'—')}</strong></div>`:empty('No outlet comparison available.'))}
      ${panel('Inventory Status','',`<div class="status-grid"><div class="status-card"><strong>${inv.out_count||0}</strong><span>Out of stock</span></div><div class="status-card"><strong>${inv.low_count||0}</strong><span>Low stock</span></div><div class="status-card"><strong>${inv.order_count||0}</strong><span>Order items</span></div></div>`)}
    </div>

    ${panel('Order List','',orderBody)}
    ${panel('Recent Uploads','',uploadTable(dash.recent_uploads,false))}`;

  requestAnimationFrame(()=>{
    drawLineChart($('#salesTrend'),[{name:'Sales',points:s.daily}],['#d90819']);
    drawLineChart($('#salesPurchaseTrend'),[
      {name:'Sales',points:s.daily},
      {name:'Purchase / Expense',points:p.daily}
    ],['#d90819','#111111']);
    drawHorizontalBarChart($('#topDishesChart'),topDishes,{formatter:v=>nf.format(v),suffix:' sold'});
    drawHorizontalBarChart($('#paymentChart'),paymentData,{formatter:money});
  });
}

function renderSales(){
  const s=dash.sales, best=s.dishes?.[0], low=s.dishes?.length?s.dishes[s.dishes.length-1]:null, high=s.dishes?.length?[...s.dishes].sort((a,b)=>Number(b.sales||0)-Number(a.sales||0))[0]:null;
  const source=s.dish_source==='sold_items'?'Sold Items Excel':s.dish_source==='sales_excel'?'Sales Excel':'Waiting for item data';
  $('#content').innerHTML=`
    <div class="kpi-grid">
      ${kpi('Total sales',money(s.total))}
      ${kpi('Food / items sold',nf.format(s.dish_qty_total||0),source)}
      ${kpi('Best seller by qty',best?best.name:'—',best?`${nf.format(best.qty)} sold · ${money(best.sales)}`:'')}
      ${kpi('Highest dish sales',high?high.name:'—',high?money(high.sales):'')}
      ${kpi('Lowest seller by qty',low?low.name:'—',low?`${nf.format(low.qty)} sold · ${money(low.sales)}`:'')}
      ${kpi('Bills',nf.format(s.bills))}
    </div>
    <div class="grid-2"><section class="panel"><div class="panel-head"><h3>Daily sales</h3></div><div class="chart-wrap"><canvas id="salesOnly"></canvas></div></section>${panel('Payment methods','Sales value by mode',bars(s.payment_modes))}</div>
    <div class="grid-2 equal">${panel('Order channels','Revenue by order type',bars(s.order_types))}${panel('Sales by employee','Based on Billed By / Cashier column',bars(s.staff))}</div>
    ${panel('Dish performance','',s.has_dish_data?dishTable(s.dishes):empty('No Sold Items data available.'))}`;
  requestAnimationFrame(()=>drawLineChart($('#salesOnly'),[{name:'Sales',points:s.daily}],['#d90819']))
}
function dishTable(items){
  const totalSales=items.reduce((a,x)=>a+Number(x.sales||0),0);
  return `<div class="table-wrap"><table class="table dish-table"><thead><tr><th>Rank</th><th>Dish Name</th><th>QTY</th><th>Amount</th><th>% of Dish Sales</th></tr></thead><tbody>${items.map((x,i)=>`<tr><td class="rank">#${String(i+1).padStart(2,'0')}</td><td><strong>${esc(x.name)}</strong></td><td>${nf.format(x.qty)} Sold</td><td>${money(x.sales)}</td><td><strong>${Number(x.pct ?? (totalSales?x.sales/totalSales*100:0)).toFixed(2)}%</strong></td></tr>`).join('')}</tbody></table></div>`
}

function renderPurchase(){const p=dash.purchase;$('#content').innerHTML=`<div class="kpi-grid">${kpi('Total Purchase / Expense',money(p.total),'From uploaded purchase file')}${kpi('Top Head',p.heads[0]?.label||'—',p.heads[0]?money(p.heads[0].value):'')}${kpi('Cost Categories',nf.format(p.heads.length))}${kpi('Payment Accounts',nf.format(p.accounts.length))}${kpi('Uploaded Lines',nf.format(p.lines.length),p.lines.length===30?'Showing latest sample of lines':'')}${kpi('Period',($('#startDate').value||'All')+' → '+($('#endDate').value||'All'))}</div><div class="grid-2"><section class="panel"><div class="panel-head"><h3>Purchase / expense trend</h3></div><div class="chart-wrap"><canvas id="purchaseTrend"></canvas></div></section>${panel('Expense heads','Account Head distribution',bars(p.heads))}</div>${panel('Purchase / expense lines','Recent parsed rows',p.lines.length?`<div class="table-wrap"><table class="table"><thead><tr><th>Date</th><th>Branch</th><th>Account head</th><th>Remarks</th><th>Amount</th></tr></thead><tbody>${p.lines.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(branchName(x.branch_id))}</td><td>${esc(x.head)}</td><td>${esc(x.remarks)}</td><td>${money(x.amount)}</td></tr>`).join('')}</tbody></table></div>`:empty('No purchase / expense data uploaded.'))}`;requestAnimationFrame(()=>drawLineChart($('#purchaseTrend'),[{name:'Purchase / Expense',points:p.daily}],['#d90819']))}

function renderDaybook(){const d=dash.daybook,l=d.latest||{};$('#content').innerHTML=`<div class="kpi-grid">${kpi('Net Sales',l.net_sales!=null?money(l.net_sales):'—','Latest selected daybook')}${kpi('Total Receipts',l.receipts!=null?money(l.receipts):'—')}${kpi('Expenses',l.expenses!=null?money(l.expenses):'—')}${kpi('Net Receipts',l.net_receipts!=null?money(l.net_receipts):'—')}${kpi('Closing Balance',l.closing_balance!=null?money(l.closing_balance):'—')}${kpi('Finance Difference',l.difference!=null?money(l.difference):'—')}</div>${panel('Daybook history','Extracted from standard daybook labels',d.daily.length?`<div class="table-wrap"><table class="table"><thead><tr><th>Date</th><th>Branch</th><th>Net Sales</th><th>Receipts</th><th>Expenses</th><th>Net Receipts</th><th>Closing</th><th>Difference</th></tr></thead><tbody>${d.daily.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(branchName(x.branch_id))}</td><td>${x.net_sales==null?'—':money(x.net_sales)}</td><td>${x.receipts==null?'—':money(x.receipts)}</td><td>${x.expenses==null?'—':money(x.expenses)}</td><td>${x.net_receipts==null?'—':money(x.net_receipts)}</td><td>${x.closing_balance==null?'—':money(x.closing_balance)}</td><td>${x.difference==null?'—':money(x.difference)}</td></tr>`).join('')}</tbody></table></div>`:empty('No Daybook file uploaded for this filter.'))}`}

function orderListTable(items){
  if(!items?.length)return empty('No items currently need ordering.');
  return `<div class="table-wrap"><table class="table"><thead><tr><th>Status</th><th>Branch</th><th>Item</th><th>Current</th><th>Minimum</th><th>Target</th><th>Order Qty</th><th>Unit</th></tr></thead><tbody>${items.map(x=>`<tr><td><span class="tag ${esc(x.status)}">${esc(x.status)}</span></td><td>${esc(branchName(x.branch_id))}</td><td><strong>${esc(x.item)}</strong></td><td>${qty(x.qty)}</td><td>${x.minimum==null?'—':qty(x.minimum)}</td><td>${x.target==null?'—':qty(x.target)}</td><td><strong>${qty(x.order_qty)}</strong></td><td>${esc(x.unit||'')}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderInventory(){
  const inv=dash.inventory,m=dash.management||{};
  const cheeseRows=(m.branches||[]).filter(x=>x.cheese_stock);
  const cheesePanel=cheeseRows.length?panel('Cheese Usage & Stock','',`<div class="table-wrap"><table class="table"><thead><tr><th>Branch</th><th>Pizzas Sold</th><th>Estimated Cheese Used</th><th>Cheese Stock</th><th>Minimum</th><th>Target</th><th>Needed to Target</th><th>Status</th></tr></thead><tbody>${cheeseRows.map(b=>{const c=b.cheese_stock;return `<tr><td>${esc(b.branch_name)}</td><td>${nf.format(b.pizza_qty)}</td><td>${qty(b.cheese_used_kg)} kg</td><td>${qty(c.current)} ${esc(c.unit)}</td><td>${c.minimum==null?'—':qty(c.minimum)+' '+esc(c.unit)}</td><td>${c.target==null?'—':qty(c.target)+' '+esc(c.unit)}</td><td>${qty(c.needed_to_target)} ${esc(c.unit)}</td><td><span class="tag ${esc(c.status)}">${esc(c.status)}</span></td></tr>`}).join('')}</tbody></table></div>`):'';

  $('#content').innerHTML=`
    <div class="kpi-grid">
      ${kpi('Out of Stock',nf.format(inv.out_count||0))}
      ${kpi('Low Stock',nf.format(inv.low_count||0))}
      ${kpi('Order Items',nf.format(inv.order_count||0))}
      ${kpi('Stock Rows',nf.format(inv.items?.length||0))}
      ${kpi('Cheese Used',`${qty(m.cheese_used_kg||0)} kg`,m.pizza_qty?`${nf.format(m.pizza_qty)} pizzas`:``)}
      ${kpi('Stock Data',inv.has_stock_data?'Active':'—')}
    </div>
    ${cheesePanel}
    ${inv.has_stock_data?panel('Inventory','',`<div class="table-wrap"><table class="table"><thead><tr><th>Status</th><th>Branch</th><th>Item</th><th>Current</th><th>Minimum</th><th>Target</th><th>Order Qty</th><th>Unit</th><th>Date</th></tr></thead><tbody>${inv.items.map(x=>`<tr><td><span class="tag ${esc(x.status)}">${esc(x.status)}</span></td><td>${esc(branchName(x.branch_id))}</td><td>${esc(x.item)}</td><td>${qty(x.qty)}</td><td>${x.minimum==null?'—':qty(x.minimum)}</td><td>${x.target==null?'—':qty(x.target)}</td><td>${qty(x.order_qty||0)}</td><td>${esc(x.unit)}</td><td>${esc(x.date)}</td></tr>`).join('')}</tbody></table></div>`):empty('No Inventory Excel uploaded for the selected branch/date.')}
    ${panel('Order List','',inv.order_list?.length?orderListTable(inv.order_list):empty('No items currently need ordering.'))}`;
}

function renderCompare(){
  const b=dash.branches||[];
  if(b.length<2){$('#content').innerHTML=empty('Branch comparison unavailable for this account.');return}
  const card=x=>`<div class="branch-card"><h3>${esc(branchName(x.branch_id))}</h3><div class="metric-row"><span>Total sales</span><strong>${money(x.sales.total)}</strong></div><div class="metric-row"><span>Food / items sold</span><strong>${nf.format(x.sales.dish_qty_total||0)}</strong></div><div class="metric-row"><span>Best seller</span><strong>${esc(x.sales.dishes?.[0]?.name||'—')}</strong></div><div class="metric-row"><span>Estimated cheese used</span><strong>${qty(x.ingredient_usage?.cheese_used_kg||0)} kg</strong></div><div class="metric-row"><span>Low / out stock</span><strong>${nf.format(x.inventory?.low_count||0)}</strong></div><div class="metric-row"><span>Purchase / expense</span><strong>${money(x.purchase.total)}</strong></div></div>`;
  $('#content').innerHTML=`<div class="compare-cards">${b.map(card).join('')}</div><div class="grid-2"><section class="panel"><div class="panel-head"><h3>Branch sales trend</h3></div><div class="chart-wrap"><canvas id="compareTrend"></canvas></div></section>${panel('Sales comparison','',bars(b.map(x=>({label:branchName(x.branch_id),value:x.sales.total}))))}</div>`;
  requestAnimationFrame(()=>drawLineChart($('#compareTrend'),b.map(x=>({name:branchName(x.branch_id),points:x.sales.daily})),['#d90819','#111111']));
}

function typeLabel(t){return String(t||'').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
function uploadTable(rows,withActions=true){if(!rows?.length)return empty('No uploads yet.');return `<div class="table-wrap"><table class="table"><thead><tr><th>Date</th><th>Branch</th><th>Type</th><th>File</th><th>Uploaded</th>${withActions?'<th></th>':''}</tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.date)}</td><td>${esc(x.branch_name)}</td><td><span class="tag ${x.type}">${esc(typeLabel(x.type))}</span></td><td>${esc(x.name)}</td><td>${esc((x.uploaded_at||'').replace('T',' '))}</td>${withActions?`<td><button class="btn danger delete-upload" data-id="${x.id}">Delete</button></td>`:''}</tr>`).join('')}</tbody></table></div>`}


function renderUpload(){
  const branchOptions=me.role==='owner'?`<option value="1">${esc(branchName(1))}</option><option value="2">${esc(branchName(2))}</option>`:`<option value="${me.branch_id}">${esc(branchName(me.branch_id))}</option>`;
  $('#content').innerHTML=`<section class="upload-card"><div class="panel-head"><h3>Daily Data Upload</h3></div><form id="uploadForm"><div class="settings-grid"><div class="field"><label>Branch</label><select id="upBranch">${branchOptions}</select></div><div class="field"><label>Business date</label><input id="upDate" type="date" required value="${new Date().toISOString().slice(0,10)}"></div></div><div class="file-grid">
  <div class="file-box"><strong>Purchase / Expense Excel</strong><input id="purchaseFile" type="file" accept=".xlsx,.xlsm"></div>
  <div class="file-box"><strong>Daybook Excel</strong><input id="daybookFile" type="file" accept=".xlsx,.xlsm"></div>
  <div class="file-box"><strong>Sales Excel</strong><input id="salesFile" type="file" accept=".xlsx,.xlsm"></div>
  <div class="file-box sold-items-box"><strong>Sold Items Excel</strong><input id="soldItemsFile" type="file" accept=".xlsx,.xlsm"><a class="template-link" href="/sold-items-template.xlsx">Sold Items template</a></div>
  <div class="file-box"><strong>Inventory Excel</strong><input id="inventoryFile" type="file" accept=".xlsx,.xlsm"><a class="template-link" href="/inventory-template.xlsx">Inventory template</a></div>
  </div><button class="btn primary" style="margin-top:18px" type="submit">Upload Excel Files</button><div id="uploadStatus" class="mini-stat" style="margin-top:10px"></div></form></section>`;
  $('#uploadForm').addEventListener('submit',handleUpload);
}

async function handleUpload(e){
  e.preventDefault();
  const files=[['purchase',$('#purchaseFile').files[0]],['daybook',$('#daybookFile').files[0]],['sales',$('#salesFile').files[0]],['sold_items',$('#soldItemsFile').files[0]],['inventory',$('#inventoryFile').files[0]]].filter(x=>x[1]);
  if(!files.length)return toast('Choose at least one Excel file',true);
  let done=0;
  for(const [type,file] of files){
    const fd=new FormData();fd.append('branch_id',$('#upBranch').value);fd.append('upload_date',$('#upDate').value);fd.append('file_type',type);fd.append('file',file);
    $('#uploadStatus').textContent=`Uploading ${typeLabel(type)}...`;
    try{const r=await api('/api/upload',{method:'POST',body:fd});done++;$('#uploadStatus').textContent=`${typeLabel(type)}: ${r.rows} rows parsed successfully.`}catch(err){toast(`${typeLabel(type)}: ${err.message}`,true);return}
  }
  toast(`${done} Excel file(s) uploaded successfully`);
}

async function renderHistory(){try{const rows=await api('/api/uploads?branch='+encodeURIComponent($('#branchFilter').value));$('#content').innerHTML=panel('Upload history','',uploadTable(rows,true));$$('.delete-upload').forEach(b=>b.onclick=async()=>{if(!confirm('Delete this uploaded dataset?'))return;try{await api('/api/uploads/'+b.dataset.id,{method:'DELETE'});toast('Upload deleted');renderHistory()}catch(e){toast(e.message,true)}})}catch(e){$('#content').innerHTML=empty(e.message)}}


async function renderUsers(){
  const rows=await api('/api/users');
  $('#content').innerHTML=`<div class="grid-2 equal"><section class="panel"><div class="panel-head"><h3>Add user</h3></div><form id="userForm"><div class="field"><label>Full name</label><input id="newName" required></div><div class="field"><label>Username</label><input id="newUsername" required></div><div class="field"><label>Password</label><input id="newPassword" type="password" minlength="6" required></div><div class="field"><label>Role</label><select id="newRole"><option value="manager">Manager</option><option value="head_employee">Head Employee</option><option value="owner">Owner / Admin</option></select></div><div class="field" id="userBranchField"><label>Branch</label><select id="newBranch"><option value="1">${esc(branchName(1))}</option><option value="2">${esc(branchName(2))}</option></select></div><button class="btn primary">Create user</button></form></section>${panel('Current users','',`<div class="table-wrap"><table class="table"><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Branch</th><th>Status</th><th></th></tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.display_name)}</td><td>${esc(x.username)}</td><td>${esc(roleLabel(x.role))}</td><td>${x.branch_id?esc(branchName(x.branch_id)):'All'}</td><td><span class="tag ${x.active?'ok':'out'}">${x.active?'Active':'Disabled'}</span></td><td>${x.id===me.id?'':`<button class="btn secondary toggle-user" data-id="${x.id}">${x.active?'Disable':'Enable'}</button>`}</td></tr>`).join('')}</tbody></table></div>`)}</div>`;
  $('#newRole').onchange=()=>$('#userBranchField').style.display=$('#newRole').value==='owner'?'none':'grid';
  $('#userForm').onsubmit=async e=>{e.preventDefault();const body={display_name:$('#newName').value,username:$('#newUsername').value,password:$('#newPassword').value,role:$('#newRole').value,branch_id:$('#newRole').value==='owner'?null:Number($('#newBranch').value)};try{await api('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});toast('User created');renderUsers()}catch(err){toast(err.message,true)}};
  $$('.toggle-user').forEach(b=>b.onclick=async()=>{try{await api('/api/users/'+b.dataset.id+'/toggle',{method:'POST'});renderUsers()}catch(e){toast(e.message,true)}})
}

function renderSettings(){
  $('#content').innerHTML=`<div class="settings-grid"><section class="panel"><div class="panel-head"><h3>Restaurant & branches</h3></div><form id="settingsForm"><div class="field"><label>Restaurant name</label><input id="setRestaurant" value="${esc(settings.restaurant_name)}" required></div><div class="field"><label>Branch 1 name</label><input id="setB1" value="${esc(settings.branch_1_name)}" required></div><div class="field"><label>Branch 2 name</label><input id="setB2" value="${esc(settings.branch_2_name)}" required></div><button class="btn primary">Save settings</button></form></section><section class="panel"><div class="panel-head"><h3>Inventory threshold</h3></div><form id="thresholdForm"><div class="field"><label>Branch</label><select id="thBranch"><option value="1">${esc(branchName(1))}</option><option value="2">${esc(branchName(2))}</option></select></div><div class="field"><label>Exact item name</label><input id="thItem" placeholder="Chicken Breast" required></div><div class="settings-grid"><div class="field"><label>Minimum qty</label><input id="thQty" type="number" step="0.01" required></div><div class="field"><label>Unit</label><input id="thUnit" placeholder="kg"></div></div><button class="btn secondary">Save threshold</button></form></section></div>`;
  $('#settingsForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({restaurant_name:$('#setRestaurant').value,branch_1_name:$('#setB1').value,branch_2_name:$('#setB2').value})});const r=await api('/api/me');settings=r.settings;$('#restaurantName').textContent=settings.restaurant_name;buildBranchFilter();toast('Settings saved')}catch(err){toast(err.message,true)}};
  $('#thresholdForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/stock-thresholds',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({branch_id:Number($('#thBranch').value),item_name:$('#thItem').value,minimum_qty:Number($('#thQty').value),unit:$('#thUnit').value})});toast('Stock threshold saved')}catch(err){toast(err.message,true)}};
}

function drawLineChart(canvas,datasets,colors){
  if(!canvas)return;const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;canvas.width=Math.max(300,rect.width*dpr);canvas.height=Math.max(180,rect.height*dpr);const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);const W=rect.width,H=rect.height,p={l:55,r:15,t:18,b:38};ctx.clearRect(0,0,W,H);
  const labels=[...new Set(datasets.flatMap(ds=>(ds.points||[]).map(x=>x.date)))].sort();if(!labels.length){ctx.fillStyle='#666666';ctx.font='13px system-ui';ctx.textAlign='center';ctx.fillText('No trend data available',W/2,H/2);return}
  const maps=datasets.map(ds=>Object.fromEntries((ds.points||[]).map(x=>[x.date,Number(x.value)||0])));const vals=maps.flatMap(m=>labels.map(l=>m[l]||0));const max=Math.max(...vals,1)*1.1;ctx.strokeStyle='#e7e9ed';ctx.lineWidth=1;ctx.fillStyle='#555555';ctx.font='10px system-ui';ctx.textAlign='right';for(let i=0;i<=4;i++){const y=p.t+(H-p.t-p.b)*i/4;ctx.beginPath();ctx.moveTo(p.l,y);ctx.lineTo(W-p.r,y);ctx.stroke();const v=max*(1-i/4);ctx.fillText(compact(v),p.l-8,y+3)}ctx.textAlign='center';const shown=Math.min(labels.length,7);labels.forEach((l,i)=>{if(labels.length<=7||i%Math.ceil(labels.length/shown)===0||i===labels.length-1){const x=p.l+(W-p.l-p.r)*(labels.length===1?.5:i/(labels.length-1));ctx.fillText(shortDate(l),x,H-14)}});
  datasets.forEach((ds,di)=>{const m=maps[di];ctx.strokeStyle=colors[di%colors.length];ctx.lineWidth=2.4;ctx.beginPath();labels.forEach((l,i)=>{const x=p.l+(W-p.l-p.r)*(labels.length===1?.5:i/(labels.length-1));const y=p.t+(H-p.t-p.b)*(1-(m[l]||0)/max);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke();labels.forEach((l,i)=>{const x=p.l+(W-p.l-p.r)*(labels.length===1?.5:i/(labels.length-1));const y=p.t+(H-p.t-p.b)*(1-(m[l]||0)/max);ctx.fillStyle=colors[di%colors.length];ctx.beginPath();ctx.arc(x,y,2.8,0,Math.PI*2);ctx.fill()})});
  if(datasets.length>1){ctx.textAlign='left';datasets.forEach((ds,i)=>{ctx.fillStyle=colors[i%colors.length];ctx.fillRect(p.l+i*150,4,12,3);ctx.fillStyle='#111111';ctx.fillText(ds.name,p.l+18+i*150,9)})}
}
function drawHorizontalBarChart(canvas,items,options={}){
  if(!canvas)return;
  const data=(items||[]).filter(x=>Number.isFinite(Number(x.value))).slice(0,8);
  const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
  canvas.width=Math.max(300,rect.width*dpr);canvas.height=Math.max(210,rect.height*dpr);
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
  const W=rect.width,H=rect.height;ctx.clearRect(0,0,W,H);
  if(!data.length){ctx.fillStyle='#666666';ctx.font='13px system-ui';ctx.textAlign='center';ctx.fillText('No data available',W/2,H/2);return}
  const max=Math.max(...data.map(x=>Number(x.value)||0),1);
  const labelW=Math.min(150,Math.max(95,W*.28)),valueW=82;
  const p={l:labelW+12,r:valueW+12,t:8,b:8};
  const plotW=Math.max(50,W-p.l-p.r), rowH=(H-p.t-p.b)/data.length;
  const format=options.formatter||compact, suffix=options.suffix||'';
  ctx.font='11px system-ui';ctx.textBaseline='middle';
  data.forEach((item,i)=>{
    const value=Number(item.value)||0, y=p.t+i*rowH+rowH/2;
    let label=String(item.label??'');
    const maxLabel=Math.max(8,Math.floor(labelW/7.2));
    if(label.length>maxLabel)label=label.slice(0,maxLabel-1)+'…';
    ctx.fillStyle='#111111';ctx.textAlign='right';ctx.fillText(label,p.l-10,y);
    const barH=Math.min(22,rowH*.52),barY=y-barH/2;
    ctx.fillStyle='#f1f1f1';roundRect(ctx,p.l,barY,plotW,barH,5);ctx.fill();
    const fillW=Math.max(value>0?3:0,plotW*(value/max));
    ctx.fillStyle='#d90819';roundRect(ctx,p.l,barY,fillW,barH,5);ctx.fill();
    ctx.fillStyle='#111111';ctx.textAlign='left';ctx.fillText(String(format(value))+suffix,p.l+plotW+10,y);
  });
}
function roundRect(ctx,x,y,w,h,r){
  const rr=Math.min(r,w/2,h/2);ctx.beginPath();ctx.moveTo(x+rr,y);ctx.arcTo(x+w,y,x+w,y+h,rr);ctx.arcTo(x+w,y+h,x,y+h,rr);ctx.arcTo(x,y+h,x,y,rr);ctx.arcTo(x,y,x+w,y,rr);ctx.closePath();
}
function compact(v){if(v>=1e7)return (v/1e7).toFixed(1)+'Cr';if(v>=1e5)return (v/1e5).toFixed(1)+'L';if(v>=1e3)return (v/1e3).toFixed(0)+'k';return Math.round(v).toString()}
function shortDate(s){if(!s)return'';const p=s.split('-');return p.length===3?`${p[1]}/${p[2]}`:s}

bootstrap();
