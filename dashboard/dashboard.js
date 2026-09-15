// ------------------------------------------------------------------
// Configuração
// ------------------------------------------------------------------

const API = '';
const DAILY_DAYS = 30;

const PALETTE = [
    '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b',
    '#ef4444', '#06b6d4', '#ec4899', '#84cc16',
];

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#233355';
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.font.size = 12;

const charts = { daily: null, unique: null, devices: null, os: null, browsers: null };

let editingQrId = null;

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

async function fetchJSON(url, options = {}) {
    // credentials: 'include' faz o navegador reusar o Basic Auth
    const res = await fetch(url, { credentials: 'include', ...options });

    if (res.status === 401) {
        // Basic Auth popup já apareceu; se ainda chegou 401 é senha errada
        throw new Error('Não autorizado. Recarregue a página e informe usuário/senha.');
    }

    if (!res.ok) {
        let detail = `Erro ${res.status}`;
        try {
            const data = await res.json();
            if (data.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        } catch {}
        throw new Error(detail);
    }

    if (res.status === 204) return null;
    return res.json();
}

const formatNumber = (n) => new Intl.NumberFormat('pt-BR').format(n ?? 0);

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function showError(message) {
    document.querySelectorAll('.error-banner').forEach((b) => b.remove());
    const banner = document.createElement('div');
    banner.className = 'error-banner';
    banner.textContent = message;
    document.querySelector('.container').insertBefore(
        banner,
        document.querySelector('.kpis')
    );
}

function fillDailyGaps(data, days, keys) {
    const map = new Map(data.map((d) => [d.date, d]));
    const result = [];
    const today = new Date();
    for (let i = days - 1; i >= 0; i--) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        const dateKey = d.toISOString().slice(0, 10);
        const row = map.get(dateKey) || {};
        const entry = { date: dateKey };
        keys.forEach((k) => { entry[k] = row[k] || 0; });
        result.push(entry);
    }
    return result;
}

function formatDayLabel(isoDate) {
    const [, m, d] = isoDate.split('-');
    return `${d}/${m}`;
}

// ------------------------------------------------------------------
// KPIs
// ------------------------------------------------------------------

async function loadStats() {
    const data = await fetchJSON(`${API}/api/stats`);
    setText('kpi-total', formatNumber(data.total_scans));
    setText('kpi-total-sub', `${formatNumber(data.total_qr_codes)} QR Codes no total`);
    setText('kpi-unique', formatNumber(data.unique_scans));
    const pct = data.total_scans
        ? ((data.unique_scans / data.total_scans) * 100).toFixed(0)
        : 0;
    setText('kpi-unique-sub', `${pct}% do total de scans`);
    setText('kpi-today', formatNumber(data.today));
    setText('kpi-today-sub', `${formatNumber(data.unique_today)} únicos`);
    setText('kpi-week', formatNumber(data.last_7_days));
    setText('kpi-week-sub', `${formatNumber(data.unique_last_7_days)} únicos`);
}

// ------------------------------------------------------------------
// Gráficos
// ------------------------------------------------------------------

async function loadDaily() {
    const data = await fetchJSON(`${API}/api/scans/daily?days=${DAILY_DAYS}`);
    const filled = fillDailyGaps(data, DAILY_DAYS, ['scans']);
    const labels = filled.map((d) => formatDayLabel(d.date));
    const values = filled.map((d) => d.scans);

    const ctx = document.getElementById('chart-daily').getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 320);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.35)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');

    if (charts.daily) charts.daily.destroy();
    charts.daily = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Scans', data: values,
                borderColor: '#3b82f6', backgroundColor: gradient,
                borderWidth: 2, tension: 0.35, fill: true,
                pointRadius: 0, pointHoverRadius: 5,
                pointHoverBackgroundColor: '#3b82f6',
                pointHoverBorderColor: '#fff', pointHoverBorderWidth: 2,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0b1220', borderColor: '#233355', borderWidth: 1,
                    padding: 10, titleColor: '#e6edf7', bodyColor: '#94a3b8',
                    displayColors: false,
                    callbacks: { label: (c) => `${formatNumber(c.parsed.y)} scans` },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 20 } },
                y: { beginAtZero: true, grid: { color: '#1a2942' }, ticks: { precision: 0 } },
            },
        },
    });
}

async function loadUniqueDaily() {
    const data = await fetchJSON(`${API}/api/scans/unique-daily?days=${DAILY_DAYS}`);
    const filled = fillDailyGaps(data, DAILY_DAYS, ['scans', 'unique_visitors']);
    const labels = filled.map((d) => formatDayLabel(d.date));
    const totalValues = filled.map((d) => d.scans);
    const uniqueValues = filled.map((d) => d.unique_visitors);

    const ctx = document.getElementById('chart-unique').getContext('2d');
    const gradTotal = ctx.createLinearGradient(0, 0, 0, 320);
    gradTotal.addColorStop(0, 'rgba(59, 130, 246, 0.25)');
    gradTotal.addColorStop(1, 'rgba(59, 130, 246, 0)');

    if (charts.unique) charts.unique.destroy();
    charts.unique = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'Total de scans', data: totalValues, borderColor: '#3b82f6', backgroundColor: gradTotal, borderWidth: 2, tension: 0.35, fill: true, pointRadius: 0, pointHoverRadius: 5 },
                { label: 'Visitantes únicos', data: uniqueValues, borderColor: '#8b5cf6', backgroundColor: 'transparent', borderWidth: 2, borderDash: [6, 4], tension: 0.35, fill: false, pointRadius: 0, pointHoverRadius: 5 },
            ],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top', align: 'end', labels: { boxWidth: 10, boxHeight: 10, padding: 14, usePointStyle: true, pointStyle: 'circle' } },
                tooltip: {
                    backgroundColor: '#0b1220', borderColor: '#233355', borderWidth: 1,
                    padding: 10, titleColor: '#e6edf7', bodyColor: '#94a3b8',
                    callbacks: { label: (c) => ` ${c.dataset.label}: ${formatNumber(c.parsed.y)}` },
                },
            },
            scales: {
                x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 20 } },
                y: { beginAtZero: true, grid: { color: '#1a2942' }, ticks: { precision: 0 } },
            },
        },
    });
}

function renderDoughnut(canvasId, chartKey, rawData, labelField) {
    const labels = rawData.map((d) => d[labelField]);
    const values = rawData.map((d) => d.scans);
    const colors = labels.map((_, i) => PALETTE[i % PALETTE.length]);

    if (charts[chartKey]) charts[chartKey].destroy();

    if (!rawData.length) {
        charts[chartKey] = new Chart(document.getElementById(canvasId), {
            type: 'doughnut',
            data: { labels: ['Sem dados'], datasets: [{ data: [1], backgroundColor: ['#233355'] }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { enabled: false } }, cutout: '70%' },
        });
        return;
    }

    charts[chartKey] = new Chart(document.getElementById(canvasId), {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: '#16233f', borderWidth: 3, hoverOffset: 6 }] },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '65%',
            plugins: {
                legend: { position: 'right', labels: { boxWidth: 10, boxHeight: 10, padding: 12, usePointStyle: true, pointStyle: 'circle' } },
                tooltip: {
                    backgroundColor: '#0b1220', borderColor: '#233355', borderWidth: 1, padding: 10,
                    callbacks: { label: (ctx) => {
                        const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                        const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                        return ` ${formatNumber(ctx.parsed)} scans (${pct}%)`;
                    }},
                },
            },
        },
    });
}

async function loadDevices() { renderDoughnut('chart-devices', 'devices', await fetchJSON(`${API}/api/scans/devices`), 'device'); }
async function loadOS() { renderDoughnut('chart-os', 'os', await fetchJSON(`${API}/api/scans/os`), 'os'); }
async function loadBrowsers() { renderDoughnut('chart-browsers', 'browsers', await fetchJSON(`${API}/api/scans/browsers`), 'browser'); }

async function loadCities() {
    const data = await fetchJSON(`${API}/api/scans/cities?limit=8`);
    const ul = document.getElementById('list-cities');
    ul.innerHTML = '';
    if (!data.length) { ul.innerHTML = '<li class="empty">Sem dados ainda</li>'; return; }
    const total = data.reduce((acc, c) => acc + c.scans, 0);
    data.forEach((c) => {
        const li = document.createElement('li');
        const pct = total ? ((c.scans / total) * 100).toFixed(0) : 0;
        li.innerHTML = `
            <div class="city-name">
                <strong>${escapeHtml(c.city)}</strong>
                <small>${escapeHtml(c.country ?? '')}</small>
            </div>
            <div class="city-count">${formatNumber(c.scans)} <span style="color:var(--text-muted);font-size:12px;">(${pct}%)</span></div>
        `;
        ul.appendChild(li);
    });
}

// ------------------------------------------------------------------
// Tabela de QR Codes
// ------------------------------------------------------------------

async function loadQRRanking() {
    const data = await fetchJSON(`${API}/api/qr_codes`);
    const tbody = document.querySelector('#table-qr tbody');
    tbody.innerHTML = '';
    if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Sem dados ainda</td></tr>';
        return;
    }
    data.forEach((qr) => {
        const tr = document.createElement('tr');
        const nameHtml = qr.name
            ? `<span class="qr-name">${escapeHtml(qr.name)}</span>`
            : `<span class="qr-name muted">sem nome</span>`;
        tr.innerHTML = `
            <td class="mono">${escapeHtml(qr.qr_id)}</td>
            <td>${nameHtml}</td>
            <td class="dest" title="${escapeHtml(qr.destination_url)}">${escapeHtml(qr.destination_url)}</td>
            <td class="right scans-count">${formatNumber(qr.scans)}</td>
            <td class="right">
                <div class="actions-cell">
                    <button class="icon-btn" title="Ver QR Code" data-action="preview" data-id="${qr.qr_id}">👁</button>
                    <button class="icon-btn" title="Analytics" data-action="analytics" data-id="${qr.qr_id}">📊</button>
                    <button class="icon-btn" title="Editar" data-action="edit" data-id="${qr.qr_id}" data-url="${escapeHtml(qr.destination_url)}" data-name="${escapeHtml(qr.name ?? '')}">✎</button>
                    <button class="icon-btn danger" title="Excluir" data-action="delete" data-id="${qr.qr_id}">🗑</button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

document.querySelector('#table-qr').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    const qrId = btn.dataset.id;
    if (action === 'preview') openPreview(qrId);
    else if (action === 'analytics') openAnalytics(qrId);
    else if (action === 'edit') openQrModal({ qrId, url: btn.dataset.url, name: btn.dataset.name });
    else if (action === 'delete') await confirmDelete(qrId);
});

// ------------------------------------------------------------------
// Modais
// ------------------------------------------------------------------

const qrModal = document.getElementById('qr-modal');
const qrForm = document.getElementById('qr-form');
const qrFormError = document.getElementById('qr-form-error');

function openQrModal({ qrId = null, url = '', name = '' } = {}) {
    editingQrId = qrId;
    document.getElementById('qr-modal-title').textContent = qrId ? 'Editar QR Code' : 'Novo QR Code';
    document.getElementById('qr-url').value = url;
    document.getElementById('qr-name').value = name;
    qrFormError.hidden = true;
    qrFormError.textContent = '';
    qrModal.showModal();
    document.getElementById('qr-url').focus();
}

document.getElementById('new-qr-btn').addEventListener('click', () => openQrModal());
document.getElementById('qr-cancel').addEventListener('click', () => qrModal.close());

qrForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    qrFormError.hidden = true;
    const destination_url = document.getElementById('qr-url').value.trim();
    const name = document.getElementById('qr-name').value.trim() || null;

    if (!destination_url) { showFormError('Informe a URL de destino.'); return; }
    if (!/^https?:\/\//i.test(destination_url)) { showFormError('A URL precisa começar com http:// ou https://'); return; }

    const saveBtn = document.getElementById('qr-save');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Salvando...';

    try {
        if (editingQrId) {
            await fetchJSON(`${API}/api/qr_codes/${editingQrId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ destination_url, name }),
            });
        } else {
            const created = await fetchJSON(`${API}/api/qr_codes`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ destination_url, name }),
            });
            qrModal.close();
            await refreshAll();
            openPreview(created.qr_id);
            return;
        }
        qrModal.close();
        await refreshAll();
    } catch (err) {
        showFormError(err.message);
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Salvar';
    }
});

function showFormError(msg) {
    qrFormError.textContent = msg;
    qrFormError.hidden = false;
}

const previewModal = document.getElementById('preview-modal');

function openPreview(qrId) {
    const img = document.getElementById('preview-img');
    const baseUrl = `${window.location.origin}/r/${qrId}`;
    img.src = `${API}/api/qr_codes/${qrId}/image?size=10`;
    img.alt = `QR Code ${qrId}`;
    setText('preview-id', `QR ID: ${qrId}`);
    setText('preview-url', baseUrl);
    const dl = document.getElementById('preview-download');
    dl.href = `${API}/api/qr_codes/${qrId}/image?size=10`;
    dl.setAttribute('download', `qr_${qrId}.png`);
    previewModal.showModal();
}

document.getElementById('preview-close').addEventListener('click', () => previewModal.close());

const analyticsModal = document.getElementById('analytics-modal');

async function openAnalytics(qrId) {
    setText('analytics-title', `Analytics — ${qrId}`);
    setText('an-total', '—'); setText('an-unique', '—');
    document.getElementById('an-cities').innerHTML = '<li class="empty">Carregando...</li>';
    document.getElementById('an-devices').innerHTML = '<li class="empty">Carregando...</li>';
    analyticsModal.showModal();
    try {
        const data = await fetchJSON(`${API}/api/qr_codes/${qrId}/analytics`);
        setText('an-total', formatNumber(data.total_scans));
        setText('an-unique', formatNumber(data.unique_scans));

        const citiesUl = document.getElementById('an-cities');
        citiesUl.innerHTML = '';
        if (!data.cities.length) citiesUl.innerHTML = '<li class="empty">Sem dados</li>';
        else {
            const total = data.cities.reduce((a, c) => a + c.scans, 0);
            data.cities.forEach((c) => {
                const li = document.createElement('li');
                const pct = total ? ((c.scans / total) * 100).toFixed(0) : 0;
                li.innerHTML = `
                    <div class="city-name">
                        <strong>${escapeHtml(c.city)}</strong>
                        <small>${escapeHtml(c.country ?? '')}</small>
                    </div>
                    <div class="city-count">${formatNumber(c.scans)} <span style="color:var(--text-muted);font-size:12px;">(${pct}%)</span></div>
                `;
                citiesUl.appendChild(li);
            });
        }

        const devicesUl = document.getElementById('an-devices');
        devicesUl.innerHTML = '';
        if (!data.devices.length) devicesUl.innerHTML = '<li class="empty">Sem dados</li>';
        else {
            const total = data.devices.reduce((a, d) => a + d.scans, 0);
            data.devices.forEach((d) => {
                const li = document.createElement('li');
                const pct = total ? ((d.scans / total) * 100).toFixed(0) : 0;
                li.innerHTML = `
                    <div class="city-name"><strong>${escapeHtml(d.device)}</strong></div>
                    <div class="city-count">${formatNumber(d.scans)} <span style="color:var(--text-muted);font-size:12px;">(${pct}%)</span></div>
                `;
                devicesUl.appendChild(li);
            });
        }
    } catch (err) {
        showError(`Falha ao carregar analytics: ${err.message}`);
        analyticsModal.close();
    }
}

document.getElementById('analytics-close').addEventListener('click', () => analyticsModal.close());

async function confirmDelete(qrId) {
    const ok = window.confirm(
        `Excluir o QR Code "${qrId}"?\n\nTodos os scans associados também serão apagados. Essa ação não pode ser desfeita.`
    );
    if (!ok) return;
    try {
        const res = await fetchJSON(`${API}/api/qr_codes/${qrId}`, { method: 'DELETE' });
        await refreshAll();
        console.log(`QR ${qrId} removido. Scans apagados: ${res.scans_deleted}`);
    } catch (err) {
        showError(`Falha ao excluir: ${err.message}`);
    }
}

// ------------------------------------------------------------------
// Refresh geral
// ------------------------------------------------------------------

async function refreshAll() {
    try {
        await Promise.all([
            loadStats(), loadDaily(), loadUniqueDaily(),
            loadDevices(), loadOS(), loadBrowsers(),
            loadCities(), loadQRRanking(),
        ]);
        setText('last-update', `Última atualização: ${new Date().toLocaleTimeString('pt-BR')}`);
    } catch (err) {
        console.error(err);
        showError(`Falha ao carregar dados: ${err.message}`);
    }
}

document.getElementById('refresh-btn').addEventListener('click', refreshAll);
refreshAll();
setInterval(refreshAll, 30000);