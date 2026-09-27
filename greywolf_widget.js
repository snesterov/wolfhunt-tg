(async function() {
  try {
    let root = document.getElementById('greywolf-root');
    if (!root) {
      root = document.createElement('div');
      root.id = 'greywolf-root';
      const cur = document.currentScript;
      const target = (cur && cur.parentElement) || document.querySelector('.t123') || document.querySelector('.r') || document.body;
      target.appendChild(root);
    }
    const timestamp = Date.now();
    let html = null;

    try {
      const res = await fetch('https://raw.githubusercontent.com/snesterov/wolfhunt-tg/main/greyzzzzwolf_5blocks.html?v=' + timestamp);
      if (res.ok) {
        html = await res.text();
      }
    } catch(e) {
      console.warn('[GZW Raw] Error loading via Raw GitHub', e);
    }

    if (!html) {
      try {
        const cdnRes = await fetch('https://cdn.jsdelivr.net/gh/snesterov/wolfhunt-tg@main/greyzzzzwolf_5blocks.html?v=' + timestamp);
        if (cdnRes.ok) {
          html = await cdnRes.text();
        }
      } catch(e) {}
    }

    if (html) {
      const range = document.createRange();
      const fragment = range.createContextualFragment(html);
      root.innerHTML = '';
      root.appendChild(fragment);
      console.log('[GREYzzzzWOLF] Лендинг успешно загружен ✅');
    } else {
      console.error('[GREYzzzzWOLF] Не удалось загрузить разметку');
    }
  } catch(err) {
    console.error('[GREYzzzzWOLF Loader Error]:', err);
  }
})();
