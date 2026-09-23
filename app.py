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

# 你当前线上服务的历史接口。v13 首次部署到“新服务”时会自动同步进去。
DEFAULT_HISTORY_SOURCE = "https://sanfensidongyuce-2.onrender.com/api/history?limit=500"
HISTORY_SOURCE_URL = os.getenv("HISTORY_SOURCE_URL", DEFAULT_HISTORY_SOURCE).strip()

live_cache = {"issue": None, "data": None, "building": False}
model_state = {
    "profile": None,
    "profile_scores": {},
    "last_calibrated_issue": None,
    "recalc_started_at": "",
    "recalc_finished_at": ""
}
background_state = {
    "profile_calibrating": False,
    "stats_building": False,
    "boot_ready": False
}

long_prior_lock = threading.RLock()
long_prior = {
    "ready": False,
    "building": False,
    "total": 0,
    "num_count": Counter(),
    "zodiac_count": Counter(),
    "trans_num_by_zodiac": defaultdict(Counter),
    "trans_zodiac_by_zodiac": defaultdict(Counter),
    "updated_at": ""
}


history_cache = {"total": 0, "items": [], "loaded_at": ""}
history_cache_lock = threading.RLock()

live_cache_lock = threading.Lock()
sync_state = {"source": HISTORY_SOURCE_URL, "imported": 0, "last_error": "", "last_sync": ""}

app = Flask(__name__)
db_lock = threading.RLock()
stats_cache = {"issue": None, "value": None}

RED_NUMS = {1,2,7,8,12,13,18,19,23,24,29,30,34,35,40,45,46}
BLUE_NUMS = {3,4,9,10,14,15,20,25,26,31,36,37,41,42,47,48}
GREEN_NUMS = {5,6,11,16,17,21,22,27,28,32,33,38,39,43,44,49}
ALL_ZODIACS = ["鼠","牛","虎","兔","龙","蛇","马","羊","猴","鸡","狗","猪"]

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
.strategyGrid{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}
.strategyBox{background:#0c1421;border:1px solid #1f2d43;border-radius:14px;padding:10px}
.strategyTitle{font-size:10px;color:#8f9cb0;margin-bottom:6px}
.strategyMain{font-size:13px;font-weight:850;line-height:1.55}
.trendBox{background:#0c1421;border:1px solid #1f2d43;border-radius:14px;padding:10px}
.trendTitle{font-size:10px;color:#8f9cb0;margin-bottom:6px}
.trendMain{font-size:13px;font-weight:850;line-height:1.55}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
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
      <div class="subtitle">TG自动入库 · 开奖秒显 · 极速窗口预测</div>
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
      <span id="tg" class="pill ok"></span><span id="adaptiveInfo" class="pill"></span><span id="calcState" class="pill"></span>
    </div>
  </section>

  <section class="card">
    <div class="sectionHead">
      <div class="sectionTitle">下一期预测状态</div>
      <div class="sectionHint">不是把刚开奖号追进去</div>
    </div>
    <div class="strategyGrid">
      <div class="strategyBox"><div class="strategyTitle">预测目标</div><div id="forecastTarget" class="strategyMain">--</div></div>
      <div class="strategyBox"><div class="strategyTitle">前瞻模型</div><div id="forecastMode" class="strategyMain">--</div></div>
    </div>
  </section>

  <section class="card">
    <div class="sectionHead">
      <div>
        <div class="sectionTitle">24个动态特码</div>
        <div class="sectionHint">12肖×2码 · 每期重算 · 升序</div>
      </div>
      <button class="copyBtn" onclick="copySpecial()">一键复制</button>
    </div>
    <div id="sp" class="balls"></div>
    <div class="pillrow" style="margin-top:10px">
      <span class="pill">12肖分层覆盖</span>
      <span class="pill">趋势加速度</span>
      <span class="pill">每肖1–3码</span>
      <span class="pill">自动校准模型</span>
    </div>
  </section>

  <section class="card">
    <div class="sectionHead">
      <div class="sectionTitle">4肖 · 一肖一码</div>
      <div class="sectionHint">每期重算 · 4肖与4码严格一一对应</div>
    </div>
    <div id="zpair" class="zpairGrid"></div>
  </section>

  <section class="card">
    <div class="sectionHead">
      <div class="sectionTitle">平特一肖</div>
      <div class="sectionHint">预测下一期7个号码中至少出现1次的生肖</div>
    </div>
    <div class="comboBox" style="text-align:center">
      <div id="pingteOne" style="font-size:36px;font-weight:900;letter-spacing:2px">--</div>
      <div id="pingteSamples" class="sectionHint" style="margin-top:8px">--</div>
    </div>
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
    <div class="pillrow"><span id="profileInfo" class="pill"></span></div>
  </section>

  <section class="card">
    <div class="sectionHead">
      <div class="sectionTitle">冷热 · 头数策略</div>
      <div class="sectionHint">历史条件成立才启用</div>
    </div>
    <div class="strategyGrid">
      <div class="strategyBox">
        <div class="strategyTitle">冷码防守</div>
        <div id="coldSignal" class="strategyMain">--</div>
      </div>
      <div class="strategyBox">
        <div class="strategyTitle">冷肖观察</div>
        <div id="coldZodiac" class="strategyMain">--</div>
      </div>
      <div class="strategyBox">
        <div class="strategyTitle">0头 / 4头</div>
        <div id="headSignal" class="strategyMain">--</div>
      </div>
      <div class="strategyBox">
        <div class="strategyTitle">牛马羊条件验证</div>
        <div id="nmySignal" class="strategyMain">--</div>
      </div>
    </div>
  </section>

  <section class="card">
    <div class="sectionHead"><div class="sectionTitle">滚动回测（后台更新）</div><div class="sectionHint">命中 / 错误</div></div>
    <div class="stats">
      <div class="stat"><div class="statName">24码</div><div id="hit22" class="rate">--</div><div id="err22" class="err"></div></div>
      <div class="stat"><div class="statName">4肖1码</div><div id="hit4" class="rate">--</div><div id="err4" class="err"></div></div>
      <div class="stat"><div class="statName">4肖</div><div id="hitZ" class="rate">--</div><div id="errZ" class="err"></div></div>
      <div class="stat"><div class="statName">平特一肖</div><div id="hitPingte" class="rate">--</div><div id="errPingte" class="err"></div></div>
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
  <div class="foot">号码颜色按红 / 蓝 / 绿波显示。新版把波色、生肖、大小、单双作为近期统计特征参与动态评分；特码使用集成前瞻模型：状态转移、遗漏风险、尾数转移、波色/大小/单双/头数共同评分；平特一肖预测的是下一期7个号码里至少出现一次的生肖。所有命中率均为历史滚动验证，不代表未来概率。</div>
</div>

<script>
const RED=new Set([1,2,7,8,12,13,18,19,23,24,29,30,34,35,40,45,46]);
const BLUE=new Set([3,4,9,10,14,15,20,25,26,31,36,37,41,42,47,48]);
function cls(n){n=Number(n);return RED.has(n)?'red':(BLUE.has(n)?'blue':'green')}
let SPECIAL24=[];
function fmt(n){return String(n).padStart(2,'0')}
async function copySpecial(){
  const text=SPECIAL24.join(' ');
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
    SPECIAL24=d.special24||[]; sp.innerHTML=balls(SPECIAL24);
    const pairs=d.zodiac_pairs||[];
    zpair.innerHTML=pairs.map(p=>`<div class="zpair">
      <div class="zpairName">${p.zodiac}</div>
      <div class="zpairCodes"><span class="microball ${cls(p.code)}">${p.code}</span></div>
    </div>`).join('');
    pingteOne.textContent=d.pingte_yixiao||'--';
    pingteSamples.textContent=`转移样本 ${d.pingte_samples??0}`;
    const tr=d.trend||{};
    const w=tr.wave||{}, sz=tr.size||{}, pa=tr.parity||{};
    waveTrend.innerHTML=`红 ${w['红']??0}%<br>蓝 ${w['蓝']??0}%<br>绿 ${w['绿']??0}%`;
    sizeTrend.innerHTML=`大 ${sz['大']??0}%<br>小 ${sz['小']??0}%`;
    parityTrend.innerHTML=`单 ${pa['单']??0}%<br>双 ${pa['双']??0}%`;
    const ps=d.profile_scores||{};
    profileInfo.textContent=`当前模型 ${d.profile||'--'} · 最近校准分 ${ps[d.profile]??0}%`;
    const fc=d.forecast||{};
    forecastTarget.textContent=fc.target_issue?`预测 ${fc.target_issue} 期`:'--';
    forecastMode.innerHTML=`${fc.mode||'前瞻预测'}<br>转移样本 ${fc.transition_samples??0} · 全历史 ${fc.long_prior_ready?'已缓存':'后台加载'}`;
    const sg=d.strategy||{};
    coldSignal.innerHTML=sg.cold_rebound_now?'冷反弹信号：启用<br>24码允许热+冷防守':'冷反弹信号：普通<br>仍以热码为主';
    coldZodiac.innerHTML=(sg.cold_zodiacs||[]).length?`偏冷：${sg.cold_zodiacs.join('、')}`:'暂无';
    headSignal.innerHTML=sg.head_advice||'暂无';
    nmySignal.innerHTML=`样本 ${sg.nmy_samples??0}<br>条件 ${sg.nmy_conditional_pct??0}% / 基准 ${sg.nmy_baseline_pct??0}%`;
    latestZodiac.textContent=d.latest_special_zodiac?`特码生肖 ${d.latest_special_zodiac}`:'特码生肖 --';
    lastIngest.textContent=d.latest_created_at?`最后录入 ${d.latest_created_at}`:'实时录入';
    tg.textContent=d.telegram?'Telegram 已连接':'Telegram 未配置';
    adaptiveInfo.textContent=`前瞻预测：${d.next_issue||'--'}期 · 每肖2码 · 4肖1码`;
    calcState.textContent=d.recalculating?'新期开奖已入库 · 模型重算中':'模型已更新';
    calcState.className=d.recalculating?'pill':'pill ok';

  }catch(e){}
}
async function loadStats(){
  try{
    const r=await fetch('/api/stats?_='+Date.now(),{cache:'no-store'});
    const st=await r.json();
    if(st.building){
      hit22.textContent='计算中'; err22.textContent='';
      hit4.textContent='计算中'; err4.textContent='';
      hitZ.textContent='计算中'; errZ.textContent='';
      hitPingte.textContent='计算中'; errPingte.textContent='';
    }else{
      hit22.textContent=(st.hit24??0).toFixed(1)+'%'; err22.textContent='错误 '+(st.err24??0).toFixed(1)+'%';
      hit4.textContent=(st.hitMain??0).toFixed(1)+'%'; err4.textContent='错误 '+(st.errMain??0).toFixed(1)+'%';
      hitZ.textContent=(st.hitZ??0).toFixed(1)+'%'; errZ.textContent='错误 '+(st.errZ??0).toFixed(1)+'%';
      hitPingte.textContent=(st.hitPingte??0).toFixed(1)+'%'; errPingte.textContent='错误 '+(st.errPingte??0).toFixed(1)+'%';
    }
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
setInterval(loadMain,500);
setInterval(loadStats,30000);
setInterval(loadHistory,5000);
</script>
</body>
</html>"""

def ensure_db_dir():
    parent = os.path.dirname(os.path.abspath(DB))
    os.makedirs(parent, exist_ok=True)

def connect():
    ensure_db_dir()
    c = sqlite3.connect(DB, timeout=20, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA temp_store=MEMORY")
    return c

def _db_retry(fn, attempts=8):
    last=None
    for i in range(attempts):
        try:
            return fn()
        except sqlite3.OperationalError as e:
            last=e
            if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                raise
            time.sleep(min(0.08*(2**i),1.2))
    raise last

def init_db():
    with db_lock:
        c=connect()
        # WAL lets readers continue while Telegram writes the next draw.
        _db_retry(lambda: c.execute("PRAGMA journal_mode=WAL").fetchone())
        c.execute("PRAGMA wal_autocheckpoint=800")
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


def _insert_migrated_draw(c, item):
    """Accept v12 /api/history item or v13 /api/export full row."""
    issue=str(item.get("issue") or item.get("期号") or "").strip()
    if not issue:
        return 0

    # Full export format.
    if all(k in item for k in ["n1","n2","n3","n4","n5","n6","special"]):
        try:
            nums=[int(item[f"n{i}"]) for i in range(1,7)] + [int(item["special"])]
        except Exception:
            return 0
        zs=[normalize_z(str(item.get(f"z{i}") or "")) for i in range(1,8)]
        cs=[str(item.get(f"c{i}") or "") for i in range(1,8)]
        raw=str(item.get("raw") or "remote-export")
        created=str(item.get("created_at") or "")
    else:
        # Old /api/history format: issue + numbers[7] + special zodiac only.
        try:
            nums=[int(x) for x in item.get("numbers",[])]
        except Exception:
            return 0
        if len(nums)!=7:
            return 0
        zs=["","","","","","",normalize_z(str(item.get("zodiac") or ""))]
        cs=[""]*7
        raw="remote-history-migration"
        created=str(item.get("created_at") or "")

    if len(set(nums))!=7 or not all(1<=n<=49 for n in nums):
        return 0

    before=c.total_changes
    c.execute("""INSERT OR IGNORE INTO draws
      (issue,n1,n2,n3,n4,n5,n6,special,z1,z2,z3,z4,z5,z6,z7,
       c1,c2,c3,c4,c5,c6,c7,raw,created_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,COALESCE(NULLIF(?,''),CURRENT_TIMESTAMP))""",
      [issue,*nums,*zs,*cs,raw,created])
    return 1 if c.total_changes>before else 0

def sync_remote_history(url=None):
    """Merge history from the currently-live old service before switching versions."""
    url=(url or HISTORY_SOURCE_URL or "").strip()
    if not url:
        return 0
    try:
        # Try the exact supplied URL first.
        r=requests.get(url,timeout=25,headers={"User-Agent":"SanfenMigration/13"})
        r.raise_for_status()
        payload=r.json()
        items=payload.get("items") if isinstance(payload,dict) else payload
        if not isinstance(items,list):
            raise ValueError("remote history response has no items list")

        imported=0
        with db_lock:
            c=connect()
            for item in items:
                if isinstance(item,dict):
                    imported += _insert_migrated_draw(c,item)
            c.commit()
            c.close()

        sync_state["source"]=url
        sync_state["imported"]=imported
        sync_state["last_error"]=""
        sync_state["last_sync"]=time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[SYNC] imported={imported} from {url}",flush=True)
        return imported
    except Exception as e:
        sync_state["source"]=url
        sync_state["last_error"]=f"{type(e).__name__}: {e}"
        sync_state["last_sync"]=time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[SYNC] failed from {url}: {type(e).__name__}: {e}",flush=True)
        return 0

def sync_best_available_history():
    """Migrate from the deployment that is live right now, then configured fallbacks.
    On Render zero-downtime deploys, our public URL normally still serves the old
    deployment while this new worker is booting. This keeps bot-collected history
    across v13 -> v14 and later same-service upgrades."""
    urls=[]

    # Best source: this service's currently-live previous deployment.
    if WEBHOOK_BASE_URL:
        urls += [
          WEBHOOK_BASE_URL + "/api/export?limit=30000",
          WEBHOOK_BASE_URL + "/api/history?limit=500"
        ]

    # Configured explicit fallback/source.
    if HISTORY_SOURCE_URL:
        if "/api/" in HISTORY_SOURCE_URL:
            base=HISTORY_SOURCE_URL.split("/api/",1)[0]
            urls += [base+"/api/export?limit=30000"]
        urls += [HISTORY_SOURCE_URL]

    seen=set()
    total=0
    for u in urls:
        if not u or u in seen:
            continue
        seen.add(u)
        n=sync_remote_history(u)
        total += n
        if not sync_state["last_error"]:
            # Success includes 0 imported (everything already present).
            break
    return total

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

def latest_row():
    def _read():
        c=connect()
        try:
            return c.execute("""SELECT * FROM draws
                                ORDER BY CAST(issue AS INTEGER) DESC LIMIT 1""").fetchone()
        finally:
            c.close()
    return _db_retry(_read)

def _patch_live_cache_latest(issue, nums, zs):
    """Update visible latest result immediately, without waiting for the heavy model."""
    with live_cache_lock:
        data = dict(live_cache.get("data") or {})
        try:
            next_issue = str(int(issue) + 1)
        except Exception:
            next_issue = ""
        data.update({
            "issue": issue,
            "next_issue": next_issue,
            "latest_numbers": list(nums),
            "latest_special_zodiac": normalize_z(zs[6] if len(zs) >= 7 else ""),
            "latest_created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "recalculating": True
        })
        live_cache["issue"] = issue
        live_cache["data"] = data
        live_cache["building"] = False

def add_draw(issue,nums,zs,colors,raw):
    if len(nums)!=7 or len(set(nums))!=7 or not all(1<=x<=49 for x in nums): return False
    prev_before_insert=latest_row()
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
            update_long_prior_incremental(prev_before_insert, nums, zs)
            stats_cache["issue"]=None
            stats_cache["value"]=None
            _patch_live_cache_latest(issue, nums, zs)
            threading.Thread(target=refresh_all_caches,daemon=True,name="cache-refresh").start()
        return changed

def all_rows():
    def _read():
        c=connect()
        try:
            return c.execute("SELECT * FROM draws ORDER BY CAST(issue AS INTEGER) DESC").fetchall()
        finally:
            c.close()
    return _db_retry(_read)

def recent_rows(limit=1200):
    """Read only the recent history needed by the live predictor."""
    def _read():
        c=connect()
        try:
            return c.execute("""SELECT * FROM draws
                                ORDER BY CAST(issue AS INTEGER) DESC
                                LIMIT ?""",(int(limit),)).fetchall()
        finally:
            c.close()
    return _db_retry(_read)

def build_long_prior():
    """Build full-history priors once in the background.
    Live predictions never wait for this."""
    with long_prior_lock:
        if long_prior["building"]:
            return
        long_prior["building"] = True
    t0=time.time()
    try:
        rows=all_rows()  # one background scan of the full DB
        num_count=Counter()
        zodiac_count=Counter()
        trans_num=defaultdict(Counter)
        trans_z=defaultdict(Counter)

        for x in rows:
            n=x["special"]
            z=normalize_z(x["z7"] or "")
            if n:
                num_count[n]+=1
            if z:
                zodiac_count[z]+=1

        # rows newest -> oldest. state rows[j] -> next outcome rows[j-1]
        for j in range(1,len(rows)):
            state=rows[j]
            outcome=rows[j-1]
            sz=normalize_z(state["z7"] or "")
            on=outcome["special"]
            oz=normalize_z(outcome["z7"] or "")
            if sz and on:
                trans_num[sz][on]+=1
            if sz and oz:
                trans_z[sz][oz]+=1

        with long_prior_lock:
            long_prior["num_count"]=num_count
            long_prior["zodiac_count"]=zodiac_count
            long_prior["trans_num_by_zodiac"]=trans_num
            long_prior["trans_zodiac_by_zodiac"]=trans_z
            long_prior["total"]=len(rows)
            long_prior["ready"]=True
            long_prior["updated_at"]=time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[PRIOR] full-history prior ready rows={len(rows)} in {time.time()-t0:.2f}s",flush=True)
    except Exception as e:
        print(f"[PRIOR] failed: {type(e).__name__}: {e}",flush=True)
    finally:
        with long_prior_lock:
            long_prior["building"]=False

def update_long_prior_incremental(prev_row, nums, zs):
    """O(1) update after each new draw; no full rescan."""
    with long_prior_lock:
        if not long_prior["ready"]:
            return
        new_special=int(nums[6])
        new_z=normalize_z(zs[6] if len(zs)>=7 else "")
        long_prior["num_count"][new_special]+=1
        if new_z:
            long_prior["zodiac_count"][new_z]+=1
        if prev_row is not None:
            prev_z=normalize_z(prev_row["z7"] or "")
            if prev_z:
                long_prior["trans_num_by_zodiac"][prev_z][new_special]+=1
                if new_z:
                    long_prior["trans_zodiac_by_zodiac"][prev_z][new_z]+=1
        long_prior["total"]+=1
        long_prior["updated_at"]=time.strftime("%Y-%m-%d %H:%M:%S")

def _long_prior_bonus(r):
    """Return tiny, stable full-history priors as normalized 0..1 scores."""
    num_bonus=defaultdict(float)
    z_bonus=defaultdict(float)
    if not r:
        return num_bonus,z_bonus,False

    with long_prior_lock:
        if not long_prior["ready"]:
            return num_bonus,z_bonus,False
        numc=Counter(long_prior["num_count"])
        latest_z=normalize_z(r[0]["z7"] or "")
        trans_num=Counter(long_prior["trans_num_by_zodiac"].get(latest_z,{}))
        trans_z=Counter(long_prior["trans_zodiac_by_zodiac"].get(latest_z,{}))

    def normalize_counter(c, keys):
        vals=[c.get(k,0) for k in keys]
        if not vals:
            return {}
        lo=min(vals); hi=max(vals)
        if hi==lo:
            return {k:.5 for k in keys}
        return {k:(c.get(k,0)-lo)/(hi-lo) for k in keys}

    base=normalize_counter(numc, range(1,50))
    trn=normalize_counter(trans_num, range(1,50))
    trz=normalize_counter(trans_z, ALL_ZODIACS)
    for n in range(1,50):
        # Long history is a stabilizer, not the driver.
        num_bonus[n]=.42*base.get(n,.5)+.58*trn.get(n,.5)
    for z in ALL_ZODIACS:
        z_bonus[z]=trz.get(z,.5)
    return num_bonus,z_bonus,True


def refresh_history_cache(limit=500):
    def _read():
        c=connect()
        try:
            total=c.execute("SELECT COUNT(*) FROM draws").fetchone()[0]
            rr=c.execute("""SELECT issue,n1,n2,n3,n4,n5,n6,special,z7,created_at
                            FROM draws ORDER BY CAST(issue AS INTEGER) DESC LIMIT ?""",(limit,)).fetchall()
            return total,rr
        finally:
            c.close()
    total,rr=_db_retry(_read)
    items=[]
    for x in rr:
        items.append({
          "issue":x["issue"],
          "numbers":[x[f"n{i}"] for i in range(1,7)]+[x["special"]],
          "zodiac":normalize_z(x["z7"] or ""),
          "created_at":x["created_at"] or ""
        })
    with history_cache_lock:
        history_cache["total"]=total
        history_cache["items"]=items
        history_cache["loaded_at"]=time.strftime("%Y-%m-%d %H:%M:%S")
    return total

def refresh_all_caches():
    try:
        refresh_history_cache()
    except Exception as e:
        print(f"[CACHE] history refresh failed: {type(e).__name__}: {e}",flush=True)
    try:
        rebuild_live_cache()
    except Exception as e:
        print(f"[CACHE] model refresh failed: {type(e).__name__}: {e}",flush=True)
    # Backtest is never part of the critical update path.
    # Stats are deliberately not started here; /api/stats will start them lazily
    # after the live forecast is already available.

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
    sp=[x["special"] for x in r if x["special"]]
    wave=defaultdict(float); size=defaultdict(float); parity=defaultdict(float)
    cfg=[(8,3,1.70),(16,5,1.35),(36,11,1.00),(80,25,.55)]
    totalcoef=sum(c for _,_,c in cfg)
    for h,half,c in cfg:
        for k,v in _weighted_category(sp,wave_of,h,half).items(): wave[k]+=c*v
        for k,v in _weighted_category(sp,size_of,h,half).items(): size[k]+=c*v
        for k,v in _weighted_category(sp,parity_of,h,half).items(): parity[k]+=c*v
    for d in (wave,size,parity):
        for k in list(d): d[k]/=totalcoef

    def accel(mapper, keys):
        a=Counter(mapper(x["special"]) for x in r[:8])
        b=Counter(mapper(x["special"]) for x in r[8:32])
        av={k:a[k]/max(1,min(8,len(r))) for k in keys}
        bv={k:b[k]/max(1,min(24,max(0,len(r)-8))) for k in keys}
        return {k:av[k]-bv[k] for k in keys}

    def blend(base, ac, keys):
        raw={k:max(.001,base.get(k,0)+.46*ac.get(k,0)) for k in keys}
        z=sum(raw.values())
        return {k:raw[k]/z for k in keys}

    return {
      "wave":blend(wave,accel(wave_of,["红","蓝","绿"]),["红","蓝","绿"]),
      "size":blend(size,accel(size_of,["大","小"]),["大","小"]),
      "parity":blend(parity,accel(parity_of,["单","双"]),["单","双"])
    }

def _number_zodiac_map(r):
    counts={n:Counter() for n in range(1,50)}
    for x in r[:min(300,len(r))]:
        for j in range(1,7):
            n=x[f"n{j}"]; z=normalize_z(x[f"z{j}"] or "")
            if n and z: counts[n][z]+=1
        n=x["special"]; z=normalize_z(x["z7"] or "")
        if n and z: counts[n][z]+=2
    return {n:c.most_common(1)[0][0] for n,c in counts.items() if c}

PROFILE_LIBRARY = {
  "趋势快": {"recent":1.30,"accel":1.35,"wave":1.20,"size":1.05,"parity":1.00,"zodiac":1.10,"long":.55,"omit":.45},
  "平衡":   {"recent":1.00,"accel":1.00,"wave":1.00,"size":1.00,"parity":1.00,"zodiac":1.00,"long":1.00,"omit":.75},
  "热码":   {"recent":1.45,"accel":.90,"wave":.70,"size":.65,"parity":.65,"zodiac":.80,"long":.45,"omit":.25},
  "结构":   {"recent":.88,"accel":1.05,"wave":1.45,"size":1.30,"parity":1.25,"zodiac":1.35,"long":.70,"omit":.45},
  "均衡覆盖":{"recent":.82,"accel":.82,"wave":1.10,"size":1.10,"parity":1.10,"zodiac":1.40,"long":1.10,"omit":.90}
}

FORECAST_BLEND = {
  "趋势快": {"transition":2.55,"hazard":.55,"tail":.50,"anti_chase":.72},
  "平衡": {"transition":2.20,"hazard":.75,"tail":.58,"anti_chase":.65},
  "热码": {"transition":1.85,"hazard":.42,"tail":.42,"anti_chase":.52},
  "结构": {"transition":2.35,"hazard":.68,"tail":.72,"anti_chase":.68},
  "均衡覆盖": {"transition":2.05,"hazard":1.05,"tail":.55,"anti_chase":.60}
}

def _zodiac_scores_profile(r, profile):
    p=PROFILE_LIBRARY[profile]
    score=defaultdict(float)
    for horizon,half,coef in [(6,2,2.30),(12,4,1.90),(24,8,1.38),(50,16,.90),(120,38,.45)]:
        for i,x in enumerate(r[:min(horizon,len(r))]):
            w=coef*exp_weight(i,half)*p["recent"]
            if x["z7"]:
                score[normalize_z(x["z7"])]+=1.75*w
            for k in ["z1","z2","z3","z4","z5","z6"]:
                if x[k]:
                    score[normalize_z(x[k])]+=.26*w

    a=Counter(normalize_z(x["z7"] or "") for x in r[:8] if x["z7"])
    b=Counter(normalize_z(x["z7"] or "") for x in r[8:32] if x["z7"])
    for z in set(score)|set(a)|set(b):
        score[z]+=p["accel"]*2.15*(a[z]/max(1,min(8,len(r)))-b[z]/max(1,min(24,max(0,len(r)-8))))
    return score

def _number_scores_profile(r, profile):
    p=PROFILE_LIBRARY[profile]
    numbers=range(1,50)
    score={n:0.0 for n in numbers}
    trend=_trend_profiles(r)
    zmap=_number_zodiac_map(r)
    zscore=_zodiac_scores_profile(r,profile)

    for horizon,half,coef in [(8,3,2.40),(16,5,1.95),(36,11,1.45),(80,25,1.00),(200,65,.55),(800,250,.22)]:
        rr=r[:min(horizon,len(r))]
        freq=Counter()
        for i,x in enumerate(rr):
            freq[x["special"]]+=exp_weight(i,half)
        mean=sum(freq.values())/49.0 if rr else 0
        factor=p["recent"] if horizon<=80 else p["long"]
        for n in numbers:
            score[n]+=coef*factor*(freq[n]-mean)/math.sqrt(mean+1.0)

    for short,base,coef in [(8,24,1.55),(16,48,1.00)]:
        a=Counter(x["special"] for x in r[:short])
        b=Counter(x["special"] for x in r[short:short+base])
        for n in numbers:
            score[n]+=coef*p["accel"]*(a[n]/max(short,1)-b[n]/max(base,1))

    for n in numbers:
        score[n]+=1.12*p["wave"]*(trend["wave"].get(wave_of(n),0)-1/3)
        score[n]+=.82*p["size"]*(trend["size"].get(size_of(n),0)-1/2)
        score[n]+=.76*p["parity"]*(trend["parity"].get(parity_of(n),0)-1/2)
        z=zmap.get(n)
        if z:
            score[n]+=.012*p["zodiac"]*zscore.get(z,0)

    full=Counter(x["special"] for x in r)
    expected=len(r)/49.0
    for n in numbers:
        score[n]+=.13*p["long"]*(full[n]-expected)/math.sqrt(expected+7.0)

    last={n:len(r) for n in numbers}
    for i,x in enumerate(r):
        if last[x["special"]]==len(r): last[x["special"]]=i
    for n in numbers:
        score[n]+=.11*p["omit"]*min(last[n],50)/50.0
    return score

def head_of(n):
    if 1 <= n <= 9: return "0头"
    if 10 <= n <= 19: return "1头"
    if 20 <= n <= 29: return "2头"
    if 30 <= n <= 39: return "3头"
    return "4头"

HEAD_BASE = {"0头":9/49,"1头":10/49,"2头":10/49,"3头":10/49,"4头":10/49}

def _cold_metrics(r):
    """Current omission/coldness for numbers and zodiacs."""
    num_gap={n:len(r) for n in range(1,50)}
    z_gap={z:len(r) for z in ALL_ZODIACS}

    for i,x in enumerate(r):
        n=x["special"]
        if num_gap[n]==len(r):
            num_gap[n]=i
        z=normalize_z(x["z7"] or "")
        if z in z_gap and z_gap[z]==len(r):
            z_gap[z]=i

    # Recent occurrence rates.
    c12=Counter(x["special"] for x in r[:12])
    c36=Counter(x["special"] for x in r[:36])
    z12=Counter(normalize_z(x["z7"] or "") for x in r[:12] if x["z7"])
    z36=Counter(normalize_z(x["z7"] or "") for x in r[:36] if x["z7"])

    num_cold={}
    for n in range(1,50):
        gap=min(num_gap[n],40)/40.0
        scarcity=1.0-min(c12[n]/max(1,12/49),1.8)/1.8
        medium=1.0-min(c36[n]/max(1,36/49),1.8)/1.8
        num_cold[n]=0.55*gap+0.30*scarcity+0.15*medium

    z_cold={}
    for z in ALL_ZODIACS:
        gap=min(z_gap[z],24)/24.0
        scarcity=1.0-min(z12[z]/max(1,12/12),1.8)/1.8
        medium=1.0-min(z36[z]/max(1,36/12),1.8)/1.8
        z_cold[z]=0.55*gap+0.30*scarcity+0.15*medium

    return num_cold,z_cold,num_gap,z_gap

def _nmy_cold_rebound_lift(r, lookback=300, cold_window=12):
    """Empirically test the user's '牛/马/羊后冷码' idea.
    A transition counts as a cold rebound if the next special had not appeared
    in the preceding cold_window special draws. Returns conditional lift vs all transitions."""
    nmy={"牛","马","羊"}
    maxj=min(len(r)-cold_window-2, lookback)
    if maxj <= 20:
        return {"samples":0,"conditional":0.0,"baseline":0.0,"lift":0.0,"active":False}

    cond_hits=cond_n=base_hits=base_n=0
    for j in range(maxj):
        outcome=r[j]["special"]
        prior_z=normalize_z(r[j+1]["z7"] or "")
        older=[r[k]["special"] for k in range(j+2,min(j+2+cold_window,len(r)))]
        is_cold = outcome not in older
        base_n += 1
        base_hits += int(is_cold)
        if prior_z in nmy:
            cond_n += 1
            cond_hits += int(is_cold)

    baseline=base_hits/base_n if base_n else 0.0
    conditional=cond_hits/cond_n if cond_n else 0.0
    lift=conditional-baseline
    active=cond_n>=18 and lift>=0.07
    return {
      "samples":cond_n,
      "conditional":round(conditional,3),
      "baseline":round(baseline,3),
      "lift":round(lift,3),
      "active":active
    }

def _head_trend(r):
    """Head-number strength normalized by theoretical head sizes.
    Returns weak-head guidance; algorithm only downweights, never hard-excludes."""
    cfg=[(8,3,1.55),(16,5,1.25),(36,11,.90),(80,25,.55)]
    score={h:0.0 for h in HEAD_BASE}
    totalcoef=sum(c for _,_,c in cfg)
    sp=[x["special"] for x in r]

    for horizon,half,coef in cfg:
        wsum=0.0
        tmp=defaultdict(float)
        for i,n in enumerate(sp[:min(horizon,len(sp))]):
            w=exp_weight(i,half)
            tmp[head_of(n)] += w
            wsum += w
        for h in HEAD_BASE:
            share=(tmp[h]/wsum) if wsum else 0.0
            # Normalize by theoretical probability so 0头 isn't unfairly penalized.
            score[h] += coef*(share/HEAD_BASE[h])

    for h in score:
        score[h] /= totalcoef

    # Acceleration: last 8 vs previous 24.
    a=Counter(head_of(x["special"]) for x in r[:8])
    b=Counter(head_of(x["special"]) for x in r[8:32])
    for h in score:
        recent=a[h]/max(1,min(8,len(r)))
        prev=b[h]/max(1,min(24,max(0,len(r)-8)))
        score[h] += 0.55*(recent-prev)/HEAD_BASE[h]

    ranked=sorted(score,key=lambda h:(score[h],h))
    weakest=ranked[0]
    weak04=min(["0头","4头"],key=lambda h:score[h])
    weak04_strength=score[weak04]
    # Only call it a "kill/downweight" signal if it is meaningfully weak.
    if weak04_strength < 0.72:
        advice=f"{weak04}偏弱（降权）"
        active=weak04
    else:
        advice="0头/4头暂无明显弱势"
        active=""
    return {
      "strength":{h:round(score[h],2) for h in score},
      "weakest":weakest,
      "active_04":active,
      "advice":advice
    }

def _strategy_context(r):
    num_cold,z_cold,num_gap,z_gap=_cold_metrics(r)
    rebound=_nmy_cold_rebound_lift(r)
    head=_head_trend(r)
    latest_z=normalize_z(r[0]["z7"] or "") if r else ""
    nmy_now=latest_z in {"牛","马","羊"}
    cold_rebound_now=bool(nmy_now and rebound["active"])
    cold_zodiacs=sorted(ALL_ZODIACS,key=lambda z:(-z_cold.get(z,0),z))[:3]
    return {
      "num_cold":num_cold,
      "z_cold":z_cold,
      "num_gap":num_gap,
      "z_gap":z_gap,
      "nmy_rebound":rebound,
      "latest_zodiac":latest_z,
      "cold_rebound_now":cold_rebound_now,
      "cold_zodiacs":cold_zodiacs,
      "head":head
    }

def _forward_transition_scores(r):
    """One-step-ahead transition model.
    Uses historical state(t) -> result(t+1) pairs. The current latest draw is only
    used as the conditioning state; its number is NOT counted as a 'hot hit' for itself."""
    num_score=defaultdict(float)
    z_score=defaultdict(float)
    head_score=defaultdict(float)
    wave_score=defaultdict(float)
    size_score=defaultdict(float)
    parity_score=defaultdict(float)

    if len(r) < 80:
        return num_score,z_score,head_score,wave_score,size_score,parity_score,{"samples":0}

    cur=r[0]
    cur_n=cur["special"]
    cur_z=normalize_z(cur["z7"] or "")
    cur_head=head_of(cur_n)
    cur_wave=wave_of(cur_n)
    cur_size=size_of(cur_n)
    cur_parity=parity_of(cur_n)
    cur_tail=cur_n % 10
    cur_zset={normalize_z(cur[f"z{k}"] or "") for k in range(1,8) if cur[f"z{k}"]}

    samples=0
    exact_samples=0
    # r is newest -> oldest. Historical transition: r[j] (state) -> r[j-1] (next outcome).
    maxj=min(len(r)-1,700)
    for j in range(1,maxj):
        prev=r[j]
        out=r[j-1]
        pn=prev["special"]
        pz=normalize_z(prev["z7"] or "")
        on=out["special"]
        oz=normalize_z(out["z7"] or "")

        # Recency decay over historical transitions.
        w=exp_weight(j,260)
        match=0.0
        if pn==cur_n:
            match += 2.10
            exact_samples += 1
        if pz==cur_z:
            match += 1.65
        if head_of(pn)==cur_head:
            match += .70
        if wave_of(pn)==cur_wave:
            match += .55
        if size_of(pn)==cur_size:
            match += .45
        if parity_of(pn)==cur_parity:
            match += .40
        if pn % 10 == cur_tail:
            match += .48

        # Similarity of all 7 zodiacs in the state draw.
        pzset={normalize_z(prev[f"z{k}"] or "") for k in range(1,8) if prev[f"z{k}"]}
        if cur_zset and pzset:
            inter=len(cur_zset & pzset)
            union=max(1,len(cur_zset | pzset))
            match += .70*(inter/union)

        # Two-step context: previous zodiac/head sequence when available.
        if j+1 < len(r):
            older=r[j+1]
            if normalize_z(older["z7"] or "") == normalize_z(r[1]["z7"] or ""):
                match += .55
            if head_of(older["special"]) == head_of(r[1]["special"]):
                match += .25

        if match <= 0:
            continue

        ww=w*match
        samples += 1
        num_score[on] += ww
        if oz:
            z_score[oz] += ww
        head_score[head_of(on)] += ww
        wave_score[wave_of(on)] += ww
        size_score[size_of(on)] += ww
        parity_score[parity_of(on)] += ww

    # Normalize each family so it contributes comparably.
    def norm(d):
        if not d: return d
        vals=list(d.values())
        lo=min(vals); hi=max(vals)
        if hi-lo < 1e-9:
            return defaultdict(float,{k:0.5 for k in d})
        return defaultdict(float,{k:(v-lo)/(hi-lo) for k,v in d.items()})

    return (
      norm(num_score),norm(z_score),norm(head_score),
      norm(wave_score),norm(size_score),norm(parity_score),
      {"samples":samples,"exact_samples":exact_samples}
    )

def _base_hot_score_without_latest(r, profile):
    """Trend score for next-period prediction.
    Excludes r[0] from direct frequency counts to avoid simply chasing what just opened."""
    p=PROFILE_LIBRARY[profile]
    hist=r[1:] if len(r)>1 else r
    score={n:0.0 for n in range(1,50)}
    trend=_trend_profiles(hist if hist else r)

    for horizon,half,coef in [(6,2,2.05),(12,4,1.75),(24,8,1.35),(60,18,.92),(120,38,.48)]:
        for i,x in enumerate(hist[:min(horizon,len(hist))]):
            w=coef*exp_weight(i,half)
            score[x["special"]] += 1.50*w
            for j in range(1,7):
                score[x[f"n{j}"]] += .48*w

    # Acceleration also ends at r[1], not the just-opened r[0].
    now=Counter(); old=Counter()
    for x in hist[:6]:
        now[x["special"]]+=1.7
        for j in range(1,7): now[x[f"n{j}"]]+=.50
    for x in hist[6:24]:
        old[x["special"]]+=1.7
        for j in range(1,7): old[x[f"n{j}"]]+=.50

    for n in range(1,50):
        score[n] += .90*p["accel"]*(now[n]/6.0-old[n]/18.0)
        score[n] += .28*p["wave"]*trend["wave"].get(wave_of(n),0)
        score[n] += .17*p["size"]*trend["size"].get(size_of(n),0)
        score[n] += .16*p["parity"]*trend["parity"].get(parity_of(n),0)
    return score

def _gap_hazard_profile(r):
    """Empirical gap hazard from special-number intervals.
    This asks: after a number has been absent about g periods, how often did a
    number historically appear on the next period? It is a statistical modifier,
    not a guarantee that overdue numbers are 'due'."""
    if len(r) < 300:
        return {n:0.5 for n in range(1,50)}

    seq=[x["special"] for x in reversed(r)]  # oldest -> newest
    last={}
    intervals=[]
    for t,n in enumerate(seq):
        if n in last:
            intervals.append(t-last[n])
        last[n]=t

    # Hazard by gap bucket using completed intervals.
    buckets=[(0,2),(3,5),(6,9),(10,14),(15,21),(22,35),(36,9999)]
    hazard={}
    for lo,hi in buckets:
        at_risk=sum(1 for d in intervals if d>lo)
        events=sum(1 for d in intervals if lo < d <= hi)
        hazard[(lo,hi)]=(events/at_risk) if at_risk else 0.0

    # Current omission gaps.
    gaps={n:len(seq) for n in range(1,50)}
    for i,x in enumerate(r):
        n=x["special"]
        if gaps[n]==len(seq):
            gaps[n]=i

    raw={}
    for n,g in gaps.items():
        val=0.0
        for (lo,hi),h in hazard.items():
            if lo <= g <= hi:
                val=h
                break
        raw[n]=val

    vals=list(raw.values())
    lo=min(vals); hi=max(vals)
    if hi-lo < 1e-9:
        return {n:0.5 for n in raw}
    return {n:(v-lo)/(hi-lo) for n,v in raw.items()}

def _tail_transition_score(r):
    """Current special tail -> next special number empirical transition."""
    out=defaultdict(float)
    if len(r)<80:
        return out
    cur_tail=r[0]["special"] % 10
    for j in range(1,min(len(r)-1,700)):
        state=r[j]["special"]
        nxt=r[j-1]["special"]
        if state % 10 == cur_tail:
            out[nxt]+=exp_weight(j,260)
    if not out:
        return out
    vals=list(out.values()); lo=min(vals); hi=max(vals)
    if hi-lo<1e-9:
        return defaultdict(float,{k:.5 for k in out})
    return defaultdict(float,{k:(v-lo)/(hi-lo) for k,v in out.items()})

def _predictive_number_scores(r, profile, ctx=None):
    """Forecast score for NEXT issue.
    Ensemble: one-step transition + recent trend excluding latest + gap hazard
    + tail transition + cold/head safeguards."""
    ctx=ctx or _strategy_context(r)
    score=_base_hot_score_without_latest(r,profile)
    num_t,z_t,head_t,wave_t,size_t,par_t,meta=_forward_transition_scores(r)
    hazard=_gap_hazard_profile(r)
    tail_t=_tail_transition_score(r)
    blend=FORECAST_BLEND.get(profile,FORECAST_BLEND["平衡"])
    long_num,long_z,long_ready=_long_prior_bonus(r)

    weak04=ctx["head"].get("active_04","")
    latest_n=r[0]["special"] if r else None

    for n in range(1,50):
        score[n] += blend["transition"]*num_t[n]
        score[n] += .78*head_t[head_of(n)]
        score[n] += .65*wave_t[wave_of(n)]
        score[n] += .54*size_t[size_of(n)]
        score[n] += .50*par_t[parity_of(n)]
        score[n] += blend["hazard"]*hazard.get(n,.5)
        score[n] += blend["tail"]*tail_t[n]
        if long_ready:
            score[n] += .48*long_num[n]

        cold=ctx["num_cold"].get(n,0)
        score[n] += (0.72 if ctx["cold_rebound_now"] else 0.10)*cold

        if weak04 and head_of(n)==weak04:
            score[n] -= .62

        # Repeat is not banned. We only remove the artificial "just opened = hot"
        # effect; transition evidence may still put the same number back in.
        if latest_n is not None and n==latest_n:
            score[n] -= blend["anti_chase"]

    meta=dict(meta)
    meta["ensemble"]="转移+遗漏风险+尾数转移+结构"
    return score,meta,z_t

def _candidate24_by_zodiac(r, profile):
    """Exactly 24 = 12 zodiacs × 2 forward-looking codes.
    Each zodiac contributes two numbers with the highest NEXT-issue score."""
    zmap=_number_zodiac_map(r)
    ctx=_strategy_context(r)
    ns,transition_meta,ztrans=_predictive_number_scores(r,profile,ctx)

    pools={z:[] for z in ALL_ZODIACS}
    for n in range(1,50):
        z=zmap.get(n)
        if z in pools:
            pools[z].append(n)

    groups=[]; selected=[]; used=set()
    for z in ALL_ZODIACS:
        ranked=sorted(pools[z],key=lambda n:(-ns[n],n))
        codes=ranked[:2]

        # In a validated cold-rebound phase, allow the second code to be a competitive cold code.
        if ctx["cold_rebound_now"] and len(ranked)>=3:
            cold_rank=sorted(pools[z],key=lambda n:(-ctx["num_cold"].get(n,0),-ns[n],n))
            cc=cold_rank[0]
            if cc not in codes and ns[cc] >= ns[codes[-1]]-.55:
                codes=[codes[0],cc]

        groups.append({"zodiac":z,"codes":codes})
        for n in codes:
            if n not in used:
                selected.append(n); used.add(n)

    if len(selected)<24:
        for n in sorted(range(1,50),key=lambda n:(-ns[n],n)):
            if n not in used:
                selected.append(n); used.add(n)
            if len(selected)>=24: break

    return selected[:24],groups,ns,_zodiac_scores_profile(r,profile),ctx,transition_meta,ztrans

def _dynamic_zodiac4_one_code(r, profile, groups, ns, zs, ctx, ztrans):
    """Predict 4 zodiacs for the NEXT issue using transition + trend, one code each."""
    if not r:
        return [],[]

    prev_zs=_zodiac_scores_profile(r[1:],profile) if len(r)>1 else {}
    latest_z=normalize_z(r[0]["z7"] or "")

    _ln,long_z,long_ready=_long_prior_bonus(r)
    adjusted={}
    for z in ALL_ZODIACS:
        momentum=zs.get(z,0)-prev_zs.get(z,0)
        adjusted[z]=zs.get(z,0)+1.05*momentum
        adjusted[z]+=1.50*ztrans[z]
        if long_ready:
            adjusted[z]+=.55*long_z[z]
        adjusted[z]+=(.72 if ctx["cold_rebound_now"] else .12)*ctx["z_cold"].get(z,0)

        # Small anti-chase cooldown. Historical transition can overcome it.
        if z==latest_z:
            adjusted[z]-=.12*max(abs(zs.get(z,0)),1.0)

    z4=sorted(ALL_ZODIACS,key=lambda z:(-adjusted.get(z,-1e9),z))[:4]
    groupmap={g["zodiac"]:g["codes"] for g in groups}
    pairs=[]
    for z in z4:
        codes=groupmap.get(z,[])
        if codes:
            code=max(codes,key=lambda n:(ns.get(n,-1e9),-n))
            pairs.append({"zodiac":z,"code":code})
    return z4,pairs

def _predict_with_profile(r, profile):
    cand24,groups,ns,zs,ctx,tmeta,ztrans=_candidate24_by_zodiac(r,profile)
    z4,zpairs=_dynamic_zodiac4_one_code(r,profile,groups,ns,zs,ctx,ztrans)
    main4=[p["code"] for p in zpairs]
    return cand24,main4,z4,groups,zpairs

def _draw_zodiac_set(x):
    return {normalize_z(x[f"z{k}"] or "") for k in range(1,8) if x[f"z{k}"]}

def _pingte_yixiao_scores(r):
    """Predict one zodiac that will appear anywhere among the next draw's 7 numbers."""
    score={z:0.0 for z in ALL_ZODIACS}
    if not r:
        return score,{"samples":0}

    # Base presence trend. Binary per draw: a zodiac counts once even if repeated.
    hist=r[1:] if len(r)>1 else r
    for horizon,half,coef in [(8,3,1.80),(16,5,1.45),(36,11,1.00),(80,25,.62),(160,50,.35)]:
        for i,x in enumerate(hist[:min(horizon,len(hist))]):
            w=coef*exp_weight(i,half)
            for z in _draw_zodiac_set(x):
                if z in score:
                    score[z]+=w

    # Presence acceleration.
    a=Counter()
    b=Counter()
    for x in hist[:8]:
        for z in _draw_zodiac_set(x): a[z]+=1
    for x in hist[8:32]:
        for z in _draw_zodiac_set(x): b[z]+=1
    for z in ALL_ZODIACS:
        score[z]+=1.25*(a[z]/8.0-b[z]/24.0)

    # Current-state -> next-draw zodiac-presence transition.
    cur=r[0]
    cur_special_z=normalize_z(cur["z7"] or "")
    cur_set=_draw_zodiac_set(cur)
    cur_head=head_of(cur["special"])
    cur_wave=wave_of(cur["special"])
    cur_size=size_of(cur["special"])
    cur_parity=parity_of(cur["special"])

    trans=defaultdict(float)
    samples=0
    for j in range(1,min(len(r)-1,700)):
        state=r[j]
        outcome=r[j-1]
        match=0.0
        if normalize_z(state["z7"] or "")==cur_special_z: match+=1.70
        if head_of(state["special"])==cur_head: match+=.62
        if wave_of(state["special"])==cur_wave: match+=.48
        if size_of(state["special"])==cur_size: match+=.38
        if parity_of(state["special"])==cur_parity: match+=.34
        stset=_draw_zodiac_set(state)
        if cur_set and stset:
            match+=.90*(len(cur_set & stset)/max(1,len(cur_set | stset)))
        if match<=0: continue
        samples+=1
        ww=exp_weight(j,280)*match
        for z in _draw_zodiac_set(outcome):
            if z in score:
                trans[z]+=ww

    if trans:
        vals=list(trans.values()); lo=min(vals); hi=max(vals)
        if hi-lo>1e-9:
            for z in ALL_ZODIACS:
                score[z]+=1.85*((trans[z]-lo)/(hi-lo))
        else:
            for z in trans:
                score[z]+=.90

    return score,{"samples":samples}

def _predict_pingte_yixiao(r):
    scores,meta=_pingte_yixiao_scores(r)
    _ln,long_z,long_ready=_long_prior_bonus(r)
    if long_ready:
        for z in ALL_ZODIACS:
            scores[z]+=.45*long_z[z]
    ranked=sorted(ALL_ZODIACS,key=lambda z:(-scores.get(z,-1e9),z))
    one=ranked[0] if ranked else ""
    return one,meta

def _profile_score_on_recent(r, profile, samples=28):
    if len(r)<260:
        return 0.0
    tests=min(samples,len(r)-220)
    h24=hmain=hz=0
    n=0
    for k in range(tests-1,-1,-1):
        train=r[k+1:]
        if len(train)<220: continue
        c24,m4,z4,_,_=_predict_with_profile(train,profile)
        actual=r[k]
        sp=actual["special"]
        az=normalize_z(actual["z7"] or "")
        h24+=int(sp in c24)
        hmain+=int(sp in m4)
        hz+=int(bool(az) and az in z4)
        n+=1
    if not n: return 0.0
    # Coverage is the main objective, but 4肖/一肖一码 matter too.
    return (.58*h24 + .17*hmain + .25*hz)/n

def _light_profile_calibration(r):
    """Very small calibration pass. Never blocks the web/model rebuild path."""
    if not r or background_state.get("profile_calibrating"):
        return
    background_state["profile_calibrating"]=True
    try:
        # Limit history and validation depth aggressively for free-tier CPU.
        rr=r[:700]
        scores={name:_profile_score_on_recent(rr,name,1) for name in PROFILE_LIBRARY}
        best=max(scores,key=lambda k:(scores[k],k))
        model_state["profile"]=best
        model_state["profile_scores"]={k:round(v*100,1) for k,v in scores.items()}
        model_state["last_calibrated_issue"]=r[0]["issue"] if r else None
        print(f"[CAL] lightweight profile={best} scores={model_state['profile_scores']}",flush=True)
    except Exception as e:
        print(f"[CAL] failed: {type(e).__name__}: {e}",flush=True)
    finally:
        background_state["profile_calibrating"]=False

def _select_profile(r, force=False):
    """Return immediately. Heavy historical profile selection never blocks a page request."""
    latest_issue=r[0]["issue"] if r else None
    cached=model_state.get("profile") or "平衡"
    last=model_state.get("last_calibrated_issue")

    due=force or not last
    if not due and latest_issue and last:
        try:
            due=abs(int(latest_issue)-int(last)) >= 12
        except Exception:
            due=False

    if due and not background_state.get("profile_calibrating"):
        threading.Thread(
            target=_light_profile_calibration,
            args=(list(r),),
            daemon=True,
            name="profile-calibration"
        ).start()

    # First request/deploy uses balanced weights immediately.
    if not model_state.get("profile"):
        model_state["profile"]="平衡"
        model_state["profile_scores"]={"平衡":0.0}
    return model_state["profile"], dict(model_state.get("profile_scores") or {})

def predict_core(r, profile=None):
    if not r:return [],[],[]
    profile=profile or _select_profile(r)[0]
    c24,m4,z4,_,_=_predict_with_profile(r,profile)
    return c24,m4,z4

def backtest_stats(r, sample=60):
    if not r or len(r)<420:
        return {"n":0,"hit24":0.0,"err24":100.0,"hitMain":0.0,"errMain":100.0,
                "hitZ":0.0,"errZ":100.0,"hitPingte":0.0,"errPingte":100.0,"profile":"--"}
    latest_issue=r[0]["issue"]
    if stats_cache["issue"]==latest_issue and stats_cache["value"] is not None:
        return stats_cache["value"]

    tests=min(sample,len(r)-320)

    # Choose profile only from older data than the validation window.
    calibration_source=r[tests:]
    profile,_scores=_select_profile(calibration_source)

    h24=hmain=hz=hping=0
    actual_tests=0
    for k in range(tests-1,-1,-1):
        train=r[k+1:]
        if len(train)<260: continue
        c24,m4,z4,_,_=_predict_with_profile(train,profile)
        py,_=_predict_pingte_yixiao(train)
        actual=r[k]
        sp=actual["special"]
        az=normalize_z(actual["z7"] or "")
        draw_z=_draw_zodiac_set(actual)

        h24+=int(sp in c24)
        hmain+=int(sp in m4)
        hz+=int(bool(az) and az in z4)
        hping+=int(bool(py) and py in draw_z)
        actual_tests+=1

    n=max(actual_tests,1)
    val={
      "n":actual_tests,
      "profile":profile,
      "hit24":round(h24/n*100,1),"err24":round((actual_tests-h24)/n*100,1),
      "hitMain":round(hmain/n*100,1),"errMain":round((actual_tests-hmain)/n*100,1),
      "hitZ":round(hz/n*100,1),"errZ":round((actual_tests-hz)/n*100,1),
      "hitPingte":round(hping/n*100,1),"errPingte":round((actual_tests-hping)/n*100,1)
    }
    stats_cache["issue"]=latest_issue
    stats_cache["value"]=val
    return val

def initialize_quick_live_cache():
    """Populate latest draw immediately without loading the full database."""
    try:
        r=recent_rows(1)
        if not r:
            return
        latest=r[0]
        latest_numbers=[latest[f"n{i}"] for i in range(1,7)]+[latest["special"]]
        try:
            next_issue=str(int(latest["issue"])+1)
        except Exception:
            next_issue=""
        data={
          "issue":latest["issue"],"next_issue":next_issue,"count":history_cache.get("total",0),
          "latest_numbers":latest_numbers,
          "latest_special_zodiac":normalize_z(latest["z7"] or ""),
          "latest_created_at":latest["created_at"] or "",
          "special24":[],"main4":[],"zodiac4":[],"zodiac_pairs":[],
          "pingte_yixiao":"",
          "pingte_samples":0,
          "profile":model_state.get("profile") or "平衡",
          "profile_scores":{},
          "forecast":{"target_issue":next_issue,"transition_samples":0,
                      "exact_previous_number_samples":0,
                      "mode":"模型后台初始化中"},
          "strategy":{"cold_rebound_now":False,"cold_zodiacs":[],
                      "latest_zodiac":normalize_z(latest["z7"] or ""),
                      "nmy_samples":0,"nmy_conditional_pct":0.0,"nmy_baseline_pct":0.0,
                      "nmy_lift_pct":0.0,"head_advice":"模型后台初始化中","head_strength":{}},
          "trend":{"wave":{},"size":{},"parity":{}},
          "telegram":bool(BOT_TOKEN),
          "recalculating":True
        }
        with live_cache_lock:
            live_cache["issue"]=latest["issue"]
            live_cache["data"]=data
            live_cache["building"]=False
        print(f"[BOOT] quick cache ready issue={latest['issue']}",flush=True)
    except Exception as e:
        print(f"[BOOT] quick cache failed: {type(e).__name__}: {e}",flush=True)

def build_model():
    model_state["recalc_started_at"]=time.strftime("%Y-%m-%d %H:%M:%S")
    r=recent_rows(1200)
    if not r:
        return {"issue":None,"count":0,"special24":[],"main4":[],"zodiac4":[],"zodiac_pairs":[],"telegram":bool(BOT_TOKEN),"recalculating":False}
    profile,profile_scores=_select_profile(r)
    c24,m4,z4,groups,zpairs=_predict_with_profile(r,profile)
    pingte_one,pingte_meta=_predict_pingte_yixiao(r)
    trend=_trend_profiles(r)
    strategy=_strategy_context(r)
    _nt,_zt,_ht,_wt,_st,_pt,transition_meta=_forward_transition_scores(r)
    latest=r[0]
    latest_numbers=[latest[f"n{i}"] for i in range(1,7)]+[latest["special"]]
    try: next_issue=str(int(latest["issue"])+1)
    except Exception: next_issue=""
    return {
      "issue":latest["issue"],"next_issue":next_issue,"count":history_cache.get("total",0),
      "latest_numbers":latest_numbers,
      "latest_special_zodiac":normalize_z(latest["z7"] or ""),
      "latest_created_at":latest["created_at"] or "",
      "special24":[f"{n:02d}" for n in sorted(c24)],
      "main4":[f"{n:02d}" for n in m4],
      "zodiac4":z4,
      "zodiac_pairs":[{"zodiac":p["zodiac"],"code":f"{p['code']:02d}"} for p in zpairs],
      "pingte_yixiao":pingte_one,
      "pingte_samples":pingte_meta.get("samples",0),
      "profile":profile,
      "profile_scores":profile_scores,
      "forecast":{
        "target_issue":next_issue,
        "transition_samples":transition_meta.get("samples",0),
        "exact_previous_number_samples":transition_meta.get("exact_samples",0),
        "long_prior_ready":bool(long_prior.get("ready")),
        "long_prior_rows":int(long_prior.get("total",0)),
        "mode":"极速混合：近1200期实时 + 全历史先验缓存"
      },
      "strategy":{
        "cold_rebound_now":strategy["cold_rebound_now"],
        "cold_zodiacs":strategy["cold_zodiacs"],
        "latest_zodiac":strategy["latest_zodiac"],
        "nmy_samples":strategy["nmy_rebound"]["samples"],
        "nmy_conditional_pct":round(strategy["nmy_rebound"]["conditional"]*100,1),
        "nmy_baseline_pct":round(strategy["nmy_rebound"]["baseline"]*100,1),
        "nmy_lift_pct":round(strategy["nmy_rebound"]["lift"]*100,1),
        "head_advice":strategy["head"]["advice"],
        "head_strength":strategy["head"]["strength"]
      },
      "trend":{
        "wave":{k:round(v*100,1) for k,v in trend["wave"].items()},
        "size":{k:round(v*100,1) for k,v in trend["size"].items()},
        "parity":{k:round(v*100,1) for k,v in trend["parity"].items()}
      },
      "telegram":bool(BOT_TOKEN),
      "recalculating":False,
      "model_recalc_started_at":model_state.get("recalc_started_at",""),
      "model_recalc_finished_at":time.strftime("%Y-%m-%d %H:%M:%S")
    }

def rebuild_live_cache():
    with live_cache_lock:
        if live_cache.get("building"):
            return live_cache.get("data")
        live_cache["building"]=True
        previous=live_cache.get("data")
    t0=time.time()
    try:
        data=build_model()
        model_state["recalc_finished_at"]=time.strftime("%Y-%m-%d %H:%M:%S")
        with live_cache_lock:
            live_cache["data"]=data
            live_cache["issue"]=data.get("issue") if isinstance(data,dict) else None
        print(f"[CACHE] model rebuilt issue={data.get('issue')} in {time.time()-t0:.2f}s",flush=True)
        return data
    except Exception as e:
        print(f"[CACHE] model rebuild failed: {type(e).__name__}: {e}",flush=True)
        return previous
    finally:
        with live_cache_lock:
            live_cache["building"]=False

def model():
    """Always return the current memory snapshot immediately."""
    with live_cache_lock:
        data=live_cache.get("data")
        building=live_cache.get("building")
    if data is not None:
        return data
    if not building:
        # First boot only. Build synchronously once.
        return rebuild_live_cache() or {"issue":None,"count":0,"recalculating":True}
    return {"issue":None,"count":0,"recalculating":True}


@app.get("/")
def home():
    return render_template_string(INDEX_HTML)

@app.get("/api/health")
def health():
    with history_cache_lock:
        count=history_cache.get("total",0)
    return jsonify({"ok":True,"ready":background_state.get("boot_ready",False),
                    "model_building":bool(live_cache.get("building")),
                    "stats_building":background_state.get("stats_building",False),
                    "long_prior_ready":bool(long_prior.get("ready")),
                    "long_prior_rows":int(long_prior.get("total",0)),
                    "db":DB,"sqlite_mode":"WAL","telegram":bool(BOT_TOKEN),
                    "telegram_mode":"webhook","webhook_base":WEBHOOK_BASE_URL,"count":count})

@app.get("/api/prediction")
def prediction():
    # Cached live endpoint: normally no full-history calculation happens here.
    resp=jsonify(model())
    resp.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
    return resp

def _build_stats_background():
    if background_state.get("stats_building"):
        return
    background_state["stats_building"]=True
    try:
        r=recent_rows(900)
        # Keep this modest on the free instance. It is background diagnostics,
        # never allowed to block the web page.
        val=backtest_stats(r,6)
        print(f"[STATS] refreshed n={val.get('n')} issue={r[0]['issue'] if r else None}",flush=True)
    except Exception as e:
        print(f"[STATS] failed: {type(e).__name__}: {e}",flush=True)
    finally:
        background_state["stats_building"]=False

@app.get("/api/stats")
def stats_api():
    # Never run a historical backtest inside an HTTP request.
    val=stats_cache.get("value")
    if val is None:
        val={"n":0,"hit24":0.0,"err24":0.0,"hitMain":0.0,"errMain":0.0,
             "hitZ":0.0,"errZ":0.0,"hitPingte":0.0,"errPingte":0.0,
             "profile":model_state.get("profile") or "平衡","building":True}
        if not background_state.get("stats_building"):
            threading.Thread(target=_build_stats_background,daemon=True,name="stats-builder").start()
    return jsonify(val)

@app.get("/api/history")
def history():
    try:
        limit=max(20,min(int(request.args.get("limit","200")),500))
    except Exception:
        limit=200
    with history_cache_lock:
        total=history_cache.get("total",0)
        items=list(history_cache.get("items",[]))[:limit]
        loaded_at=history_cache.get("loaded_at","")
    # If cache is unexpectedly empty, rebuild once.
    if not items:
        try:
            refresh_history_cache()
            with history_cache_lock:
                total=history_cache.get("total",0)
                items=list(history_cache.get("items",[]))[:limit]
                loaded_at=history_cache.get("loaded_at","")
        except Exception as e:
            return jsonify({"total":0,"items":[],"error":str(e)}),503
    resp=jsonify({"total":total,"items":items,"cache_time":loaded_at})
    resp.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
    return resp

@app.get("/api/export")
def export_history():
    try:
        limit=max(20,min(int(request.args.get("limit","20000")),30000))
    except Exception:
        limit=20000
    def _read():
        c=connect()
        try:
            rr=c.execute("""SELECT * FROM draws
                            ORDER BY CAST(issue AS INTEGER) DESC LIMIT ?""",(limit,)).fetchall()
            total=c.execute("SELECT COUNT(*) FROM draws").fetchone()[0]
            return total,rr
        finally:
            c.close()
    total,rr=_db_retry(_read)
    items=[{k:x[k] for k in x.keys()} for x in rr]
    return jsonify({"total":total,"items":items})

@app.get("/api/sync-status")
def sync_status():
    with history_cache_lock:
        count=history_cache.get("total",0)
    return jsonify({**sync_state,"history_count":count})

@app.post("/api/sync-history")
def sync_history_now():
    body=request.get_json(silent=True) or {}
    url=str(body.get("url") or HISTORY_SOURCE_URL or "").strip()
    n=sync_remote_history(url)
    refresh_all_caches()
    return jsonify({"ok":not bool(sync_state["last_error"]),"imported":n,**sync_state})


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

    # Preserve latest bot-collected history before takeover.
    sync_best_available_history()

    # Make the site usable immediately. Do NOT wait for model/backtest here.
    try:
        refresh_history_cache()
    except Exception as e:
        print(f"[BOOT] history cache failed: {type(e).__name__}: {e}",flush=True)
    initialize_quick_live_cache()
    background_state["boot_ready"]=True

    # Webhook can now receive new draws.
    if BOT_TOKEN:
        threading.Thread(target=webhook_keeper,daemon=True,name="telegram-webhook-keeper").start()

    # Live model first, then full-history prior in parallel. Neither blocks the site.
    threading.Thread(target=rebuild_live_cache,daemon=True,name="initial-model-build").start()
    threading.Thread(target=build_long_prior,daemon=True,name="full-history-prior").start()

boot()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=PORT)
