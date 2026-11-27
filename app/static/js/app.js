document.addEventListener('DOMContentLoaded', () => {
  const node = document.getElementById('trendData');
  const canvas = document.getElementById('trendChart');
  if (node && canvas && window.Chart) {
    try {
      const rows = JSON.parse(node.textContent);
      new Chart(canvas, { type: 'line', data: { labels: rows.map(x => x.day), datasets: [{
        data: rows.map(x => x.value), borderColor: '#55e68b', backgroundColor: 'rgba(54,214,122,.13)',
        fill: true, tension: .42, pointRadius: 3, pointHoverRadius: 6, borderWidth: 2
      }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, ticks: { color: '#82948a' } },
          y: { beginAtZero: true, grid: { color: 'rgba(140,170,150,.12)' }, ticks: { color: '#82948a' } } } } });
    } catch (error) { console.error('Chart could not be rendered.', error); }
  }
});

async function enrollDevice() {
  const name = window.prompt('Give this device a name');
  if (!name || !name.trim()) return;
  const ua = navigator.userAgent;
  const platform = /Win/i.test(ua) ? 'windows' : /Mac/i.test(ua) ? 'macos' : 'linux';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  try {
    const response = await fetch(window.CARBONTRACK_ENROLL_URL, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf || '' },
      body: JSON.stringify({ name: name.trim(), platform })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Device enrollment failed.');
    window.alert('Device enrolled. Copy this token now; it is shown only once:\n\n' + data.token);
    window.location.reload();
  } catch (error) { window.alert(error.message || 'Could not enroll device.'); }
}
window.enrollDevice = enrollDevice;
