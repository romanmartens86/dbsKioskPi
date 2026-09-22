// dbsKioskPi Manager Frontend Logic - Multi-Device Fleet Edition

const basePath = window.INGRESS_PATH || '';

function apiUrl(path) {
  return `${basePath}${path}`;
}

let fleetDevices = [];
let activeDeviceId = null;
let playlistItems = [];
let bellSchedule = [];

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
  // Normalize legacy tab names if called
  if (['fleet', 'kiosk', 'setup', 'cec'].includes(tabId)) {
    tabId = 'displays';
  }

  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

  const activeBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId));
  if (activeBtn) activeBtn.classList.add('active');

  const content = document.getElementById(`tab-${tabId}`);
  if (content) content.classList.add('active');

  if (tabId === 'displays') {
    loadFleetDashboard();
    loadPlaylist();
    fetchStatus();
    loadAudioDevices();
  }
  if (tabId === 'bell') {
    loadBellSchedule();
    fetchStatus();
    loadAudioDevices();
    renderBellMatrix();
  }
  if (tabId === 'system') {
    fetchStatus();
    updateLogLinks();
  }
}

function toggleSetupAccordion(forceOpen = null) {
  const content = document.getElementById('setup-accordion-content');
  const arrow = document.getElementById('accordion-arrow');
  if (!content) return;
  const isCurrentlyOpen = content.style.display !== 'none';
  const shouldOpen = forceOpen !== null ? forceOpen : !isCurrentlyOpen;
  content.style.display = shouldOpen ? 'block' : 'none';
  if (arrow) arrow.style.transform = shouldOpen ? 'rotate(180deg)' : 'rotate(0deg)';
}

// -----------------------------------------------------------------------------
// Fleet & Device Management
// -----------------------------------------------------------------------------
async function loadFleetData() {
  try {
    const res = await fetch(apiUrl('/api/devices'));
    if (res.ok) {
      const data = await res.json();
      fleetDevices = data.devices || [];
      activeDeviceId = data.active_device_id || (fleetDevices[0] ? fleetDevices[0].id : null);
      updateDeviceSelectDropdown();
      populateSetupFormWithActiveDevice();
    }
  } catch (e) {
    console.error('Konnte Geräte nicht laden:', e);
  }
}

function updateDeviceSelectDropdown() {
  const select = document.getElementById('device-select');
  if (!select) return;
  select.innerHTML = '';
  fleetDevices.forEach(dev => {
    const opt = document.createElement('option');
    opt.value = dev.id;
    opt.innerText = `📍 ${dev.name || 'Kiosk'} (${dev.host || 'Nicht konfiguriert'})`;
    if (dev.id === activeDeviceId) opt.selected = true;
    select.appendChild(opt);
  });

  const activeDev = fleetDevices.find(d => d.id === activeDeviceId) || fleetDevices[0];
  const ind = document.getElementById('active-device-indicator');
  if (ind && activeDev) {
    ind.innerText = `${activeDev.name} (${activeDev.host || 'Keine IP'})`;
  }
  const statTitle = document.getElementById('stat-active-dev-title');
  if (statTitle && activeDev) {
    statTitle.innerText = `${activeDev.name} (${activeDev.host || 'Keine IP'})`;
  }
}

function populateSetupFormWithActiveDevice() {
  const activeDev = fleetDevices.find(d => d.id === activeDeviceId) || fleetDevices[0];
  if (!activeDev) return;

  const nameInput = document.getElementById('dev-name');
  const hostInput = document.getElementById('ssh-host');
  const portInput = document.getElementById('ssh-port');
  const userInput = document.getElementById('ssh-user');
  const passInput = document.getElementById('ssh-pass');
  const bellCheck = document.getElementById('bell-enabled-check');
  const bellVolSlider = document.getElementById('bell-volume-slider');
  const bellVolVal = document.getElementById('bell-volume-val');

  if (nameInput) nameInput.value = activeDev.name || '';
  if (hostInput) hostInput.value = activeDev.host || '';
  if (portInput) portInput.value = activeDev.port || 22;
  if (userInput) userInput.value = activeDev.username || 'dbsadmin';
  if (passInput) {
    passInput.value = activeDev.password || '';
    passInput.placeholder = activeDev.has_password ? '••••••••' : 'Passwort eingeben';
  }
  if (bellCheck) bellCheck.checked = activeDev.bell_enabled !== false;
  if (bellVolSlider) {
    const vol = activeDev.bell_volume !== undefined ? activeDev.bell_volume : 80;
    bellVolSlider.value = vol;
    if (bellVolVal) bellVolVal.innerText = `${vol}%`;
  }
  loadAudioDevices();
}

async function onDeviceSelectChange(devId) {
  try {
    const res = await fetch(apiUrl('/api/devices/select'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: devId })
    });
    const data = await res.json();
    if (data.success) {
      activeDeviceId = devId;
      updateDeviceSelectDropdown();
      populateSetupFormWithActiveDevice();
      fetchStatus();
      loadPlaylist();
      loadAudioDevices();
      updateLogLinks();
      showToast(`Aktives Display gewechselt zu: ${data.active_device.name}`);
    }
  } catch (e) {
    showToast(`Fehler beim Wechseln: ${e}`, true);
  }
}

async function promptNewDevice() {
  const name = prompt('Name oder Standort des neuen Kiosks (z. B. "Flur Oben", "Mensa", "Lehrerzimmer"):');
  if (!name || !name.trim()) return;

  const host = prompt('IP-Adresse des Raspberry Pi (kann auch später eingetragen werden):', '');

  try {
    const res = await fetch(apiUrl('/api/devices'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        host: host ? host.trim() : '',
        port: 22,
        username: 'dbsadmin',
        password: '',
        api_port: 8088,
        bell_enabled: true,
        bell_volume: 80
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Kiosk "${name}" erfolgreich hinzugefügt!`);
      await loadFleetData();
      switchTab('displays');
      toggleSetupAccordion(true);
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (e) {
    showToast(`Fehler beim Erstellen: ${e}`, true);
  }
}

async function saveDeviceSettings() {
  const name = document.getElementById('dev-name').value.trim();
  const host = document.getElementById('ssh-host').value.trim();
  const port = document.getElementById('ssh-port').value;
  const username = document.getElementById('ssh-user').value.trim();
  const password = document.getElementById('ssh-pass').value;

  if (!name) {
    showToast('Bitte einen Namen/Standort für das Gerät angeben', true);
    return;
  }

  try {
    const res = await fetch(apiUrl('/api/devices'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: activeDeviceId,
        name,
        host,
        port,
        username,
        password,
        api_port: 8088
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast('Geräteeinstellungen gespeichert!');
      await loadFleetData();
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (e) {
    showToast(`Fehler: ${e}`, true);
  }
}

async function deleteCurrentDevice() {
  const activeDev = fleetDevices.find(d => d.id === activeDeviceId);
  if (!activeDev) return;

  if (!confirm(`Bist du sicher, dass du das Display "${activeDev.name}" aus der Verwaltung entfernen möchtest?`)) {
    return;
  }

  try {
    const res = await fetch(apiUrl('/api/devices/delete'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: activeDeviceId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Display "${activeDev.name}" entfernt.`);
      await loadFleetData();
      switchTab('displays');
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (e) {
    showToast(`Fehler: ${e}`, true);
  }
}

async function updateDeviceBellSettings() {
  const enabled = document.getElementById('bell-enabled-check').checked;
  const slider = document.getElementById('bell-volume-slider');
  const volume = parseInt(slider.value);
  document.getElementById('bell-volume-val').innerText = `${volume}%`;

  const activeDev = fleetDevices.find(d => d.id === activeDeviceId);
  if (!activeDev) return;

  try {
    await fetch(apiUrl('/api/devices'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: activeDeviceId,
        name: activeDev.name,
        host: activeDev.host,
        port: activeDev.port,
        username: activeDev.username,
        api_port: activeDev.api_port,
        bell_enabled: enabled,
        bell_volume: volume
      })
    });
    activeDev.bell_enabled = enabled;
    activeDev.bell_volume = volume;
    showToast(`Glocke für "${activeDev.name}": ${enabled ? 'Aktiviert (' + volume + '%)' : 'Deaktiviert'}`);
    renderBellMatrix();
  } catch (e) {
    showToast(`Fehler: ${e}`, true);
  }
}

async function loadAudioDevices(forceRefresh = false) {
  const select = document.getElementById('bell-audio-device-select');
  const badge = document.getElementById('bell-audio-status-badge');
  if (!select) return;

  if (forceRefresh) {
    select.innerHTML = '<option value="default">🔄 Lade Soundkarten...</option>';
    if (badge) badge.innerText = 'Lade...';
  }

  const activeDev = fleetDevices.find(d => d.id === activeDeviceId);
  const targetId = activeDeviceId || (activeDev ? activeDev.id : '');

  try {
    const res = await fetch(apiUrl(`/api/pi/audio/devices?device_id=${targetId}`));
    if (res.ok) {
      const data = await res.json();
      const currentDev = data.current_device || (activeDev && activeDev.audio_device) || 'default';
      const devices = data.devices || [];

      select.innerHTML = '';
      devices.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.id;
        opt.innerText = d.name;
        if (d.id === currentDev) {
          opt.selected = true;
        }
        select.appendChild(opt);
      });

      if (!devices.some(d => d.id === currentDev) && currentDev !== 'default') {
        const customOpt = document.createElement('option');
        customOpt.value = currentDev;
        customOpt.innerText = `⚙️ Benutzerdefiniert (${currentDev})`;
        customOpt.selected = true;
        select.appendChild(customOpt);
      }

      if (badge) {
        if (currentDev.includes('vc4hdmi0') || currentDev.includes('HDMI 0')) {
          badge.innerText = 'HDMI 0';
          badge.className = 'status-pill status-pill-online';
        } else if (currentDev.includes('vc4hdmi') || currentDev.includes('HDMI')) {
          badge.innerText = 'HDMI';
          badge.className = 'status-pill status-pill-online';
        } else if (currentDev.includes('Headphones') || currentDev.includes('Klinke')) {
          badge.innerText = '3.5mm Klinke';
          badge.className = 'status-pill';
        } else {
          badge.innerText = 'Auto / Standard';
          badge.className = 'status-pill';
        }
      }
      if (forceRefresh) showToast('Soundkarten erfolgreich erkannt');
    }
  } catch (e) {
    console.error('Konnte Audio-Geräte nicht laden:', e);
    if (forceRefresh) showToast('Fehler beim Laden der Soundkarten', true);
  }
}

async function updateDeviceAudioDevice() {
  const select = document.getElementById('bell-audio-device-select');
  if (!select) return;
  const newDev = select.value;
  const activeDev = fleetDevices.find(d => d.id === activeDeviceId);

  showToast(`Stelle Audio-Ausgang auf "${newDev}" um...`);
  try {
    const res = await fetch(apiUrl('/api/pi/audio/device'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: activeDeviceId, audio_device: newDev })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Audio-Ausgang erfolgreich gespeichert!');
      if (activeDev) activeDev.audio_device = newDev;
      loadAudioDevices();
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (e) {
    showToast(`Fehler beim Speichern des Audio-Ausgangs: ${e}`, true);
  }
}

// -----------------------------------------------------------------------------
// Fleet Dashboard Rendering
// -----------------------------------------------------------------------------
async function loadFleetDashboard() {
  const grid = document.getElementById('fleet-grid');
  if (!grid) return;

  try {
    const res = await fetch(apiUrl('/api/fleet/status'));
    if (!res.ok) throw new Error('Statusabfrage fehlgeschlagen');
    const data = await res.json();
    const devices = data.devices || [];

    grid.innerHTML = '';
    if (devices.length === 0) {
      grid.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-secondary);">Noch keine Kiosk-Geräte angelegt. Klicke oben auf "➕ Neu".</div>';
      return;
    }

    devices.forEach(dev => {
      const card = document.createElement('div');
      const isActive = dev.id === activeDeviceId;
      card.className = `fleet-card ${isActive ? 'active-device' : ''}`;

      const isOnline = dev.online === true;
      const statusBadge = isOnline
        ? '<span class="badge online"><span style="width: 7px; height: 7px; border-radius: 50%; background: currentColor;"></span> Online</span>'
        : '<span class="badge offline"><span style="width: 7px; height: 7px; border-radius: 50%; background: currentColor;"></span> Offline</span>';

      const live = dev.live_status || {};
      const tvPower = live.screen_power ? (live.screen_power === 'on' ? '🟢 Ein' : '🌙 Standby') : (dev.host ? 'Unbekannt' : 'Nicht konfiguriert');
      const currentUrl = live.kiosk_url ? (live.kiosk_url.length > 38 ? live.kiosk_url.substring(0, 35) + '...' : live.kiosk_url) : '-';
      const bellStatus = dev.bell_enabled !== false ? `🔔 Aktiv (${dev.bell_volume || 80}%)` : '🔕 Stumm';

      card.innerHTML = `
        <div onclick="selectFleetCard('${dev.id}')" style="cursor: pointer;">
          <div class="fleet-card-header">
            <div>
              <div class="fleet-card-title">📍 ${escapeHtml(dev.name)}</div>
              <div class="fleet-card-ip">${dev.host || 'Keine IP hinterlegt'}</div>
            </div>
            <div>${statusBadge}</div>
          </div>

          <div class="fleet-card-body">
            <div class="fleet-stat-row">
              <span class="fleet-stat-label">HDMI-TV Status:</span>
              <span class="fleet-stat-value">${tvPower}</span>
            </div>
            <div class="fleet-stat-row">
              <span class="fleet-stat-label">Schulglocke:</span>
              <span class="fleet-stat-value">${bellStatus}</span>
            </div>
            <div class="fleet-stat-row">
              <span class="fleet-stat-label">Aktive Webseite:</span>
              <span class="fleet-stat-value" style="font-family: monospace; font-size: 11px;">${escapeHtml(currentUrl)}</span>
            </div>
          </div>
        </div>

        <div class="fleet-card-actions">
          <button class="btn btn-secondary" style="font-size: 12px; padding: 5px 12px; flex: 1;" onclick="selectFleetCard('${dev.id}')">
            ⚙️ Auswählen & Bearbeiten
          </button>
          <button class="btn btn-secondary" style="font-size: 12px; padding: 5px 8px;" title="Raspberry Pi neu starten (Reboot)" onclick="rebootDevice('${dev.id}', '${escapeHtml(dev.name)}')">
            🔁
          </button>
          <button class="btn btn-danger" style="font-size: 12px; padding: 5px 9px;" title="Raspberry Pi herunterfahren (Shutdown)" onclick="shutdownDevice('${dev.id}', '${escapeHtml(dev.name)}')">
            🛑 Aus
          </button>
        </div>
      `;
      grid.appendChild(card);
    });

  } catch (err) {
    grid.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--danger);">Fehler beim Laden des Flottenstatus: ${err}</div>`;
  }
}

function selectFleetCard(devId) {
  onDeviceSelectChange(devId).then(() => {
    const ind = document.getElementById('active-device-indicator');
    if (ind) {
      ind.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  });
}

async function triggerFleetAction(action) {
  const names = {
    screen_on: 'alle Fernseher einzuschalten',
    screen_off: 'alle Fernseher in Standby zu versetzen',
    reload: 'alle Kiosk-Bildschirme neu zu laden',
    shutdown: 'ALLE Displays herunterzufahren (Achtung: Erfordert physischen Kaltstart!)',
    reboot: 'alle Displays neu zu starten'
  };
  if (!confirm(`Möchtest du wirklich ${names[action] || action}?`)) return;

  showToast('Sende Sammelbefehl an alle Displays...');
  try {
    const res = await fetch(apiUrl('/api/fleet/action'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message);
      setTimeout(loadFleetDashboard, 2000);
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (e) {
    showToast(`Fehler: ${e}`, true);
  }
}

function selectDeviceAndTab(devId, tabId) {
  onDeviceSelectChange(devId).then(() => {
    switchTab(tabId);
    if (tabId === 'setup') {
      toggleSetupAccordion(true);
    }
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// -----------------------------------------------------------------------------
// Copy Playlist Modal
// -----------------------------------------------------------------------------
function openCopyPlaylistModal() {
  const modal = document.getElementById('copy-modal');
  const sourceNameEl = document.getElementById('copy-source-name');
  const targetList = document.getElementById('copy-target-list');

  const activeDev = fleetDevices.find(d => d.id === activeDeviceId) || { name: 'Aktuelles Display' };
  sourceNameEl.innerText = `"${activeDev.name}"`;

  targetList.innerHTML = '';
  const otherDevices = fleetDevices.filter(d => d.id !== activeDeviceId);

  if (otherDevices.length === 0) {
    targetList.innerHTML = '<p style="color: var(--text-secondary); font-size: 13px;">Keine weiteren Displays vorhanden. Bitte lege zuerst weitere Kioske an.</p>';
  } else {
    otherDevices.forEach(dev => {
      const label = document.createElement('label');
      label.style.display = 'flex';
      label.style.alignItems = 'center';
      label.style.gap = '10px';
      label.style.padding = '8px';
      label.style.background = 'var(--bg-tertiary)';
      label.style.borderRadius = '6px';
      label.style.cursor = 'pointer';

      label.innerHTML = `
        <input type="checkbox" value="${dev.id}" class="copy-target-check" checked style="width: 16px; height: 16px;">
        <span style="font-weight: 600;">📍 ${escapeHtml(dev.name)}</span>
        <span style="font-size: 12px; color: var(--text-secondary); margin-left: auto;">(${dev.host || 'Keine IP'})</span>
      `;
      targetList.appendChild(label);
    });
  }

  modal.style.display = 'flex';
}

function closeCopyPlaylistModal() {
  document.getElementById('copy-modal').style.display = 'none';
}

async function executeCopyPlaylist() {
  const checkboxes = document.querySelectorAll('.copy-target-check:checked');
  const targetIds = Array.from(checkboxes).map(c => c.value);

  if (targetIds.length === 0) {
    showToast('Bitte mindestens ein Ziel-Display auswählen', true);
    return;
  }

  showToast('Übertrage Playlist auf Ziel-Displays...');
  try {
    const res = await fetch(apiUrl('/api/kiosk/copy-playlist'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_device_id: activeDeviceId,
        target_device_ids: targetIds
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message);
      closeCopyPlaylistModal();
    } else {
      showToast(`Fehler: ${data.error}`, true);
    }
  } catch (err) {
    showToast(`Fehler: ${err}`, true);
  }
}

// -----------------------------------------------------------------------------
// 1. Remote Provisioning & SSH
// -----------------------------------------------------------------------------
async function testSSH() {
  const host = document.getElementById('ssh-host').value.trim();
  const port = document.getElementById('ssh-port').value;
  const username = document.getElementById('ssh-user').value.trim();
  const password = document.getElementById('ssh-pass').value;
  const name = document.getElementById('dev-name').value.trim();

  if (!host) {
    showToast('Bitte IP-Adresse eingeben', true);
    return;
  }

  showToast('Teste SSH-Verbindung...');
  try {
    const res = await fetch(apiUrl('/api/test-ssh'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: activeDeviceId, name, host, port, username, password })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Verbindung erfolgreich!');
      await loadFleetData();
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
  const name = document.getElementById('dev-name').value.trim();

  if (!host || !password) {
    showToast('IP-Adresse und Passwort sind für die Installation erforderlich', true);
    return;
  }

  if (!confirm(`Möchtest du die vollständige Installation auf dem Display "${name}" (${host}) jetzt starten?`)) {
    return;
  }

  const termCard = document.getElementById('terminal-card');
  const term = document.getElementById('terminal-output');
  termCard.style.display = 'block';
  term.innerText = `Starte Provisioning für ${name}...\n`;

  try {
    const res = await fetch(apiUrl('/api/provision/start'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: activeDeviceId, name, host, port, username, password })
    });
    const data = await res.json();
    if (!data.success) {
      showToast(data.error, true);
      return;
    }

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
async function loadPlaylist() {
  try {
    const res = await fetch(apiUrl(`/api/kiosk/playlist?device_id=${activeDeviceId}`));
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        playlistItems = data;
      } else if (data && Array.isArray(data.playlist) && data.playlist.length > 0) {
        playlistItems = data.playlist;
      } else {
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
        <input type="url" value="${item.url || ''}" oninput="playlistItems[${index}].url = this.value" onchange="playlistItems[${index}].url = this.value" placeholder="https://...">
      </div>
      <div class="form-group" style="flex: 1;">
        <label>Anzeigedauer (Sekunden)</label>
        <input type="number" min="5" max="3600" value="${item.duration || 30}" oninput="playlistItems[${index}].duration = parseInt(this.value, 10) || 30" onchange="playlistItems[${index}].duration = parseInt(this.value, 10) || 30">
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
  // Synchronisiere Eingaben aus dem DOM
  const urlInputs = document.querySelectorAll('#playlist-container input[type="url"]');
  const durInputs = document.querySelectorAll('#playlist-container input[type="number"]');
  urlInputs.forEach((inp, i) => {
    if (playlistItems[i]) playlistItems[i].url = inp.value.trim();
  });
  durInputs.forEach((inp, i) => {
    if (playlistItems[i]) playlistItems[i].duration = parseInt(inp.value, 10) || 30;
  });

  showToast('Speichere Playlist auf diesem Display...');
  try {
    const res = await fetch(apiUrl(`/api/kiosk/playlist?device_id=${activeDeviceId}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(playlistItems)
    });
    let data;
    try {
      data = await res.json();
    } catch (e) {
      const text = await res.text().catch(() => '');
      throw new Error(`Ungültige Server-Antwort (HTTP ${res.status}): ${text.slice(0, 150)}`);
    }
    if (res.ok && data && (data.success !== false)) {
      showToast('Playlist gespeichert und Display neu geladen!');
    } else {
      showToast(`Fehler: ${(data && data.error) || 'Speichern fehlgeschlagen'}`, true);
    }
  } catch (err) {
    showToast(`Fehler beim Speichern: ${err.message || err}`, true);
  }
}

// -----------------------------------------------------------------------------
// 3. Schulglocken-Planer & MP3
// -----------------------------------------------------------------------------
async function loadBellSchedule() {
  try {
    const res = await fetch(apiUrl('/api/bell/schedule'));
    if (res.ok) {
      const data = await res.json();
      bellSchedule = data.schedule || data;
    }
  } catch (e) {
    bellSchedule = [];
  }
  if (!Array.isArray(bellSchedule) || bellSchedule.length === 0) {
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
  showToast('Speichere zentralen Glocken-Zeitplan und synchronisiere Flotte...');
  try {
    const res = await fetch(apiUrl('/api/bell/schedule'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ schedule: bellSchedule })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Schulglocken-Zeitplan erfolgreich gespeichert!');
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
  statusEl.innerText = `Übertrage ${file.name} auf alle Kioske...`;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(apiUrl('/api/bell/upload'), {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      showToast('MP3 Schulglocke erfolgreich an alle Displays verteilt!');
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
  showToast('Sende Läut-Befehl an gewähltes Display...');
  try {
    const res = await fetch(apiUrl(`/api/bell/play?device_id=${activeDeviceId}`), {
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

function renderBellMatrix() {
  const container = document.getElementById('bell-matrix-container');
  if (!container) return;

  if (!fleetDevices || fleetDevices.length === 0) {
    container.innerHTML = '<p style="color: var(--text-secondary); padding: 12px;">Keine Displays angelegt.</p>';
    return;
  }

  let html = `
    <div class="table-responsive">
      <table>
        <thead>
          <tr>
            <th>Kiosk / Standort</th>
            <th>IP-Adresse</th>
            <th>Glocke im Raum</th>
            <th>Lautstärke</th>
            <th>Aktion</th>
          </tr>
        </thead>
        <tbody>
  `;

  fleetDevices.forEach((dev) => {
    const isBellOn = dev.bell_enabled !== false;
    const vol = dev.bell_volume !== undefined ? dev.bell_volume : 80;
    html += `
      <tr>
        <td style="font-weight: 600;">📍 ${escapeHtml(dev.name)}</td>
        <td style="font-family: monospace; font-size: 13px; color: var(--text-secondary);">${dev.host || '-'}</td>
        <td>
          <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
            <input type="checkbox" ${isBellOn ? 'checked' : ''} onchange="toggleDeviceBellMatrix('${dev.id}', this.checked)" style="width: 16px; height: 16px;">
            <span>${isBellOn ? '🔔 Aktiv' : '🔕 Stumm'}</span>
          </label>
        </td>
        <td>
          <div style="display: flex; align-items: center; gap: 8px;">
            <input type="range" min="10" max="100" value="${vol}" onchange="updateDeviceVolumeMatrix('${dev.id}', this.value)" style="width: 90px;">
            <span id="matrix-vol-${dev.id}" style="font-size: 12px; font-weight: 600; min-width: 35px;">${vol}%</span>
          </div>
        </td>
        <td>
          <button class="btn btn-secondary" style="font-size: 12px; padding: 4px 10px;" onclick="testPlayBellForDevice('${dev.id}')" title="Test-Gong auf diesem Gerät abspielen">
            🔔 Testen
          </button>
        </td>
      </tr>
    `;
  });

  html += `
        </tbody>
      </table>
    </div>
  `;

  container.innerHTML = html;
}

async function toggleDeviceBellMatrix(devId, enabled) {
  const dev = fleetDevices.find(d => d.id === devId);
  if (!dev) return;
  dev.bell_enabled = enabled;
  try {
    await fetch(apiUrl('/api/devices'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: dev.id,
        name: dev.name,
        host: dev.host,
        port: dev.port,
        username: dev.username,
        api_port: dev.api_port,
        bell_enabled: enabled,
        bell_volume: dev.bell_volume !== undefined ? dev.bell_volume : 80
      })
    });
    showToast(`Gong für "${dev.name}": ${enabled ? 'Aktiviert' : 'Stummgeschaltet'}`);
    if (dev.id === activeDeviceId) {
      const check = document.getElementById('bell-enabled-check');
      if (check) check.checked = enabled;
    }
    renderBellMatrix();
  } catch (e) {
    showToast(`Fehler: ${e}`, true);
  }
}

async function updateDeviceVolumeMatrix(devId, volume) {
  const dev = fleetDevices.find(d => d.id === devId);
  if (!dev) return;
  dev.bell_volume = parseInt(volume, 10);
  const volEl = document.getElementById(`matrix-vol-${devId}`);
  if (volEl) volEl.innerText = `${volume}%`;

  try {
    await fetch(apiUrl('/api/devices'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: dev.id,
        name: dev.name,
        host: dev.host,
        port: dev.port,
        username: dev.username,
        api_port: dev.api_port,
        bell_enabled: dev.bell_enabled !== false,
        bell_volume: dev.bell_volume
      })
    });
    if (dev.id === activeDeviceId) {
      const slider = document.getElementById('bell-volume-slider');
      const valText = document.getElementById('bell-volume-val');
      if (slider) slider.value = volume;
      if (valText) valText.innerText = `${volume}%`;
    }
  } catch (e) {
    console.error('Fehler beim Speichern der Lautstärke:', e);
  }
}

async function testPlayBellForDevice(devId) {
  const dev = fleetDevices.find(d => d.id === devId);
  const name = dev ? dev.name : 'Display';
  showToast(`Sende Test-Gong an "${name}"...`);
  try {
    const res = await fetch(apiUrl(`/api/bell/play?device_id=${devId}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: 100 })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Gong wird auf "${name}" abgespielt!`);
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
  showToast(`Sende TV-Befehl (${action}) an aktives Display...`);
  try {
    const res = await fetch(apiUrl(`/api/cec/screen?device_id=${activeDeviceId}`), {
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
    const res = await fetch(apiUrl(`/api/cec/schedule?device_id=${activeDeviceId}`), {
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
  const activeDev = fleetDevices.find(d => d.id === activeDeviceId) || { name: 'Aktuelles Display' };
  showToast(`Starte Kiosk-Browser auf "${activeDev.name}" neu...`);
  try {
    const res = await fetch(apiUrl('/api/kiosk/restart'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: activeDeviceId })
    });
    const data = await res.json();
    if (res.ok && data.success !== false) {
      showToast('Kiosk-Browser wird neu gestartet.');
      setTimeout(fetchStatus, 3000);
    } else {
      showToast(`Fehler beim Neustart: ${data.error || 'Unbekannt'}`, true);
    }
  } catch (e) {
    showToast(`Netzwerkfehler: ${e}`, true);
  }
}

async function rebootPiDevice() {
  const activeDev = fleetDevices.find(d => d.id === activeDeviceId) || { name: 'Aktuelles Display' };
  if (!confirm(`Möchtest du das Gerät "${activeDev.name}" wirklich komplett neu starten (Reboot)?`)) return;

  showToast(`Sende Reboot-Befehl an "${activeDev.name}"...`);
  try {
    const res = await fetch(apiUrl('/api/pi/reboot'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: activeDeviceId })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`System-Neustart initiiert: ${data.message}`);
      setTimeout(fetchStatus, 4000);
    } else {
      showToast(`Fehler beim Neustart: ${data.error || 'Unbekannt'}`, true);
    }
  } catch (e) {
    showToast(`Netzwerkfehler: ${e}`, true);
  }
}

async function shutdownPiDevice() {
  const activeDev = fleetDevices.find(d => d.id === activeDeviceId) || { name: 'Aktuelles Display' };
  if (!confirm(`⚠️ ACHTUNG: Möchtest du das Gerät "${activeDev.name}" wirklich herunterfahren?\n\nDas Display schaltet sich vollständig ab und kann erst wieder gestartet werden, wenn die Stromversorgung physisch getrennt und wieder angeschlossen wird (Kaltstart).`)) return;

  showToast(`Fahre "${activeDev.name}" herunter...`);
  try {
    const res = await fetch(apiUrl('/api/pi/shutdown'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: activeDeviceId })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Gerät wird heruntergefahren: ${data.message}`);
      const badge = document.getElementById('pi-status-badge');
      const badgeText = document.getElementById('pi-status-text');
      if (badge) badge.className = 'badge offline';
      if (badgeText) badgeText.innerText = 'Wird heruntergefahren...';
    } else {
      showToast(`Fehler beim Herunterfahren: ${data.error || 'Unbekannt'}`, true);
    }
  } catch (e) {
    showToast(`Netzwerkfehler: ${e}`, true);
  }
}

async function rebootDevice(devId, devName) {
  if (!confirm(`Möchtest du das Display "${devName}" wirklich neu starten (Reboot)?`)) return;

  showToast(`Sende Reboot-Befehl an "${devName}"...`);
  try {
    const res = await fetch(apiUrl('/api/pi/reboot'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: devId })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message || `Gerät "${devName}" startet neu.`);
      setTimeout(loadFleetDashboard, 3000);
    } else {
      showToast(`Fehler: ${data.error || 'Neustart fehlgeschlagen'}`, true);
    }
  } catch (e) {
    showToast(`Netzwerkfehler: ${e}`, true);
  }
}

async function shutdownDevice(devId, devName) {
  if (!confirm(`⚠️ ACHTUNG: Möchtest du das Display "${devName}" wirklich herunterfahren?\n\nDas Display schaltet sich vollständig ab und kann erst wieder gestartet werden, wenn die Stromversorgung physisch getrennt und wieder angeschlossen wird (Kaltstart).`)) return;

  showToast(`Fahre "${devName}" herunter...`);
  try {
    const res = await fetch(apiUrl('/api/pi/shutdown'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: devId })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message || `Gerät "${devName}" wird heruntergefahren.`);
      setTimeout(loadFleetDashboard, 3000);
    } else {
      showToast(`Fehler: ${data.error || 'Herunterfahren fehlgeschlagen'}`, true);
    }
  } catch (e) {
    showToast(`Netzwerkfehler: ${e}`, true);
  }
}

// -----------------------------------------------------------------------------
// 5. Live Status Polling & Healthcheck
// -----------------------------------------------------------------------------
async function fetchStatus() {
  const badge = document.getElementById('pi-status-badge');
  const badgeText = document.getElementById('pi-status-text');

  try {
    const res = await fetch(apiUrl(`/api/kiosk/status?device_id=${activeDeviceId}`));
    if (!res.ok) throw new Error('Offline');
    const data = await res.json();

    badge.className = 'badge online';
    badgeText.innerText = 'Online';

    const sKiosk = document.getElementById('stat-kiosk-service');
    const sPower = document.getElementById('stat-screen-power');
    const sInput = document.getElementById('stat-input-lock');
    const sUrl = document.getElementById('stat-kiosk-url');
    if (sKiosk) sKiosk.innerText = data.kiosk_service || 'aktiv';
    if (sPower) sPower.innerText = (data.screen_power || 'unbekannt').toUpperCase();
    if (sUrl) sUrl.innerText = data.kiosk_url || '-';

    const btnInput = document.getElementById('btn-toggle-input');
    if (data.input_lock) {
      const isLocked = data.input_lock.block_keyboard || data.input_lock.rules_active;
      if (sInput) {
        sInput.innerHTML = isLocked
          ? '<span style="color: #22c55e;">🔒 Gesperrt / Unsichtbar</span>'
          : '<span style="color: #eab308;">🔓 Entsperrt</span>';
      }
      if (btnInput) {
        btnInput.innerHTML = isLocked ? '🔓 Eingabe entsperren' : '🔒 Eingabe sperren';
        btnInput.setAttribute('data-locked', isLocked ? 'true' : 'false');
      }
    }

    if (data.bell) {
      const bellInfo = data.bell.sound_exists
        ? `Vorhanden (${Math.round((data.bell.sound_size_bytes || 0) / 1024)} KB)`
        : 'Keine MP3 vorhanden';
      const sBell = document.getElementById('stat-bell-info');
      if (sBell) sBell.innerText = bellInfo;
      const fileStatus = document.getElementById('bell-file-status');
      if (fileStatus) fileStatus.innerText = `Status: ${bellInfo}`;
    }

    if (data.bell && data.bell.audio_device) {
      const badge = document.getElementById('bell-audio-status-badge');
      const sel = document.getElementById('bell-audio-device-select');
      const dev = data.bell.audio_device;
      if (badge) {
        if (dev.includes('vc4hdmi0') || dev.includes('HDMI 0')) {
          badge.innerText = 'HDMI 0';
          badge.className = 'status-pill status-pill-online';
        } else if (dev.includes('vc4hdmi') || dev.includes('HDMI')) {
          badge.innerText = 'HDMI';
          badge.className = 'status-pill status-pill-online';
        } else if (dev.includes('Headphones') || dev.includes('Klinke')) {
          badge.innerText = '3.5mm Klinke';
          badge.className = 'status-pill';
        } else {
          badge.innerText = 'Auto / Standard';
          badge.className = 'status-pill';
        }
      }
      if (sel && sel.value !== dev && sel.querySelector(`option[value="${dev}"]`)) {
        sel.value = dev;
      }
    }

    if (data.cec_on_time && document.getElementById('cec-on-time')) document.getElementById('cec-on-time').value = data.cec_on_time;
    if (data.cec_off_time && document.getElementById('cec-off-time')) document.getElementById('cec-off-time').value = data.cec_off_time;

  } catch (e) {
    badge.className = 'badge offline';
    badgeText.innerText = 'Offline (Nicht erreichbar)';
    const sKiosk = document.getElementById('stat-kiosk-service');
    const sPower = document.getElementById('stat-screen-power');
    const sInput = document.getElementById('stat-input-lock');
    if (sKiosk) sKiosk.innerText = 'Offline';
    if (sPower) sPower.innerText = 'Offline';
    if (sInput) sInput.innerText = '-';
  }
}

async function toggleInputLock() {
  const btn = document.getElementById('btn-toggle-input');
  const isLocked = btn && btn.getAttribute('data-locked') === 'true';
  const newLock = !isLocked;

  const msg = newLock
    ? 'Möchtest du Tastatur- und Mauseingaben sperren und den Mauszeiger ausblenden?'
    : 'Möchtest du Tastatur- und Mauseingaben für Wartungsarbeiten am Kiosk entsperren?';

  if (!confirm(msg)) return;

  try {
    const res = await fetch(apiUrl(`/api/kiosk/input?device_id=${activeDeviceId}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: activeDeviceId,
        block_keyboard: newLock,
        block_mouse: newLock
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      alert(newLock ? 'Eingabeschnittstelle erfolgreich gesperrt.' : 'Eingabeschnittstelle entsperrt.');
      fetchStatus();
    } else {
      alert('Fehler: ' + (data.error || 'Aktion fehlgeschlagen'));
    }
  } catch (e) {
    alert('Verbindungsfehler: ' + e.message);
  }
}

function updateLogLinks() {
  const devId = activeDeviceId || '';
  const viewHc = document.getElementById('link-view-healthcheck');
  const dlHc = document.getElementById('link-download-healthcheck');
  const viewInst = document.getElementById('link-view-install-log');
  const dlInst = document.getElementById('link-download-install-log');
  const viewCfg = document.getElementById('link-view-config-log');
  const viewComm = document.getElementById('link-view-comm-log');
  const dlComm = document.getElementById('link-download-comm-log');
  const dlCommAll = document.getElementById('link-download-comm-log-all');

  if (viewHc) viewHc.href = apiUrl(`/api/pi/healthcheck?device_id=${devId}`);
  if (dlHc) dlHc.href = apiUrl(`/api/pi/healthcheck?device_id=${devId}`);
  if (viewInst) viewInst.href = apiUrl(`/api/pi/download-install-log?device_id=${devId}`);
  if (dlInst) dlInst.href = apiUrl(`/api/pi/download-install-log?device_id=${devId}`);
  if (viewCfg) viewCfg.href = apiUrl(`/api/pi/download-config-log?device_id=${devId}`);
  if (viewComm) viewComm.href = apiUrl(`/api/pi/download-comm-log?device_id=${devId}&minutes=10`);
  if (dlComm) dlComm.href = apiUrl(`/api/pi/download-comm-log?device_id=${devId}&minutes=10`);
  if (dlCommAll) dlCommAll.href = apiUrl(`/api/pi/download-comm-log?device_id=${devId}&minutes=60`);
}

function getSelectedLogUrl() {
  const select = document.getElementById('log-type-select');
  const type = select ? select.value : 'comm-10';
  const devId = activeDeviceId || '';

  switch (type) {
    case 'comm-10':
      return apiUrl(`/api/pi/download-comm-log?device_id=${devId}&minutes=10`);
    case 'comm-60':
      return apiUrl(`/api/pi/download-comm-log?device_id=${devId}&minutes=60`);
    case 'healthcheck':
      return apiUrl(`/api/pi/healthcheck?device_id=${devId}`);
    case 'install':
      return apiUrl(`/api/pi/download-install-log?device_id=${devId}`);
    case 'config':
      return apiUrl(`/api/pi/download-config-log?device_id=${devId}`);
    default:
      return apiUrl(`/api/pi/download-comm-log?device_id=${devId}&minutes=10`);
  }
}

function viewSelectedLog() {
  const url = getSelectedLogUrl();
  window.open(url, '_blank');
}

function downloadSelectedLog() {
  const url = getSelectedLogUrl();
  const select = document.getElementById('log-type-select');
  const type = select ? select.value : 'comm-10';
  const a = document.createElement('a');
  a.href = url;
  a.download = `kiosk-${type}-log.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function updatePiAgentOnDevice() {
  const activeDev = fleetDevices.find(d => d.id === activeDeviceId) || { name: 'Aktuelles Display' };
  if (!confirm(`Möchtest du den dbs-api Hintergrunddienst auf "${activeDev.name}" jetzt auf den neuesten Stand aktualisieren?\n\nDie neue Datei wird per SSH übertragen und der Dienst dbs-api.service neu gestartet.`)) return;

  showToast(`Aktualisiere dbs-api auf "${activeDev.name}"...`);
  try {
    const res = await fetch(apiUrl('/api/pi/update-agent'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: activeDeviceId })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message || 'dbs-api erfolgreich aktualisiert!');
    } else {
      showToast(`Fehler: ${data.error || 'Aktualisierung fehlgeschlagen'}`, true);
    }
  } catch (err) {
    showToast(`Verbindungsfehler: ${err.message || err}`, true);
  }
}

async function runLiveHealthcheck() {
  const btn = document.getElementById('btn-run-healthcheck');
  const box = document.getElementById('healthcheck-result-box');
  const out = document.getElementById('healthcheck-output');

  btn.disabled = true;
  btn.innerText = '⏳ Führe Diagnose durch...';
  showToast('Führe System-Healthcheck auf Raspberry Pi aus...');
  box.style.display = 'block';
  out.innerText = 'Starte Tiefendiagnose auf dem Raspberry Pi... Bitte ca. 5 Sekunden warten...\n';

  try {
    const res = await fetch(apiUrl(`/api/pi/healthcheck/run?device_id=${activeDeviceId}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: activeDeviceId })
    });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch (parseErr) {
      throw new Error(`Ungültige Antwort vom Server (${res.status}): ${text.substring(0, 150)}`);
    }

    if (data.success && data.output) {
      out.innerText = data.output;
      showToast('Healthcheck erfolgreich abgeschlossen!');
    } else {
      out.innerText = 'Fehler bei der Diagnose: ' + (data.error || 'Unbekannter Fehler');
      showToast('Healthcheck fehlgeschlagen: ' + (data.error || ''), true);
    }
  } catch (err) {
    out.innerText = 'Verbindungsfehler: ' + (err.message || err);
    showToast('Verbindungsfehler: ' + (err.message || err), true);
  } finally {
    btn.disabled = false;
    btn.innerText = '🔍 Healthcheck jetzt live ausführen';
  }
}

// Initialer Start
window.addEventListener('DOMContentLoaded', async () => {
  await loadFleetData();
  loadFleetDashboard();
  loadPlaylist();
  fetchStatus();
  updateLogLinks();
  renderBellMatrix();

  // Dropzone setup
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

