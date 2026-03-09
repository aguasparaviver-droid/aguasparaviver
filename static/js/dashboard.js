const map = L.map('map', {
  zoomControl: false,
  preferCanvas: true
}).setView([-19.861, -44.608], 14);

L.control.zoom({ position: 'topright' }).addTo(map);

L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  {
    maxZoom: 24,
    attribution: '&copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community'
  }
).addTo(map);

const allMarkers = [];

const filterPreservado = document.getElementById('filterPreservado');
const filterDegradado = document.getElementById('filterDegradado');
const missingList = document.getElementById('missingList');
const missingCount = document.getElementById('missingCount');
const detailsContent = document.getElementById('detailsContent');
const detailsDrawer = document.getElementById('detailsDrawer');
const drawerClose = document.getElementById('drawerClose');
const sidebar = document.getElementById('sidebar');
const floatingMenuButton = document.getElementById('floatingMenuButton');

function updateSidebarState() {
  const isClosed = sidebar.classList.contains('closed');

  if (isClosed) {
    floatingMenuButton.classList.remove('sidebar-open');
    floatingMenuButton.setAttribute('aria-label', 'Abrir barra lateral');
    floatingMenuButton.setAttribute('title', 'Abrir barra lateral');
  } else {
    floatingMenuButton.classList.add('sidebar-open');
    floatingMenuButton.setAttribute('aria-label', 'Fechar barra lateral');
    floatingMenuButton.setAttribute('title', 'Fechar barra lateral');
  }
}

function toggleSidebar() {
  sidebar.classList.toggle('closed');
  updateSidebarState();
}

function openDetailsDrawer() {
  detailsDrawer.classList.add('open');
}

function closeDetailsDrawer() {
  detailsDrawer.classList.remove('open');
}

floatingMenuButton.addEventListener('click', toggleSidebar);
drawerClose.addEventListener('click', closeDetailsDrawer);

filterPreservado.addEventListener('change', applyFilters);
filterDegradado.addEventListener('change', applyFilters);

function escapeHtml(text) {
  if (text === null || text === undefined || text === '') return '-';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatPhone(phone) {
  if (!phone) return '-';
  const digits = String(phone).replace(/\D/g, '');
  return digits || phone;
}

function formatDate(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('pt-BR');
}

function getEstadoKey(estado) {
  const v = (estado || '').toLowerCase().trim();
  if (v.includes('preserv')) return 'preservado';
  if (v.includes('degrad')) return 'degradado';
  return 'outro';
}

function getMarkerStyle(estado) {
  const key = getEstadoKey(estado);

  if (key === 'preservado') {
    return {
      radius: 8,
      weight: 2,
      color: '#ecfeff',
      fillColor: '#10b981',
      fillOpacity: 0.96
    };
  }

  if (key === 'degradado') {
    return {
      radius: 8,
      weight: 2,
      color: '#fff7ed',
      fillColor: '#f97316',
      fillOpacity: 0.96
    };
  }

  return {
    radius: 7,
    weight: 2,
    color: '#ffffff',
    fillColor: '#38bdf8',
    fillOpacity: 0.92
  };
}

function popupHtml(r) {
  const foto = r.foto_url
    ? `<img class="popup-img" src="${r.foto_url}" alt="Foto da nascente" onerror="this.style.display='none'">`
    : '';

  return `
    <div class="popup-card">
      ${foto}
      <div class="popup-body">
        <h3 class="popup-title">Registro de nascente</h3>
        <div class="popup-line"><span class="popup-label">Estado:</span> ${escapeHtml(r.estado_local)}</div>
        <div class="popup-line"><span class="popup-label">Período:</span> ${escapeHtml(r.periodo_aparece)}</div>
        <div class="popup-line"><span class="popup-label">Referência:</span> ${escapeHtml(r.ponto_referencia)}</div>
        <div class="popup-line"><span class="popup-label">Telefone:</span> ${escapeHtml(r.telefone)}</div>
        <div class="popup-line"><span class="popup-label">Data:</span> ${escapeHtml(formatDate(r.created_at))}</div>
      </div>
    </div>
  `;
}

function buildDetailsHtml(r) {
  const estadoKey = getEstadoKey(r.estado_local);
  const dotClass =
    estadoKey === 'preservado'
      ? 'dot-preservado'
      : estadoKey === 'degradado'
        ? 'dot-degradado'
        : '';

  const foto = r.foto_url
    ? `<img class="detail-image" src="${r.foto_url}" alt="Foto da nascente" onerror="this.style.display='none'">`
    : '';

  return `
    <div class="detail-card">
      ${foto}
      <div class="detail-content">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;">
          <div>
            <div style="font-size:18px;font-weight:800;">Registro de nascente</div>
            <div style="font-size:12px;color:var(--muted);margin-top:4px;">
              Enviado em ${escapeHtml(formatDate(r.created_at))}
            </div>
          </div>
        </div>

        <div class="status-chip">
          <span class="dot ${dotClass}"></span>
          ${escapeHtml(r.estado_local || 'Não informado')}
        </div>

        <div class="detail-grid" style="margin-top:14px;">
          <div class="detail-item">
            <div class="detail-label">Telefone</div>
            <div class="detail-value">${escapeHtml(r.telefone)}</div>
          </div>

          <div class="detail-item">
            <div class="detail-label">Está no local</div>
            <div class="detail-value">${escapeHtml(r.esta_no_local)}</div>
          </div>

          <div class="detail-item">
            <div class="detail-label">Tempo de existência</div>
            <div class="detail-value">${escapeHtml(r.tempo_existencia)}</div>
          </div>

          <div class="detail-item">
            <div class="detail-label">Período em que aparece</div>
            <div class="detail-value">${escapeHtml(r.periodo_aparece)}</div>
          </div>

          <div class="detail-item">
            <div class="detail-label">Ponto de referência</div>
            <div class="detail-value">${escapeHtml(r.ponto_referencia)}</div>
          </div>

          <div class="detail-item">
            <div class="detail-label">Latitude / Longitude</div>
            <div class="detail-value">
              ${r.latitude ?? '-'} / ${r.longitude ?? '-'}
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function setDetails(r) {
  detailsContent.className = '';
  detailsContent.innerHTML = buildDetailsHtml(r);
  openDetailsDrawer();
}

function updateKpis(registros) {
  const total = registros.length;
  const mapeados = registros.filter(r => r.latitude != null && r.longitude != null).length;
  const semCoord = registros.filter(r => r.latitude == null || r.longitude == null).length;
  const preservado = registros.filter(r => getEstadoKey(r.estado_local) === 'preservado').length;
  const degradado = registros.filter(r => getEstadoKey(r.estado_local) === 'degradado').length;
  const comFoto = registros.filter(r => !!r.foto_url).length;
  const semFoto = total - comFoto;

  document.getElementById('kpiTotal').textContent = total;
  document.getElementById('kpiMapeados').textContent = mapeados;
  document.getElementById('kpiPreservado').textContent = preservado;
  document.getElementById('kpiDegradado').textContent = degradado;

  document.getElementById('summarySemCoord').textContent = semCoord;
  document.getElementById('summaryComFoto').textContent = comFoto;
  document.getElementById('summarySemFoto').textContent = semFoto;
}

function renderMissingList(registros) {
  const semCoordenadas = registros.filter(r => r.latitude == null || r.longitude == null);

  missingCount.textContent = semCoordenadas.length;

  if (!semCoordenadas.length) {
    missingList.innerHTML = `
      <div class="missing-item">
        <div class="meta">Todos os registros atuais possuem coordenadas.</div>
      </div>
    `;
    return;
  }

  missingList.innerHTML = semCoordenadas.map((r) => {
    const phone = formatPhone(r.telefone);
    const waLink = phone !== '-' ? `https://wa.me/${phone}` : '#';

    return `
      <div class="missing-item">
        <div class="name">Registro sem localização</div>
        <div class="meta"><strong>Telefone:</strong> ${escapeHtml(r.telefone || '-')}</div>
        <div class="meta"><strong>Referência:</strong> ${escapeHtml(r.ponto_referencia || '-')}</div>
        <div class="meta"><strong>Estado:</strong> ${escapeHtml(r.estado_local || '-')}</div>
        <div class="meta"><strong>Data:</strong> ${escapeHtml(formatDate(r.created_at))}</div>
        ${
          phone !== '-'
            ? `<a class="phone-link" href="${waLink}" target="_blank" rel="noopener noreferrer">Contatar no WhatsApp</a>`
            : ''
        }
      </div>
    `;
  }).join('');
}

function markerShouldBeVisible(registro) {
  const estado = getEstadoKey(registro.estado_local);

  if (estado === 'preservado' && !filterPreservado.checked) return false;
  if (estado === 'degradado' && !filterDegradado.checked) return false;

  return true;
}

function applyFilters() {
  const bounds = [];

  allMarkers.forEach(({ marker, registro }) => {
    const visible = markerShouldBeVisible(registro);

    if (visible) {
      if (!map.hasLayer(marker)) marker.addTo(map);
      bounds.push([registro.latitude, registro.longitude]);
    } else {
      if (map.hasLayer(marker)) map.removeLayer(marker);
    }
  });

  if (bounds.length) {
    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 16 });
  }
}

async function carregarRegistros() {
  const res = await fetch('/api/registros');
  const data = await res.json();
  const registros = data.registros || [];

  updateKpis(registros);
  renderMissingList(registros);

  allMarkers.forEach(({ marker }) => {
    if (map.hasLayer(marker)) map.removeLayer(marker);
  });
  allMarkers.length = 0;

  const bounds = [];

  registros.forEach((r) => {
    const lat = r.latitude;
    const lng = r.longitude;

    if (lat === null || lat === undefined || lng === null || lng === undefined) {
      return;
    }

    const marker = L.circleMarker([lat, lng], getMarkerStyle(r.estado_local));

    marker.bindPopup(popupHtml(r), {
      maxWidth: 270,
      closeButton: true
    });

    marker.on('click', () => {
      setDetails(r);
    });

    if (markerShouldBeVisible(r)) {
      marker.addTo(map);
      bounds.push([lat, lng]);
    }

    allMarkers.push({ marker, registro: r });
  });

  if (bounds.length) {
    map.fitBounds(bounds, { padding: [70, 70], maxZoom: 16 });
  } else {
    map.setView([-19.861, -44.608], 14);
  }
}

updateSidebarState();
carregarRegistros();