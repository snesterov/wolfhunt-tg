/**
 * 🐺 WOLFHUNT PRO v2.1.0 — POPUP CONTROLLER
 * Управление 24/7 облачным сервисом Render.
 */

const CLOUD_URL = "https://wolfhunt-tg.onrender.com";
const $ = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", async () => {
  initTabs();
  initFaq();
  initReactions();
  initVkControls();
  initTgControls();
  await refreshVkUi();
  await refreshTgUi();

  // Автообновление UI раз в 4 секунды при открытом popup
  setInterval(async () => {
    await refreshVkUi();
    await refreshTgUi();
  }, 4000);
});

// ----------------------------------------------------------------------------
// 1. НАВИГАЦИЯ И FAQ
// ----------------------------------------------------------------------------
function initTabs() {
  const tabVk = $("wh-tab-vk");
  const tabTg = $("wh-tab-tg");
  const viewVk = $("wh-view-vk");
  const viewTg = $("wh-view-tg");

  if (tabVk && tabTg) {
    tabVk.onclick = () => {
      viewVk.style.display = "block";
      viewTg.style.display = "none";
      tabVk.style.background = "linear-gradient(135deg,#0077ff,#0055cc)";
      tabVk.style.color = "#fff";
      tabVk.style.boxShadow = "0 4px 14px rgba(0,119,255,0.4)";
      tabTg.style.background = "transparent";
      tabTg.style.color = "#94a3b8";
      tabTg.style.boxShadow = "none";
    };

    tabTg.onclick = () => {
      viewVk.style.display = "none";
      viewTg.style.display = "block";
      tabTg.style.background = "linear-gradient(135deg,#0284c7,#0369a1)";
      tabTg.style.color = "#fff";
      tabTg.style.boxShadow = "0 4px 14px rgba(2,132,199,0.4)";
      tabVk.style.background = "transparent";
      tabVk.style.color = "#94a3b8";
      tabVk.style.boxShadow = "none";
      refreshTgUi();
    };
  }
}

function initFaq() {
  const toggleVk = $("wh-vk-faq-toggle");
  const contentVk = $("wh-vk-faq-content");
  const arrowVk = $("wh-vk-faq-arrow");
  if (toggleVk && contentVk) {
    toggleVk.onclick = () => {
      const isHidden = contentVk.style.display === "none";
      contentVk.style.display = isHidden ? "block" : "none";
      if (arrowVk) arrowVk.innerText = isHidden ? "Свернуть ▴" : "Развернуть ▾";
    };
  }

  const toggleTg = $("wh-tg-faq-toggle");
  const contentTg = $("wh-tg-faq-content");
  const arrowTg = $("wh-tg-faq-arrow");
  if (toggleTg && contentTg) {
    toggleTg.onclick = () => {
      const isHidden = contentTg.style.display === "none";
      contentTg.style.display = isHidden ? "block" : "none";
      if (arrowTg) arrowTg.innerText = isHidden ? "Свернуть ▴" : "Развернуть ▾";
    };
  }
}

function initReactions() {
  // 1. VK Реакции
  const vkMap = [
    { id: "wh-vk-re-heart", emoji: "❤" },
    { id: "wh-vk-re-fire", emoji: "🔥" },
    { id: "wh-vk-re-like", emoji: "👍" },
    { id: "wh-vk-re-clap", emoji: "👏" },
    { id: "wh-vk-re-love", emoji: "😍" }
  ];

  async function syncVkReactions() {
    let selected = vkMap.filter(item => $(item.id) && $(item.id).checked).map(item => item.emoji);
    if (!selected.length) {
      if ($("wh-vk-re-heart")) $("wh-vk-re-heart").checked = true;
      selected = ["❤"];
    }
    await chrome.storage.local.set({ wh_vk_reactions: selected });
    fetch(`${CLOUD_URL}/api/vk/set_reactions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reactions: selected })
    }).catch(() => {});
  }

  chrome.storage.local.get(["wh_vk_reactions"], (res) => {
    let saved = res.wh_vk_reactions;
    if (saved && Array.isArray(saved) && saved.length) {
      vkMap.forEach(item => {
        if ($(item.id)) $(item.id).checked = saved.includes(item.emoji);
      });
    }
  });

  vkMap.forEach(item => {
    if ($(item.id)) {
      $(item.id).onchange = () => syncVkReactions();
    }
  });

  // 2. Telegram Реакции
  const tgMap = [
    { id: "wh-tg-re-heart", emoji: "❤️" },
    { id: "wh-tg-re-fire", emoji: "🔥" },
    { id: "wh-tg-re-like", emoji: "👍" },
    { id: "wh-tg-re-clap", emoji: "👏" },
    { id: "wh-tg-re-love", emoji: "😍" }
  ];

  async function syncTgReactions() {
    let selected = tgMap.filter(item => $(item.id) && $(item.id).checked).map(item => item.emoji);
    if (!selected.length) {
      if ($("wh-tg-re-heart")) $("wh-tg-re-heart").checked = true;
      selected = ["❤️"];
    }
    await chrome.storage.local.set({ wh_tg_reactions: selected });
    fetch(`${CLOUD_URL}/api/tg/set_reactions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reactions: selected })
    }).catch(() => {});
  }

  chrome.storage.local.get(["wh_tg_reactions"], (res) => {
    let saved = res.wh_tg_reactions;
    if (saved && Array.isArray(saved) && saved.length) {
      tgMap.forEach(item => {
        if ($(item.id)) $(item.id).checked = saved.includes(item.emoji);
      });
    }
  });

  tgMap.forEach(item => {
    if ($(item.id)) {
      $(item.id).onchange = () => syncTgReactions();
    }
  });
}

// ----------------------------------------------------------------------------
// 2. ВКОНТАКТЕ УПРАВЛЕНИЕ И UI
// ----------------------------------------------------------------------------
async function refreshVkUi() {
  const s = await chrome.storage.local.get([
    "wh_token", "wh_name", "wh_nick", "wh_running",
    "wh_story_likes", "wh_post_likes", "wh_today_likes", "wh_all_time_total",
    "wh_all_time_stories", "wh_all_time_posts", "wh_vk_logs"
  ]);

  let serverIsAuth = false;
  let serverIsRunning = false;
  let serverData = null;

  try {
    const res = await fetch(`${CLOUD_URL}/api/vk/status`, { headers: { 'Cache-Control': 'no-cache' } });
    if (res.ok) {
      serverData = await res.json();
      if (serverData.status === "ok") {
        serverIsAuth = !!serverData.is_authorized;
        serverIsRunning = !!serverData.is_running;
      }
    }
  } catch (e) {}

  // Если в облаке токен сброшен, но в плагине он сохранен — отправляем его в облако!
  if (!serverIsAuth && s.wh_token) {
    try {
      const aRes = await fetch(`${CLOUD_URL}/api/vk/auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: s.wh_token })
      });
      const aData = await aRes.json();
      if (aData.status === "ok") {
        serverIsAuth = true;
        serverIsRunning = true;
        await chrome.storage.local.set({ wh_running: "true" });
      } else {
        // Токен устарел или недействителен
        await chrome.storage.local.remove(["wh_token"]);
        serverIsAuth = false;
        const msg = $("wh-msg");
        if (msg) {
          msg.innerText = "🛑 Срок действия токена завершился. Получите бессрочный доступ по кнопке выше.";
          msg.style.color = "#f87171";
        }
      }
    } catch (e) {}
  }

  const isAuth = serverIsAuth;
  const isRunning = isAuth && (serverIsRunning || s.wh_running === "true");

  // Карточка авторизации: показываем если нет активной авторизации
  if ($("wh-auth-card")) $("wh-auth-card").style.display = isAuth ? "none" : "block";
  if ($("wh-reset-btn")) $("wh-reset-btn").style.display = isAuth ? "inline-flex" : "none";

  // Профиль
  if ($("wh-name")) $("wh-name").innerText = isAuth ? (serverData?.name || s.wh_name || "Сергей Нестеров") : "ВКонтакте (требуется вход)";
  if ($("wh-nick")) $("wh-nick").innerText = isAuth ? (serverData?.screen_name ? `@${serverData.screen_name}` : (s.wh_nick ? `@${s.wh_nick}` : "id49239823")) : "Токен не подключен";
  if ($("wh-dot")) $("wh-dot").style.background = isAuth ? "#10b981" : "#64748b";

  // Счетчики (никогда не сбрасываются в 0)
  const bestStories = Math.max(parseInt(s.wh_story_likes || 0), parseInt(serverData?.today_stories || 0));
  const bestPosts = Math.max(parseInt(s.wh_post_likes || 0), parseInt(serverData?.today_posts || 0));
  const bestToday = Math.max(parseInt(s.wh_today_likes || 0), parseInt(serverData?.today_total || 0), bestStories);
  const bestAll = Math.max(parseInt(s.wh_all_time_total || 0), parseInt(serverData?.all_time_total || 0), bestToday);
  const bestVkViews = Math.max(parseInt(s.wh_vk_views || 0), parseInt(serverData?.views_today || 0));

  if ($("wh-stories")) $("wh-stories").innerText = bestStories;
  if ($("wh-vk-views")) $("wh-vk-views").innerText = bestVkViews;
  if ($("wh-post-likes")) $("wh-post-likes").innerText = bestPosts;
  if ($("wh-today-likes")) $("wh-today-likes").innerText = `${bestToday} / 300`;
  if ($("wh-all-time-total")) $("wh-all-time-total").innerText = bestAll;

  if ($("wh-sub")) {
    if (!isAuth) {
      $("wh-sub").innerText = "⚠️ Токен не подключен (нажмите Шаг 1 ниже)";
      $("wh-sub").style.color = "#f59e0b";
    } else if (bestStories >= 300) {
      $("wh-sub").innerText = "🌙 Лимит 300 исчерпан. Сон до 00:00 МСК";
      $("wh-sub").style.color = "#94a3b8";
    } else if (isRunning) {
      $("wh-sub").innerText = "🟢 Охота активна 24/7 (Истории)";
      $("wh-sub").style.color = "#34d399";
    } else {
      $("wh-sub").innerText = "⏸ На паузе (готов к охоте)";
      $("wh-sub").style.color = "#f59e0b";
    }
  }

  // Кнопка Старт / Пауза
  const toggleBtn = $("wh-toggle-btn");
  if (toggleBtn) {
    if (isRunning) {
      toggleBtn.innerText = "⏸ Приостановить";
      toggleBtn.style.background = "linear-gradient(135deg,#f43f5e,#be123c)";
    } else {
      toggleBtn.innerText = "🚀 Запустить охоту 24/7";
      toggleBtn.style.background = "linear-gradient(135deg,#10b981,#059669)";
    }
  }

  // Логи
  renderLogs("wh-log-stream", serverData?.logs || s.wh_vk_logs || []);
}

function initVkControls() {
  // Кнопка Сохранить токен
  const saveBtn = $("wh-save-btn");
  if (saveBtn) {
    saveBtn.onclick = async () => {
      const raw = ($("wh-token-raw") ? $("wh-token-raw").value : "").trim();
      const msg = $("wh-msg");
      if (!raw) {
        if (msg) { msg.innerText = "⚠️ Вставьте токен или ссылку!"; msg.style.color = "#f87171"; }
        return;
      }

      let token = raw;
      if (token.includes("access_token=")) {
        const m = token.match(/access_token=([^&]+)/);
        if (m) token = m[1];
      }

      saveBtn.disabled = true;
      if (msg) { msg.innerText = "⏳ Подключение к 24/7 облаку..."; msg.style.color = "#38bdf8"; }

      chrome.runtime.sendMessage({ action: "auth_vk", token: token }, async (res) => {
        saveBtn.disabled = false;
        if (res && res.status === "ok") {
          if (msg) { msg.innerText = "✔ Успешно подключено к облаку Render!"; msg.style.color = "#34d399"; }
          if ($("wh-token-raw")) $("wh-token-raw").value = "";
          await refreshVkUi();
        } else {
          if (msg) { msg.innerText = `❌ Ошибка: ${res?.error || "Неверный токен"}`; msg.style.color = "#f87171"; }
        }
      });
    };
  }

  // Кнопка Переключить охоту (Старт / Стоп)
  const toggleBtn = $("wh-toggle-btn");
  if (toggleBtn) {
    toggleBtn.onclick = () => {
      toggleBtn.disabled = true;
      chrome.runtime.sendMessage({ action: "toggle_vk" }, () => {
        toggleBtn.disabled = false;
        refreshVkUi();
      });
    };
  }

  // Кнопка Сменить аккаунт
  const resetBtn = $("wh-reset-btn");
  if (resetBtn) {
    resetBtn.onclick = () => {
      if (confirm("Отключить профиль ВКонтакте?")) {
        chrome.runtime.sendMessage({ action: "logout_vk" }, () => {
          refreshVkUi();
        });
      }
    };
  }

  // Кнопка Тестовый разовый лайк
  const nowBtn = $("wh-btn-now");
  if (nowBtn) {
    nowBtn.onclick = () => {
      nowBtn.disabled = true;
      nowBtn.innerText = "⏳ Лайкаем...";
      chrome.runtime.sendMessage({ action: "hunt_vk_now" }, (res) => {
        nowBtn.disabled = false;
        nowBtn.innerText = "⚡ Тестовый лайк";
        refreshVkUi();
      });
    };
  }

  // Кнопка Копировать лог
  const copyBtn = $("wh-btn-vk-copy-log");
  if (copyBtn) {
    copyBtn.onclick = async () => {
      const s = await chrome.storage.local.get(["wh_vk_logs"]);
      const logs = (s.wh_vk_logs || []).map(l => `[${l.time}] ${l.text}`).join("\n");
      navigator.clipboard.writeText(logs);
      copyBtn.innerText = "✔ Скопировано";
      setTimeout(() => { copyBtn.innerText = "📋 Лог"; }, 1500);
    };
  }
}

// ----------------------------------------------------------------------------
// 3. TELEGRAM УПРАВЛЕНИЕ И UI
// ----------------------------------------------------------------------------
async function refreshTgUi() {
  try {
    const res = await fetch(`${CLOUD_URL}/api/tg/status`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.status !== "ok") return;

    const isAuth = !!data.is_authorized;
    const isRunning = !!data.is_running;
    const user = data.user;

    if ($("wh-tg-auth-card")) $("wh-tg-auth-card").style.display = isAuth ? "none" : "block";
    if ($("wh-tg-reset-btn")) $("wh-tg-reset-btn").style.display = isAuth ? "inline-flex" : "none";
    if ($("wh-tg-dot")) $("wh-tg-dot").style.background = isAuth ? "#10b981" : "#64748b";

    if (isAuth && user) {
      if ($("wh-tg-name")) $("wh-tg-name").innerText = `${user.first_name || ""} ${user.last_name || ""}`.trim() || "Telegram";
      if ($("wh-tg-nick")) $("wh-tg-nick").innerText = user.username ? `@${user.username}` : `id${user.id}`;
    }

    if ($("wh-tg-sub")) {
      if (!isAuth) {
        $("wh-tg-sub").innerText = "⏸ Не авторизован";
        $("wh-tg-sub").style.color = "#94a3b8";
      } else if (parseInt(data.reactions_today || 0) >= 150) {
        $("wh-tg-sub").innerText = "🌙 Лимит 150 исчерпан. Сон до 00:00 МСК";
        $("wh-tg-sub").style.color = "#94a3b8";
      } else if (isRunning) {
        $("wh-tg-sub").innerText = "🟢 Автоохота 24/7 активна";
        $("wh-tg-sub").style.color = "#10b981";
      } else {
        $("wh-tg-sub").innerText = "⏸ На паузе";
        $("wh-tg-sub").style.color = "#f59e0b";
      }
    }

    if (!isAuth) {
      const st = await chrome.storage.local.get(["wh_tg_code_pending", "wh_tg_phone"]);
      const isPending = (st.wh_tg_code_pending === "true" || !!data.code_pending);
      if (isPending) {
        if ($("wh-tg-step-phone")) $("wh-tg-step-phone").style.display = "none";
        if ($("wh-tg-step-code")) $("wh-tg-step-code").style.display = "block";
        const msg = $("wh-tg-auth-msg");
        if (msg && !msg.innerText) {
          msg.innerText = `✔ Введите полученный код для ${data.phone || st.wh_tg_phone || "вашего номера"}:`;
          msg.style.color = "#38bdf8";
        }
      } else {
        if ($("wh-tg-step-phone")) $("wh-tg-step-phone").style.display = "block";
        if ($("wh-tg-step-code")) $("wh-tg-step-code").style.display = "none";
      }
    } else {
      await chrome.storage.local.remove(["wh_tg_code_pending", "wh_tg_phone"]);
      if ($("wh-tg-step-code")) $("wh-tg-step-code").style.display = "none";
      if ($("wh-tg-step-pwd")) $("wh-tg-step-pwd").style.display = "none";
    }

    const tgToggleBtn = $("wh-tg-toggle-btn");
    if (tgToggleBtn) {
      if (isRunning) {
        tgToggleBtn.innerText = "⏸ Приостановить TG";
        tgToggleBtn.style.background = "linear-gradient(135deg,#f43f5e,#be123c)";
      } else {
        tgToggleBtn.innerText = "🚀 Запустить TG 24/7";
        tgToggleBtn.style.background = "linear-gradient(135deg,#0284c7,#0369a1)";
      }
    }

    const curTgSt = await chrome.storage.local.get(["wh_tg_reactions_today", "wh_tg_reactions_all_time"]);
    const bestTgToday = Math.max(parseInt(curTgSt.wh_tg_reactions_today || 0), parseInt(data.reactions_today || 0));
    const bestTgAll = Math.max(parseInt(curTgSt.wh_tg_reactions_all_time || 0), parseInt(data.reactions_all_time || 0), bestTgToday);

    if ($("wh-tg-stat-reactions")) $("wh-tg-stat-reactions").innerText = bestTgToday;
    if ($("wh-tg-stat-views")) $("wh-tg-stat-views").innerText = data.views_today || "0";
    if ($("wh-tg-stat-limit")) $("wh-tg-stat-limit").innerText = `${bestTgToday} / 150`;
    if ($("wh-tg-stat-all-time")) $("wh-tg-stat-all-time").innerText = bestTgAll;

    renderLogs("wh-tg-log-stream", data.logs || []);
  } catch (err) {}
}

function initTgControls() {
  const btnSend = $("wh-tg-btn-send");
  if (btnSend) {
    btnSend.onclick = async () => {
      const phone = ($("wh-tg-phone-input") ? $("wh-tg-phone-input").value : "").trim();
      const msg = $("wh-tg-auth-msg");
      if (!phone) {
        if (msg) { msg.innerText = "⚠️ Введите номер телефона!"; msg.style.color = "#f87171"; }
        return;
      }
      btnSend.disabled = true;
      if (msg) { msg.innerText = "⏳ Отправка кода в Telegram..."; msg.style.color = "#38bdf8"; }

      try {
        const res = await fetch(`${CLOUD_URL}/api/tg/send_code`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone })
        });
        const data = await res.json();
        btnSend.disabled = false;
        
        const isAlreadySent = (data.error && (data.error.includes("already used") || data.error.includes("ResendCodeRequest")));
        if (data.status === "ok" || isAlreadySent) {
          await chrome.storage.local.set({ wh_tg_code_pending: "true", wh_tg_phone: phone });
          if ($("wh-tg-step-phone")) $("wh-tg-step-phone").style.display = "none";
          if ($("wh-tg-step-code")) $("wh-tg-step-code").style.display = "block";
          if (msg) {
            msg.innerText = isAlreadySent ? `✔ Код уже отправлен на ${phone}! Введите его ниже:` : `✔ Код отправлен на ${phone}! Введите его:`;
            msg.style.color = "#34d399";
          }
          if ($("wh-tg-code-input")) $("wh-tg-code-input").focus();
        } else {
          if (msg) { msg.innerText = `❌ ${data.error || "Ошибка"}`; msg.style.color = "#f87171"; }
        }
      } catch (e) {
        btnSend.disabled = false;
        if (msg) { msg.innerText = `❌ Ошибка сети: ${e.message}`; msg.style.color = "#f87171"; }
      }
    };
  }

  const btnManual = $("wh-tg-btn-manual-code");
  if (btnManual) {
    btnManual.onclick = () => {
      if ($("wh-tg-step-phone")) $("wh-tg-step-phone").style.display = "none";
      if ($("wh-tg-step-code")) $("wh-tg-step-code").style.display = "block";
      const msg = $("wh-tg-auth-msg");
      if (msg) {
        msg.innerText = "👉 Введите 5-значный код из SMS или приложения Telegram:";
        msg.style.color = "#38bdf8";
      }
      if ($("wh-tg-code-input")) $("wh-tg-code-input").focus();
    };
  }

  const btnVerify = $("wh-tg-btn-verify");
  if (btnVerify) {
    btnVerify.onclick = async () => {
      const code = ($("wh-tg-code-input") ? $("wh-tg-code-input").value : "").trim();
      const pwd = ($("wh-tg-pwd-input") ? $("wh-tg-pwd-input").value : "").trim();
      const msg = $("wh-tg-auth-msg");
      if (!code && !pwd) {
        if (msg) { msg.innerText = "⚠️ Введите 5-значный код!"; msg.style.color = "#f87171"; }
        return;
      }
      btnVerify.disabled = true;
      if (msg) { msg.innerText = "⏳ Проверка кода..."; msg.style.color = "#38bdf8"; }

      try {
        let endpoint = pwd ? "/api/tg/auth_2fa" : "/api/tg/verify_code";
        let payload = pwd ? { password: pwd } : { code: code };
        const res = await fetch(`${CLOUD_URL}${endpoint}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        btnVerify.disabled = false;

        if (data.status === "2fa_required") {
          if ($("wh-tg-step-pwd")) $("wh-tg-step-pwd").style.display = "block";
          if (msg) { msg.innerText = "🔐 Введите облачный пароль 2FA"; msg.style.color = "#f59e0b"; }
        } else if (data.status === "ok") {
          await chrome.storage.local.remove(["wh_tg_code_pending", "wh_tg_phone"]);
          if (data.session_string) {
            await chrome.storage.local.set({ wh_tg_session: data.session_string });
          }
          if ($("wh-tg-step-code")) $("wh-tg-step-code").style.display = "none";
          if ($("wh-tg-step-pwd")) $("wh-tg-step-pwd").style.display = "none";
          if ($("wh-tg-code-input")) $("wh-tg-code-input").value = "";
          if ($("wh-tg-pwd-input")) $("wh-tg-pwd-input").value = "";
          if (msg) { msg.innerText = "✔ Telegram успешно подключен!"; msg.style.color = "#34d399"; }
          await refreshTgUi();
        } else {
          if (msg) { msg.innerText = `❌ ${data.error || "Неверный код"}`; msg.style.color = "#f87171"; }
        }
      } catch (e) {
        btnVerify.disabled = false;
        if (msg) { msg.innerText = `❌ ${e.message}`; msg.style.color = "#f87171"; }
      }
    };
  }

  const btnBack = $("wh-tg-btn-back");
  if (btnBack) {
    btnBack.onclick = async () => {
      await chrome.storage.local.remove(["wh_tg_code_pending"]);
      fetch(`${CLOUD_URL}/api/tg/cancel_code`, { method: "POST" }).catch(() => {});
      if ($("wh-tg-step-code")) $("wh-tg-step-code").style.display = "none";
      if ($("wh-tg-step-pwd")) $("wh-tg-step-pwd").style.display = "none";
      if ($("wh-tg-step-phone")) $("wh-tg-step-phone").style.display = "block";
      const msg = $("wh-tg-auth-msg");
      if (msg) msg.innerText = "";
    };
  }

  const tgToggleBtn = $("wh-tg-toggle-btn");
  if (tgToggleBtn) {
    tgToggleBtn.onclick = async () => {
      tgToggleBtn.disabled = true;
      await fetch(`${CLOUD_URL}/api/tg/toggle`, { method: "POST" });
      tgToggleBtn.disabled = false;
      await refreshTgUi();
    };
  }

  const tgResetBtn = $("wh-tg-reset-btn");
  if (tgResetBtn) {
    tgResetBtn.onclick = async () => {
      if (confirm("Выйти из профиля Telegram?")) {
        await chrome.storage.local.remove(["wh_tg_code_pending", "wh_tg_phone"]);
        await fetch(`${CLOUD_URL}/api/tg/logout`, { method: "POST" });
        await refreshTgUi();
      }
    };
  }

  const tgNowBtn = $("wh-tg-btn-now");
  if (tgNowBtn) {
    tgNowBtn.onclick = async () => {
      tgNowBtn.disabled = true;
      tgNowBtn.innerText = "⏳ Лайкаем...";
      await fetch(`${CLOUD_URL}/api/tg/like_once`, { method: "POST" });
      tgNowBtn.disabled = false;
      tgNowBtn.innerText = "⚡ Тестовый лайк";
      await refreshTgUi();
    };
  }

  const copyTgBtn = $("wh-btn-tg-copy-log");
  if (copyTgBtn) {
    copyTgBtn.onclick = async () => {
      try {
        const res = await fetch(`${CLOUD_URL}/api/tg/status`);
        const data = await res.json();
        const logs = (data.logs || []).map(l => `[${l.time}] ${l.text}`).join("\n");
        navigator.clipboard.writeText(logs);
        copyTgBtn.innerText = "✔ Скопировано";
        setTimeout(() => { copyTgBtn.innerText = "📋 Лог"; }, 1500);
      } catch (e) {}
    };
  }
}

// ----------------------------------------------------------------------------
// РЕНДЕР ЛОГОВ
// ----------------------------------------------------------------------------
function renderLogs(containerId, logs) {
  const container = $(containerId);
  if (!container) return;
  if (!logs || !logs.length) {
    container.innerHTML = "<div>[Система]: Ожидание событий...</div>";
    return;
  }
  container.innerHTML = logs.map(l => {
    let col = "#94a3b8";
    if (l.type === "success") col = "#34d399";
    if (l.type === "warn") col = "#f59e0b";
    if (l.type === "error") col = "#f87171";
    return `<div style="color:${col}; margin-bottom:2px;">[${l.time}] ${l.text}</div>`;
  }).join("");
  container.scrollTop = container.scrollHeight;
}
