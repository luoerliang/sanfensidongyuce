import os, re, csv, sqlite3, threading, time, math, statistics
from collections import Counter, defaultdict
from flask import Flask, jsonify, render_template_string
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

DB = os.getenv("DB_PATH", "history.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", "10000"))

app = Flask(__name__)
db_lock = threading.Lock()

INDEX_HTML = """<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>三分彩动态统计</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;margin:0;background:#f5f6f8;color:#111}
main{max-width:760px;margin:auto;padding:18px}.card{background:#fff;border-radius:16px;padding:18px;margin:12px 0;box-shadow:0 2px 10px #0000000d}
h1{font-size:22px}.muted{color:#777;font-size:13px}.nums{display:flex;flex-wrap:wrap;gap:8px}
.ball{border-radius:10px;padding:9px 11px;background:#eef0f3;font-weight:700}.big{font-size:18px}
.tag{display:inline-block;padding:7px 10px;border-radius:12px;background:#eef0f3;margin:4px}
.ok{color:#18794e}.bad{color:#b42318}
</style></head><body><main>
<h1>三分彩 · 动态统计分析</h1>
<div class="card"><div class="muted">最新已入库期号</div><div id="issue" class="big">加载中…</div><div id="count" class="muted"></div></div>
<div class="card"><h3>22个动态特码候选</h3><div id="sp" class="nums"></div></div>
<div class="card"><h3>4码</h3><div id="code" class="nums"></div></div>
<div class="card"><h3>4肖</h3><div id="z"></div></div>
<div class="card"><div id="tg" class="muted"></div><div class="muted">波色仅保存展示，不参与特码/4码评分。输出是历史统计候选，不代表确定性预测。</div></div>
<script>
async function load(){try{let r=await fetch('/api/prediction');let d=await r.json();
issue.textContent=d.issue||'暂无数据';count.textContent='历史期数：'+d.count;
sp.innerHTML=d.special22.map(x=>'<span class="ball">'+x+'</span>').join('');
code.innerHTML=d.codes4.map(x=>'<span class="ball">'+x+'</span>').join('');
z.innerHTML=d.zodiac4.map(x=>'<span class="tag">'+x+'</span>').join('');
tg.textContent=d.telegram?'Telegram：已配置':'Telegram：未配置 BOT_TOKEN';
}catch(e){issue.textContent='读取失败';}} load();setInterval(load,15000);
</script></main></body></html>"""

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
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    nums=None
    for line in lines:
        # 支持官方机器人常见的 01~09 前导零格式，以及 1~9 / 10~49
        vals=re.findall(r"(?<!\d)(?:0?[1-9]|[1-4]\d)(?!\d)", line)
        if len(vals)==7:
            cand=[int(x) for x in vals]
            if len(set(cand))==7 and all(1<=n<=49 for n in cand):
                nums=cand
                break
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
        return changed

def all_rows():
    c=connect(); r=c.execute("SELECT * FROM draws ORDER BY CAST(issue AS INTEGER) DESC").fetchall(); c.close(); return r

def exp_weight(i,half_life):
    return 0.5 ** (i/max(half_life,1))

def model():
    r=all_rows()
    if not r:return {"issue":None,"count":0,"special22":[],"codes4":[],"zodiac4":[],"telegram":bool(BOT_TOKEN)}
    numbers=range(1,50)

    # Ensemble: multiple horizons + recency decay + long-term shrinkage + omission.
    special_score={n:0.0 for n in numbers}
    horizons=[(30,10,1.35),(80,25,1.15),(200,60,0.95),(500,160,0.70),(1500,500,0.45)]
    for horizon,half,coef in horizons:
        rr=r[:min(horizon,len(r))]
        freq=Counter()
        for i,x in enumerate(rr):
            freq[x["special"]]+=exp_weight(i,half)
        mean=(sum(freq.values())/49.0) if rr else 0
        for n in numbers:
            # standardized-ish excess, stabilized to avoid tiny-window explosions
            special_score[n]+=coef*(freq[n]-mean)/math.sqrt(mean+1.0)

    # Long-history Bayesian shrinkage.
    full=Counter(x["special"] for x in r)
    total=len(r)
    expected=total/49.0
    for n in numbers:
        special_score[n]+=0.35*(full[n]-expected)/math.sqrt(expected+4.0)

    # Omission: capped and weak so it cannot dominate frequency/trend.
    last_seen={n:len(r) for n in numbers}
    for i,x in enumerate(r):
        n=x["special"]
        if last_seen[n]==len(r): last_seen[n]=i
    for n in numbers:
        special_score[n]+=0.18*min(last_seen[n],80)/80.0

    # Main-number context is deliberately weak; colors are never referenced.
    for i,x in enumerate(r[:300]):
        w=exp_weight(i,80)*0.08
        for j in range(1,7):
            special_score[x[f"n{j}"]]+=w

    top22=sorted(numbers,key=lambda n:(-special_score[n],n))[:22]

    # 4-code ensemble uses all seven numeric positions, independent of color.
    code_score={n:0.0 for n in numbers}
    for horizon,half,coef in [(30,10,1.25),(100,30,1.0),(300,90,.75),(1000,300,.45)]:
        for i,x in enumerate(r[:min(horizon,len(r))]):
            w=coef*exp_weight(i,half)
            for j in range(1,7): code_score[x[f"n{j}"]]+=w
            code_score[x["special"]]+=1.15*w
    codes=sorted(numbers,key=lambda n:(-code_score[n],n))[:4]

    # Zodiac ensemble.
    zscore=defaultdict(float)
    for horizon,half,coef in [(30,10,1.3),(100,30,1.0),(300,90,.7),(1000,300,.4)]:
        for i,x in enumerate(r[:min(horizon,len(r))]):
            w=coef*exp_weight(i,half)
            for k in ["z1","z2","z3","z4","z5","z6","z7"]:
                if x[k]: zscore[normalize_z(x[k])]+=w
    zodiac=sorted(zscore,key=lambda z:(-zscore[z],z))[:4]

    return {"issue":r[0]["issue"],"count":len(r),
            "special22":[f"{n:02d}" for n in sorted(top22)],
            "codes4":[f"{n:02d}" for n in sorted(codes)],
            "zodiac4":zodiac,"telegram":bool(BOT_TOKEN)}

@app.get("/")
def home(): return render_template_string(INDEX_HTML)

@app.get("/api/health")
def health(): return jsonify({"ok":True,"db":DB,"telegram":bool(BOT_TOKEN),"count":len(all_rows())})

@app.get("/api/prediction")
def prediction(): return jsonify(model())

async def cmd_id(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")

async def cmd_status(update:Update,context:ContextTypes.DEFAULT_TYPE):
    m=model()
    await update.message.reply_text(f"运行正常\\n历史期数: {m['count']}\\n最新期号: {m['issue']}")

async def receive(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    sender = update.effective_user
    sender_name = (sender.username if sender else None) or (sender.full_name if sender else "unknown")
    sender_is_bot = bool(getattr(sender, "is_bot", False)) if sender else False
    print(f"[TG] chat={update.effective_chat.id} sender={sender_name} is_bot={sender_is_bot} text={update.message.text[:160]!r}", flush=True)

    if ALLOWED_CHAT_ID and str(update.effective_chat.id) != ALLOWED_CHAT_ID:
        print(f"[TG] ignored: chat id does not match ALLOWED_CHAT_ID={ALLOWED_CHAT_ID}", flush=True)
        return

    p=parse_draw(update.message.text)
    if not p:
        print("[TG] received but parser did not recognize a complete draw", flush=True)
        return

    issue,nums,zs,colors=p
    print(f"[TG] parsed issue={issue} nums={nums} zodiac={zs} colors={colors}", flush=True)
    if add_draw(issue,nums,zs,colors,update.message.text):
        print(f"[TG] inserted issue={issue}", flush=True)
        # 避免与官方开奖机器人形成 bot-to-bot 回复循环；只有真人消息才回复确认。
        if not sender_is_bot:
            try:
                await update.message.reply_text(f"已入库 {issue}，统计结果已更新。")
            except Exception as e:
                print(f"[TG] inserted but reply failed: {type(e).__name__}: {e}", flush=True)
    else:
        print(f"[TG] duplicate/invalid issue={issue}, not inserted", flush=True)

async def post_init(application):
    # Removes stale webhook so long polling can work.
    await application.bot.delete_webhook(drop_pending_updates=False)

def tg_worker():
    if not BOT_TOKEN:
        print("BOT_TOKEN not configured; web service will still run.",flush=True);return
    try:
        a=ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()
        a.add_handler(CommandHandler("id",cmd_id))
        a.add_handler(CommandHandler("status",cmd_status))
        a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,receive))
        a.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False, stop_signals=None)
    except Exception as e:
        print(f"Telegram worker failed: {type(e).__name__}: {e}",flush=True)

def boot():
    init_db()
    import_history_once()
    if BOT_TOKEN:
        threading.Thread(target=tg_worker, daemon=True, name="telegram-worker").start()

boot()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=PORT)
