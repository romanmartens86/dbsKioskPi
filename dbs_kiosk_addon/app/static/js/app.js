// dbsKioskPi Manager Frontend Logic

const basePath = window.INGRESS_PATH || '';

function apiUrl(path) {
  return `${basePath}${path}`;
}

function showToast(message, isError = false) {
  const toast = document.getElementById('toast');
  toast.innerText = message;
  toast.style.display = 'block';
  toast.style.borderLeftColor = isError ? 'var(--danger)' : 'var(--accent)';
  setTimeout(() => {
    toast.style.display = 'none';
  }, 4000);
}

function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

  const activeBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(tabId));
  if (activeBtn) activeBtn.classList.add('active');

  const content = document.getElementById(`tab-${tabId}`);
  if (content) content.classList.add('active');

  if (tabId === 'kiosk') loadPlaylist();
  if (tabId === 'bell') { loadBellSchedule(); fetchStatus(); }
  if (tabId === 'status') fetchStatus();
}

// -----------------------------------------------------------------------------
// 1. Remote Provisioning & SSH
// -----------------------------------------------------------------------------
async function testSSH() {
  const host = document.getElementById('ssh-host').value.trim();
  const port = document.getElementById('ssh-port').value;
  const username = document.getElementById('ssh-user').value.trim();
  const password = document.getElementById('ssh-pass').value;

  if (!host) {
    showToast('Bitte IP-Adresse eingeben', true);
    return;
  }

  showToast('Teste SSH-Verbindung...');
  try {
    const res = await fetch(apiUrl('/api/test-ssh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, port, username, password })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Verbindung erfolgreich!');
      setTimeout(fetchStatus, 600);
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (err) {
    showToast(`Verbindung fehlgeschlagen: ${err}`, true);
  }
}

async function startProvisioning() {
  const host = document.getElementById('ssh-host').value.trim();
  const port = document.getElementById('ssh-port').value;
  const username = document.getElementById('ssh-user').value.trim();
  const password = document.getElementById('ssh-pass').value;

  if (!host || !password) {
    showToast('IP-Adresse und Passwort sind für die Installation erforderlich', true);
    return;
  }

  if (!confirm(`Möchtest du die vollständige Installation auf dem Raspberry Pi (${host}) jetzt starten?`)) {
    return;
  }

  const termCard = document.getElementById('terminal-card');
  const term = document.getElementById('terminal-output');
  termCard.style.display = 'block';
  term.innerText = 'Starte Provisioning...\n';

  try {
    const res = await fetch(apiUrl('/api/provision/start'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host, port, username, password })
    });
    const data = await res.json();
    if (!data.success) {
      showToast(data.error, true);
      return;
    }

    // Connect to SSE stream
    const evtSource = new EventSource(apiUrl('/api/provision/stream'));
    evtSource.onmessage = (e) => {
      if (e.data.includes('PROVISIONING_COMPLETE')) {
        term.innerText += '\n[OK] Installation abgeschlossen! Der Kiosk startet neu.\n';
        term.scrollTop = term.scrollHeight;
        evtSource.close();
        showToast('KioskPi Installation erfolgreich!');
        setTimeout(fetchStatus, 15000);
      } else {
        term.innerText += e.data + '\n';
        term.scrollTop = term.scrollHeight;
      }
    };
    evtSource.onerror = () => {
      evtSource.close();
    };
  } catch (err) {
    showToast(`Fehler beim Starten: ${err}`, true);
  }
}

// -----------------------------------------------------------------------------
// 2. Playlist / Multi-URL Rotation
// -----------------------------------------------------------------------------
let playlistItems = [];

async function loadPlaylist() {
  try {
    const res = await fetch(apiUrl('/api/kiosk/playlist'));
    if (res.ok) {
      playlistItems = await res.json();
      if (!Array.isArray(playlistItems) || playlistItems.length === 0) {
        playlistItems = [{ url: "https://dbs.edupage.org/infoscreen/7?scaletowidth=1920", duration: 30 }];
      }
    }
  } catch (e) {
    playlistItems = [{ url: "https://dbs.edupage.org/infoscreen/7?scaletowidth=1920", duration: 30 }];
  }
  renderPlaylist();
}

function renderPlaylist() {
  const container = document.getElementById('playlist-container');
  container.innerHTML = '';

  playlistItems.forEach((item, index) => {
    const div = document.createElement('div');
    div.className = 'form-grid';
    div.style.marginBottom = '12px';
    div.style.alignItems = 'flex-end';
    div.innerHTML = `
      <div class="form-group" style="flex: 3;">
        <label>Webseiten-URL #${index + 1}</label>
        <input type="url" value="${item.url || ''}" onchange="playlistItems[${index}].url = this.value" placeholder="https://...">
      </div>
      <div class="form-group" style="flex: 1;">
        <label>Anzeigedauer (Sekunden)</label>
        <input type="number" min="5" max="3600" value="${item.duration || 30}" onchange="playlistItems[${index}].duration = parseInt(this.value)">
      </div>
      <div style="margin-bottom: 2px;">
        <button class="btn btn-danger" onclick="removePlaylistItem(${index})" title="Entfernen">🗑️</button>
      </div>
    `;
    container.appendChild(div);
  });
}

function addPlaylistItem() {
  playlistItems.push({ url: "https://", duration: 20 });
  renderPlaylist();
}

function removePlaylistItem(idx) {
  if (playlistItems.length <= 1) {
    showToast('Mindestens eine URL muss erhalten bleiben', true);
    return;
  }
  playlistItems.splice(idx, 1);
  renderPlaylist();
}

async function savePlaylist() {
  showToast('Speichere Playlist auf dem Kiosk...');
  try {
    const res = await fetch(apiUrl('/api/kiosk/playlist'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(playlistItems)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Playlist gespeichert und Kiosk neu geladen!');
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (err) {
    showToast(`Fehler beim Speichern: ${err}`, true);
  }
}

// -----------------------------------------------------------------------------
// 3. Schulglocken-Planer & MP3
// -----------------------------------------------------------------------------
let bellSchedule = [];

async function loadBellSchedule() {
  try {
    const res = await fetch(apiUrl('/api/bell/schedule'));
    if (res.ok) {
      bellSchedule = await res.json();
    }
  } catch (e) {
    bellSchedule = [];
  }
  if (!Array.isArray(bellSchedule) || bellSchedule.length === 0) {
    // Standard Schultag-Vorlage
    bellSchedule = [
      { id: 1, time: "07:55", name: "1. Vorwarnung", days: ["mon", "tue", "wed", "thu", "fri"], volume: 100 },
      { id: 2, time: "08:00", name: "Beginn 1. Stunde", days: ["mon", "tue", "wed", "thu", "fri"], volume: 100 },
      { id: 3, time: "08:45", name: "Ende 1. Stunde", days: ["mon", "tue", "wed", "thu", "fri"], volume: 100 },
      { id: 4, time: "09:35", name: "Große Pause", days: ["mon", "tue", "wed", "thu", "fri"], volume: 100 },
      { id: 5, time: "09:55", name: "Ende Pause", days: ["mon", "tue", "wed", "thu", "fri"], volume: 100 }
    ];
  }
  renderSchedule();
}

function renderSchedule() {
  const tbody = document.getElementById('schedule-tbody');
  tbody.innerHTML = '';

  const dayLabels = [
    { k: 'mon', l: 'Mo' }, { k: 'tue', l: 'Di' }, { k: 'wed', l: 'Mi' },
    { k: 'thu', l: 'Do' }, { k: 'fri', l: 'Fr' }
  ];

  bellSchedule.forEach((row, idx) => {
    const tr = document.createElement('tr');

    let daysHtml = dayLabels.map(d => {
      const checked = (row.days || []).includes(d.k) ? 'checked' : '';
      return `
        <label class="day-label">
          <input type="checkbox" ${checked} onchange="toggleScheduleDay(${idx}, '${d.k}', this.checked)">
          ${d.l}
        </label>
      `;
    }).join('');

    tr.innerHTML = `
      <td><input type="time" value="${row.time || '08:00'}" onchange="bellSchedule[${idx}].time = this.value" style="width: 110px;"></td>
      <td><input type="text" value="${row.name || ''}" onchange="bellSchedule[${idx}].name = this.value" placeholder="z. B. 1. Stunde" style="width: 100%;"></td>
      <td><div class="day-checkboxes">${daysHtml}</div></td>
      <td><input type="number" min="10" max="100" value="${row.volume || 100}" onchange="bellSchedule[${idx}].volume = parseInt(this.value)" style="width: 75px;">%</td>
      <td><button class="btn btn-danger" style="padding: 6px 10px;" onclick="removeScheduleRow(${idx})">🗑️</button></td>
    `;
    tbody.appendChild(tr);
  });
}

function toggleScheduleDay(idx, day, checked) {
  if (!bellSchedule[idx].days) bellSchedule[idx].days = [];
  if (checked) {
    if (!bellSchedule[idx].days.includes(day)) bellSchedule[idx].days.push(day);
  } else {
    bellSchedule[idx].days = bellSchedule[idx].days.filter(d => d !== day);
  }
}

function addScheduleRow() {
  bellSchedule.push({
    id: Date.now(),
    time: "11:30",
    name: "Mittagspause",
    days: ["mon", "tue", "wed", "thu", "fri"],
    volume: 100
  });
  renderSchedule();
}

function removeScheduleRow(idx) {
  bellSchedule.splice(idx, 1);
  renderSchedule();
}

async function saveBellSchedule() {
  showToast('Speichere Glocken-Zeitplan...');
  try {
    const res = await fetch(apiUrl('/api/bell/schedule'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bellSchedule)
    });
    const data = await res.json();
    if (data.success) {
      showToast('Schulglocken-Zeitplan erfolgreich auf Kiosk aktiviert!');
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (err) {
    showToast(`Fehler beim Speichern: ${err}`, true);
  }
}

async function uploadBellFile(file) {
  if (!file) return;
  const statusEl = document.getElementById('bell-file-status');
  statusEl.innerText = `Übertrage ${file.name}...`;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(apiUrl('/api/bell/upload'), {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      showToast('MP3 Schulglocke erfolgreich übertragen!');
      statusEl.innerText = `Aktiv: ${file.name} (${Math.round(file.size / 1024)} KB)`;
    } else {
      showToast(`Fehler beim Hochladen: ${data.error}`, true);
      statusEl.innerText = 'Fehler beim Hochladen';
    }
  } catch (err) {
    showToast(`Upload-Fehler: ${err}`, true);
    statusEl.innerText = 'Upload fehlgeschlagen';
  }
}

async function testPlayBell() {
  showToast('Sende Läut-Befehl an Kiosk...');
  try {
    const res = await fetch(apiUrl('/api/bell/play'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: 100 })
    });
    const data = await res.json();
    if (data.success) {
      showToast('Schulglocke wird abgespielt!');
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (err) {
    showToast(`Fehler: ${err}`, true);
  }
}

// -----------------------------------------------------------------------------
// 4. HDMI-CEC TV Steuerung
// -----------------------------------------------------------------------------
async function toggleScreen(action) {
  showToast(`Sende TV-Befehl (${action})...`);
  try {
    const res = await fetch(apiUrl('/api/cec/screen'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    if (data.success) {
      showToast(action === 'on' ? 'TV eingeschaltet!' : 'TV in Standby geschaltet.');
      setTimeout(fetchStatus, 2000);
    }
  } catch (e) {
    showToast(`Fehler: ${e}`, true);
  }
}

async function saveCecSchedule() {
  const on_time = document.getElementById('cec-on-time').value;
  const off_time = document.getElementById('cec-off-time').value;

  showToast('Speichere TV-Zeiten...');
  try {
    const res = await fetch(apiUrl('/api/cec/schedule'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on_time, off_time })
    });
    const data = await res.json();
    if (data.success) {
      showToast('TV-Schaltzeiten erfolgreich aktualisiert!');
    }
  } catch (e) {
    showToast(`Fehler: ${e}`, true);
  }
}

async function restartKioskService() {
  showToast('Starte Kiosk-Browser neu...');
  try {
    await fetch(apiUrl('/api/kiosk/status'));
    showToast('Befehl gesendet.');
  } catch (e) {}
}

// -----------------------------------------------------------------------------
// 5. Live Status Polling
// -----------------------------------------------------------------------------
async function fetchStatus() {
  const badge = document.getElementById('pi-status-badge');
  const badgeText = document.getElementById('pi-status-text');

  try {
    const res = await fetch(apiUrl('/api/kiosk/status'));
    if (!res.ok) throw new Error('Offline');
    const data = await res.json();

    badge.className = 'badge online';
    badgeText.innerText = 'Online';

    document.getElementById('stat-kiosk-service').innerText = data.kiosk_service || 'unbekannt';
    document.getElementById('stat-screen-power').innerText = (data.screen_power || 'unbekannt').toUpperCase();
    document.getElementById('stat-kiosk-url').innerText = data.kiosk_url || '-';

    if (data.bell) {
      const bellInfo = data.bell.sound_exists
        ? `Vorhanden (${Math.round((data.bell.sound_size_bytes || 0) / 1024)} KB)`
        : 'Keine MP3 vorhanden';
      document.getElementById('stat-bell-info').innerText = bellInfo;
      const fileStatus = document.getElementById('bell-file-status');
      if (fileStatus) fileStatus.innerText = `Status: ${bellInfo}`;
    }

    if (data.cec_on_time) document.getElementById('cec-on-time').value = data.cec_on_time;
    if (data.cec_off_time) document.getElementById('cec-off-time').value = data.cec_off_time;

  } catch (e) {
    badge.className = 'badge offline';
    badgeText.innerText = 'Offline (Nicht erreichbar)';
    document.getElementById('stat-kiosk-service').innerText = 'Offline';
    document.getElementById('stat-screen-power').innerText = 'Offline';
  }
}

// Initialer Status-Check
window.addEventListener('DOMContentLoaded', () => {
  fetchStatus();
  // Drag & drop dropzone setup
  const dropzone = document.getElementById('bell-dropzone');
  if (dropzone) {
    ['dragenter', 'dragover'].forEach(name => {
      dropzone.addEventListener(name, (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    });
    ['dragleave', 'drop'].forEach(name => {
      dropzone.addEventListener(name, (e) => { e.preventDefault(); dropzone.classList.remove('dragover'); });
    });
    dropzone.addEventListener('drop', (e) => {
      const files = e.dataTransfer.files;
      if (files.length > 0) uploadBellFile(files[0]);
    });
  }
});
