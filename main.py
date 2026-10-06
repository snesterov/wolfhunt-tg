"""
🐺 WOLFHUNT PRO — 24/7 AUTONOMOUS CLOUD BACKEND
Высокопроизводительный сервер автоматизации Telegram и ВКонтакте (Render).
Строгий 4-тактный цикл: Истории х3 (Приоритет №1) + Посты х1 (разбавка).
"""

import asyncio
import os
import random
import json
from datetime import datetime, timezone, timedelta
import aiohttp
from aiohttp import web
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError
from telethon.tl import functions, types

# ==============================================================================
# 1. TELEGRAM BACKEND (MTPROTO ENGINE 24/7)
# ==============================================================================
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

SESSION_FILE = "wolfhunt_tg_session"
SESSION_STR_FILE = "session_string.txt"
TG_STATE_FILE = "wolfhunt_tg_db.json"
DAILY_TG_LIMIT = 150

client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

tg_state = {
    "phone": None,
    "phone_code_hash": None,
    "is_authorized": False,
    "user": None,
    "is_running": False,
    "reactions_today": 0,
    "views_today": 0,
    "reactions_all_time": 0,
    "views_all_time": 0,
    "reactions_list": ["❤️", "🔥", "👍"],
    "last_date": str(datetime.now().date()),
    "logs": []
}

seen_tg_stories = set()
tg_hunter_task = None

def load_tg_data():
    global tg_state
    if os.path.exists(TG_STATE_FILE):
        try:
            with open(TG_STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                tg_state.update(saved)
                print(f"[TG Cloud] Загружено состояние: {tg_state.get('reactions_all_time', 0)} реакций за всё время")
        except Exception as e:
            print(f"[TG Cloud] Ошибка чтения {TG_STATE_FILE}: {e}")

def save_tg_data():
    try:
        to_save = {
            "is_authorized": tg_state.get("is_authorized", False),
            "user": tg_state.get("user"),
            "is_running": tg_state.get("is_running", False),
            "reactions_today": tg_state.get("reactions_today", 0),
            "views_today": tg_state.get("views_today", 0),
            "reactions_all_time": tg_state.get("reactions_all_time", 0),
            "views_all_time": tg_state.get("views_all_time", 0),
            "last_date": tg_state.get("last_date", str(datetime.now().date())),
            "reactions_list": tg_state.get("reactions_list", ["❤️", "🔥", "👍"]),
            "logs": tg_state.get("logs", [])[-50:]
        }
        with open(TG_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[TG Cloud] Ошибка сохранения {TG_STATE_FILE}: {e}")

def add_tg_log(text, log_type="info"):
    now_time = datetime.now().strftime("%H:%M:%S")
    entry = {"time": now_time, "text": text, "type": log_type}
    tg_state["logs"].append(entry)
    if len(tg_state["logs"]) > 50:
        tg_state["logs"].pop(0)
    print(f"[{now_time}] [TG {log_type.upper()}] {text}")

async def keep_alive_loop():
    """Фоновый страж против засыпания сервиса на Render (каждые 9 минут)"""
    await asyncio.sleep(30)
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "https://wolfhunt-tg.onrender.com/api/tg/status")
    print(f"🛡 Keep-alive монитор активен для: {external_url}")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(external_url, timeout=15) as resp:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [KEEP-ALIVE] Ping status: {resp.status}")
        except Exception as e:
            print(f"[KEEP-ALIVE NOTICE] {e}")
        await asyncio.sleep(540)

async def tg_hunter_loop():
    add_tg_log("▶ Охота на истории Telegram запущена!", "success")
    while tg_state["is_running"]:
        try:
            today = str(datetime.now().date())
            if tg_state["last_date"] != today:
                tg_state["last_date"] = today
                tg_state["reactions_today"] = 0
                tg_state["views_today"] = 0
                add_tg_log("🔄 Новый день: суточный счетчик Telegram сброшен (0/150)", "info")

            if tg_state["reactions_today"] >= DAILY_TG_LIMIT:
                now = datetime.now()
                tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
                wait_sec = int((tomorrow - now).total_seconds()) + 30
                add_tg_log(f"🛑 Лимит {DAILY_TG_LIMIT} исчерпан. Пауза до 00:00 ({wait_sec//3600}ч)", "warn")
                await asyncio.sleep(min(wait_sec, 3600))
                continue

            stories_data = await client(functions.stories.GetAllStoriesRequest())
            users_map = {}
            if hasattr(stories_data, 'users') and stories_data.users:
                for u in stories_data.users:
                    name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
                    if not name:
                        name = f"@{u.username}" if getattr(u, 'username', None) else f"id{u.id}"
                    users_map[u.id] = name

            new_count = 0
            seen_users_this_round = set()
            for peer_stories in stories_data.peer_stories:
                if not tg_state["is_running"] or tg_state["reactions_today"] >= DAILY_TG_LIMIT:
                    break
                peer = peer_stories.peer
                if not isinstance(peer, types.PeerUser):
                    continue
                user_id = peer.user_id
                if user_id in seen_users_this_round:
                    continue

                for story in peer_stories.stories:
                    if not tg_state["is_running"] or tg_state["reactions_today"] >= DAILY_TG_LIMIT:
                        break
                    story_key = f"{user_id}_{story.id}"
                    if story_key in seen_tg_stories:
                        continue
                    if getattr(story, 'out', False) or getattr(story, 'sent_reaction', None) is not None:
                        seen_tg_stories.add(story_key)
                        continue

                    # Просмотр истории
                    await client(functions.stories.ReadStoriesRequest(peer=peer, max_id=story.id))
                    tg_state["views_today"] += 1
                    tg_state["views_all_time"] = tg_state.get("views_all_time", 0) + 1
                    save_tg_data()

                    # Реакция
                    emoji = random.choice(tg_state["reactions_list"])
                    await client(functions.stories.SendReactionRequest(
                        peer=peer,
                        story_id=story.id,
                        reaction=types.ReactionEmoji(emoticon=emoji)
                    ))
                    seen_tg_stories.add(story_key)
                    seen_users_this_round.add(user_id)
                    tg_state["reactions_today"] += 1
                    tg_state["reactions_all_time"] = tg_state.get("reactions_all_time", 0) + 1
                    save_tg_data()
                    new_count += 1
                    contact_name = users_map.get(user_id, f"Пользователь {user_id}")
                    pause = random.randint(25, 45)
                    add_tg_log(f"{emoji} Реакция: {contact_name} ({tg_state['reactions_today']}/{DAILY_TG_LIMIT})", "success")
                    await asyncio.sleep(pause)
                    break

            if new_count == 0:
                add_tg_log("👁 Все свежие истории уже отсмотрены. Следующая проверка через 3 мин.", "info")
                await asyncio.sleep(180)

        except FloodWaitError as e:
            add_tg_log(f"⏳ Пауза FloodWait: {e.seconds} сек", "warn")
            await asyncio.sleep(e.seconds + 10)
        except Exception as e:
            add_tg_log(f"Ошибка охоты Telegram: {e}", "warn")
            await asyncio.sleep(60)

# ==============================================================================
# 2. VK 24/7 AUTONOMOUS CLOUD ENGINE (STRICT 4-TACT CYCLE)
# ==============================================================================
VK_DATA_FILE = "wolfhunt_vk_users.json"
LATEST_EXTENSION_VERSION = "2.1.0"
EXTENSION_DOWNLOAD_URL = "https://wolfhunt-tg.onrender.com/downloads/WOLFHUNT_CHROME_EXTENSION.zip"
EXTENSION_UPDATE_TITLE = "Обновление WolfHunt PRO v2.1.0!"
EXTENSION_UPDATE_DESC = "Автономное облако 24/7. Строгий 4-тактный цикл: Истории х3 (Приоритет №1) + Посты х1. Защита от Flood Control."

VK_STATE = {
    "vk_user_id": 49239823,
    "vk_token": "",
    "vk_name": "Сергей Нестеров",
    "vk_screen_name": "id49239823",
    "vk_running": False,
    "vk_today_date": "",
    "vk_today_stories": 0,
    "vk_today_posts": 0,
    "vk_all_time_stories": 0,
    "vk_all_time_posts": 0,
    "vk_all_time_total": 0,
    "vk_phase": 0,
    "seen_stories": [],
    "seen_posts": []
}

VK_LOGS = []

def load_vk_data():
    global VK_STATE, VK_LOGS
    if os.path.exists(VK_DATA_FILE):
        try:
            with open(VK_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Если база в формате старого мультипользовательского словаря, берем первого/активного
                    if "vk_token" not in data and len(data) > 0:
                        first_k = next(iter(data))
                        data = data[first_k]
                    VK_STATE.update(data)
                print(f"[VK Cloud] База загружена. Пользователь: {VK_STATE.get('vk_name')} (id{VK_STATE.get('vk_user_id')}), всего действий: {VK_STATE.get('vk_all_time_total', 0)}")
        except Exception as e:
            print(f"[VK Cloud] Ошибка загрузки базы {VK_DATA_FILE}: {e}")

def save_vk_data():
    try:
        to_save = {
            "vk_user_id": VK_STATE.get("vk_user_id"),
            "vk_token": VK_STATE.get("vk_token", ""),
            "vk_name": VK_STATE.get("vk_name", "Пользователь"),
            "vk_screen_name": VK_STATE.get("vk_screen_name", ""),
            "vk_running": VK_STATE.get("vk_running", False),
            "vk_today_date": VK_STATE.get("vk_today_date", ""),
            "vk_today_stories": VK_STATE.get("vk_today_stories", 0),
            "vk_today_posts": VK_STATE.get("vk_today_posts", 0),
            "vk_all_time_stories": VK_STATE.get("vk_all_time_stories", 0),
            "vk_all_time_posts": VK_STATE.get("vk_all_time_posts", 0),
            "vk_all_time_total": VK_STATE.get("vk_all_time_stories", 0) + VK_STATE.get("vk_all_time_posts", 0),
            "vk_phase": VK_STATE.get("vk_phase", 0),
            "seen_stories": VK_STATE.get("seen_stories", [])[-500:],
            "seen_posts": VK_STATE.get("seen_posts", [])[-500:]
        }
        with open(VK_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[VK Cloud] Ошибка сохранения базы {VK_DATA_FILE}: {e}")

def append_vk_log(l_type: str, msg: str):
    time_str = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%H:%M:%S")
    entry = {"time": time_str, "type": l_type, "text": msg}
    VK_LOGS.append(entry)
    if len(VK_LOGS) > 60:
        VK_LOGS.pop(0)
    print(f"[{time_str}] [VK {l_type.upper()}] {msg}")

async def call_vk_api(session: aiohttp.ClientSession, method: str, params: dict) -> dict:
    params["v"] = "5.131"
    url = f"https://api.vk.com/method/{method}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://vk.com/"
    }
    timeout = aiohttp.ClientTimeout(total=12)
    try:
        async with session.post(url, data=params, headers=headers, timeout=timeout) as resp:
            data = await resp.json(content_type=None)
            if data and "error" in data:
                err = data["error"]
                err_code = err.get("error_code")
                err_msg = err.get("error_msg", "")
                if err_code == 6:
                    await asyncio.sleep(2.5)
                elif err_code == 9 or "flood" in err_msg.lower():
                    append_vk_log("warn", f"⏳ [VK Защита] Мягкая пауза 60с (Код 9: Flood control). Охота возобновится автоматически.")
            return data
    except Exception as e:
        return {"error": {"error_msg": str(e), "error_code": -1}}

async def run_vk_tact_stories(session: aiohttp.ClientSession, u: dict) -> bool:
    token = u.get("vk_token")
    if not token:
        return False
    append_vk_log("info", "👁 [Фаза: Истории] Поиск свежих историй друзей...")
    res = await call_vk_api(session, "stories.get", {"access_token": token, "extended": "1", "fields": "first_name,last_name"})
    if "error" in res:
        err_code = res["error"].get("error_code")
        if err_code == 9:
            await asyncio.sleep(60)
        elif err_code == 5:
            append_vk_log("warn", "🛑 [Токен ВК истек] Срок действия токена завершился. Авторизуйтесь заново.")
            u["vk_running"] = False
            save_vk_data()
        return False

    if "response" not in res or not res["response"].get("items"):
        append_vk_log("info", "🔍 [Истории] Свежих историй друзей сейчас нет. Ожидание публикаций...")
        return False

    items = res["response"]["items"]
    profiles = {p["id"]: p for p in res["response"].get("profiles", [])}
    seen_stories = u.setdefault("seen_stories", [])

    for author in items:
        owner_id = author.get("id") or author.get("owner_id")
        stories_list = author.get("stories", [])
        if not stories_list:
            continue
        fresh_story = stories_list[-1]
        s_id = fresh_story["id"]
        seen_key = f"{owner_id}_{s_id}"
        if seen_key in seen_stories:
            continue

        p_info = profiles.get(owner_id, {})
        fn = (p_info.get("first_name", "") + " " + p_info.get("last_name", "")).strip() or f"id{owner_id}"

        act_res = await call_vk_api(session, "stories.sendInteraction", {
            "access_token": token,
            "owner_id": owner_id,
            "story_id": s_id,
            "message": "❤"
        })
        if "error" in act_res:
            err_code = act_res["error"].get("error_code")
            if err_code == 9:
                await asyncio.sleep(60)
                return False

        seen_stories.append(seen_key)
        if len(seen_stories) > 500:
            seen_stories.pop(0)

        u["vk_today_stories"] = u.get("vk_today_stories", 0) + 1
        u["vk_all_time_stories"] = u.get("vk_all_time_stories", 0) + 1
        u["vk_all_time_total"] = u.get("vk_all_time_stories", 0) + u.get("vk_all_time_posts", 0)
        save_vk_data()
        append_vk_log("success", f"🔥 [Истории] Охота: {fn} ❤")
        return True

    append_vk_log("info", "🔍 [Истории] Все доступные истории друзей уже отсмотрены.")
    return False

async def run_vk_tact_posts(session: aiohttp.ClientSession, u: dict) -> bool:
    token = u.get("vk_token")
    if not token:
        return False
    append_vk_log("info", "🔍 [Фаза: Посты] Поиск свежих записей друзей...")
    
    # Сначала пробуем получить свежие посты друзей напрямую
    items = []
    fr_res = await call_vk_api(session, "friends.get", {
        "access_token": token,
        "count": "25",
        "order": "hints",
        "fields": "first_name,last_name"
    })
    if "response" in fr_res and fr_res["response"].get("items"):
        friends = fr_res["response"]["items"]
        random.shuffle(friends)
        for fr in friends[:6]:
            fr_id = fr.get("id")
            if not fr_id:
                continue
            w_res = await call_vk_api(session, "wall.get", {
                "access_token": token,
                "owner_id": fr_id,
                "count": "3"
            })
            if "response" in w_res and w_res["response"].get("items"):
                for p in w_res["response"]["items"]:
                    p["_author_name"] = f"{fr.get('first_name', '')} {fr.get('last_name', '')}".strip()
                    items.append(p)
            if len(items) >= 5:
                break

    if not items:
        # Fallback на newsfeed.get
        nf_res = await call_vk_api(session, "newsfeed.get", {
            "access_token": token,
            "filters": "post",
            "count": "10"
        })
        if "response" in nf_res and nf_res["response"].get("items"):
            items = nf_res["response"]["items"]

    if not items:
        append_vk_log("info", "🔍 [Посты] Свежих записей для лайка сейчас нет.")
        return False

    seen_posts = u.setdefault("seen_posts", [])
    for p in items:
        owner_id = p.get("source_id") or p.get("owner_id")
        post_id = p.get("post_id") or p.get("id")
        if not owner_id or not post_id or owner_id <= 0:
            continue
        p_key = f"{owner_id}_{post_id}"
        if p_key in seen_posts:
            continue
        likes_info = p.get("likes", {})
        if likes_info.get("user_likes") == 1:
            seen_posts.append(p_key)
            continue

        like_res = await call_vk_api(session, "likes.add", {
            "access_token": token,
            "type": "post",
            "owner_id": owner_id,
            "item_id": post_id
        })
        if "error" in like_res:
            err_code = like_res["error"].get("error_code")
            if err_code == 9:
                await asyncio.sleep(60)
                return False
            continue

        seen_posts.append(p_key)
        if len(seen_posts) > 500:
            seen_posts.pop(0)

        u["vk_today_posts"] = u.get("vk_today_posts", 0) + 1
        u["vk_all_time_posts"] = u.get("vk_all_time_posts", 0) + 1
        u["vk_all_time_total"] = u.get("vk_all_time_stories", 0) + u.get("vk_all_time_posts", 0)
        save_vk_data()
        author_name = p.get("_author_name") or f"id{owner_id}"
        append_vk_log("success", f"❤ [Посты] Разбавка: Лайк к записи {author_name}")
        return True

    return False

async def vk_cloud_hunter_worker():
    print("🚀 [VK Cloud Engine] Автономный воркер 24/7 запущен!")
    await asyncio.sleep(5)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                u = VK_STATE
                if u.get("vk_running") and u.get("vk_token"):
                    msk_now = datetime.now(timezone.utc) + timedelta(hours=3)
                    today_str = msk_now.strftime("%Y-%m-%d")

                    # 1. Сброс счетчиков в 00:00 МСК
                    if u.get("vk_today_date") != today_str:
                        u["vk_today_date"] = today_str
                        u["vk_today_stories"] = 0
                        u["vk_today_posts"] = 0
                        u["vk_auto_paused_limit"] = False
                        save_vk_data()
                        append_vk_log("success", "🚀 Новый день (00:00 МСК)! Счетчики сброшены, охота 24/7 активна ✅")

                    # 2. Суточный лимит 300 действий
                    total_today = u.get("vk_today_stories", 0) + u.get("vk_today_posts", 0)
                    if total_today >= 300:
                        if not u.get("vk_auto_paused_limit"):
                            u["vk_auto_paused_limit"] = True
                            save_vk_data()
                            append_vk_log("warn", f"🛑 [Суточный лимит 300] Пауза на ночь ({total_today} действий). Автостарт в 00:00 МСК! 🌙")
                        await asyncio.sleep(600)
                        continue

                    # 3. Строгий 4-тактный цикл: Истории х3 (Приоритет №1) + Посты х1 (разбавка)
                    phase = u.get("vk_phase", 0)
                    u["vk_phase"] = (phase + 1) % 4
                    save_vk_data()

                    if phase == 0:
                        append_vk_log("info", "🎯 [Такт 1/4: Истории] Охота на истории (Приоритет №1)...")
                        await run_vk_tact_stories(session, u)
                    elif phase == 1:
                        append_vk_log("info", "🎯 [Такт 2/4: Истории] Охота на истории (Приоритет №1)...")
                        await run_vk_tact_stories(session, u)
                    elif phase == 2:
                        append_vk_log("info", "🎯 [Такт 3/4: Истории] Охота на истории (Приоритет №1)...")
                        await run_vk_tact_stories(session, u)
                    else:
                        append_vk_log("info", "📰 [Такт 4/4: Посты] Разбавка ленты постом...")
                        await run_vk_tact_posts(session, u)

                    # 4. Безопасная пауза 25-45 сек
                    pause = random.randint(25, 45)
                    await asyncio.sleep(pause)
                else:
                    await asyncio.sleep(10)
            except Exception as e:
                print(f"[VK Cloud Hunter Exception]: {e}")
                await asyncio.sleep(15)

# ==============================================================================
# 3. REST API ENDPOINTS
# ==============================================================================

# --- VK HANDLERS ---
async def handle_vk_auth(request: web.Request):
    data = await request.json()
    token = data.get("token", "").strip()
    if not token:
        return web.json_response({"error": "token required"}, status=400)
    async with aiohttp.ClientSession() as session:
        res = await call_vk_api(session, "users.get", {"access_token": token, "fields": "screen_name"})
        if "response" not in res or not res["response"]:
            return web.json_response({"error": "Недействительный токен ВКонтакте"}, status=401)
        u_info = res["response"][0]
        u_id = u_info["id"]
        fn = f"{u_info.get('first_name', '')} {u_info.get('last_name', '')}".strip()
        sn = u_info.get("screen_name", f"id{u_id}")

        VK_STATE["vk_user_id"] = u_id
        VK_STATE["vk_token"] = token
        VK_STATE["vk_name"] = fn
        VK_STATE["vk_screen_name"] = sn
        VK_STATE["vk_running"] = True
        VK_STATE["vk_today_date"] = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%d")
        save_vk_data()

        append_vk_log("success", f"✔ Профиль успешно подключен: {fn} (@{sn}) ✅")
        return web.json_response({
            "status": "ok",
            "user_id": u_id,
            "name": fn,
            "screen_name": sn
        })

async def handle_vk_status(request: web.Request):
    u = VK_STATE
    is_auth = bool(u.get("vk_token"))
    return web.json_response({
        "status": "ok",
        "is_authorized": is_auth,
        "is_running": u.get("vk_running", False),
        "user_id": u.get("vk_user_id"),
        "name": u.get("vk_name", "Пользователь"),
        "screen_name": u.get("vk_screen_name", ""),
        "today_stories": u.get("vk_today_stories", 0),
        "today_posts": u.get("vk_today_posts", 0),
        "today_total": u.get("vk_today_stories", 0) + u.get("vk_today_posts", 0),
        "all_time_stories": u.get("vk_all_time_stories", 0),
        "all_time_posts": u.get("vk_all_time_posts", 0),
        "all_time_total": u.get("vk_all_time_stories", 0) + u.get("vk_all_time_posts", 0),
        "extension_version": LATEST_EXTENSION_VERSION,
        "latest_extension_version": LATEST_EXTENSION_VERSION,
        "has_update": False,
        "update_url": EXTENSION_DOWNLOAD_URL,
        "update_title": EXTENSION_UPDATE_TITLE,
        "update_desc": EXTENSION_UPDATE_DESC,
        "logs": VK_LOGS
    })

async def handle_vk_toggle(request: web.Request):
    data = await request.json()
    action = data.get("action", "toggle")
    if action == "start":
        VK_STATE["vk_running"] = True
        append_vk_log("success", "🚀 ВК Хантер запущен на сервере Render (24/7)! Первый такт через 3 с.")
    elif action == "stop":
        VK_STATE["vk_running"] = False
        append_vk_log("warn", "⏸ ВК Хантер приостановлен пользователем.")
    else:
        VK_STATE["vk_running"] = not VK_STATE.get("vk_running", False)
        st_text = "запущен" if VK_STATE["vk_running"] else "на паузе"
        append_vk_log("info", f"🔄 Состояние ВК Хантера переключено: {st_text}")
    save_vk_data()
    return web.json_response({"status": "ok", "is_running": VK_STATE["vk_running"]})

async def handle_vk_logout(request: web.Request):
    VK_STATE["vk_running"] = False
    VK_STATE["vk_token"] = ""
    save_vk_data()
    append_vk_log("info", "🚪 Профиль ВКонтакте отключен.")
    return web.json_response({"status": "ok"})

async def handle_vk_sync(request: web.Request):
    """Синхронизация с расширением Chrome или сайтом"""
    try:
        data = await request.json()
        if data.get("token") and not VK_STATE.get("vk_token"):
            VK_STATE["vk_token"] = data["token"]
            if data.get("name"): VK_STATE["vk_name"] = data["name"]
            if data.get("nick"): VK_STATE["vk_screen_name"] = data["nick"]
            save_vk_data()

        return web.json_response({
            "status": "ok",
            "is_running": VK_STATE.get("vk_running", False),
            "today_stories": VK_STATE.get("vk_today_stories", 0),
            "today_posts": VK_STATE.get("vk_today_posts", 0),
            "today_total": VK_STATE.get("vk_today_stories", 0) + VK_STATE.get("vk_today_posts", 0),
            "all_time_stories": VK_STATE.get("vk_all_time_stories", 0),
            "all_time_posts": VK_STATE.get("vk_all_time_posts", 0),
            "all_time_total": VK_STATE.get("vk_all_time_stories", 0) + VK_STATE.get("vk_all_time_posts", 0),
            "extension_version": LATEST_EXTENSION_VERSION,
            "latest_extension_version": LATEST_EXTENSION_VERSION,
            "has_update": False,
            "update_url": EXTENSION_DOWNLOAD_URL,
            "update_title": EXTENSION_UPDATE_TITLE,
            "update_desc": EXTENSION_UPDATE_DESC
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_vk_like_once(request: web.Request):
    """Разовый тестовый лайк"""
    async with aiohttp.ClientSession() as session:
        done = await run_vk_tact_stories(session, VK_STATE)
    return web.json_response({"status": "ok", "done": done})

async def handle_vk_proxy(request: web.Request):
    """CORS-прокси для методов VK API из браузера"""
    try:
        body = await request.json()
        method = body.get("method", "")
        token = body.get("access_token", "") or VK_STATE.get("vk_token", "")
        params = body.get("params", {})
        if not method or not token:
            return web.json_response({"error": "method and access_token required"}, status=400)
        params["access_token"] = token
        params["v"] = params.get("v", "5.131")
        url = f"https://api.vk.com/method/{method}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_vk_stories_proxy(request: web.Request):
    """CORS-прокси для чтения историй VK"""
    try:
        token = request.query.get("access_token", "") or VK_STATE.get("vk_token", "")
        if not token:
            return web.json_response({"error": "access_token required"}, status=400)
        async with aiohttp.ClientSession() as session:
            url = "https://api.vk.com/method/stories.get"
            params = {"access_token": token, "extended": "1", "fields": "first_name,last_name", "v": "5.131"}
            async with session.post(url, data=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# --- TELEGRAM HANDLERS ---
async def handle_tg_status(request: web.Request):
    return web.json_response({
        "status": "ok",
        "is_authorized": tg_state["is_authorized"],
        "is_running": tg_state["is_running"],
        "user": tg_state["user"],
        "reactions_today": tg_state["reactions_today"],
        "views_today": tg_state["views_today"],
        "reactions_all_time": tg_state.get("reactions_all_time", 0),
        "views_all_time": tg_state.get("views_all_time", 0),
        "daily_limit": DAILY_TG_LIMIT,
        "logs": tg_state["logs"]
    })

async def handle_tg_send_code(request: web.Request):
    try:
        data = await request.json()
        phone = data.get("phone", "").strip()
        if not phone:
            return web.json_response({"error": "phone required"}, status=400)
        await client.connect()
        res = await client.send_code_request(phone)
        tg_state["phone"] = phone
        tg_state["phone_code_hash"] = res.phone_code_hash
        add_tg_log(f"Код подтверждения отправлен на номер {phone}", "info")
        return web.json_response({"status": "ok", "phone_code_hash": res.phone_code_hash})
    except Exception as e:
        add_tg_log(f"Ошибка отправки кода Telegram: {e}", "warn")
        return web.json_response({"error": str(e)}, status=500)

async def handle_tg_verify_code(request: web.Request):
    try:
        data = await request.json()
        code = data.get("code", "").strip()
        phone = tg_state.get("phone")
        phone_code_hash = tg_state.get("phone_code_hash")
        if not phone or not code or not phone_code_hash:
            return web.json_response({"error": "phone, code and phone_code_hash required"}, status=400)
        try:
            user = await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            return web.json_response({"status": "2fa_required"})
        me = await client.get_me()
        tg_state["is_authorized"] = True
        tg_state["user"] = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name or "",
            "username": me.username or ""
        }
        # Сохраняем сессию
        if isinstance(client.session, StringSession):
            with open(SESSION_STR_FILE, "w", encoding="utf-8") as sf:
                sf.write(client.session.save())
        save_tg_data()
        add_tg_log(f"✔ Telegram успешно авторизован: {me.first_name}", "success")
        return web.json_response({"status": "ok", "user": tg_state["user"]})
    except Exception as e:
        add_tg_log(f"Ошибка верификации кода: {e}", "warn")
        return web.json_response({"error": str(e)}, status=500)

async def handle_tg_auth_2fa(request: web.Request):
    try:
        data = await request.json()
        password = data.get("password", "").strip()
        await client.sign_in(password=password)
        me = await client.get_me()
        tg_state["is_authorized"] = True
        tg_state["user"] = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name or "",
            "username": me.username or ""
        }
        if isinstance(client.session, StringSession):
            with open(SESSION_STR_FILE, "w", encoding="utf-8") as sf:
                sf.write(client.session.save())
        save_tg_data()
        add_tg_log(f"✔ 2FA успешно пройдена: {me.first_name}", "success")
        return web.json_response({"status": "ok", "user": tg_state["user"]})
    except Exception as e:
        add_tg_log(f"Ошибка 2FA: {e}", "warn")
        return web.json_response({"error": str(e)}, status=500)

async def handle_tg_toggle(request: web.Request):
    global tg_hunter_task
    if not tg_state["is_authorized"]:
        return web.json_response({"error": "not authorized"}, status=400)
    tg_state["is_running"] = not tg_state["is_running"]
    save_tg_data()
    if tg_state["is_running"]:
        if tg_hunter_task is None or tg_hunter_task.done():
            tg_hunter_task = asyncio.create_task(tg_hunter_loop())
        add_tg_log("▶ Telegram Хантер запущен 24/7!", "success")
    else:
        if tg_hunter_task and not tg_hunter_task.done():
            tg_hunter_task.cancel()
        add_tg_log("⏸ Telegram Хантер приостановлен.", "warn")
    return web.json_response({"status": "ok", "is_running": tg_state["is_running"]})

async def handle_tg_logout(request: web.Request):
    global tg_hunter_task
    tg_state["is_running"] = False
    if tg_hunter_task and not tg_hunter_task.done():
        tg_hunter_task.cancel()
    try:
        if client.is_connected():
            await client.log_out()
    except Exception:
        pass
    tg_state["is_authorized"] = False
    tg_state["user"] = None
    tg_state["phone"] = None
    tg_state["phone_code_hash"] = None
    save_tg_data()
    for fname in [f"{SESSION_FILE}.session", f"{SESSION_FILE}.session-journal", SESSION_STR_FILE]:
        if os.path.exists(fname):
            try:
                os.remove(fname)
            except Exception:
                pass
    add_tg_log("🚪 Telegram сессия очищена.", "info")
    return web.json_response({"status": "ok"})

async def handle_tg_like_once(request: web.Request):
    """Разовый тестовый лайк в Telegram"""
    try:
        stories_data = await client(functions.stories.GetAllStoriesRequest())
        if hasattr(stories_data, 'peer_stories') and stories_data.peer_stories:
            for ps in stories_data.peer_stories:
                if isinstance(ps.peer, types.PeerUser) and ps.stories:
                    st = ps.stories[-1]
                    await client(functions.stories.ReadStoriesRequest(peer=ps.peer, max_id=st.id))
                    emoji = random.choice(tg_state["reactions_list"])
                    await client(functions.stories.SendReactionRequest(
                        peer=ps.peer,
                        story_id=st.id,
                        reaction=types.ReactionEmoji(emoticon=emoji)
                    ))
                    tg_state["reactions_today"] += 1
                    tg_state["reactions_all_time"] = tg_state.get("reactions_all_time", 0) + 1
                    save_tg_data()
                    add_tg_log(f"⚡ Разовый тест Telegram: реакция {emoji}", "success")
                    return web.json_response({"status": "ok", "reacted": True, "emoji": emoji})
        return web.json_response({"status": "ok", "reacted": False, "message": "Свежих историй нет"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# --- STATIC & DOWNLOAD HANDLERS ---
async def handle_download_extension(request):
    for p in ["WOLFHUNT_CHROME_EXTENSION.zip", "downloads/WOLFHUNT_CHROME_EXTENSION.zip"]:
        if os.path.exists(p):
            return web.FileResponse(p, headers={
                "Content-Disposition": 'attachment; filename="WOLFHUNT_CHROME_EXTENSION.zip"'
            })
    return web.Response(text="Файл расширения временно недоступен", status=404)

async def handle_widget_js(request):
    js_code = """(async function() {
  try {
    let root = document.getElementById('wolfhunt-root') || document.getElementById('wolfhunt-container');
    if (!root) {
      root = document.createElement('div');
      root.id = 'wolfhunt-root';
      const target = document.querySelector('.t123') || document.querySelector('.r') || document.body;
      target.appendChild(root);
    }
    let html = null;
    try {
      const cdnRes = await fetch('https://cdn.jsdelivr.net/gh/snesterov/wolfhunt-tg@main/wolfhunt_tilda.html?v=' + Date.now());
      if (cdnRes.ok) html = await cdnRes.text();
    } catch(e) {}
    if (!html) {
      const res = await fetch('https://wolfhunt-tg.onrender.com/widget.html?v=' + Date.now());
      if (res.ok) html = await res.text();
    }
    if (html) {
      const range = document.createRange();
      const fragment = range.createContextualFragment(html);
      root.innerHTML = '';
      root.appendChild(fragment);
    }
  } catch(err) {
    console.error('[WolfHunt Dynamic Loader] Error:', err);
  }
})();"""
    return web.Response(text=js_code, content_type="application/javascript", headers={
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache, no-store, must-revalidate"
    })

async def handle_widget_html(request):
    html_path = os.path.join(os.path.dirname(__file__), "wolfhunt_tilda.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = "<div>WolfHunt Widget</div>"
    return web.Response(text=content, content_type="text/html", headers={
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache, no-store, must-revalidate"
    })

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=200)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as ex:
            resp = ex
        except Exception as e:
            resp = web.json_response({"error": str(e)}, status=500)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return resp

async def init_app():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/", lambda r: web.Response(text="🐺 WolfHunt Cloud Backend 24/7 Running!"))
    app.router.add_get("/widget.js", handle_widget_js)
    app.router.add_get("/widget.html", handle_widget_html)
    app.router.add_get("/downloads/WOLFHUNT_CHROME_EXTENSION.zip", handle_download_extension)
    app.router.add_get("/download/extension", handle_download_extension)

    # Telegram API
    app.router.add_get("/api/tg/status", handle_tg_status)
    app.router.add_post("/api/tg/send_code", handle_tg_send_code)
    app.router.add_post("/api/tg/verify_code", handle_tg_verify_code)
    app.router.add_post("/api/tg/auth_2fa", handle_tg_auth_2fa)
    app.router.add_post("/api/tg/toggle", handle_tg_toggle)
    app.router.add_post("/api/tg/logout", handle_tg_logout)
    app.router.add_post("/api/tg/like_once", handle_tg_like_once)

    # VK API
    app.router.add_post("/api/vk/auth", handle_vk_auth)
    app.router.add_get("/api/vk/status", handle_vk_status)
    app.router.add_post("/api/vk/toggle", handle_vk_toggle)
    app.router.add_post("/api/vk/logout", handle_vk_logout)
    app.router.add_post("/api/vk/sync", handle_vk_sync)
    app.router.add_get("/api/vk/sync", handle_vk_status)
    app.router.add_post("/api/vk/like_once", handle_vk_like_once)
    app.router.add_post("/api/vk/proxy", handle_vk_proxy)
    app.router.add_get("/api/vk/stories", handle_vk_stories_proxy)

    # Запуск баз и фоновых воркеров
    load_vk_data()
    load_tg_data()
    asyncio.create_task(keep_alive_loop())
    asyncio.create_task(vk_cloud_hunter_worker())

    # Восстановление сессии Telegram
    global client
    try:
        if os.path.exists(SESSION_STR_FILE):
            with open(SESSION_STR_FILE, "r", encoding="utf-8") as sf:
                s_str = sf.read().strip()
            if s_str:
                client = TelegramClient(StringSession(s_str), API_ID, API_HASH)
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            tg_state["is_authorized"] = True
            tg_state["user"] = {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name or "",
                "username": me.username or ""
            }
            add_tg_log(f"✔ Восстановлена сессия: {me.first_name} (@{me.username or me.id})", "success")
    except Exception as e:
        print("[Telegram Auth Notice]:", e)

    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 WolfHunt Cloud Backend запускается на порту {port}...")
    web.run_app(init_app(), host="0.0.0.0", port=port)
