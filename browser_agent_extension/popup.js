// Browser Agent — popup bootstrap.
// Renders one button per registered feature and runs it on click.
const statusEl = document.getElementById('status');
const featuresEl = document.getElementById('features');

function setStatus(msg) {
  statusEl.textContent = msg;
}

for (const feature of getFeatures()) {
  const btn = document.createElement('button');
  btn.className = 'feature';
  btn.textContent = feature.label;
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    setStatus('Working…');
    try {
      const msg = await feature.run();
      setStatus(msg || 'Done.');
    } catch (e) {
      setStatus('Error: ' + (e && e.message ? e.message : String(e)));
    } finally {
      btn.disabled = false;
    }
  });
  featuresEl.appendChild(btn);
}

if (getFeatures().length === 0) {
  setStatus('No features registered.');
}
