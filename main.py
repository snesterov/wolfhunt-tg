"""
🐺 WOLFHUNT PRO — TELEGRAM BACKEND BRIDGE
Микросервер-мост между Tilda и Telegram MTProto API.
Позволяет клиентам авторизоваться прямо на сайте через телефон + код из Telegram.
"""

import asyncio
import os
import random
import re
from datetime import datetime, timedelta
import aiohttp
from aiohttp import web
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError
from telethon.tl import functions, types

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

SESSION_FILE = "wolfhunt_tg_session"
SESSION_STR_FILE = "session_string.txt"
DAILY_LIMIT = 150

client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

state = {
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

seen_stories = set()
hunter_task = None

TG_STATE_FILE = "wolfhunt_tg_db.json"

def load_tg_data():
    global state
    if os.path.exists(TG_STATE_FILE):
        try:
            with open(TG_STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                state.update(saved)
                print(f"[TG SaaS] Loaded persistent state from {TG_STATE_FILE}: {state.get('reactions_all_time', 0)} total reactions")
        except Exception as e:
            print(f"[TG SaaS] Error loading {TG_STATE_FILE}: {e}")

def save_tg_data():
    try:
        # Exclude unpickleable objects
        to_save = {
            "is_authorized": state.get("is_authorized", False),
            "user": state.get("user"),
            "is_running": state.get("is_running", False),
            "reactions_today": state.get("reactions_today", 0),
            "views_today": state.get("views_today", 0),
            "reactions_all_time": state.get("reactions_all_time", 0),
            "views_all_time": state.get("views_all_time", 0),
            "last_date": state.get("last_date", str(datetime.now().date())),
            "reactions_list": state.get("reactions_list", ["❤️", "🔥", "👍"]),
            "logs": state.get("logs", [])[-50:]
        }
        with open(TG_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[TG SaaS] Error saving {TG_STATE_FILE}: {e}")

def add_log(text, log_type="info"):
    now_time = datetime.now().strftime("%H:%M:%S")
    entry = {"time": now_time, "text": text, "type": log_type}
    state["logs"].append(entry)
    if len(state["logs"]) > 50:
        state["logs"].pop(0)
    print(f"[{now_time}] [{log_type.upper()}] {text}")

async def keep_alive_loop():
    """Фоновый страж против засыпания сервиса на Render (каждые 9 минут)"""
    await asyncio.sleep(30)
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "https://wolfhunt-tg.onrender.com/api/tg/status")
    print(f"🛡 Keep-alive монитор активен для: {external_url}")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(external_url, timeout=15) as resp:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [KEEP-ALIVE] Render ping status: {resp.status}")
        except Exception as e:
            print(f"[KEEP-ALIVE NOTICE] {e}")
        await asyncio.sleep(540) # 9 минут

async def hunter_loop():
    add_log("▶ Охота на истории Telegram запущена! Первый поиск историй мгновенно...", "success")
    while state["is_running"]:
        try:
            today = str(datetime.now().date())
            if state["last_date"] != today:
                state["last_date"] = today
                state["reactions_today"] = 0
                state["views_today"] = 0
                add_log("🔄 Новый день: суточный счетчик Telegram сброшен (0/150)", "info")

            if state["reactions_today"] >= DAILY_LIMIT:
                now = datetime.now()
                tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
                wait_sec = int((tomorrow - now).total_seconds()) + 30
                add_log(f"🛑 Лимит {DAILY_LIMIT} исчерпан. Пауза до 00:00 ({wait_sec//3600}ч)", "warn")
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
                if not state["is_running"] or state["reactions_today"] >= DAILY_LIMIT:
                    break
                peer = peer_stories.peer
                # ФИЛЬТР: ТОЛЬКО ЖИВЫЕ ЛЮДИ (КОНТАКТЫ), КАНАЛЫ ИГНОРИРУЕМ
                if not isinstance(peer, types.PeerUser):
                    continue
                user_id = peer.user_id
                if user_id in seen_users_this_round:
                    continue

                for story in peer_stories.stories:
                    if not state["is_running"] or state["reactions_today"] >= DAILY_LIMIT:
                        break
                    story_key = f"{user_id}_{story.id}"
                    if story_key in seen_stories:
                        continue
                    if getattr(story, 'out', False) or getattr(story, 'sent_reaction', None) is not None:
                        seen_stories.add(story_key)
                        continue

                    # Просмотр истории
                    await client(functions.stories.ReadStoriesRequest(peer=peer, max_id=story.id))
                    state["views_today"] += 1
                    state["views_all_time"] = state.get("views_all_time", 0) + 1
                    save_tg_data()

                    # Реакция - СТАВИТСЯ СРАЗУ!
                    emoji = random.choice(state["reactions_list"])
                    await client(functions.stories.SendReactionRequest(
                        peer=peer,
                        story_id=story.id,
                        reaction=types.ReactionEmoji(emoticon=emoji)
                    ))
                    seen_stories.add(story_key)
                    seen_users_this_round.add(user_id)
                    state["reactions_today"] += 1
                    state["reactions_all_time"] = state.get("reactions_all_time", 0) + 1
                    save_tg_data()
                    new_count += 1
                    contact_name = users_map.get(user_id, f"Пользователь {user_id}")
                    pause = random.randint(25, 45)
                    add_log(f"{emoji} Реакция: {contact_name} ({state['reactions_today']}/{DAILY_LIMIT})", "success")

                    # Пауза строго ПОСЛЕ совершенного действия
                    await asyncio.sleep(pause)
                    break # Переходим к следующему контакту для максимального охвата аудитории!

            if new_count == 0:
                add_log("👁 Все свежие истории уже отсмотрены. Следующая проверка через 3 мин.", "info")
                await asyncio.sleep(180)

        except FloodWaitError as e:
            add_log(f"⏳ Пауза FloodWait: {e.seconds} сек", "warn")
            await asyncio.sleep(e.seconds + 10)
        except Exception as e:
            add_log(f"Ошибка охоты: {e}", "warn")
            await asyncio.sleep(60)

# CORS MIDDLEWARE
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response(status=200)
    else:
        try:
            resp = await handler(request)
        except web.HTTPException as ex:
            resp = ex
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp

async def handle_status(request):
    return web.json_response({
        "status": "ok",
        "is_authorized": state["is_authorized"],
        "user": state["user"],
        "is_running": state["is_running"],
        "reactions_today": state["reactions_today"],
        "views_today": state["views_today"],
        "reactions_all_time": state.get("reactions_all_time", 0),
        "views_all_time": state.get("views_all_time", 0),
        "limit": DAILY_LIMIT,
        "logs": state["logs"][-15:]
    })

async def handle_send_code(request):
    data = await request.json()
    raw_phone = data.get("phone", "").strip()
    if not raw_phone:
        return web.json_response({"status": "error", "message": "Укажите номер телефона"}, status=400)

    digits = re.sub(r'\D', '', raw_phone)
    if len(digits) == 10:
        phone = "+7" + digits
    elif len(digits) == 11 and (digits.startswith("8") or digits.startswith("7")):
        phone = "+7" + digits[1:]
    elif raw_phone.startswith("+"):
        phone = "+" + digits
    else:
        phone = "+" + digits if digits else raw_phone

    try:
        if not client.is_connected():
            await client.connect()
        sent = await client.send_code_request(phone)
        state["phone"] = phone
        state["phone_code_hash"] = sent.phone_code_hash
        add_log(f"Код подтверждения запрошен для {phone}", "info")
        return web.json_response({"status": "ok", "message": "Код отправлен в Telegram"})
    except Exception as e:
        err_str = str(e)
        add_log(f"Ошибка запроса кода: {err_str}", "warn")
        user_msg = err_str
        if "wait of" in err_str.lower() or "flood" in err_str.lower():
            sec_match = re.search(r'(\d+)\s+seconds', err_str)
            sec_txt = f" (примерно {round(int(sec_match.group(1))/60)} мин.)" if sec_match else ""
            user_msg = f"⚠️ Telegram временно заблокировал частые запросы кодов (Flood Wait){sec_txt}. Подождите и не нажимайте кнопку!"
        elif "phone_number_invalid" in err_str.lower():
            user_msg = "⚠️ Неверный формат номера. Введите номер в международном формате (например, +79951234567)"
        elif "phone_number_banned" in err_str.lower():
            user_msg = "⚠️ Данный номер телефона заблокирован в Telegram."
        return web.json_response({"status": "error", "message": user_msg}, status=400)

async def handle_verify_code(request):
    data = await request.json()
    code = data.get("code", "").strip()
    password = data.get("password", "").strip()

    if not code:
        return web.json_response({"status": "error", "message": "Введите код из Telegram"}, status=400)

    try:
        if not client.is_connected():
            await client.connect()

        try:
            await client.sign_in(phone=state["phone"], code=code, phone_code_hash=state["phone_code_hash"])
        except SessionPasswordNeededError:
            if not password:
                return web.json_response({"status": "need_password", "message": "Требуется 2FA пароль"})
            await client.sign_in(password=password)

        me = await client.get_me()
        state["is_authorized"] = True
        state["user"] = {
            "id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name or "",
            "username": me.username or ""
        }

        # Вечное сохранение сессии через StringSession
        session_str = ""
        try:
            session_str = client.session.save()
            with open(SESSION_STR_FILE, "w", encoding="utf-8") as sf:
                sf.write(session_str)
        except Exception as e:
            print("Ошибка сохранения session_string:", e)

        add_log(f"✔ Профиль авторизован: {me.first_name} (@{me.username or me.id}) ✅", "success")
        return web.json_response({"status": "ok", "user": state["user"], "session_string": session_str})
    except PhoneCodeInvalidError:
        return web.json_response({"status": "error", "message": "⚠️ Неверный код подтверждения. Проверьте 5 цифр в чате Telegram."}, status=400)
    except Exception as e:
        err_str = str(e)
        user_msg = err_str
        if "phone_code_expired" in err_str.lower():
            user_msg = "⚠️ Срок действия кода истек. Нажмите «Получить код» повторно."
        elif "password_hash_invalid" in err_str.lower():
            user_msg = "⚠️ Неверный облачный пароль 2FA."
        return web.json_response({"status": "error", "message": user_msg}, status=400)

async def handle_restore_session(request):
    """Мгновенное бесшовное восстановление авторизации после перезагрузки Render"""
    global client
    data = await request.json()
    session_str = data.get("session_string", "").strip()
    if not session_str:
        return web.json_response({"status": "error", "message": "Строка сессии не передана"}, status=400)

    try:
        if client and client.is_connected():
            await client.disconnect()

        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            state["is_authorized"] = True
            state["user"] = {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name or "",
                "username": me.username or ""
            }
            try:
                with open(SESSION_STR_FILE, "w", encoding="utf-8") as sf:
                    sf.write(session_str)
            except Exception:
                pass
            add_log(f"✔ Сессия автоматически восстановлена: {me.first_name} (@{me.username or me.id}) ✅", "success")
            return web.json_response({"status": "ok", "user": state["user"]})
        else:
            return web.json_response({"status": "error", "message": "Сессия устарела"}, status=401)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_toggle(request):
    global hunter_task
    data = await request.json()
    action = data.get("action") # "start" или "stop"
    reactions = data.get("reactions")
    if reactions and isinstance(reactions, list):
        state["reactions_list"] = reactions

    if action == "start":
        if not state["is_authorized"]:
            return web.json_response({"status": "error", "message": "Сначала авторизуйте Telegram профиль"}, status=400)
        state["is_running"] = True
        if not hunter_task or hunter_task.done():
            hunter_task = asyncio.create_task(hunter_loop())
        return web.json_response({"status": "ok", "is_running": True})
    else:
        state["is_running"] = False
        if hunter_task and not hunter_task.done():
            hunter_task.cancel()
        add_log("⏹ Telegram Охота приостановлена.", "warn")
        return web.json_response({"status": "ok", "is_running": False})

async def handle_like_once(request):
    """Разовый лайк на одну историю без запуска автоохоты 24/7"""
    if not state["is_authorized"]:
        return web.json_response({"status": "error", "message": "Сначала авторизуйте Telegram профиль"}, status=400)

    try:
        if not client.is_connected():
            await client.connect()

        if state["reactions_today"] >= DAILY_LIMIT:
            return web.json_response({"status": "error", "message": f"Суточный лимит {DAILY_LIMIT} исчерпан"}, status=400)

        data = {}
        try:
            data = await request.json()
        except Exception:
            pass
        reactions = data.get("reactions")
        if reactions and isinstance(reactions, list) and len(reactions) > 0:
            state["reactions_list"] = reactions

        stories_data = await client(functions.stories.GetAllStoriesRequest())
        users_map = {}
        if hasattr(stories_data, 'users') and stories_data.users:
            for u in stories_data.users:
                name = f"{getattr(u, 'first_name', '') or ''} {getattr(u, 'last_name', '') or ''}".strip()
                if not name:
                    name = f"@{u.username}" if getattr(u, 'username', None) else f"id{u.id}"
                users_map[u.id] = name

        for peer_stories in stories_data.peer_stories:
            peer = peer_stories.peer
            if not isinstance(peer, types.PeerUser):
                continue
            user_id = peer.user_id

            for story in peer_stories.stories:
                story_key = f"{user_id}_{story.id}"
                if story_key in seen_stories:
                    continue
                if getattr(story, 'out', False) or getattr(story, 'sent_reaction', None) is not None:
                    seen_stories.add(story_key)
                    continue

                # Просмотр истории
                await client(functions.stories.ReadStoriesRequest(peer=peer, max_id=story.id))
                state["views_today"] += 1
                    state["views_all_time"] = state.get("views_all_time", 0) + 1
                    save_tg_data()

                # Реакция - строго РАЗОВО!
                emoji = random.choice(state["reactions_list"])
                await client(functions.stories.SendReactionRequest(
                    peer=peer,
                    story_id=story.id,
                    reaction=types.ReactionEmoji(emoticon=emoji)
                ))
                seen_stories.add(story_key)
                state["reactions_today"] += 1
                    state["reactions_all_time"] = state.get("reactions_all_time", 0) + 1
                    save_tg_data()
                contact_name = users_map.get(user_id, f"Пользователь {user_id}")
                add_log(f"⚡ Разовый лайк: {contact_name} {emoji} ({state['reactions_today']}/{DAILY_LIMIT})", "success")

                return web.json_response({
                    "status": "ok",
                    "reacted": True,
                    "contact": contact_name,
                    "emoji": emoji,
                    "reactions_today": state["reactions_today"],
                    "views_today": state["views_today"]
                })

        add_log("⚡ Разовый поиск: свежих непросмотренных историй друзей нет.", "info")
        return web.json_response({"status": "ok", "reacted": False, "message": "Свежих историй не найдено"})

    except Exception as e:
        add_log(f"Ошибка разового лайка: {e}", "warn")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_logout(request):
    global hunter_task
    state["is_running"] = False
    if hunter_task and not hunter_task.done():
        hunter_task.cancel()
    try:
        if client.is_connected():
            await client.log_out()
    except Exception:
        pass
    state["is_authorized"] = False
    state["user"] = None
    state["phone"] = None
    state["phone_code_hash"] = None
    for fname in [f"{SESSION_FILE}.session", f"{SESSION_FILE}.session-journal", SESSION_STR_FILE]:
        if os.path.exists(fname):
            try:
                os.remove(fname)
            except Exception:
                pass
    add_log("🚪 Профиль Telegram отключен (выход). Готов к новому входу.", "info")
    return web.json_response({"status": "ok", "message": "Сессия очищена"})

async def handle_vk_proxy(request):
    """Прокси для любых методов VK API — обходит CORS/JSONP ограничения браузера."""
    try:
        body = await request.json()
        method = body.get("method", "")
        token = body.get("access_token", "")
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


# ==============================================================================
# VK MULTI-TENANT CLOUD HUNTER (24/7 AUTONOMOUS BACKGROUND ENGINE)
# ==============================================================================
VK_USERS_FILE = "wolfhunt_vk_users.json"
LATEST_EXTENSION_VERSION = "2.0.1"
EXTENSION_DOWNLOAD_URL = "https://wolfhunt-tg.onrender.com/downloads/WOLFHUNT_CHROME_EXTENSION.zip"
EXTENSION_UPDATE_TITLE = "Доступно обновление расширения WolfHunt PRO v2.0.1!"
EXTENSION_UPDATE_DESC = "Сбор именинников 1 раз в сутки пачками по 5, защитные паузы и новый 3D-логотип Волка. Обновите папку расширения."

VK_USERS_DB = {}
VK_USER_LOGS = {}

def load_vk_data():
    global VK_USERS_DB
    if os.path.exists(VK_USERS_FILE):
        try:
            with open(VK_USERS_FILE, "r", encoding="utf-8") as f:
                VK_USERS_DB = json.load(f)
                for u in VK_USERS_DB.values():
                    u["vk_running"] = False
                print(f"[VK SaaS] Loaded {len(VK_USERS_DB)} active VK profiles from cloud storage (all paused by default)")
        except Exception as e:
            print(f"[VK SaaS] Error loading storage: {e}")

def save_vk_data():
    try:
        with open(VK_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(VK_USERS_DB, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[VK SaaS] Error saving storage: {e}")

def append_vk_user_log(user_key: str, l_type: str, msg: str):
    time_str = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%H:%M:%S")
    entry = {"time": time_str, "type": l_type, "text": msg}
    k = str(user_key)
    if k not in VK_USER_LOGS:
        VK_USER_LOGS[k] = []
    VK_USER_LOGS[k].append(entry)
    if len(VK_USER_LOGS[k]) > 50:
        VK_USER_LOGS[k].pop(0)

def parse_spintax(text: str, first_name: str = "друг") -> str:
    text = text.replace("%first_name%", first_name or "друг")
    safety = 10
    import re
    while "{" in text and "}" in text and safety > 0:
        safety -= 1
        text = re.sub(r"\{([^{}]+)\}", lambda m: random.choice(m.group(1).split("|")).strip(), text)
    return text

async def call_vk_api_cloud(session: aiohttp.ClientSession, method: str, params: dict) -> dict:
    params["v"] = "5.131"
    url = f"https://api.vk.com/method/{method}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://vk.com/"
    }
    try:
        async with session.post(url, data=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json(content_type=None)
            return data
    except Exception as e:
        return {"error": {"error_msg": str(e), "error_code": -1}}

async def run_vk_tact_stories(session: aiohttp.ClientSession, u: dict) -> bool:
    token = u["vk_token"]
    u_id = str(u["vk_user_id"])
    append_vk_user_log(u_id, "info", "👁 [Фаза: Истории] Поиск свежих историй друзей...")
    res = await call_vk_api_cloud(session, "stories.get", {"access_token": token, "extended": "1"})
    if "response" not in res or not res["response"].get("items"):
        return False
    items = res["response"]["items"]
    profiles = {p["id"]: p for p in res["response"].get("profiles", [])}
    for author in items:
        owner_id = author.get("id") or author.get("owner_id")
        stories_list = author.get("stories", [])
        if not stories_list: continue
        fresh_story = stories_list[-1]
        s_id = fresh_story["id"]
        seen_key = f"{owner_id}_{s_id}"
        seen_cache = u.setdefault("seen_stories", [])
        if seen_key in seen_cache: continue
        p_info = profiles.get(owner_id, {})
        fn = (p_info.get("first_name", "") + " " + p_info.get("last_name", "")).strip() or f"id{owner_id}"
        await call_vk_api_cloud(session, "stories.sendInteraction", {
            "access_token": token, "owner_id": owner_id, "story_id": s_id, "message": "❤"
        })
        seen_cache.append(seen_key)
        if len(seen_cache) > 500: seen_cache.pop(0)
        u["vk_today_stories"] = u.get("vk_today_stories", 0) + 1
        u["vk_all_time_stories"] = u.get("vk_all_time_stories", 0) + 1
        u["vk_all_time_total"] = u.get("vk_all_time_stories", 0) + u.get("vk_all_time_posts", 0)
        append_vk_user_log(u_id, "success", f"🔥 [Истории] Охота: {fn} ❤")
        save_vk_data()
        return True
    return False

async def run_vk_tact_birthdays(session: aiohttp.ClientSession, u: dict) -> bool:
    token = u["vk_token"]
    u_id = str(u["vk_user_id"])
    if not u.get("vk_bday_enabled", True): return False
    msk_now = datetime.now(timezone.utc) + timedelta(hours=3)
    if msk_now.hour < 6 or msk_now.hour > 22: return False
    cur_dm = f"{msk_now.day}.{msk_now.month}"
    cur_year = str(msk_now.year)
    today_str = msk_now.strftime("%Y-%m-%d")

    # 1. Сбор именинников ровно 1 раз в сутки
    if u.get("bday_cache_date") != today_str:
        res = await call_vk_api_cloud(session, "friends.get", {
            "access_token": token, "fields": "bdate,first_name,can_write_private_message"
        })
        bdays = []
        if "response" in res and res["response"].get("items"):
            for f in res["response"]["items"]:
                bdate = f.get("bdate", "")
                parts = bdate.split(".")
                if len(parts) >= 2 and f"{int(parts[0])}.{int(parts[1])}" == cur_dm:
                    bdays.append({"id": f["id"], "name": f.get("first_name", "друг"), "can_msg": f.get("can_write_private_message", 1) != 0})
        u["bday_cache"] = bdays
        u["bday_cache_date"] = today_str
        save_vk_data()
        if bdays:
            append_vk_user_log(u_id, "info", f"🎂 [День Рождения] База на сегодня сформирована: {len(bdays)} именинников. Отправка пачками до 5 в Такте №2.")
        else:
            append_vk_user_log(u_id, "info", "🎂 [День Рождения] База на сегодня проверена: именинников среди друзей нет.")

    bdays = u.get("bday_cache", [])
    if not bdays: return False

    congratulated = u.setdefault("vk_congratulated", [])
    bday_text = u.get("vk_bday_text", "{С днем рождения|С праздником}, %first_name%! {Всего самого наилучшего}! 🎂")

    # 2. Очередь не поздравленных на сегодня
    pending = [f for f in bdays if f"{cur_year}_{f['id']}" not in congratulated]
    if not pending:
        return False

    # 3. Отправка пачками до 5 за такт
    batch = pending[:5]
    sent_batch_count = 0
    append_vk_user_log(u_id, "info", f"🎂 [Такт 2/3: День Рождения] Отправка партии ({len(batch)} из {len(pending)} в очереди)...")

    for i, f in enumerate(batch):
        b_key = f"{cur_year}_{f['id']}"
        if not f.get("can_msg"):
            congratulated.append(b_key)
            continue
        try:
            msg = parse_spintax(bday_text, f["name"])
            await call_vk_api_cloud(session, "messages.send", {
                "access_token": token, "user_id": f["id"], "message": msg, "random_id": random.randint(1000000, 99999999)
            })
            congratulated.append(b_key)
            u["vk_bday_count"] = u.get("vk_bday_count", 0) + 1
            sent_batch_count += 1
            append_vk_user_log(u_id, "success", f"🎂 [Поздравление {sent_batch_count}/{len(batch)}]: {f['name']} ({msg[:30]}...)")
        except Exception as e:
            congratulated.append(b_key)
            append_vk_user_log(u_id, "warn", f"⚠️ Ошибка поздравления {f['name']}: {e}")

        if i < len(batch) - 1:
            await asyncio.sleep(4.0)

    save_vk_data()
    remaining = len(pending) - len(batch)
    if remaining > 0:
        append_vk_user_log(u_id, "info", f"🎂 [Такт 2/3: Партия завершена] Отправлено: {sent_batch_count}. Осталось в очереди на следующие такты: {remaining}.")
    else:
        append_vk_user_log(u_id, "success", f"🎂 [Такт 2/3: Именинники закрыты] Все поздравления на сегодня отправлены ({sent_batch_count})! ✅")
    return True

async def run_vk_tact_posts(session: aiohttp.ClientSession, u: dict) -> bool:
    token = u["vk_token"]
    u_id = str(u["vk_user_id"])
    append_vk_user_log(u_id, "info", "🔍 [Фаза: Посты] Поиск свежих записей друзей...")
    res = await call_vk_api_cloud(session, "newsfeed.get", {
        "access_token": token, "filters": "post", "count": "15"
    })
    if "response" not in res or not res["response"].get("items"): return False
    items = res["response"]["items"]
    seen_posts = u.setdefault("seen_posts", [])
    for p in items:
        owner_id = p.get("source_id") or p.get("owner_id")
        post_id = p.get("post_id")
        if not owner_id or owner_id <= 0 or not post_id: continue
        p_key = f"{owner_id}_{post_id}"
        if p_key in seen_posts: continue
        likes_info = p.get("likes", {})
        if likes_info.get("user_likes") == 1:
            seen_posts.append(p_key); continue
        await call_vk_api_cloud(session, "likes.add", {
            "access_token": token, "type": "post", "owner_id": owner_id, "item_id": post_id
        })
        seen_posts.append(p_key)
        if len(seen_posts) > 500: seen_posts.pop(0)
        u["vk_today_posts"] = u.get("vk_today_posts", 0) + 1
        u["vk_all_time_posts"] = u.get("vk_all_time_posts", 0) + 1
        u["vk_all_time_total"] = u.get("vk_all_time_stories", 0) + u.get("vk_all_time_posts", 0)
        append_vk_user_log(u_id, "success", f"❤ [Посты] Разбавка: Лайк к записи id{owner_id}")
        save_vk_data()
        return True
    return False

async def vk_multi_user_hunter_worker():
    print("🚀 [VK Cloud Engine] Мультипользовательский воркер 24/7 запущен!")
    await asyncio.sleep(5)
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                msk_now = datetime.now(timezone.utc) + timedelta(hours=3)
                today_str = msk_now.strftime("%Y-%m-%d")
                users_list = list(VK_USERS_DB.values())
                for u in users_list:
                    u_id = str(u.get("vk_user_id"))
                    if not u.get("vk_running") or not u.get("vk_token"): continue
                    if u.get("vk_today_date") != today_str:
                        u["vk_today_date"] = today_str
                        u["vk_today_stories"] = 0
                        u["vk_today_posts"] = 0
                        u["vk_auto_paused_limit"] = False
                        append_vk_user_log(u_id, "success", "🚀 Новый день (00:00 МСК)! Счетчики сброшены, охота 24/7 продолжается.")
                        save_vk_data()
                    total_likes = u.get("vk_today_stories", 0) + u.get("vk_today_posts", 0)
                    if total_likes >= 300:
                        if not u.get("vk_auto_paused_limit"):
                            u["vk_auto_paused_limit"] = True
                            append_vk_user_log(u_id, "warn", f"🛑 [Суточный лимит 300] Пауза на ночь ({total_likes} лайков). Автостарт в 00:00 МСК! 🌙")
                            save_vk_data()
                        continue
                    phase = u.get("vk_current_phase", 0)
                    u["vk_current_phase"] = (phase + 1) % 3
                    save_vk_data()
                    if phase == 0:
                        append_vk_user_log(u_id, "info", "🎯 [Такт 1/3: Истории] Охота на истории (Приоритет №1)...")
                        await run_vk_tact_stories(session, u)
                    elif phase == 1:
                        done = await run_vk_tact_birthdays(session, u)
                        if not done:
                            append_vk_user_log(u_id, "info", "👁 [Такт 2/3: Истории] Очередь именинников на сегодня пуста. Охота на истории (Приоритет №1)...")
                            await run_vk_tact_stories(session, u)
                    else:
                        append_vk_user_log(u_id, "info", "📰 [Такт 3/3: Посты] Разбавка ленты постом...")
                        await run_vk_tact_posts(session, u)
                    await asyncio.sleep(random.randint(2, 5))
            except Exception as e:
                print(f"[VK SaaS Worker Exception]: {e}")
            await asyncio.sleep(random.randint(25, 45))

# ==============================================================================
# VK REST API HANDLERS FOR TILDA
# ==============================================================================
async def handle_vk_auth(request: web.Request):
    data = await request.json()
    token = data.get("token", "").strip()
    if not token:
        return web.json_response({"error": "token required"}, status=400)
    async with aiohttp.ClientSession() as session:
        res = await call_vk_api_cloud(session, "users.get", {"access_token": token, "fields": "screen_name"})
        if "response" not in res or not res["response"]:
            return web.json_response({"error": "Недействительный токен ВКонтакте"}, status=401)
        u_info = res["response"][0]
        u_id = str(u_info["id"])
        fn = f"{u_info.get('first_name', '')} {u_info.get('last_name', '')}".strip()
        sn = u_info.get("screen_name", "")
        
        user_record = VK_USERS_DB.setdefault(u_id, {})
        user_record["vk_user_id"] = u_info["id"]
        user_record["vk_token"] = token
        user_record["vk_name"] = fn
        user_record["vk_screen_name"] = sn
        user_record["vk_running"] = True
        user_record["vk_today_date"] = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%d")
        save_vk_data()
        
        append_vk_user_log(u_id, "success", f"✔ Профиль успешно подключен к 24/7 облаку: {fn} (@{sn}) ✅")
        return web.json_response({
            "status": "ok",
            "user_id": u_info["id"],
            "name": fn,
            "screen_name": sn
        })

async def handle_vk_sync(request: web.Request):
    """Двусторонняя синхронизация между Chrome расширением и сайтом / базой."""
    try:
        data = await request.json()
        u_id = str(data.get("user_id", "")).strip()
        if not u_id:
            return web.json_response({"error": "user_id required"}, status=400)
            
        u = VK_USERS_DB.setdefault(u_id, {})
        u["vk_user_id"] = u_id
        if data.get("token"): u["vk_token"] = data["token"]
        if data.get("name"): u["vk_name"] = data["name"]
        if data.get("nick"): u["vk_screen_name"] = data["nick"]
        if "running" in data: u["vk_running"] = bool(data["running"])
        if "today_stories" in data: u["vk_today_stories"] = int(data["today_stories"])
        if "today_posts" in data: u["vk_today_posts"] = int(data["today_posts"])
        if "bday_count" in data: u["vk_bday_count"] = int(data["bday_count"])
        if "all_time_stories" in data:
            u["vk_all_time_stories"] = max(u.get("vk_all_time_stories", 0), int(data["all_time_stories"]))
        if "all_time_posts" in data:
            u["vk_all_time_posts"] = max(u.get("vk_all_time_posts", 0), int(data["all_time_posts"]))
        if "all_time_bdays" in data:
            u["vk_all_time_bdays"] = max(u.get("vk_all_time_bdays", 0), int(data["all_time_bdays"]))
        u["vk_all_time_total"] = u.get("vk_all_time_stories", 0) + u.get("vk_all_time_posts", 0)
        
        if data.get("bday_text_update"):
            u["vk_bday_text"] = data["bday_text_update"]
        if "bday_enabled_update" in data:
            u["vk_bday_enabled"] = bool(data["bday_enabled_update"])
            
        if data.get("logs") and isinstance(data["logs"], list):
            VK_USER_LOGS[u_id] = data["logs"][-50:]
            
        u["last_sync_time"] = datetime.now(timezone.utc).isoformat()
        u["client_mode"] = "chrome_extension_home_ip"
        save_vk_data()
        
        ext_ver = str(data.get("extension_version", "2.0.0")).strip()
        u["extension_version"] = ext_ver
        has_update = (ext_ver != LATEST_EXTENSION_VERSION)

        default_bday = "{С днем рождения|С праздником|Поздравляю с днем рождения}, %first_name%! {Желаю крепкого здоровья, энергии и грандиозных успехов|Всего самого наилучшего и исполнения желаний}! {🎂|🎉|🎁|🥂}"
        return web.json_response({
            "status": "ok",
            "user_id": u_id,
            "bday_text": u.get("vk_bday_text", default_bday),
            "bday_enabled": u.get("vk_bday_enabled", True),
            "is_running": u.get("vk_running", False),
            "tariff": u.get("tariff", "pro"),
            "today_stories": u.get("vk_today_stories", 0),
            "today_posts": u.get("vk_today_posts", 0),
            "today_bdays": u.get("vk_bday_count", 0),
            "today_total": u.get("vk_today_stories", 0) + u.get("vk_today_posts", 0),
            "all_time_stories": u.get("vk_all_time_stories", 0),
            "all_time_posts": u.get("vk_all_time_posts", 0),
            "all_time_bdays": u.get("vk_all_time_bdays", 0),
            "all_time_total": u.get("vk_all_time_total", 0),
            "extension_version": ext_ver,
            "latest_extension_version": LATEST_EXTENSION_VERSION,
            "has_update": has_update,
            "update_url": EXTENSION_DOWNLOAD_URL,
            "update_title": EXTENSION_UPDATE_TITLE,
            "update_desc": EXTENSION_UPDATE_DESC
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_vk_status(request: web.Request):
    u_id = request.query.get("user_id")
    token = request.query.get("access_token")
    if not u_id and token:
        for k, v in VK_USERS_DB.items():
            if v.get("vk_token") == token:
                u_id = k
                break
    if not u_id and VK_USERS_DB:
        u_id = next(iter(VK_USERS_DB))
    if not u_id or u_id not in VK_USERS_DB:
        return web.json_response({"status": "not_authorized", "is_running": False})
    u = VK_USERS_DB[u_id]
    logs = VK_USER_LOGS.get(u_id, [])
    default_bday = "{С днем рождения|С праздником|Поздравляю с днем рождения}, %first_name%! {Желаю крепкого здоровья, энергии и грандиозных успехов|Всего самого наилучшего и исполнения желаний}! {🎂|🎉|🎁|🥂}"
    ext_ver = u.get("extension_version", "")
    has_update = (ext_ver != "" and ext_ver != LATEST_EXTENSION_VERSION)

    return web.json_response({
        "status": "ok",
        "is_authorized": True,
        "is_running": u.get("vk_running", False),
        "user_id": u.get("vk_user_id"),
        "name": u.get("vk_name"),
        "screen_name": u.get("vk_screen_name"),
        "today_stories": u.get("vk_today_stories", 0),
        "today_posts": u.get("vk_today_posts", 0),
        "today_stories": u.get("vk_today_stories", 0),
        "today_posts": u.get("vk_today_posts", 0),
        "today_total": u.get("vk_today_stories", 0) + u.get("vk_today_posts", 0),
        "today_bdays": u.get("vk_bday_count", 0),
        "all_time_stories": u.get("vk_all_time_stories", 0),
        "all_time_posts": u.get("vk_all_time_posts", 0),
        "all_time_bdays": u.get("vk_all_time_bdays", 0),
        "all_time_total": u.get("vk_all_time_stories", 0) + u.get("vk_all_time_posts", 0),
        "bday_text": u.get("vk_bday_text", default_bday),
        "bday_enabled": u.get("vk_bday_enabled", True),
        "client_mode": u.get("client_mode", "chrome_extension_home_ip"),
        "last_sync_time": u.get("last_sync_time", ""),
        "extension_version": ext_ver,
        "latest_extension_version": LATEST_EXTENSION_VERSION,
        "has_update": has_update,
        "update_url": EXTENSION_DOWNLOAD_URL,
        "update_title": EXTENSION_UPDATE_TITLE,
        "update_desc": EXTENSION_UPDATE_DESC,
        "logs": logs
    })

async def handle_vk_toggle(request: web.Request):
    data = await request.json()
    u_id = str(data.get("user_id", "")).strip()
    if not u_id and VK_USERS_DB:
        u_id = next(iter(VK_USERS_DB))
    action = data.get("action", "toggle")
    if not u_id:
        u_id = "default_user"
    u = VK_USERS_DB.setdefault(u_id, {"vk_user_id": u_id})
    if action == "start":
        u["vk_running"] = True
        append_vk_user_log(u_id, "success", "🚀 ВК Хантер запущен (сигнал синхронизации)! Охота активна ✅")
    elif action == "stop":
        u["vk_running"] = False
        append_vk_user_log(u_id, "warn", "⏸ ВК Хантер приостановлен пользователем (сигнал синхронизации).")
    else:
        u["vk_running"] = not u.get("vk_running", False)
    save_vk_data()
    return web.json_response({"status": "ok", "is_running": u["vk_running"]})

async def handle_vk_save_settings(request: web.Request):
    data = await request.json()
    u_id = str(data.get("user_id", ""))
    if u_id not in VK_USERS_DB:
        return web.json_response({"error": "User not found"}, status=404)
    u = VK_USERS_DB[u_id]
    if "bday_text" in data:
        u["vk_bday_text"] = data["bday_text"]
    if "bday_enabled" in data:
        u["vk_bday_enabled"] = bool(data["bday_enabled"])
    save_vk_data()
    append_vk_user_log(u_id, "success", "💾 Настройки поздравления сохранены в облачной базе ✅")
    return web.json_response({"status": "ok"})

async def handle_vk_like_once(request: web.Request):
    data = await request.json()
    u_id = str(data.get("user_id", ""))
    if u_id not in VK_USERS_DB:
        return web.json_response({"error": "User not found"}, status=404)
    u = VK_USERS_DB[u_id]
    async with aiohttp.ClientSession() as session:
        done = await run_vk_tact_stories(session, u)
    return web.json_response({"status": "ok", "done": done})

async def handle_download_extension(request):
    """Прямая отдача архива расширения Chrome"""
    for p in ["WOLFHUNT_CHROME_EXTENSION.zip", "downloads/WOLFHUNT_CHROME_EXTENSION.zip"]:
        if os.path.exists(p):
            return web.FileResponse(p, headers={
                "Content-Disposition": 'attachment; filename="WOLFHUNT_CHROME_EXTENSION.zip"'
            })
    return web.Response(text="Файл расширения временно недоступен", status=404)

async def handle_widget_js(request):
    """Динамический загрузчик виджета для Tilda с автоматической подгрузкой свежего UI"""
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
    """Отдача разметки и скрипта виджета WolfHunt с автосинхронизацией из CDN"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://cdn.jsdelivr.net/gh/snesterov/wolfhunt-tg@main/wolfhunt_tilda.html", timeout=aiohttp.ClientTimeout(total=3)) as r:
                if r.status == 200:
                    cdn_html = await r.text()
                    if "wh-all-time-total" in cdn_html:
                        return web.Response(text=cdn_html, content_type="text/html", headers={
                            "Access-Control-Allow-Origin": "*",
                            "Cache-Control": "no-cache, no-store, must-revalidate"
                        })
    except Exception as e:
        print("[Widget HTML] CDN fetch fallback:", e)

    html_path = os.path.join(os.path.dirname(__file__), "wolfhunt_tilda.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = "<div style='color:#f87171; padding:20px; font-family:sans-serif;'><h3>WolfHunt Widget: файл wolfhunt_tilda.html не найден на сервере</h3></div>"
    return web.Response(text=content, content_type="text/html", headers={
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache, no-store, must-revalidate"
    })

async def handle_tg_save_proxy(request: web.Request):
    """Сохранение SOCKS5 настроек для сессии Telegram"""
    try:
        data = await request.json()
        host = data.get("host", "").strip()
        user = data.get("user", "").strip()
        pwd = data.get("pass", "").strip()
        enabled = bool(data.get("enabled", False))
        state["proxy_host"] = host
        state["proxy_user"] = user
        state["proxy_pass"] = pwd
        state["proxy_enabled"] = enabled
        save_tg_data()
        msg = f"🌐 SOCKS5 прокси привязан: {host}" if (enabled and host) else "🌐 Прокси отключен (используется прямой IP)"
        append_log("info", msg)
        return web.json_response({"status": "ok", "proxy_enabled": enabled})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

async def init_app():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/", lambda r: web.Response(text="🐺 WolfHunt Telegram Bridge Running!"))
    app.router.add_get("/widget.js", handle_widget_js)
    app.router.add_get("/widget.html", handle_widget_html)
    app.router.add_get("/downloads/WOLFHUNT_CHROME_EXTENSION.zip", handle_download_extension)
    app.router.add_get("/download/extension", handle_download_extension)
    app.router.add_get("/api/tg/status", handle_status)
    app.router.add_post("/api/tg/send_code", handle_send_code)
    app.router.add_post("/api/tg/verify_code", handle_verify_code)
    app.router.add_post("/api/tg/restore_session", handle_restore_session)
    app.router.add_post("/api/tg/like_once", handle_like_once)
    app.router.add_post("/api/tg/toggle", handle_toggle)
    app.router.add_post("/api/tg/logout", handle_logout)
    app.router.add_post("/api/tg/save_proxy", handle_tg_save_proxy)
    app.router.add_post("/api/vk/proxy", handle_vk_proxy)
    app.router.add_post("/api/vk/auth", handle_vk_auth)
    app.router.add_get("/api/vk/status", handle_vk_status)
    app.router.add_post("/api/vk/sync", handle_vk_sync)
    app.router.add_get("/api/vk/sync", handle_vk_status)
    app.router.add_post("/api/vk/toggle", handle_vk_toggle)
    app.router.add_post("/api/vk/save_settings", handle_vk_save_settings)
    app.router.add_post("/api/vk/like_once", handle_vk_like_once)

    # Запуск фонового keep-alive
    load_vk_data()
    load_tg_data()
    asyncio.create_task(keep_alive_loop())
    asyncio.create_task(vk_multi_user_hunter_worker())

    # При старте проверим сохраненную сессию (файл .session или StringSession)
    global client
    try:
        # 1. Проверяем StringSession файл
        if os.path.exists(SESSION_STR_FILE):
            with open(SESSION_STR_FILE, "r", encoding="utf-8") as sf:
                s_str = sf.read().strip()
            if s_str:
                client = TelegramClient(StringSession(s_str), API_ID, API_HASH)

        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            state["is_authorized"] = True
            state["user"] = {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name or "",
                "username": me.username or ""
            }
            add_log(f"✔ Восстановлена сессия: {me.first_name} (@{me.username or me.id})", "success")
    except Exception as e:
        print("Сессия не найдена или ошибка подключения:", e)

    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 WolfHunt TG Bridge запускается на порту {port}...")
    web.run_app(init_app(), host="0.0.0.0", port=port)
