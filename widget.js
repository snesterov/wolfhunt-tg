(async function() {
  try {
    let root = document.getElementById('wolfhunt-root') || document.getElementById('wolfhunt-container');
    if (!root) {
      root = document.createElement('div');
      root.id = 'wolfhunt-root';
      const target = document.querySelector('.t123') || document.querySelector('.r') || document.body;
      target.appendChild(root);
    }
    const timestamp = Date.now();
    let html = null;
    try {
      const cdnRes = await fetch('https://cdn.jsdelivr.net/gh/snesterov/wolfhunt-tg@main/wolfhunt_tilda.html?v=' + timestamp);
      if (cdnRes.ok) {
        html = await cdnRes.text();
      }
    } catch(e) {
      console.warn('[WolfHunt CDN] CDN failed, trying fallback...', e);
    }
    if (!html) {
      const fbRes = await fetch('https://raw.githubusercontent.com/snesterov/wolfhunt-tg/main/wolfhunt_tilda.html?v=' + timestamp);
      if (fbRes.ok) {
        html = await fbRes.text();
      }
    }
    if (!html) {
      const renderRes = await fetch('https://wolfhunt-tg.onrender.com/widget.html?v=' + timestamp);
      if (renderRes.ok) {
        html = await renderRes.text();
      }
    }
    if (html) {
      const range = document.createRange();
      const fragment = range.createContextualFragment(html);
      root.innerHTML = '';
      root.appendChild(fragment);
      console.log('[WolfHunt Pro] Auto-loaded latest widget layout successfully ✅');
    } else {
      console.error('[WolfHunt Pro] Could not load widget markup from any source');
    }
  } catch(err) {
    console.error('[WolfHunt Pro Loader Error]:', err);
  }
})();
