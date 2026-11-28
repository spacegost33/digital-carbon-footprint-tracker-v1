(() => {
  const live = document.getElementById('ct-device-live');
  const status = document.getElementById('ct-refresh-status');
  if (!live || !status) return;
  let busy = false;
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(live.dataset.snapshotUrl, {
        credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: controller.signal
      });
      if (!response.ok) throw new Error('Refresh unavailable');
      const html = await response.text();
      // The fragment is same-origin server-rendered Jinja HTML (autoescaped).
      live.innerHTML = html;
      status.textContent = 'Latest refresh successful.';
    } catch (_) {
      status.textContent = 'Refresh failed. Showing the last successful snapshot; reload or sign in again if needed.';
    } finally { clearTimeout(timeout); busy = false; }
  }
  setInterval(refresh, 60000);
})();
