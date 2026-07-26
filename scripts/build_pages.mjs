import fs from "node:fs";
import path from "node:path";

const projectDir = path.resolve(import.meta.dirname);
const csvPath = path.resolve(projectDir, "../output/latest.csv");
const changesPath = path.resolve(projectDir, "../output/changes.json");
const pagesDir = path.resolve(projectDir, "../docs");

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      if (quoted && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      row.push(field);
      field = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[index + 1] === "\n") index += 1;
      row.push(field);
      if (row.some(Boolean)) rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function categoryFromUrl(url) {
  const value = url.toLowerCase();
  if (value.includes("food-dining")) return "食品飲料";
  if (value.includes("digital-mobile") || value.includes("televisions-appliances")) return "家電 3C";
  if (value.includes("household-baby-toys")) return "日用品";
  if (value.includes("furniture-kitchen")) return "家具家居";
  if (value.includes("health-beauty")) return "保健美容";
  if (value.includes("clothing-accessories")) return "服飾配件";
  if (value.includes("online-exclusive-exercise")) return "運動休閒";
  return "其他";
}

const rows = parseCsv(fs.readFileSync(csvPath, "utf8").replace(/^\uFEFF/, ""));
const headers = rows.shift();
const column = Object.fromEntries(headers.map((header, index) => [header, index]));
const deals = rows.map((row) => {
  const url = row[column["商品網址"]] || "";
  return {
    date: row[column["日期"]] || "",
    name: row[column["商品"]] || "",
    price: row[column["價格"]] || "請查看官網",
    originalPrice: column["原價"] === undefined ? "" : row[column["原價"]],
    discountAmount: column["折價金額"] === undefined ? "" : row[column["折價金額"]],
    promotion: column["優惠說明"] === undefined ? "" : row[column["優惠說明"]],
    url,
    image: column["圖片網址"] === undefined ? "" : row[column["圖片網址"]],
    category: column["分類"] === undefined ? categoryFromUrl(url) : row[column["分類"]],
  };
});
const updatedDate = deals[0]?.date || new Date().toISOString().slice(0, 10);
const embeddedDeals = JSON.stringify(deals).replaceAll("<", "\\u003c");
const changes = fs.existsSync(changesPath)
  ? JSON.parse(fs.readFileSync(changesPath, "utf8"))
  : { date: updatedDate, generated_at: updatedDate, has_previous: false, added: [], removed: [], price_changes: [] };
const updatedTime = changes.generated_at || changes.date || updatedDate;
const embeddedChanges = JSON.stringify(changes).replaceAll("<", "\\u003c");
const ogPath = path.join(pagesDir, "og.png");
const ogBase64 = fs.existsSync(ogPath)
  ? fs.readFileSync(ogPath).toString("base64")
  : "";

const html = `<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#07182f">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Costco 優惠">
  <link rel="manifest" href="./manifest.webmanifest">
  <link rel="apple-touch-icon" href="./og.png">
  <title>Costco 每日優惠</title>
  <meta name="description" content="搜尋與分類 Costco 台灣官方線上優惠，快速找到 Apple 追蹤商品。">
  <meta property="og:title" content="Costco 每日優惠">
  <meta property="og:description" content="搜尋・分類・Apple 追蹤">
  <meta property="og:image" content="./og.png">
  <style>
    :root{color-scheme:dark;--navy:#07182f;--panel:#0d2748;--panel2:#12345e;--line:#214972;--cyan:#26c6e8;--red:#e31937;--text:#f7fbff;--muted:#a8bdd2}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 85% 0,#13355c 0,transparent 32%),var(--navy);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Noto Sans TC",sans-serif;min-height:100vh}
    button,input{font:inherit}.shell{width:min(1120px,100%);margin:auto;padding:28px 20px 64px}.eyebrow{display:inline-flex;gap:8px;align-items:center;color:var(--cyan);font-weight:750;letter-spacing:.08em;font-size:.8rem}.dot{width:8px;height:8px;border-radius:50%;background:var(--red);box-shadow:0 0 0 5px #e3193722}
    header{padding:28px 0 22px}h1{font-size:clamp(2.25rem,8vw,5.4rem);line-height:.94;margin:18px 0 16px;letter-spacing:-.055em;max-width:780px}.red{color:var(--red)}.lead{color:var(--muted);font-size:clamp(1rem,2vw,1.22rem);max-width:720px;line-height:1.7}.status-banner{display:flex;align-items:center;gap:10px;margin-top:18px;padding:13px 16px;border:1px solid #f3b33d;background:#6b470c66;color:#ffe2a1;border-radius:14px;font-weight:750}.status-banner[hidden]{display:none}
    .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}.stat{background:#0d2748cc;border:1px solid var(--line);padding:18px;border-radius:18px}.stat strong{display:block;font-size:1.8rem}.stat span{color:var(--muted);font-size:.86rem}
    .toolbar{position:sticky;top:0;z-index:10;background:#07182fe8;backdrop-filter:blur(16px);padding:12px 0}.search{display:flex;align-items:center;gap:10px;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:0 16px}.search input{width:100%;height:54px;background:none;border:0;color:var(--text);outline:none;font-size:1rem}.search input::placeholder{color:#7891aa}
    .changes{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:18px 0}.change{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:16px;padding:14px;text-align:left;cursor:pointer}.change strong{display:block;font-size:1.55rem}.change span{color:var(--muted);font-size:.82rem}.change.active{border-color:var(--cyan);box-shadow:0 0 0 1px var(--cyan)}.chips{display:flex;gap:8px;overflow:auto;padding:12px 0 4px;scrollbar-width:none}.chips::-webkit-scrollbar{display:none}.chip{white-space:nowrap;border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:999px;padding:9px 14px;cursor:pointer}.chip.active{background:var(--cyan);border-color:var(--cyan);color:#032238;font-weight:800}
    .sectionhead{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:30px 0 14px}.sectionhead h2{margin:0;font-size:1.35rem}.sectionhead p{margin:0;color:var(--muted);font-size:.88rem}.list-controls{display:flex;align-items:end;gap:10px;flex-wrap:wrap;justify-content:flex-end}.control{display:flex;flex-direction:column;gap:5px;color:var(--muted);font-size:.78rem}.control select,.control input{height:42px;background:var(--panel);border:1px solid var(--line);border-radius:12px;color:var(--text);padding:0 12px}.control select{appearance:none;padding-right:34px;background-image:linear-gradient(45deg,transparent 50%,var(--cyan) 50%),linear-gradient(135deg,var(--cyan) 50%,transparent 50%);background-position:calc(100% - 16px) 17px,calc(100% - 11px) 17px;background-size:5px 5px;background-repeat:no-repeat}.control input{width:140px}.control[hidden]{display:none}
    .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.card{display:flex;flex-direction:column;min-height:310px;background:linear-gradient(145deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:20px;padding:12px 18px 18px;color:var(--text);transition:transform .18s,border-color .18s;overflow:hidden}.card:hover{transform:translateY(-3px);border-color:var(--cyan)}.product-link{color:inherit;text-decoration:none}.thumb{aspect-ratio:1/1;width:100%;height:auto;margin:0 0 14px;border-radius:14px;background:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden}.thumb img{display:block;width:auto;height:auto;max-width:100%;max-height:100%;object-fit:contain;object-position:center}.placeholder{font-size:1.05rem;font-weight:900;letter-spacing:-.03em;color:var(--red)}.card .top{display:flex;align-items:center;justify-content:space-between;gap:10px}.badge{font-size:.72rem;color:var(--cyan);background:#26c6e817;padding:5px 8px;border-radius:999px}.actions{display:flex;align-items:center;gap:8px}.watch{color:#ffca45;font-size:.78rem;font-weight:800}.favorite{width:38px;height:38px;border:1px solid var(--line);border-radius:50%;background:#07182f99;color:var(--muted);cursor:pointer;font-size:1.2rem;line-height:1}.favorite.saved{color:#ff6680;border-color:#ff6680;background:#e3193720}.card h3{font-size:1rem;line-height:1.5;margin:16px 0;flex:1}.price-row{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}.price{font-size:1.35rem;font-weight:850;color:#ff7187}.original-price{color:var(--muted);text-decoration:line-through;font-size:.9rem}.saving{color:#ffca45;font-size:.78rem;font-weight:800;margin-top:5px}.promotion{color:var(--cyan);font-size:.78rem;margin-top:5px}.unavailable{color:var(--muted);font-size:.78rem;margin-top:5px}.go{color:var(--muted);font-size:.78rem;margin-top:8px}.empty{text-align:center;color:var(--muted);padding:64px 20px;border:1px dashed var(--line);border-radius:20px;grid-column:1/-1}
    footer{color:var(--muted);font-size:.78rem;line-height:1.7;margin-top:42px;border-top:1px solid var(--line);padding-top:20px}
    @media(max-width:820px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.shell{padding:18px 14px 44px}.stats{grid-template-columns:1fr 1fr}.stat:last-child{grid-column:1/-1}.changes{grid-template-columns:1fr}.grid{grid-template-columns:1fr}.card{min-height:178px}.sectionhead{align-items:start;flex-direction:column;gap:10px}.list-controls{width:100%;justify-content:flex-start}.control{flex:1}.control select,.control input{width:100%}}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div class="eyebrow"><span class="dot"></span>台灣官方線上優惠整理</div>
      <h1><span class="red">Costco</span><br>每日優惠</h1>
      <p class="lead">不用翻遍所有頁面。搜尋、分類，再把 Apple、iPhone、MacBook、iPad 與 iPod 優惠放到最前面。</p>
      <div class="status-banner" id="status-banner" hidden>⚠️ 資料已超過兩天沒有更新，請稍後再查看或檢查 GitHub Actions。</div>
      <div class="stats">
        <div class="stat"><strong id="total">${deals.length}</strong><span>優惠商品</span></div>
        <div class="stat"><strong id="apple">0</strong><span>Apple 追蹤結果</span></div>
        <div class="stat"><strong>${updatedTime}</strong><span>最後成功更新（台灣時間）</span></div>
      </div>
    </header>
    <div class="toolbar">
      <label class="search" aria-label="搜尋優惠"><span>⌕</span><input id="search" type="search" placeholder="搜尋商品，例如 iPad、咖啡、衛生紙…"></label>
      <div class="chips" id="chips" aria-label="商品分類"></div>
    </div>
    <div class="changes" id="changes">
      <button class="change" data-change="新增"><strong>${changes.added.length}</strong><span>今日新增</span></button>
      <button class="change" data-change="價格變動"><strong>${changes.price_changes.length}</strong><span>價格變動</span></button>
      <button class="change" data-change="已結束"><strong>${changes.removed.length}</strong><span>已結束優惠</span></button>
    </div>
    <div class="sectionhead">
      <div><h2 id="heading">全部優惠</h2><p id="result">正在整理商品…</p></div>
      <div class="list-controls">
        <label class="control">價格
          <select id="price-filter">
            <option value="all">全部價格</option>
            <option value="under500">$500 以下</option>
            <option value="500to1000">$500～$1,000</option>
            <option value="1000to3000">$1,000～$3,000</option>
            <option value="over3000">$3,000 以上</option>
            <option value="custom">自訂最高預算</option>
          </select>
        </label>
        <label class="control" id="budget-wrap" hidden>最高預算
          <input id="budget" type="number" min="1" step="100" inputmode="numeric" placeholder="例如 2000">
        </label>
        <label class="control">排序
          <select id="sort">
            <option value="new">今日新增優先</option>
            <option value="low">價格由低到高</option>
            <option value="high">價格由高到低</option>
            <option value="name">商品名稱</option>
          </select>
        </label>
      </div>
    </div>
    <section class="grid" id="grid"></section>
    <footer>本網站整理 Costco 台灣官方公開線上優惠。價格、庫存與實體賣場活動可能隨時變動，購買前請以 Costco 官網或現場為準。本網站並非 Costco 官方網站。<br><br>iPhone：請按 Safari 的「分享」按鈕，再選擇「加入主畫面」。</footer>
  </main>
  <script>
    const deals=${embeddedDeals};
    const dailyChanges=${embeddedChanges};
    const watch=["apple","iphone","macbook","ipad","ipod"];
    const categories=["全部","我的收藏","Apple 追蹤",...new Set(deals.map(d=>d.category))];
    let selected="全部";
    const search=document.querySelector("#search"),sort=document.querySelector("#sort"),priceFilter=document.querySelector("#price-filter"),budget=document.querySelector("#budget"),budgetWrap=document.querySelector("#budget-wrap"),grid=document.querySelector("#grid"),chips=document.querySelector("#chips"),result=document.querySelector("#result"),heading=document.querySelector("#heading"),changeButtons=document.querySelectorAll(".change");
    const addedUrls=new Set(dailyChanges.added.map(d=>d.url));
    const dataDate=new Date((dailyChanges.date||"${updatedDate}")+"T00:00:00+08:00"),daysOld=Math.floor((Date.now()-dataDate.getTime())/86400000);document.querySelector("#status-banner").hidden=daysOld<=2;
    let favorites;try{favorites=new Set(JSON.parse(localStorage.getItem("costcoFavorites")||"[]"))}catch{favorites=new Set()}
    const isWatched=d=>watch.some(k=>d.name.toLowerCase().includes(k));
    document.querySelector("#apple").textContent=deals.filter(isWatched).length;
    function renderChips(){chips.innerHTML=categories.map(c=>'<button class="chip '+(c===selected?'active':'')+'" data-category="'+c+'">'+c+'</button>').join("");chips.querySelectorAll("button").forEach(b=>b.onclick=()=>{selected=b.dataset.category;changeButtons.forEach(x=>x.classList.remove("active"));renderChips();render()})}
    function escapeHtml(v){return v.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
    function renderCard(d){const priceNote=d.old_price?'<div class="go">'+escapeHtml(d.old_price)+' → '+escapeHtml(d.price)+'（'+escapeHtml(d.direction)+'）</div>':'';const original=d.originalPrice||d.original_price||"",discount=d.discountAmount||d.discount_amount||"",promotion=d.promotion||"",hasDiscount=Boolean(original||discount||promotion);const saved=favorites.has(d.url);return '<article class="card"><a class="product-link" href="'+d.url+'" target="_blank" rel="noopener"><div class="thumb">'+(d.image?'<img src="'+escapeHtml(d.image)+'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="placeholder" hidden>Costco 優惠</span>':'<span class="placeholder">Costco 優惠</span>')+'</div></a><div class="top"><span class="badge">'+escapeHtml(d.category)+'</span><span class="actions">'+(isWatched(d)?'<span class="watch">★ 追蹤</span>':'')+'<button class="favorite '+(saved?'saved':'')+'" data-url="'+escapeHtml(d.url)+'" aria-label="'+(saved?'取消收藏':'加入收藏')+'" title="'+(saved?'取消收藏':'加入收藏')+'">'+(saved?'♥':'♡')+'</button></span></div><h3><a class="product-link" href="'+d.url+'" target="_blank" rel="noopener">'+escapeHtml(d.name)+'</a></h3><div class="price-row">'+(original?'<span class="original-price">原價 '+escapeHtml(original)+'</span>':'')+'<span class="price">'+(original?'特價 ':'')+escapeHtml(d.price)+'</span></div>'+(discount?'<div class="saving">省下 '+escapeHtml(discount)+'</div>':'')+(promotion?'<div class="promotion">'+escapeHtml(promotion)+'</div>':'')+(!hasDiscount?'<div class="unavailable">官網目前未提供折扣後價格</div>':'')+priceNote+'<a class="product-link go" href="'+d.url+'" target="_blank" rel="noopener">查看官方商品 →</a></article>'}
    function priceNumber(d){const match=d.price.match(/[\\d,]+/);return match?Number(match[0].replaceAll(",","")):Number.MAX_SAFE_INTEGER}
    function matchesPrice(d){const price=priceNumber(d);if(priceFilter.value==="all")return true;if(price===Number.MAX_SAFE_INTEGER)return false;if(priceFilter.value==="under500")return price<=500;if(priceFilter.value==="500to1000")return price>500&&price<=1000;if(priceFilter.value==="1000to3000")return price>1000&&price<=3000;if(priceFilter.value==="over3000")return price>3000;if(priceFilter.value==="custom"){const maximum=Number(budget.value);return !maximum||price<=maximum}return true}
    function sortDeals(items){const copy=[...items];if(sort.value==="low")return copy.sort((a,b)=>priceNumber(a)-priceNumber(b)||a.name.localeCompare(b.name,"zh-Hant"));if(sort.value==="high")return copy.sort((a,b)=>priceNumber(b)-priceNumber(a)||a.name.localeCompare(b.name,"zh-Hant"));if(sort.value==="name")return copy.sort((a,b)=>a.name.localeCompare(b.name,"zh-Hant"));return copy.sort((a,b)=>Number(addedUrls.has(b.url))-Number(addedUrls.has(a.url))||a.name.localeCompare(b.name,"zh-Hant"))}
    function bindFavorites(){grid.querySelectorAll(".favorite").forEach(button=>button.onclick=()=>{const url=button.dataset.url;if(favorites.has(url))favorites.delete(url);else favorites.add(url);localStorage.setItem("costcoFavorites",JSON.stringify([...favorites]));render()})}
    function render(){const q=search.value.trim().toLowerCase();let source=deals;if(selected==="新增")source=dailyChanges.added;if(selected==="價格變動")source=dailyChanges.price_changes;if(selected==="已結束")source=dailyChanges.removed;const special=["新增","價格變動","已結束"].includes(selected);const filtered=sortDeals(source.filter(d=>(special||selected==="全部"||(selected==="我的收藏"?favorites.has(d.url):selected==="Apple 追蹤"?isWatched(d):d.category===selected))&&(!q||d.name.toLowerCase().includes(q))&&matchesPrice(d)));heading.textContent=special?"今日"+selected:selected;result.textContent='顯示 '+filtered.length+' 項商品';grid.innerHTML=filtered.length?filtered.map(renderCard).join(""):'<div class="empty">'+(selected==="我的收藏"?"尚未收藏商品，請按商品旁的 ♡。":"沒有符合目前條件的商品。")+'</div>';bindFavorites()}
    changeButtons.forEach(b=>b.onclick=()=>{selected=b.dataset.change;changeButtons.forEach(x=>x.classList.toggle("active",x===b));renderChips();render()});
    search.addEventListener("input",render);sort.addEventListener("change",render);priceFilter.addEventListener("change",()=>{budgetWrap.hidden=priceFilter.value!=="custom";render()});budget.addEventListener("input",render);renderChips();render();
    if("serviceWorker" in navigator)window.addEventListener("load",()=>navigator.serviceWorker.register("./service-worker.js"));
  </script>
</body>
</html>`;

fs.mkdirSync(pagesDir, { recursive: true });
fs.writeFileSync(path.join(pagesDir, "index.html"), html);
fs.writeFileSync(path.join(pagesDir, ".nojekyll"), "");
fs.writeFileSync(
  path.join(pagesDir, "manifest.webmanifest"),
  JSON.stringify(
    {
      name: "Costco 台灣每日優惠",
      short_name: "Costco 優惠",
      description: "每日整理 Costco 台灣官方線上優惠",
      start_url: "./",
      scope: "./",
      display: "standalone",
      background_color: "#07182f",
      theme_color: "#07182f",
      lang: "zh-Hant",
      icons: [
        {
          src: "./og.png",
          sizes: "any",
          type: "image/png",
          purpose: "any",
        },
      ],
    },
    null,
    2,
  ) + "\n",
);
fs.writeFileSync(
  path.join(pagesDir, "service-worker.js"),
  `const CACHE="costco-daily-${updatedDate}";
const CORE=["./","./index.html","./manifest.webmanifest","./og.png"];
self.addEventListener("install",event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener("activate",event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener("fetch",event=>{if(event.request.method!=="GET"||new URL(event.request.url).origin!==location.origin)return;event.respondWith(fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));return response}).catch(()=>caches.match(event.request).then(response=>response||caches.match("./index.html"))))});
`,
);
console.log(`Built GitHub Pages with ${deals.length} deals for ${updatedDate}`);
