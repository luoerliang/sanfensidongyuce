
import os, re, sqlite3, threading, time
from flask import Flask, jsonify, render_template_string
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

DB = os.getenv("DB_PATH", "/var/data/history.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
PREDICT_INTERVAL = int(os.getenv("PREDICT_INTERVAL", "30"))

app = Flask(__name__)
INDEX_HTML = '\n<!doctype html><html lang="zh-CN"><head>\n<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n<title>澳门三分彩动态分析</title>\n<style>\nbody{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;margin:0;background:#f5f6f8;color:#111}\nmain{max-width:760px;margin:auto;padding:18px}.card{background:#fff;border-radius:16px;padding:18px;margin:12px 0;box-shadow:0 2px 10px #0000000d}\nh1{font-size:22px}.muted{color:#777;font-size:13px}.nums{display:flex;flex-wrap:wrap;gap:8px}\n.ball{border-radius:10px;padding:9px 11px;background:#eef0f3;font-weight:700}.big{font-size:18px}\n.tag{display:inline-block;padding:7px 10px;border-radius:12px;background:#eef0f3;margin:4px}\n</style></head><body><main>\n<h1>澳门三分彩 · 动态分析</h1>\n<div class="card"><div class="muted">最新已接收期号</div><div id="issue" class="big">加载中…</div><div id="count" class="muted"></div></div>\n<div class="card"><h3>22个动态特码</h3><div id="sp" class="nums"></div></div>\n<div class="card"><h3>4码</h3><div id="code" class="nums"></div></div>\n<div class="card"><h3>4肖</h3><div id="z"></div></div>\n<div class="card"><div class="muted">说明：波色只保存，不参与特码和4码评分。结果为历史统计模型，不代表确定性预测。</div></div>\n<script>\nasync function load(){let r=await fetch(\'/api/prediction\');let d=await r.json();\ndocument.querySelector(\'#issue\').textContent=d.issue||\'暂无数据\';\ndocument.querySelector(\'#count\').textContent=\'历史期数：\'+d.count;\ndocument.querySelector(\'#sp\').innerHTML=d.special22.map(x=>\'<span class="ball">\'+x+\'</span>\').join(\'\');\ndocument.querySelector(\'#code\').innerHTML=d.codes4.map(x=>\'<span class="ball">\'+x+\'</span>\').join(\'\');\ndocument.querySelector(\'#z\').innerHTML=d.zodiac4.map(x=>\'<span class="tag">\'+x+\'</span>\').join(\'\');\n} load(); setInterval(load,15000);\n</script></main></body></html>\n'
lock = threading.Lock()

RED = "🔴"
GREEN = "🟢"
BLUE = "🔵"

def db():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS draws(
        issue TEXT PRIMARY KEY,
        n1 INTEGER,n2 INTEGER,n3 INTEGER,n4 INTEGER,n5 INTEGER,n6 INTEGER,special INTEGER,
        z1 TEXT,z2 TEXT,z3 TEXT,z4 TEXT,z5 TEXT,z6 TEXT,z7 TEXT,
        c1 TEXT,c2 TEXT,c3 TEXT,c4 TEXT,c5 TEXT,c6 TEXT,c7 TEXT,
        raw TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.commit(); c.close()

def import_csv():
    if not os.path.exists("history.csv"):
        return
    c = db()
    try:
        with open("history.csv","r",encoding="utf-8-sig",newline="") as f:
            rows = csv.DictReader(f)
            for r in rows:
                issue = (r.get("期号") or "").strip()
                nums = []
                for k in ["正码1","正码2","正码3","正码4","正码5","正码6","特码"]:
                    try: nums.append(int(r.get(k,"")))
                    except: nums.append(None)
                if not issue or any(x is None for x in nums): continue
                zs=[(r.get(k) or "").strip() for k in ["正码1生肖","正码2生肖","正码3生肖","正码4生肖","正码5生肖","正码6生肖"]]
                z7=(r.get("生肖") or "").strip()
                cs=[(r.get("波色") or "").strip()]*7
                c.execute("""INSERT OR IGNORE INTO draws
                (issue,n1,n2,n3,n4,n5,n6,special,z1,z2,z3,z4,z5,z6,z7,
                 c1,c2,c3,c4,c5,c6,c7,raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [issue,*nums,*zs,z7,*cs,"imported"])
        c.commit()
    finally: c.close()

def parse_message(text):
    m = re.search(r"第\s*[:：]\s*(\d+)\s*期", text)
    if not m:
        m = re.search(r"第\s*(\d+)\s*期", text)
    if not m: return None
    issue=m.group(1)

    lines=[x.strip() for x in text.splitlines() if x.strip()]
    nums=None; zline=None; cline=None
    for line in lines:
        if re.fullmatch(r"\s*\d+(?:\s+\d+){6}\s*", line):
            nums=[int(x) for x in line.split()]
        if sum(line.count(x) for x in ["馬","龙","龍","牛","虎","兔","蛇","羊","猴","鸡","雞","狗","猪","豬","鼠"]) >= 5:
            zline=line
        if any(x in line for x in [RED,GREEN,BLUE]):
            cline=[x for x in line if x in [RED,GREEN,BLUE]]
    if not nums or len(nums)!=7:
        return None
    zs=re.findall(r"[鼠牛虎兔龙龍蛇马馬羊猴鸡雞狗猪豬]", zline or "")
    if len(zs)!=7:
        zs=[""]*7
    if not cline or len(cline)!=7:
        cline=[""]*7
    # Official format in user's example: first 6 are 正码, last is 特码.
    return issue, nums, zs, cline

def add_draw(issue, nums, zs, cs, raw):
    c=db()
    try:
        c.execute("""INSERT OR IGNORE INTO draws
        (issue,n1,n2,n3,n4,n5,n6,special,z1,z2,z3,z4,z5,z6,z7,
         c1,c2,c3,c4,c5,c6,c7,raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [issue,*nums[:6],nums[6],*zs,*cs,raw])
        c.commit()
        return c.total_changes > 0
    finally: c.close()

def rows():
    c=db()
    r=c.execute("SELECT * FROM draws ORDER BY issue DESC").fetchall()
    c.close(); return r

def score_prediction():
    r=rows()
    if not r: return {"issue":None,"count":0,"special22":[],"codes4":[],"zodiac4":[]}
    # newest-to-oldest; dynamic multi-window frequency/trend model.
    nums=range(1,50)
    windows=[20,50,100,300,1000]
    sp={n:0.0 for n in nums}
    for w in windows:
        rr=r[:min(w,len(r))]
        for i,x in enumerate(rr):
            age=i
            weight=1/(1+age/12)
            for n in nums:
                if x["special"]==n: sp[n]+=2.5*weight
                if n in [x[f"n{j}"] for j in range(1,7)]: sp[n]+=0.35*weight
    # Long-term stabilizer + omission component, intentionally not using color.
    for x in r:
        for n in nums:
            if x["special"]==n: sp[n]+=0.25
    ranked=sorted(nums,key=lambda n:(-sp[n],n))[:22]
    special22=sorted(ranked)

    code_score={n:0.0 for n in nums}
    for w in [20,50,100,300]:
        rr=r[:min(w,len(r))]
        for i,x in enumerate(rr):
            weight=1/(1+i/15)
            for j in range(1,7):
                code_score[x[f"n{j}"]]+=weight
            code_score[x["special"]]+=0.8*weight
    codes4=sorted(sorted(nums,key=lambda n:(-code_score[n],n))[:4])

    zodiac={}
    for w in [20,50,100,300]:
        rr=r[:min(w,len(r))]
        for i,x in enumerate(rr):
            weight=1/(1+i/15)
            for k in ["z1","z2","z3","z4","z5","z6","z7"]:
                z=x[k]
                if z: zodiac[z]=zodiac.get(z,0)+weight
    zodiac4=sorted(zodiac,key=lambda z:(-zodiac[z],z))[:4]
    return {"issue":r[0]["issue"],"count":len(r),"special22":[f"{n:02d}" for n in special22],
            "codes4":[f"{n:02d}" for n in codes4],"zodiac4":zodiac4}

@app.get("/")
def index(): return render_template_string(INDEX_HTML)

@app.get("/api/prediction")
def prediction(): return jsonify(score_prediction())

@app.get("/api/health")
def health(): return jsonify({"ok":True,"count":score_prediction()["count"]})

async def telegram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    if ALLOWED_CHAT_ID and str(update.message.chat_id) != ALLOWED_CHAT_ID: return
    parsed=parse_message(update.message.text)
    if not parsed: return
    issue,nums,zs,cs=parsed
    add_draw(issue,nums,zs,cs,update.message.text)

def run_tg():
    if not BOT_TOKEN:
        return
    application=ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_handler))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":
    init_db()
    import_csv()
    threading.Thread(target=run_tg,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))
