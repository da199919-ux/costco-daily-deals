import fs from "node:fs";
import path from "node:path";

const projectDir = path.resolve(import.meta.dirname);
const csvPath = path.resolve(projectDir, "../output/latest.csv");
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
    url,
    image: column["圖片網址"] === undefined ? "" : row[column["圖片網址"]],
    category: column["分類"] === undefined ? categoryFromUrl(url) : row[column["分類"]],
  };
});
const updatedDate = deals[0]?.date || new Date().toISOString().slice(0, 10);
const embeddedDeals = JSON.stringify(deals).replaceAll("<", "\\u003c");
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
  <title>Costco 每日優惠</title>
  <meta name="description" content="搜尋與分類 Costco 台灣官方線上優惠，快速找到 Apple 追蹤商品。">
  <meta property="og:title" content="Costco 每日優惠">
  <meta property="og:description" content="搜尋・分類・Apple 追蹤">
  <meta property="og:image" content="./og.png">
  <style>
    :root{color-scheme:dark;--navy:#07182f;--panel:#0d2748;--panel2:#12345e;--line:#214972;--cyan:#26c6e8;--red:#e31937;--text:#f7fbff;--muted:#a8bdd2}
    *{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 85% 0,#13355c 0,transparent 32%),var(--navy);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Noto Sans TC",sans-serif;min-height:100vh}
    button,input{font:inherit}.shell{width:min(1120px,100%);margin:auto;padding:28px 20px 64px}.eyebrow{display:inline-flex;gap:8px;align-items:center;color:var(--cyan);font-weight:750;letter-spacing:.08em;font-size:.8rem}.dot{width:8px;height:8px;border-radius:50%;background:var(--red);box-shadow:0 0 0 5px #e3193722}
    header{padding:28px 0 22px}h1{font-size:clamp(2.25rem,8vw,5.4rem);line-height:.94;margin:18px 0 16px;letter-spacing:-.055em;max-width:780px}.red{color:var(--red)}.lead{color:var(--muted);font-size:clamp(1rem,2vw,1.22rem);max-width:720px;line-height:1.7}
    .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:24px 0}.stat{background:#0d2748cc;border:1px solid var(--line);padding:18px;border-radius:18px}.stat strong{display:block;font-size:1.8rem}.stat span{color:var(--muted);font-size:.86rem}
    .toolbar{position:sticky;top:0;z-index:10;background:#07182fe8;backdrop-filter:blur(16px);padding:12px 0}.search{display:flex;align-items:center;gap:10px;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:0 16px}.search input{width:100%;height:54px;background:none;border:0;color:var(--text);outline:none;font-size:1rem}.search input::placeholder{color:#7891aa}
    .chips{display:flex;gap:8px;overflow:auto;padding:12px 0 4px;scrollbar-width:none}.chips::-webkit-scrollbar{display:none}.chip{white-space:nowrap;border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:999px;padding:9px 14px;cursor:pointer}.chip.active{background:var(--cyan);border-color:var(--cyan);color:#032238;font-weight:800}
    .sectionhead{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:30px 0 14px}.sectionhead h2{margin:0;font-size:1.35rem}.sectionhead p{margin:0;color:var(--muted);font-size:.88rem}
    .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.card{display:flex;flex-direction:column;min-height:310px;background:linear-gradient(145deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:20px;padding:12px 18px 18px;text-decoration:none;color:var(--text);transition:transform .18s,border-color .18s;overflow:hidden}.card:hover{transform:translateY(-3px);border-color:var(--cyan)}.thumb{height:148px;margin:0 -6px 14px;border-radius:14px;background:#fff;display:grid;place-items:center;overflow:hidden}.thumb img{width:100%;height:100%;object-fit:contain}.placeholder{font-size:1.05rem;font-weight:900;letter-spacing:-.03em;color:var(--red)}.card .top{display:flex;justify-content:space-between;gap:10px}.badge{font-size:.72rem;color:var(--cyan);background:#26c6e817;padding:5px 8px;border-radius:999px}.watch{color:#ffca45;font-size:.78rem;font-weight:800}.card h3{font-size:1rem;line-height:1.5;margin:16px 0;flex:1}.price{font-size:1.35rem;font-weight:850}.go{color:var(--muted);font-size:.78rem;margin-top:8px}.empty{text-align:center;color:var(--muted);padding:64px 20px;border:1px dashed var(--line);border-radius:20px;grid-column:1/-1}
    footer{color:var(--muted);font-size:.78rem;line-height:1.7;margin-top:42px;border-top:1px solid var(--line);padding-top:20px}
    @media(max-width:820px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.shell{padding:18px 14px 44px}.stats{grid-template-columns:1fr 1fr}.stat:last-child{grid-column:1/-1}.grid{grid-template-columns:1fr}.card{min-height:178px}.sectionhead{align-items:start;flex-direction:column;gap:4px}}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div class="eyebrow"><span class="dot"></span>台灣官方線上優惠整理</div>
      <h1><span class="red">Costco</span><br>每日優惠</h1>
      <p class="lead">不用翻遍所有頁面。搜尋、分類，再把 Apple、iPhone、MacBook、iPad 與 iPod 優惠放到最前面。</p>
      <div class="stats">
        <div class="stat"><strong id="total">${deals.length}</strong><span>優惠商品</span></div>
        <div class="stat"><strong id="apple">0</strong><span>Apple 追蹤結果</span></div>
        <div class="stat"><strong>${updatedDate}</strong><span>資料日期</span></div>
      </div>
    </header>
    <div class="toolbar">
      <label class="search" aria-label="搜尋優惠"><span>⌕</span><input id="search" type="search" placeholder="搜尋商品，例如 iPad、咖啡、衛生紙…"></label>
      <div class="chips" id="chips" aria-label="商品分類"></div>
    </div>
    <div class="sectionhead"><div><h2 id="heading">全部優惠</h2><p id="result">正在整理商品…</p></div><p>點商品前往 Costco 官網</p></div>
    <section class="grid" id="grid"></section>
    <footer>本網站整理 Costco 台灣官方公開線上優惠。價格、庫存與實體賣場活動可能隨時變動，購買前請以 Costco 官網或現場為準。本網站並非 Costco 官方網站。</footer>
  </main>
  <script>
    const deals=${embeddedDeals};
    const watch=["apple","iphone","macbook","ipad","ipod"];
    const categories=["全部","Apple 追蹤",...new Set(deals.map(d=>d.category))];
    let selected="全部";
    const search=document.querySelector("#search"),grid=document.querySelector("#grid"),chips=document.querySelector("#chips"),result=document.querySelector("#result"),heading=document.querySelector("#heading");
    const isWatched=d=>watch.some(k=>d.name.toLowerCase().includes(k));
    document.querySelector("#apple").textContent=deals.filter(isWatched).length;
    function renderChips(){chips.innerHTML=categories.map(c=>'<button class="chip '+(c===selected?'active':'')+'" data-category="'+c+'">'+c+'</button>').join("");chips.querySelectorAll("button").forEach(b=>b.onclick=()=>{selected=b.dataset.category;renderChips();render()})}
    function escapeHtml(v){return v.replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
    function render(){const q=search.value.trim().toLowerCase();const filtered=deals.filter(d=>(selected==="全部"||(selected==="Apple 追蹤"?isWatched(d):d.category===selected))&&(!q||d.name.toLowerCase().includes(q)));heading.textContent=selected;result.textContent='顯示 '+filtered.length+' 項商品';grid.innerHTML=filtered.length?filtered.map(d=>'<a class="card" href="'+d.url+'" target="_blank" rel="noopener"><div class="thumb">'+(d.image?'<img src="'+escapeHtml(d.image)+'" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="placeholder" hidden>Costco 優惠</span>':'<span class="placeholder">Costco 優惠</span>')+'</div><div class="top"><span class="badge">'+escapeHtml(d.category)+'</span>'+(isWatched(d)?'<span class="watch">★ 追蹤</span>':'')+'</div><h3>'+escapeHtml(d.name)+'</h3><div class="price">'+escapeHtml(d.price)+'</div><div class="go">查看官方商品 →</div></a>').join(""):'<div class="empty">沒有找到符合條件的優惠，試試其他關鍵字。</div>'}
    search.addEventListener("input",render);renderChips();render();
  </script>
</body>
</html>`;

fs.mkdirSync(pagesDir, { recursive: true });
fs.writeFileSync(path.join(pagesDir, "index.html"), html);
fs.writeFileSync(path.join(pagesDir, ".nojekyll"), "");
console.log(`Built GitHub Pages with ${deals.length} deals for ${updatedDate}`);
