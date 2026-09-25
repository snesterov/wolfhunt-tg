"""
🐺 WOLFHUNT PRO — TELEGRAM BACKEND BRIDGE
Микросервер-мост между Tilda и Telegram MTProto API.
Позволяет клиентам авторизоваться прямо на сайте через телефон + код из Telegram.
"""

import asyncio
import os
import random
import re
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

def get_msk_now():
    """Возвращает текущее время по Москве (UTC+3)."""
    return datetime.now(MSK)
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

client = TelegramClient(StringSession(), API_ID, API_HASH)

state = {
    "phone": None,
    "phone_code_hash": None,
    "is_authorized": False,
    "user": None,
    "is_running": False,
    "reactions_today": 0,
    "views_today": 0,
    "reactions_list": ["❤️", "🔥", "👍"],
    "last_date": str(get_msk_now().date()),
    "logs": []
}

seen_stories = set()
hunter_task = None

def add_log(text, log_type="info"):
    now_time = get_msk_now().strftime("%H:%M:%S")
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
                    print(f"[{get_msk_now().strftime('%H:%M:%S')}] [KEEP-ALIVE] Render ping status: {resp.status}")
        except Exception as e:
            print(f"[KEEP-ALIVE NOTICE] {e}")
        await asyncio.sleep(540) # 9 минут

async def hunter_loop():
    add_log("▶ Охота на истории Telegram запущена! Первый поиск историй мгновенно...", "success")
    while state["is_running"]:
        try:
            today = str(get_msk_now().date())
            if state["last_date"] != today:
                state["last_date"] = today
                state["reactions_today"] = 0
                state["views_today"] = 0
                add_log("🔄 Новый день: суточный счетчик Telegram сброшен (0/150)", "info")

            if state["reactions_today"] >= DAILY_LIMIT:
                now = get_msk_now()
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

    global client
    try:
        if not client.is_connected():
            await client.connect()
        try:
            sent = await client.send_code_request(phone)
        except Exception as e:
            if "cannot be reused" in str(e).lower() or "disconnected" in str(e).lower():
                client = TelegramClient(StringSession(), API_ID, API_HASH)
                await client.connect()
                sent = await client.send_code_request(phone)
            else:
                raise e
        state["phone"] = phone
        state["phone_code_hash"] = sent.phone_code_hash
        add_log(f"Код подтверждения запрошен для {phone}", "info")
        return web.json_response({"status": "ok", "message": "Код отправлен в Telegram"})
    except Exception as e:
        add_log(f"Ошибка запроса кода: {e}", "warn")
        return web.json_response({"status": "error", "message": str(e)}, status=400)

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
        return web.json_response({"status": "error", "message": "Неверный код подтверждения"}, status=400)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

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

                # Реакция - строго РАЗОВО!
                emoji = random.choice(state["reactions_list"])
                await client(functions.stories.SendReactionRequest(
                    peer=peer,
                    story_id=story.id,
                    reaction=types.ReactionEmoji(emoticon=emoji)
                ))
                seen_stories.add(story_key)
                state["reactions_today"] += 1
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
    global hunter_task, client
    state["is_running"] = False
    if hunter_task and not hunter_task.done():
        hunter_task.cancel()
    try:
        if client.is_connected():
            await client.log_out()
    except Exception:
        pass
    # Пересоздаем чистый клиент после логаута
    client = TelegramClient(StringSession(), API_ID, API_HASH)
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

async def handle_vk_stories(request):
    token = request.query.get("access_token")
    if not token:
        return web.json_response({"error": "access_token required"}, status=400)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.vk.com/method/stories.get", params={
                "access_token": token,
                "extended": 1,
                "fields": "first_name,last_name",
                "v": "5.131"
            }, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json(content_type=None)
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_vk_avatar(request):
    photo_url = request.query.get("url")
    if not photo_url:
        return web.Response(status=400, text="url required")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(photo_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    ct = resp.headers.get("Content-Type", "image/jpeg")
                    return web.Response(body=data, content_type=ct, headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "public, max-age=86400"})
    except Exception as e:
        print("[VK AVATAR NOTICE]", e)
    return web.Response(status=404)

async def handle_vk_user(request):
    token = request.query.get("access_token")
    if not token:
        return web.json_response({"error": "access_token required"}, status=400)
    user_id = request.query.get("user_id")
    params = {"access_token": token, "fields": "photo_100,photo_200,photo_max,screen_name", "v": "5.131"}
    if user_id:
        params["user_ids"] = user_id
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.vk.com/method/users.get", params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json(content_type=None)
                if data and "response" in data and len(data["response"]) > 0:
                    u = data["response"][0]
                    p_url = u.get("photo_200") or u.get("photo_max") or u.get("photo_100")
                    if p_url:
                        try:
                            async with session.get(p_url, timeout=aiohttp.ClientTimeout(total=5)) as img_r:
                                if img_r.status == 200:
                                    img_b = await img_r.read()
                                    b64 = base64.b64encode(img_b).decode("ascii")
                                    ct = img_r.headers.get("Content-Type", "image/jpeg")
                                    u["photo_base64"] = f"data:{ct};base64,{b64}"
                        except Exception as e:
                            pass
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def handle_tg_avatar(request):
    global client
    avatar_path = "tg_avatar.jpg"
    try:
        if state["is_authorized"] and client.is_connected():
            if not os.path.exists(avatar_path):
                await client.download_profile_photo("me", file=avatar_path)
            if os.path.exists(avatar_path):
                return web.FileResponse(avatar_path)
    except Exception as e:
        print("[TG AVATAR NOTICE]", e)
    return web.Response(status=404)


async def init_app():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/", lambda r: web.Response(text="🐺 WolfHunt Telegram Bridge Running!"))
    app.router.add_get("/api/tg/status", handle_status)
    app.router.add_get("/api/tg/avatar", handle_tg_avatar)
    app.router.add_get("/api/vk/stories", handle_vk_stories)
    app.router.add_get("/api/vk/user", handle_vk_user)
    app.router.add_get("/api/vk/avatar", handle_vk_avatar)
    app.router.add_post("/api/tg/send_code", handle_send_code)
    app.router.add_post("/api/tg/verify_code", handle_verify_code)
    app.router.add_post("/api/tg/restore_session", handle_restore_session)
    app.router.add_post("/api/tg/like_once", handle_like_once)
    app.router.add_post("/api/tg/toggle", handle_toggle)
    app.router.add_post("/api/tg/logout", handle_logout)

    # Запуск фонового keep-alive
    asyncio.create_task(keep_alive_loop())

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
