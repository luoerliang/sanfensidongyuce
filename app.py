import os, re, csv, sqlite3, threading, math, time, hashlib
from collections import Counter, defaultdict
from flask import Flask, jsonify, render_template_string, request
import requests

DB = os.getenv("DB_PATH", "history.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", "10000"))
RENDER_SERVICE_NAME = os.getenv("RENDER_SERVICE_NAME", "").strip()
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
if not WEBHOOK_BASE_URL:
    WEBHOOK_BASE_URL = RENDER_EXTERNAL_URL
if not WEBHOOK_BASE_URL and RENDER_SERVICE_NAME:
    WEBHOOK_BASE_URL = f"https://{RENDER_SERVICE_NAME}.onrender.com"
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode("utf-8")).hexdigest()[:48] if BOT_TOKEN else ""
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

app = Flask(__name__)
db_lock = threading.Lock()
stats_cache = {"issue": None, "value": None}

RED_NUMS = {1,2,7,8,12,13,18,19,23,24,29,30,34,35,40,45,46}
BLUE_NUMS = {3,4,9,10,14,15,20,25,26,31,36,37,41,42,47,48}
GREEN_NUMS = {5,6,11,16,17,21,22,27,28,32,33,38,39,43,44,49}

INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#08101d">
<title>三分彩智能看板</title>
<style>
:root{
  --bg:#070b13; --panel:#101827; --line:#233149; --text:#f6f8fc; --muted:#8794aa;
  --accent:#6b8cff; --green:#35d491; --red:#ff566b; --blue:#4d8cff; --wavegreen:#34c77b;
}
*{box-sizing:border-box}
html,body{margin:0;background:radial-gradient(circle at 15% -10%,#1a2949 0,#0b1220 34%,#070b13 70%);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Helvetica Neue",sans-serif}
body{min-height:100vh}
.wrap{max-width:780px;margin:auto;padding:calc(env(safe-area-inset-top) + 14px) 14px 36px}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin:2px 2px 14px}
.livebox{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;padding:8px 11px;border-radius:999px;
background:#10231d;border:1px solid #1e5b45;color:#7ce4b4;white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;background:#2fdb91;box-shadow:0 0 0 5px #2fdb9120;animation:pulse 1.6s infinite}
@keyframes pulse{50%{box-shadow:0 0 0 8px #2fdb9106}}
.title{font-size:27px;font-weight:850;letter-spacing:-.7px;line-height:1.05}
.subtitle{color:var(--muted);font-size:12px;margin-top:6px}
.card{background:linear-gradient(180deg,#111a2a,#0d1522);border:1px solid #1f2b40;border-radius:22px;padding:17px;
box-shadow:0 16px 40px #0000002c;margin-bottom:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.metricLabel{font-size:11px;color:var(--muted)}
.metric{font-size:20px;font-weight:850;margin-top:7px;letter-spacing:.2px}
.sectionHead{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;margin-bottom:13px}
.sectionTitle{font-size:18px;font-weight:850}
.sectionHint{font-size:11px;color:var(--muted)}
.copyBtn{border:1px solid #38527f;background:linear-gradient(145deg,#223a66,#172a4b);color:#dbe8ff;
padding:7px 10px;border-radius:11px;font-size:11px;font-weight:800;cursor:pointer;-webkit-tap-highlight-color:transparent}
.copyBtn:active{transform:scale(.97)}
.toast{position:fixed;left:50%;bottom:calc(env(safe-area-inset-bottom) + 28px);transform:translateX(-50%);
background:#111a2a;border:1px solid #2c3a53;color:#fff;padding:10px 14px;border-radius:999px;font-size:12px;
box-shadow:0 12px 30px #0007;opacity:0;pointer-events:none;transition:.2s;z-index:99}
.toast.show{opacity:1}
.balls{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.ball,.smallball{display:flex;align-items:center;justify-content:center;font-weight:850;color:#fff}
.ball{aspect-ratio:1/1;border-radius:12px;font-size:14px;box-shadow:inset 0 1px 0 #ffffff20,0 4px 10px #00000018}
.smallball{width:31px;height:31px;border-radius:50%;font-size:12px}
.red{background:linear-gradient(145deg,#ff6b7b,#d93850)}
.blue{background:linear-gradient(145deg,#5a9cff,#3560d9)}
.green{background:linear-gradient(145deg,#48d997,#20a965)}
.special{outline:2px solid #fff;outline-offset:2px}
.latestRow{display:grid;grid-template-columns:repeat(7,1fr);gap:7px}
.combo{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.comboBox{background:#0c1421;border:1px solid #1e2a3f;border-radius:17px;padding:13px}
.comboTitle{font-size:13px;color:#aeb8c9;margin-bottom:10px;font-weight:750}
.code4{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}
.zodiac4{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}
.zodiac{padding:11px 6px;text-align:center;border-radius:13px;background:#172236;border:1px solid #263650;font-weight:850}
.zpairGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}
.zpair{background:#0c1421;border:1px solid #223149;border-radius:15px;padding:10px 6px;text-align:center;min-width:0}
.zpairName{font-size:17px;font-weight:900;margin-bottom:8px}
.zpairCodes{display:flex;gap:4px;justify-content:center;flex-wrap:wrap}
.microball{width:25px;height:25px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;font-weight:900}
.trendGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}
.trendBox{background:#0c1421;border:1px solid #1f2d43;border-radius:14px;padding:10px}
.trendTitle{font-size:10px;color:#8f9cb0;margin-bottom:6px}
.trendMain{font-size:13px;font-weight:850;line-height:1.55}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.stat{background:#0c1421;border:1px solid #1d2a40;border-radius:16px;padding:12px}
.statName{font-size:11px;color:#9ca8bb}.rate{font-size:22px;font-weight:900;margin-top:6px}.err{font-size:11px;color:#ff8492;margin-top:4px}
.historyCard{padding-bottom:10px}
.historyScroll{height:430px;overflow-y:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;padding-right:3px}
.historyItem{display:grid;grid-template-columns:112px 1fr;gap:10px;align-items:center;padding:11px 2px;border-bottom:1px solid #19253a}
.historyIssue{font-size:12px;font-weight:800;color:#c3ccda;word-break:break-all}
.historyNums{display:flex;gap:5px;flex-wrap:wrap}
.historyMeta{font-size:10px;color:#6f7d92;margin-top:4px}
.pillrow{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
.pill{font-size:11px;padding:7px 9px;border-radius:999px;background:#101a2a;border:1px solid #26364e;color:#aeb9c9}
.pill.ok{color:#7de7b6;border-color:#225d49;background:#0f251f}
.foot{font-size:10px;color:#657389;line-height:1.55;text-align:center;padding:4px 6px 0}
@media(max-width:520px){
  .title{font-size:25px}
  .balls{grid-template-columns:repeat(7,1fr)}
  .ball{border-radius:11px;font-size:13px}
  .stats{grid-template-columns:1fr 1fr 1fr}
  .rate{font-size:20px}
  .historyItem{grid-template-columns:104px 1fr}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div class="livebox"><span class="dot"></span><span>实时录入</span></div>
    <div style="text-align:right">
      <div class="title">三分彩 · 智能看板</div>
      <div class="subtitle">TG自动入库 · 动态模型 · 每10秒刷新</div>
    </div>
  </div>

  <div class="grid2">
    <section class="card">
      <div class="metricLabel">最新期号</div>
      <div id="issue" class="metric">--</div>
    </section>
    <section class="card">
      <div class="metricLabel">下一期</div>
      <div id="nextIssue" class="metric">--</div>
    </section>
  </div>

  <section class="card">
    <div class="sectionHead"><div class="sectionTitle">开奖结果</div><div class="sectionHint">最新一期 · 前6码 + 特码</div></div>
    <div id="latestNums" class="latestRow"></div>
    <div class="pillrow">
      <span id="latestZodiac" class="pill"></span>
      <span id="lastIngest" class="pill ok"></span>
      <span id="tg" class="pill ok"></span><span id="adaptiveInfo" class="pill"></span>
    </div>
  </section>

  <section class="card">
    <div class="sectionHead">
      <div>
        <div class="sectionTitle">22个动态特码</div>
        <div class="sectionHint">每期重算 · 升序</div>
      </div>
      <button class="copyBtn" onclick="copySpecial()">一键复制</button>
    </div>
    <div id="sp" class="balls"></div>
    <div class="pillrow" style="margin-top:10px">
      <span class="pill">短期10/20/50期</span>
      <span class="pill">趋势加速度</span>
      <span class="pill">临界位动态换码</span>
      <span class="pill">不随机硬换</span>
    </div>
  </section>

  <section class="card">
    <div class="sectionHead">
      <div class="sectionTitle">4肖 · 对应候选码</div>
      <div class="sectionHint">每肖1–3码 · 近期出现率优先</div>
    </div>
    <div id="zpair" class="zpairGrid"></div>
  </section>

  <section class="card">
    <div class="sectionHead">
      <div class="sectionTitle">走势指数</div>
      <div class="sectionHint">波色 / 大小 / 单双</div>
    </div>
    <div class="trendGrid">
      <div class="trendBox"><div class="trendTitle">波色走势</div><div id="waveTrend" class="trendMain">--</div></div>
      <div class="trendBox"><div class="trendTitle">大小指数</div><div id="sizeTrend" class="trendMain">--</div></div>
      <div class="trendBox"><div class="trendTitle">单双走势</div><div id="parityTrend" class="trendMain">--</div></div>
    </div>
  </section>

  <section class="card">
    <div class="sectionHead"><div class="sectionTitle">近60期滚动回测</div><div class="sectionHint">命中 / 错误</div></div>
    <div class="stats">
      <div class="stat"><div class="statName">22码</div><div id="hit22" class="rate">--</div><div id="err22" class="err"></div></div>
      <div class="stat"><div class="statName">4主码</div><div id="hit4" class="rate">--</div><div id="err4" class="err"></div></div>
      <div class="stat"><div class="statName">4肖</div><div id="hitZ" class="rate">--</div><div id="errZ" class="err"></div></div>
    </div>
  </section>

  <section class="card historyCard">
    <div class="sectionHead">
      <div class="sectionTitle">历史开奖</div>
      <div id="historyCount" class="sectionHint">--</div>
    </div>
    <div id="historyScroll" class="historyScroll"></div>
  </section>

  <div id="toast" class="toast">已复制</div>
  <div class="foot">号码颜色按红 / 蓝 / 绿波显示。新版把波色、生肖、大小、单双作为近期统计特征参与动态评分；命中率是历史滚动回测，不代表未来中奖概率。</div>
</div>

<script>
const RED=new Set([1,2,7,8,12,13,18,19,23,24,29,30,34,35,40,45,46]);
const BLUE=new Set([3,4,9,10,14,15,20,25,26,31,36,37,41,42,47,48]);
function cls(n){n=Number(n);return RED.has(n)?'red':(BLUE.has(n)?'blue':'green')}
let SPECIAL22=[];
function fmt(n){return String(n).padStart(2,'0')}
async function copySpecial(){
  const text=SPECIAL22.join(' ');
  try{
    await navigator.clipboard.writeText(text);
  }catch(e){
    const ta=document.createElement('textarea');
    ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();
  }
  const t=document.getElementById('toast');
  t.textContent='已复制：'+text;
  t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),1800);
}
function balls(nums,small=false){
  return (nums||[]).map((n,i)=>`<span class="${small?'smallball':'ball'} ${cls(n)} ${small&&i===6?'special':''}">${fmt(n)}</span>`).join('')
}
async function loadMain(){
  try{
    const r=await fetch('/api/prediction?_='+Date.now(),{cache:'no-store'});
    const d=await r.json();
    issue.textContent=d.issue||'暂无';
    nextIssue.textContent=d.next_issue||'--';
    latestNums.innerHTML=balls(d.latest_numbers||[]);
    if(latestNums.lastElementChild) latestNums.lastElementChild.classList.add('special');
    SPECIAL22=d.special22||[]; sp.innerHTML=balls(SPECIAL22);
    const pairs=d.zodiac_pairs||[];
    zpair.innerHTML=pairs.map(p=>`<div class="zpair">
      <div class="zpairName">${p.zodiac}</div>
      <div class="zpairCodes">${(p.codes||[]).map(n=>`<span class="microball ${cls(n)}">${n}</span>`).join('')}</div>
    </div>`).join('');
    const tr=d.trend||{};
    const w=tr.wave||{}, sz=tr.size||{}, pa=tr.parity||{};
    waveTrend.innerHTML=`红 ${w['红']??0}%<br>蓝 ${w['蓝']??0}%<br>绿 ${w['绿']??0}%`;
    sizeTrend.innerHTML=`大 ${sz['大']??0}%<br>小 ${sz['小']??0}%`;
    parityTrend.innerHTML=`单 ${pa['单']??0}%<br>双 ${pa['双']??0}%`;
    latestZodiac.textContent=d.latest_special_zodiac?`特码生肖 ${d.latest_special_zodiac}`:'特码生肖 --';
    lastIngest.textContent=d.latest_created_at?`最后录入 ${d.latest_created_at}`:'实时录入';
    tg.textContent=d.telegram?'Telegram 已连接':'Telegram 未配置';
    const ad=d.adaptive||{};
    adaptiveInfo.textContent=`22码变化 ${ad.changes??0} · 4肖变化 ${ad.zodiac_changes??0} · 敏感度 ${ad.target??0}`;

  }catch(e){}
}
async function loadStats(){
  try{
    const r=await fetch('/api/stats?_='+Date.now(),{cache:'no-store'});
    const st=await r.json();
    hit22.textContent=(st.hit22??0).toFixed(1)+'%'; err22.textContent='错误 '+(st.err22??0).toFixed(1)+'%';
    hit4.textContent=(st.hit4??0).toFixed(1)+'%'; err4.textContent='错误 '+(st.err4??0).toFixed(1)+'%';
    hitZ.textContent=(st.hitZ??0).toFixed(1)+'%'; errZ.textContent='错误 '+(st.errZ??0).toFixed(1)+'%';
  }catch(e){}
}
async function loadHistory(){
  try{
    const r=await fetch('/api/history?limit=200&_='+Date.now(),{cache:'no-store'});
    const d=await r.json();
    historyCount.textContent=`共 ${Number(d.total||0).toLocaleString()} 期 · 显示最近 ${d.items.length} 期`;
    historyScroll.innerHTML=d.items.map(x=>`
      <div class="historyItem">
        <div><div class="historyIssue">${x.issue}</div><div class="historyMeta">${x.zodiac||''}</div></div>
        <div class="historyNums">${balls(x.numbers,true)}</div>
      </div>`).join('');
  }catch(e){}
}
loadMain(); loadStats(); loadHistory();
setInterval(loadMain,2000);
setInterval(loadStats,30000);
setInterval(loadHistory,20000);
</script>
</body>
</html>"""

def ensure_db_dir():
    parent = os.path.dirname(os.path.abspath(DB))
    os.makedirs(parent, exist_ok=True)

def connect():
    ensure_db_dir()
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db_lock:
        c=connect()
        c.execute("""CREATE TABLE IF NOT EXISTS draws(
          issue TEXT PRIMARY KEY,
          n1 INTEGER,n2 INTEGER,n3 INTEGER,n4 INTEGER,n5 INTEGER,n6 INTEGER,special INTEGER,
          z1 TEXT,z2 TEXT,z3 TEXT,z4 TEXT,z5 TEXT,z6 TEXT,z7 TEXT,
          c1 TEXT,c2 TEXT,c3 TEXT,c4 TEXT,c5 TEXT,c6 TEXT,c7 TEXT,
          raw TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.commit(); c.close()

def normalize_z(z):
    return {"馬":"马","龍":"龙","雞":"鸡","豬":"猪"}.get(z,z)

def import_history_once():
    if not os.path.exists("history.csv"): return
    with db_lock:
        c=connect()
        existing=c.execute("SELECT COUNT(*) FROM draws").fetchone()[0]
        if existing:
            c.close(); return
        with open("history.csv","r",encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f):
                issue=(r.get("期号") or "").strip()
                try:
                    nums=[int(r[k]) for k in ["正码1","正码2","正码3","正码4","正码5","正码6","特码"]]
                except Exception:
                    continue
                if not issue or not all(1<=n<=49 for n in nums): continue
                zs=[normalize_z((r.get(k) or "").strip()) for k in
                    ["正码1生肖","正码2生肖","正码3生肖","正码4生肖","正码5生肖","正码6生肖"]]
                zs.append(normalize_z((r.get("生肖") or "").strip()))
                c.execute("""INSERT OR IGNORE INTO draws
                (issue,n1,n2,n3,n4,n5,n6,special,z1,z2,z3,z4,z5,z6,z7,raw)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",[issue,*nums,*zs,"history.csv"])
        c.commit(); c.close()

def parse_draw(text):
    m=re.search(r"第\s*[:：]?\s*(\d{8,})\s*期",text)
    if not m:return None
    issue=m.group(1)
    nums=None
    for line in [x.strip() for x in text.splitlines() if x.strip()]:
        vals=re.findall(r"(?<!\d)(?:0?[1-9]|[1-4]\d)(?!\d)",line)
        if len(vals)==7:
            cand=[int(x) for x in vals]
            if len(set(cand))==7 and all(1<=n<=49 for n in cand):
                nums=cand; break
    if not nums:return None
    zs=re.findall(r"[鼠牛虎兔龙龍蛇马馬羊猴鸡雞狗猪豬]",text)
    zs=[normalize_z(x) for x in zs[-7:]] if len(zs)>=7 else [""]*7
    colors=re.findall(r"[🔴🟢🔵]",text)
    colors=colors[-7:] if len(colors)>=7 else [""]*7
    return issue,nums,zs,colors

def add_draw(issue,nums,zs,colors,raw):
    if len(nums)!=7 or len(set(nums))!=7 or not all(1<=x<=49 for x in nums): return False
    with db_lock:
        c=connect()
        before=c.total_changes
        c.execute("""INSERT OR IGNORE INTO draws
        (issue,n1,n2,n3,n4,n5,n6,special,z1,z2,z3,z4,z5,z6,z7,c1,c2,c3,c4,c5,c6,c7,raw)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [issue,*nums,*zs,*colors,raw[:4000]])
        c.commit()
        changed=c.total_changes>before
        c.close()
        if changed:
            stats_cache["issue"]=None
            stats_cache["value"]=None
        return changed

def all_rows():
    c=connect()
    r=c.execute("SELECT * FROM draws ORDER BY CAST(issue AS INTEGER) DESC").fetchall()
    c.close()
    return r

def exp_weight(i,half_life):
    return 0.5 ** (i/max(half_life,1))

def wave_of(n):
    if n in RED_NUMS: return "红"
    if n in BLUE_NUMS: return "蓝"
    return "绿"

def size_of(n):
    return "大" if n >= 25 else "小"

def parity_of(n):
    return "单" if n % 2 else "双"

def _weighted_category(seq, mapper, horizon, half):
    out=defaultdict(float)
    total=0.0
    for i,n in enumerate(seq[:min(horizon,len(seq))]):
        w=exp_weight(i,half)
        out[mapper(n)] += w
        total += w
    if total <= 0:
        return {}
    return {k:v/total for k,v in out.items()}

def _trend_profiles(r):
    """Observed recent distributions. Used as statistical features only."""
    sp=[x["special"] for x in r if x["special"]]
    # Multi-window weighted average, heavily tilted to recent issues.
    wave=defaultdict(float); size=defaultdict(float); parity=defaultdict(float)
    cfg=[(8,3,1.55),(16,5,1.25),(36,11,.95),(80,25,.60)]
    totalcoef=sum(c for _,_,c in cfg)
    for h,half,c in cfg:
        for k,v in _weighted_category(sp,wave_of,h,half).items(): wave[k]+=c*v
        for k,v in _weighted_category(sp,size_of,h,half).items(): size[k]+=c*v
        for k,v in _weighted_category(sp,parity_of,h,half).items(): parity[k]+=c*v
    for d in (wave,size,parity):
        for k in list(d): d[k]/=totalcoef

    # Acceleration: latest 8 versus preceding 24.
    def accel(mapper, keys):
        a=Counter(mapper(x["special"]) for x in r[:8])
        b=Counter(mapper(x["special"]) for x in r[8:32])
        av={k:a[k]/max(1,min(8,len(r))) for k in keys}
        bv={k:b[k]/max(1,min(24,max(0,len(r)-8))) for k in keys}
        return {k:av[k]-bv[k] for k in keys}
    wa=accel(wave_of,["红","蓝","绿"])
    sa=accel(size_of,["大","小"])
    pa=accel(parity_of,["单","双"])

    # Blend acceleration into a preference score, then convert to display percentages.
    def blend(base, ac, keys):
        raw={k:max(0.001,base.get(k,0)+0.42*ac.get(k,0)) for k in keys}
        z=sum(raw.values())
        return {k:raw[k]/z for k in keys}
    return {
      "wave":blend(wave,wa,["红","蓝","绿"]),
      "size":blend(size,sa,["大","小"]),
      "parity":blend(parity,pa,["单","双"])
    }

def _number_zodiac_map(r):
    counts={n:Counter() for n in range(1,50)}
    for x in r[:min(260,len(r))]:
        for j in range(1,7):
            n=x[f"n{j}"]; z=normalize_z(x[f"z{j}"] or "")
            if n and z: counts[n][z]+=1
        n=x["special"]; z=normalize_z(x["z7"] or "")
        if n and z: counts[n][z]+=2
    out={}
    for n,c in counts.items():
        if c: out[n]=c.most_common(1)[0][0]
    return out

def _zodiac_scores(r):
    score=defaultdict(float)
    # Short windows make 4肖 move more readily.
    for horizon,half,coef in [(6,2,2.25),(12,4,1.85),(24,8,1.35),(50,16,.90),(120,38,.45)]:
        for i,x in enumerate(r[:min(horizon,len(r))]):
            w=coef*exp_weight(i,half)
            if x["z7"]:
                score[normalize_z(x["z7"])]+=1.75*w
            for k in ["z1","z2","z3","z4","z5","z6"]:
                if x[k]:
                    score[normalize_z(x[k])]+=0.28*w

    # Zodiac acceleration: last 8 specials versus previous 24.
    a=Counter(normalize_z(x["z7"] or "") for x in r[:8] if x["z7"])
    b=Counter(normalize_z(x["z7"] or "") for x in r[8:32] if x["z7"])
    allz=set(score)|set(a)|set(b)
    for z in allz:
        score[z]+=2.0*(a[z]/max(1,min(8,len(r))) - b[z]/max(1,min(24,max(0,len(r)-8))))
    return score

def _adaptive_zodiac4(r):
    cur=_zodiac_scores(r)
    ranked=sorted(cur,key=lambda z:(-cur[z],z))
    top=ranked[:4]
    if len(r)<40 or len(ranked)<5:
        return top, {"changes":0}

    prev=_zodiac_scores(r[1:])
    prev_top=sorted(prev,key=lambda z:(-prev[z],z))[:4]
    prev_set=set(prev_top)
    cur_set=set(top)

    # If unchanged, allow one deterministic trend-driven rotation when an outsider
    # is close to the weakest incumbent and has stronger momentum.
    if cur_set==prev_set:
        momentum={z:cur.get(z,0)-prev.get(z,0) for z in set(cur)|set(prev)}
        weakest=min(top,key=lambda z:cur.get(z,0))
        outsiders=[z for z in ranked if z not in cur_set]
        if outsiders:
            challenger=max(outsiders,key=lambda z:(momentum.get(z,0),cur.get(z,0)))
            scale=max(abs(cur.get(top[0],0)-cur.get(weakest,0)),1.0)
            close=(cur.get(challenger,0) >= cur.get(weakest,0)-0.16*scale)
            rising=(momentum.get(challenger,0) > momentum.get(weakest,0))
            if close and rising:
                top=[z for z in top if z!=weakest]+[challenger]
                top=sorted(top,key=lambda z:(-cur.get(z,0),z))
    changes=len(set(top)^prev_set)//2
    return top, {"changes":changes}

def _recent_volatility(r):
    if len(r)<40:return .5
    a=Counter(x["special"] for x in r[:16])
    b=Counter(x["special"] for x in r[16:32])
    return max(0.0,min(sum(abs(a[n]-b[n]) for n in range(1,50))/32.0,1.0))

def _base_special_scores(r):
    numbers=range(1,50)
    score={n:0.0 for n in numbers}
    profiles=_trend_profiles(r)
    zmap=_number_zodiac_map(r)
    zscore=_zodiac_scores(r)

    # Number-frequency and acceleration.
    for horizon,half,coef in [(8,3,2.35),(16,5,1.95),(36,11,1.45),(80,25,1.02),(200,65,.58),(800,250,.24)]:
        rr=r[:min(horizon,len(r))]
        freq=Counter()
        for i,x in enumerate(rr):
            freq[x["special"]]+=exp_weight(i,half)
        mean=sum(freq.values())/49.0 if rr else 0
        for n in numbers:
            score[n]+=coef*(freq[n]-mean)/math.sqrt(mean+1.0)

    # Direct acceleration.
    for short,base,coef in [(8,24,1.45),(16,48,.95)]:
        a=Counter(x["special"] for x in r[:short])
        b=Counter(x["special"] for x in r[short:short+base])
        for n in numbers:
            score[n]+=coef*(a[n]/max(short,1)-b[n]/max(base,1))

    # Trend-index features: wave + big/small + odd/even.
    for n in numbers:
        score[n]+=1.05*(profiles["wave"].get(wave_of(n),0)-1/3)
        score[n]+=0.78*(profiles["size"].get(size_of(n),0)-1/2)
        score[n]+=0.72*(profiles["parity"].get(parity_of(n),0)-1/2)
        z=zmap.get(n)
        if z:
            # Normalize zodiac context to avoid overpowering direct number evidence.
            score[n]+=0.010*zscore.get(z,0)

    # Weak long baseline + omission.
    full=Counter(x["special"] for x in r)
    expected=len(r)/49.0
    for n in numbers:
        score[n]+=0.14*(full[n]-expected)/math.sqrt(expected+7.0)
    last={n:len(r) for n in numbers}
    for i,x in enumerate(r):
        if last[x["special"]]==len(r): last[x["special"]]=i
    for n in numbers:
        score[n]+=0.10*min(last[n],50)/50.0
    return score

def _adaptive_top22(r):
    numbers=list(range(1,50))
    cur=_base_special_scores(r)
    ranked=sorted(numbers,key=lambda n:(-cur[n],n))
    if len(r)<50:
        return ranked[:22],{"changes":0,"target":0,"volatility":0.0}
    prev=_base_special_scores(r[1:])
    prev_set=set(sorted(numbers,key=lambda n:(-prev[n],n))[:22])
    delta={n:cur[n]-prev[n] for n in numbers}
    vol=_recent_volatility(r)
    target=max(2,min(int(round(3+vol*5)),8))
    cutoff=cur[ranked[21]]
    spread=max(abs(cur[ranked[8]]-cutoff),.18)
    adjusted={}
    for n in numbers:
        boundary=1.0-max(0.0,min(abs(cur[n]-cutoff)/spread,1.0))
        mom=delta[n]
        adjusted[n]=cur[n]+mom*(1.45+2.0*vol)*boundary
        if n in prev_set and mom<0: adjusted[n]+=mom*(.55+vol)
        if n not in prev_set and mom>0: adjusted[n]+=mom*(.90+1.35*vol)
    top=sorted(numbers,key=lambda n:(-adjusted[n],n))[:22]
    changes=len(set(top)^prev_set)//2
    return top,{"changes":changes,"target":target,"volatility":round(vol,3)}

def _zodiac_code_pairs(r, zodiac4):
    """For each selected zodiac return 1-3 highest-scoring mapped numbers."""
    zmap=_number_zodiac_map(r)
    nscores=_base_special_scores(r)
    profiles=_trend_profiles(r)

    # Add recent all-position occurrence rate for code selection.
    occ=Counter()
    for i,x in enumerate(r[:80]):
        w=exp_weight(i,18)
        occ[x["special"]]+=1.7*w
        for j in range(1,7): occ[x[f"n{j}"]]+=.55*w

    pairs=[]
    primaries=[]
    for z in zodiac4:
        pool=[n for n in range(1,50) if zmap.get(n)==z]
        if not pool:
            pool=list(range(1,50))
        sc={}
        for n in pool:
            sc[n]=nscores[n]+0.12*occ[n]
            sc[n]+=0.30*profiles["wave"].get(wave_of(n),0)
            sc[n]+=0.18*profiles["size"].get(size_of(n),0)
            sc[n]+=0.16*profiles["parity"].get(parity_of(n),0)
        ranked=sorted(pool,key=lambda n:(-sc[n],n))
        if not ranked:
            codes=[]
        elif len(ranked)==1:
            codes=ranked[:1]
        else:
            # Dynamic 1-3 count based on score concentration.
            top=sc[ranked[0]]
            second=sc[ranked[1]]
            third=sc[ranked[2]] if len(ranked)>2 else -1e9
            denom=max(abs(top),.5)
            if (top-second)/denom > .28:
                k=1
            elif len(ranked)>2 and (second-third)/denom < .10:
                k=3
            else:
                k=2
            codes=ranked[:k]
        if codes: primaries.append(codes[0])
        pairs.append({"zodiac":z,"codes":codes})
    return pairs,primaries

def predict_core(r):
    if not r:return [],[],[]
    top22,_=_adaptive_top22(r)
    zodiac4,_=_adaptive_zodiac4(r)
    pairs,primaries=_zodiac_code_pairs(r,zodiac4)
    # codes4 are the primary code under each zodiac, so they always correspond.
    return top22,primaries,zodiac4

def backtest_stats(r, sample=60):
    if not r or len(r)<350:
        return {"n":0,"hit22":0.0,"err22":100.0,"hit4":0.0,"err4":100.0,"hitZ":0.0,"errZ":100.0}
    latest_issue=r[0]["issue"]
    if stats_cache["issue"]==latest_issue and stats_cache["value"] is not None:
        return stats_cache["value"]

    tests=min(sample, len(r)-300)
    h22=h4=hz=0
    actual_tests=0
    # r is newest -> oldest. Predict target r[k] using only older rows r[k+1:].
    for k in range(tests-1,-1,-1):
        train=r[k+1:]
        if len(train)<300: continue
        p22,p4,pz=predict_core(train)
        actual=r[k]
        actual_special=actual["special"]
        actual_z=normalize_z(actual["z7"] or "")
        h22 += int(actual_special in p22)
        h4 += int(actual_special in p4)
        hz += int(bool(actual_z) and actual_z in pz)
        actual_tests += 1

    n=max(actual_tests,1)
    val={
      "n":actual_tests,
      "hit22":round(h22/n*100,1),"err22":round((actual_tests-h22)/n*100,1),
      "hit4":round(h4/n*100,1),"err4":round((actual_tests-h4)/n*100,1),
      "hitZ":round(hz/n*100,1),"errZ":round((actual_tests-hz)/n*100,1)
    }
    stats_cache["issue"]=latest_issue
    stats_cache["value"]=val
    return val

def model():
    r=all_rows()
    if not r:
        return {"issue":None,"count":0,"special22":[],"codes4":[],"zodiac4":[],"zodiac_pairs":[],"telegram":bool(BOT_TOKEN)}
    top22,codes,zodiac=predict_core(r)
    _tmp22,adaptive_meta=_adaptive_top22(r)
    _ztop,zmeta=_adaptive_zodiac4(r)
    zpairs,_primary=_zodiac_code_pairs(r,zodiac)
    trend=_trend_profiles(r)
    latest=r[0]
    latest_numbers=[latest[f"n{i}"] for i in range(1,7)]+[latest["special"]]
    try: next_issue=str(int(latest["issue"])+1)
    except Exception: next_issue=""
    return {
      "issue":latest["issue"],"next_issue":next_issue,"count":len(r),
      "latest_numbers":latest_numbers,
      "latest_special_zodiac":normalize_z(latest["z7"] or ""),
      "latest_created_at":latest["created_at"] or "",
      "special22":[f"{n:02d}" for n in sorted(top22)],
      "codes4":[f"{n:02d}" for n in codes],
      "zodiac4":zodiac,
      "zodiac_pairs":[{"zodiac":p["zodiac"],"codes":[f"{n:02d}" for n in p["codes"]]} for p in zpairs],
      "adaptive":{**adaptive_meta,"zodiac_changes":zmeta.get("changes",0)},
      "trend":{
        "wave":{k:round(v*100,1) for k,v in trend["wave"].items()},
        "size":{k:round(v*100,1) for k,v in trend["size"].items()},
        "parity":{k:round(v*100,1) for k,v in trend["parity"].items()}
      },
      "telegram":bool(BOT_TOKEN)
    }

@app.get("/")
def home():
    return render_template_string(INDEX_HTML)

@app.get("/api/health")
def health():
    return jsonify({"ok":True,"db":DB,"telegram":bool(BOT_TOKEN),"telegram_mode":"webhook","webhook_base":WEBHOOK_BASE_URL,"count":len(all_rows())})

@app.get("/api/prediction")
def prediction():
    # Lightweight live endpoint: does not run the historical backtest.
    return jsonify(model())

@app.get("/api/stats")
def stats_api():
    return jsonify(backtest_stats(all_rows(),60))

@app.get("/api/history")
def history():
    try: limit=max(20,min(int(request.args.get("limit","200")),500))
    except Exception: limit=200
    c=connect()
    total=c.execute("SELECT COUNT(*) FROM draws").fetchone()[0]
    rr=c.execute("""SELECT issue,n1,n2,n3,n4,n5,n6,special,z7,created_at
                    FROM draws ORDER BY CAST(issue AS INTEGER) DESC LIMIT ?""",(limit,)).fetchall()
    c.close()
    items=[]
    for x in rr:
        items.append({
          "issue":x["issue"],
          "numbers":[x[f"n{i}"] for i in range(1,7)]+[x["special"]],
          "zodiac":normalize_z(x["z7"] or ""),
          "created_at":x["created_at"] or ""
        })
    return jsonify({"total":total,"items":items})

def tg_send(chat_id, text, reply_to_message_id=None):
    if not BOT_TOKEN:
        return False
    payload={"chat_id":chat_id,"text":text}
    if reply_to_message_id:
        payload["reply_to_message_id"]=reply_to_message_id
    try:
        r=requests.post(f"{TG_API}/sendMessage",json=payload,timeout=12)
        if not r.ok:
            print(f"[TG] sendMessage failed {r.status_code}: {r.text[:300]}",flush=True)
        return r.ok
    except Exception as e:
        print(f"[TG] sendMessage exception: {type(e).__name__}: {e}",flush=True)
        return False

def set_telegram_webhook():
    if not BOT_TOKEN:
        print("[TG] BOT_TOKEN not configured; webhook disabled",flush=True)
        return False
    if not WEBHOOK_BASE_URL:
        print("[TG] no public webhook URL detected; set WEBHOOK_BASE_URL manually",flush=True)
        return False
    url=f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
    payload={
        "url":url,
        "secret_token":WEBHOOK_SECRET,
        "allowed_updates":["message"],
        "drop_pending_updates":False,
        "max_connections":20
    }
    try:
        r=requests.post(f"{TG_API}/setWebhook",json=payload,timeout=15)
        print(f"[TG] setWebhook url={url} -> {r.status_code} {r.text[:400]}",flush=True)
        return r.ok
    except Exception as e:
        print(f"[TG] setWebhook exception: {type(e).__name__}: {e}",flush=True)
        return False

def webhook_keeper():
    # Re-assert webhook during deploy overlap, then every 10 minutes.
    for delay in (0,8,20,40):
        if delay:
            time.sleep(delay)
        set_telegram_webhook()
    while True:
        time.sleep(600)
        set_telegram_webhook()

def process_telegram_message(msg):
    text=msg.get("text") or ""
    chat=msg.get("chat") or {}
    sender=msg.get("from") or {}
    chat_id=chat.get("id")
    message_id=msg.get("message_id")
    sender_name=sender.get("username") or " ".join(
        x for x in [sender.get("first_name"),sender.get("last_name")] if x
    ) or "unknown"
    sender_is_bot=bool(sender.get("is_bot"))
    print(f"[TG-WEBHOOK] chat={chat_id} sender={sender_name} is_bot={sender_is_bot} text={text[:160]!r}",flush=True)

    # Commands remain available for setup/testing.
    cmd=(text.strip().split()[0].split("@")[0].lower() if text.strip().startswith("/") else "")
    if cmd=="/id":
        tg_send(chat_id,f"Chat ID: {chat_id}",message_id)
        return
    if cmd=="/status":
        m=model()
        tg_send(chat_id,f"运行正常\\n历史期数: {m['count']}\\n最新期号: {m['issue']}",message_id)
        return

    if ALLOWED_CHAT_ID and str(chat_id)!=ALLOWED_CHAT_ID:
        print(f"[TG-WEBHOOK] ignored: chat id does not match ALLOWED_CHAT_ID={ALLOWED_CHAT_ID}",flush=True)
        return

    p=parse_draw(text)
    if not p:
        print("[TG-WEBHOOK] message received but parser did not recognize a complete draw",flush=True)
        return

    issue,nums,zs,colors=p
    print(f"[TG-WEBHOOK] parsed issue={issue} nums={nums} zodiac={zs} colors={colors}",flush=True)
    if add_draw(issue,nums,zs,colors,text):
        print(f"[TG-WEBHOOK] inserted issue={issue}",flush=True)
        # Official bot messages are never auto-replied to, avoiding bot loops/flood control.
        if not sender_is_bot:
            tg_send(chat_id,f"已入库 {issue}，统计结果已更新。",message_id)
    else:
        print(f"[TG-WEBHOOK] duplicate/invalid issue={issue}, not inserted",flush=True)

@app.post(WEBHOOK_PATH)
def telegram_webhook():
    if WEBHOOK_SECRET:
        got=request.headers.get("X-Telegram-Bot-Api-Secret-Token","")
        if got!=WEBHOOK_SECRET:
            return jsonify({"ok":False,"error":"bad secret"}),403
    data=request.get_json(silent=True) or {}
    msg=data.get("message")
    if msg:
        process_telegram_message(msg)
    return jsonify({"ok":True})

@app.get("/api/webhook")
def webhook_status():
    if not BOT_TOKEN:
        return jsonify({"ok":False,"configured":False})
    try:
        r=requests.get(f"{TG_API}/getWebhookInfo",timeout=10)
        payload=r.json()
        payload["_detected_base_url"]=WEBHOOK_BASE_URL
        return jsonify(payload)
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500

def boot():
    init_db()
    import_history_once()
    if BOT_TOKEN:
        threading.Thread(target=webhook_keeper,daemon=True,name="telegram-webhook-keeper").start()

boot()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=PORT)
