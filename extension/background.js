/**
 * 🐺 WOLFHUNT PRO v2.1.0 — CHROME EXTENSION BACKGROUND SERVICE WORKER
 * Единый облачный спутник для управления и мониторинга 24/7 сервера Render.
 * Все действия ВКонтакте выполняются СТРОГО на сервере Render, исключая риск бана и конфликтов IP.
 */

const CLOUD_BASE_URL = "https://wolfhunt-tg.onrender.com";

async function logMsg(text, type = "info") {
  const timeStr = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const s = await chrome.storage.local.get(['wh_vk_logs']);
  const logs = s.wh_vk_logs || [];
  logs.push({ time: timeStr, text: text, type: type });
  if (logs.length > 60) logs.shift();
  await chrome.storage.local.set({ wh_vk_logs: logs });
}

async function syncWithCloud() {
  try {
    const s = await chrome.storage.local.get([
      'wh_token', 'wh_name', 'wh_nick', 'wh_user_id',
      'wh_today_likes', 'wh_story_likes', 'wh_post_likes', 'wh_vk_views',
      'wh_all_time_stories', 'wh_all_time_posts', 'wh_all_time_total', 'wh_vk_reactions',
      'wh_tg_session', 'wh_tg_reactions_today', 'wh_tg_reactions_all_time', 'wh_tg_reactions'
    ]);

    // 1. Если токен ВК есть локально, отправляем на сервер для гарантии 24/7 работы
    if (s.wh_token) {
      await fetch(`${CLOUD_BASE_URL}/api/vk/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: s.wh_token,
          user_id: s.wh_user_id,
          name: s.wh_name,
          nick: s.wh_nick,
          all_time_stories: s.wh_all_time_stories,
          all_time_posts: s.wh_all_time_posts,
          all_time_total: s.wh_all_time_total,
          today_stories: s.wh_story_likes || s.wh_today_likes,
          reactions: s.wh_vk_reactions
        })
      }).catch(() => {});
    }

    // 2. Двусторонняя синхронизация Telegram (гарантия сохранения сессии и счетчиков)
    try {
      const tgRes = await fetch(`${CLOUD_BASE_URL}/api/tg/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_string: s.wh_tg_session,
          reactions_today: s.wh_tg_reactions_today,
          reactions_all_time: s.wh_tg_reactions_all_time,
          reactions: s.wh_tg_reactions,
          running: s.wh_tg_running || "true"
        })
      });
      if (tgRes.ok) {
        const tgData = await tgRes.json();
        if (tgData.status === "ok") {
          const curTgToday = parseInt(s.wh_tg_reactions_today || 0);
          const curTgAll = parseInt(s.wh_tg_reactions_all_time || 0);
          const bestTgToday = Math.max(curTgToday, parseInt(tgData.reactions_today || 0));
          const bestTgAll = Math.max(curTgAll, parseInt(tgData.reactions_all_time || 0), bestTgToday);
          await chrome.storage.local.set({
            wh_tg_authorized: tgData.is_authorized ? 'true' : 'false',
            wh_tg_running: tgData.is_running ? 'true' : 'false',
            wh_tg_reactions_today: String(bestTgToday),
            wh_tg_reactions_all_time: String(bestTgAll),
            wh_tg_views_today: String(tgData.views_today || 0),
            wh_tg_logs: tgData.logs || []
          });
        }
      }
    } catch (e) {}

    const res = await fetch(`${CLOUD_BASE_URL}/api/vk/status`, {
      headers: { 'Cache-Control': 'no-cache' }
    });
    if (!res.ok) return;
    const data = await res.json();

    if (data.status === "ok") {
      const curToday = parseInt(s.wh_today_likes || 0);
      const curStories = parseInt(s.wh_story_likes || 0);
      const curPosts = parseInt(s.wh_post_likes || 0);
      const curAll = parseInt(s.wh_all_time_total || 0);
      const curAllSt = parseInt(s.wh_all_time_stories || 0);
      const curAllPo = parseInt(s.wh_all_time_posts || 0);

      const sStories = parseInt(data.today_stories || 0);
      const sPosts = parseInt(data.today_posts || 0);
      const sTotal = parseInt(data.today_total || 0);
      const sAll = parseInt(data.all_time_total || 0);
      const sAllSt = parseInt(data.all_time_stories || 0);
      const sAllPo = parseInt(data.all_time_posts || 0);

      const bestStories = Math.max(curStories, sStories);
      const bestPosts = Math.max(curPosts, sPosts);
      const bestToday = Math.max(curToday, sTotal, bestStories);
      const bestAllSt = Math.max(curAllSt, sAllSt, bestStories);
      const bestAllPo = Math.max(curAllPo, sAllPo, bestPosts);
      const bestAll = Math.max(curAll, sAll, bestAllSt + bestAllPo, bestToday);

      const updates = {
        wh_running: data.is_running ? 'true' : 'false',
        wh_user_id: data.user_id ? String(data.user_id) : (s.wh_user_id || '49239823'),
        wh_name: data.name || s.wh_name || 'Сергей Нестеров',
        wh_nick: data.screen_name || s.wh_nick || 'id49239823',
        wh_today_likes: String(bestToday),
        wh_story_likes: String(bestStories),
        wh_post_likes: String(bestPosts),
        wh_vk_views: String(data.views_today || 0),
        wh_all_time_stories: String(bestAllSt),
        wh_all_time_posts: String(bestAllPo),
        wh_all_time_total: String(bestAll)
      };

      if (data.logs && Array.isArray(data.logs)) {
        updates.wh_vk_logs = data.logs;
      }

      await chrome.storage.local.set(updates);

      // Обновление бейджа на иконке расширения
      if (chrome.action && chrome.action.setBadgeText) {
        if (data.is_running) {
          chrome.action.setBadgeText({ text: 'ON' });
          chrome.action.setBadgeBackgroundColor({ color: '#10b981' });
        } else {
          chrome.action.setBadgeText({ text: '' });
        }
      }
    }
  } catch (err) {
    // Тихо игнорируем секундные сбои сети
  }
}

// Периодический опрос сервера раз в 10 секунд
setInterval(syncWithCloud, 10000);

chrome.runtime.onStartup.addListener(() => {
  syncWithCloud();
});

chrome.runtime.onInstalled.addListener(() => {
  syncWithCloud();
  console.log("🐺 WolfHunt PRO v2.1.0 Cloud Companion установлен.");
});

// Слушатель сообщений от popup окна
chrome.runtime.onMessage.addListener((req, sender, sendResponse) => {
  if (req.action === "toggle_vk") {
    fetch(`${CLOUD_BASE_URL}/api/vk/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: req.subAction || "toggle" })
    })
    .then(r => r.json())
    .then(data => {
      syncWithCloud();
      sendResponse(data);
    })
    .catch(err => sendResponse({ error: err.message }));
    return true;
  }

  if (req.action === "hunt_vk_now") {
    fetch(`${CLOUD_BASE_URL}/api/vk/like_once`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    })
    .then(r => r.json())
    .then(data => {
      syncWithCloud();
      sendResponse(data);
    })
    .catch(err => sendResponse({ error: err.message }));
    return true;
  }

  if (req.action === "auth_vk") {
    fetch(`${CLOUD_BASE_URL}/api/vk/auth`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: req.token })
    })
    .then(r => r.json())
    .then(data => {
      if (data.status === "ok") {
        chrome.storage.local.set({
          wh_token: req.token,
          wh_user_id: String(data.user_id),
          wh_name: data.name,
          wh_nick: data.screen_name,
          wh_running: 'true'
        });
      }
      syncWithCloud();
      sendResponse(data);
    })
    .catch(err => sendResponse({ error: err.message }));
    return true;
  }

  if (req.action === "logout_vk") {
    fetch(`${CLOUD_BASE_URL}/api/vk/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    })
    .then(r => r.json())
    .then(data => {
      chrome.storage.local.remove(['wh_token', 'wh_name', 'wh_nick', 'wh_user_id', 'wh_running']);
      syncWithCloud();
      sendResponse(data);
    })
    .catch(err => sendResponse({ error: err.message }));
    return true;
  }

  if (req.action === "sync_cloud") {
    syncWithCloud().then(() => sendResponse({ status: "ok" }));
    return true;
  }
});
