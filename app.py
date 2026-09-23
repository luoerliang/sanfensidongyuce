import os, re, csv, sqlite3, threading, math, time
from collections import Counter, defaultdict
from flask import Flask, jsonify, render_template_string, request
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

DB = os.getenv("DB_PATH", "history.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", "10000"))

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
    <div class="sectionHead"><div class="sectionTitle">4肖 · 4码</div><div class="sectionHint">独立动态计算</div></div>
    <div class="combo">
      <div class="comboBox">
        <div class="comboTitle">4码</div>
        <div id="code" class="code4"></div>
      </div>
      <div class="comboBox">
        <div class="comboTitle">4肖</div>
        <div id="z" class="zodiac4"></div>
      </div>
    </div>
  </section>

  <section class="card">
    <div class="sectionHead"><div class="sectionTitle">近60期滚动回测</div><div class="sectionHint">命中 / 错误</div></div>
    <div class="stats">
      <div class="stat"><div class="statName">22码</div><div id="hit22" class="rate">--</div><div id="err22" class="err"></div></div>
      <div class="stat"><div class="statName">4码</div><div id="hit4" class="rate">--</div><div id="err4" class="err"></div></div>
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
  <div class="foot">号码颜色按六合彩标准红 / 蓝 / 绿波显示。波色仅用于展示，不进入特码与4码评分。命中率为历史滚动回测，不代表未来中奖概率。</div>
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
    code.innerHTML=balls(d.codes4||[]);
    z.innerHTML=(d.zodiac4||[]).map(x=>`<div class="zodiac">${x}</div>`).join('');
    latestZodiac.textContent=d.latest_special_zodiac?`特码生肖 ${d.latest_special_zodiac}`:'特码生肖 --';
    lastIngest.textContent=d.latest_created_at?`最后录入 ${d.latest_created_at}`:'实时录入';
    tg.textContent=d.telegram?'Telegram 已连接':'Telegram 未配置';
    const ad=d.adaptive||{};
    adaptiveInfo.textContent=`自适应换码 ${ad.changes??0} 个 · 当前敏感度目标 ${ad.target??0}`;
    const st=d.stats||{};
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
loadMain(); loadHistory();
setInterval(loadMain,10000);
setInterval(loadHistory,30000);
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

def _recent_volatility(r):
    """Measure how much the last 20 issues differ from the preceding 20.
    Used only to adjust responsiveness; no random swapping."""
    if len(r) < 45:
        return 0.5
    a = Counter(x["special"] for x in r[:20])
    b = Counter(x["special"] for x in r[20:40])
    diff = sum(abs(a.get(n,0)-b.get(n,0)) for n in range(1,50)) / 40.0
    return max(0.0, min(diff, 1.0))

def _base_special_scores(r):
    numbers=range(1,50)
    score={n:0.0 for n in numbers}
    # More sensitive short windows + long-term baseline.
    horizons=[(10,4,2.20),(20,7,1.85),(50,16,1.40),(100,32,1.00),(300,95,0.62),(1000,320,0.30)]
    for horizon,half,coef in horizons:
        rr=r[:min(horizon,len(r))]
        freq=Counter()
        for i,x in enumerate(rr):
            freq[x["special"]]+=exp_weight(i,half)
        mean=(sum(freq.values())/49.0) if rr else 0
        for n in numbers:
            score[n]+=coef*(freq[n]-mean)/math.sqrt(mean+1.0)

    # Recent acceleration: last 10 vs previous 30, and last 20 vs previous 60.
    for short,base,coef in [(10,30,1.15),(20,60,0.80)]:
        a=Counter(x["special"] for x in r[:min(short,len(r))])
        b=Counter(x["special"] for x in r[short:min(short+base,len(r))])
        al=max(1,min(short,len(r)))
        bl=max(1,min(base,max(0,len(r)-short)))
        for n in numbers:
            accel=a.get(n,0)/al - b.get(n,0)/bl
            score[n]+=coef*accel

    # Long-history shrinkage, intentionally modest.
    full=Counter(x["special"] for x in r)
    expected=len(r)/49.0
    for n in numbers:
        score[n]+=0.18*(full[n]-expected)/math.sqrt(expected+6.0)

    # Omission is weak and capped: never dominates.
    last_seen={n:len(r) for n in numbers}
    for i,x in enumerate(r):
        n=x["special"]
        if last_seen[n]==len(r):
            last_seen[n]=i
    for n in numbers:
        gap=min(last_seen[n],60)
        score[n]+=0.15*(gap/60.0)

    # Weak context from recent main numbers. Wave/color is never used.
    for i,x in enumerate(r[:120]):
        w=exp_weight(i,28)*0.035
        for j in range(1,7):
            score[x[f"n{j}"]]+=w
    return score

def _adaptive_top22(r):
    """Adaptive candidate selection.
    It compares the current ranking with the ranking one issue ago, then
    increases responsiveness when recent statistics are changing quickly.
    It does NOT use random numbers and does NOT force arbitrary replacements."""
    numbers=list(range(1,50))
    cur=_base_special_scores(r)
    ranked=sorted(numbers,key=lambda n:(-cur[n],n))
    if len(r)<80:
        return ranked[:22], {"changes":0,"target":0,"volatility":0.0}

    prev=_base_special_scores(r[1:])
    prev_set=set(sorted(numbers,key=lambda n:(-prev[n],n))[:22])

    # Score momentum from one issue to the next.
    delta={n:cur[n]-prev[n] for n in numbers}
    vol=_recent_volatility(r)
    # Dynamic responsiveness target shown to user. Usually ~3-8, but not forced.
    target=int(round(3 + vol*5))
    target=max(2,min(target,8))

    # Candidates near the 22-cut get momentum adjustment.
    cutoff=cur[ranked[21]]
    spread=max(abs(cur[ranked[10]]-cutoff),0.20)
    adjusted={}
    for n in numbers:
        boundary=1.0-max(0.0,min(abs(cur[n]-cutoff)/spread,1.0))
        momentum=delta[n]
        # More weight when the number is near the inclusion boundary.
        adjusted[n]=cur[n] + momentum*(1.2+1.8*vol)*boundary

        # Trend-sensitive stability: falling incumbents lose a little,
        # rising outsiders gain a little. This is data-driven, not random.
        if n in prev_set and momentum < 0:
            adjusted[n] += momentum*(0.55+vol)
        elif n not in prev_set and momentum > 0:
            adjusted[n] += momentum*(0.75+1.25*vol)

    top=sorted(numbers,key=lambda n:(-adjusted[n],n))[:22]
    changes=len(set(top)^prev_set)//2
    return top, {"changes":changes,"target":target,"volatility":round(vol,3)}

def predict_core(r):
    numbers=range(1,50)
    if not r:return [],[],[]

    top22, _meta = _adaptive_top22(r)

    # 4-code is also more responsive, but remains independent of wave/color.
    code_score={n:0.0 for n in numbers}
    for horizon,half,coef in [(10,4,2.0),(20,7,1.6),(50,16,1.15),(100,32,.85),(300,95,.48)]:
        rr=r[:min(horizon,len(r))]
        for i,x in enumerate(rr):
            w=coef*exp_weight(i,half)
            for j in range(1,7):
                code_score[x[f"n{j}"]]+=0.72*w
            code_score[x["special"]]+=1.35*w
    codes=sorted(numbers,key=lambda n:(-code_score[n],n))[:4]

    # Zodiac: same adaptive emphasis on recent windows.
    zscore=defaultdict(float)
    for horizon,half,coef in [(10,4,2.0),(20,7,1.6),(50,16,1.15),(100,32,.82),(300,95,.45)]:
        for i,x in enumerate(r[:min(horizon,len(r))]):
            w=coef*exp_weight(i,half)
            # Give special zodiac stronger influence than main-zodiac context.
            if x["z7"]:
                zscore[normalize_z(x["z7"])]+=1.55*w
            for k in ["z1","z2","z3","z4","z5","z6"]:
                if x[k]:
                    zscore[normalize_z(x[k])]+=0.45*w
    zodiac=sorted(zscore,key=lambda z:(-zscore[z],z))[:4]
    return top22,codes,zodiac

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
        return {"issue":None,"count":0,"special22":[],"codes4":[],"zodiac4":[],"telegram":bool(BOT_TOKEN),"stats":{}}
    top22,codes,zodiac=predict_core(r)
    _tmp22, adaptive_meta = _adaptive_top22(r)
    latest=r[0]
    latest_numbers=[latest[f"n{i}"] for i in range(1,7)] + [latest["special"]]
    try: next_issue=str(int(latest["issue"])+1)
    except Exception: next_issue=""
    return {
      "issue":latest["issue"],"next_issue":next_issue,"count":len(r),
      "latest_numbers":latest_numbers,
      "latest_special_zodiac":normalize_z(latest["z7"] or ""),
      "latest_created_at":latest["created_at"] or "",
      "special22":[f"{n:02d}" for n in sorted(top22)],
      "codes4":[f"{n:02d}" for n in sorted(codes)],
      "zodiac4":zodiac,
      "adaptive":adaptive_meta,
      "telegram":bool(BOT_TOKEN),
      "stats":backtest_stats(r,60)
    }

@app.get("/")
def home():
    return render_template_string(INDEX_HTML)

@app.get("/api/health")
def health():
    return jsonify({"ok":True,"db":DB,"telegram":bool(BOT_TOKEN),"count":len(all_rows())})

@app.get("/api/prediction")
def prediction():
    return jsonify(model())

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

async def cmd_id(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")

async def cmd_status(update:Update,context:ContextTypes.DEFAULT_TYPE):
    m=model()
    await update.message.reply_text(f"运行正常\\n历史期数: {m['count']}\\n最新期号: {m['issue']}")

async def receive(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    sender=update.effective_user
    sender_name=(sender.username if sender else None) or (sender.full_name if sender else "unknown")
    sender_is_bot=bool(getattr(sender,"is_bot",False)) if sender else False
    print(f"[TG] chat={update.effective_chat.id} sender={sender_name} is_bot={sender_is_bot} text={update.message.text[:160]!r}",flush=True)

    if ALLOWED_CHAT_ID and str(update.effective_chat.id)!=ALLOWED_CHAT_ID:
        print(f"[TG] ignored: chat id does not match ALLOWED_CHAT_ID={ALLOWED_CHAT_ID}",flush=True)
        return

    p=parse_draw(update.message.text)
    if not p:
        print("[TG] received but parser did not recognize a complete draw",flush=True)
        return
    issue,nums,zs,colors=p
    print(f"[TG] parsed issue={issue} nums={nums} zodiac={zs} colors={colors}",flush=True)
    if add_draw(issue,nums,zs,colors,update.message.text):
        print(f"[TG] inserted issue={issue}",flush=True)
        # 机器人开奖消息不回复，避免群内刷屏和 Flood control。
        if not sender_is_bot:
            try:
                await update.message.reply_text(f"已入库 {issue}，统计结果已更新。")
            except Exception as e:
                print(f"[TG] inserted but reply failed: {type(e).__name__}: {e}",flush=True)
    else:
        print(f"[TG] duplicate/invalid issue={issue}, not inserted",flush=True)

async def post_init(application):
    await application.bot.delete_webhook(drop_pending_updates=False)

def tg_worker():
    if not BOT_TOKEN:
        print("BOT_TOKEN not configured; web service will still run.",flush=True)
        return
    try:
        a=ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
        a.add_handler(CommandHandler("id",cmd_id))
        a.add_handler(CommandHandler("status",cmd_status))
        a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,receive))
        a.run_polling(allowed_updates=Update.ALL_TYPES,close_loop=False,stop_signals=None)
    except Exception as e:
        print(f"Telegram worker failed: {type(e).__name__}: {e}",flush=True)

def boot():
    init_db()
    import_history_once()
    if BOT_TOKEN:
        threading.Thread(target=tg_worker,daemon=True,name="telegram-worker").start()

boot()

if __name__=="__main__":
    app.run(host="0.0.0.0",port=PORT)
