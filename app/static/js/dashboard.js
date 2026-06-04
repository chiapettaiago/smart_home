const API_BASE_URL = '/api';
const SERVICE_BASE_URL = '';
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content || '';

const appState = {
    devices: [],
    automations: {},
    presence: {},
    energy: {},
    actions: [],
};
let dashboardRequestInFlight = false;
let dashboardRefreshPending = false;

document.addEventListener('DOMContentLoaded', async () => {
    initializeDeviceRegistration();
    initializeDeviceContextMenu();
    initializeDeviceActions();
    await loadDashboardData();
    updateCurrentTime();
    setInterval(updateCurrentTime, 1000);
    setInterval(loadDashboardData, 5000);
});

function initializeDeviceActions() {
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-device-action]');
        if (!button) return;
        event.stopPropagation();
        executeAction(Number(button.dataset.deviceId), button.dataset.deviceAction);
    });

    document.addEventListener('click', event => {
        const automationDelete = event.target.closest('[data-automation-delete]');
        if (automationDelete) {
            event.stopPropagation();
            deleteAutomation(Number(automationDelete.dataset.automationDelete));
            return;
        }

        const presenceButton = event.target.closest('[data-presence-action]');
        if (presenceButton) {
            event.stopPropagation();
            setPresence(presenceButton.dataset.presenceUser, presenceButton.dataset.presenceAction === 'home');
        }
    });
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function initializeDeviceRegistration() {
    const modal = document.getElementById('device-modal');
    const form = document.getElementById('device-form');
    const options = document.getElementById('device-type-options');
    const field = document.getElementById('device-field');
    const closeButton = document.getElementById('btn-close-device-modal');
    const backButton = document.getElementById('btn-back-device-type');

    if (!modal || !form || !options || !field || !closeButton || !backButton) return;

    const modalController = window.bootstrap
        ? window.bootstrap.Modal.getOrCreateInstance(modal)
        : null;
    let selectedType = null;

    const resetModal = () => {
        form.reset();
        form.classList.add('hidden');
        options.classList.remove('hidden');
        const errorElement = document.getElementById('device-form-error');
        if (errorElement) errorElement.classList.add('hidden');
        selectedType = null;
    };

    const openModal = () => {
        if (modalController) {
            modalController.show();
            return;
        }
        modal.classList.add('show');
        modal.style.display = 'block';
        modal.setAttribute('aria-hidden', 'false');
    };

    const closeModal = () => {
        if (modalController) {
            modalController.hide();
            return;
        }
        modal.classList.remove('show');
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
        resetModal();
    };

    document.querySelectorAll('.js-open-device-modal').forEach(button => {
        button.addEventListener('click', openModal);
    });

    closeButton.addEventListener('click', closeModal);
    modal.addEventListener('hidden.bs.modal', resetModal);

    document.querySelectorAll('.device-type-option').forEach(option => {
        option.addEventListener('click', () => {
            selectedType = option.dataset.deviceType;
            options.classList.add('hidden');
            form.classList.remove('hidden');
            const error = document.getElementById('device-form-error');
            if (error) error.classList.add('hidden');

            if (selectedType === 'roku') {
                setText('device-field-label', 'IP da TV Roku');
                setText('device-field-help', 'Exemplo: 192.168.1.100');
                field.placeholder = '192.168.1.100';
                field.inputMode = 'decimal';
            } else {
                setText('device-field-label', 'Token do Home Assistant');
                setText('device-field-help', 'Informe o Long-Lived Access Token para sincronizar dispositivos Tuya.');
                field.placeholder = 'Cole o token do Home Assistant';
                field.inputMode = 'text';
            }
            field.focus();
        });
    });

    backButton.addEventListener('click', () => {
        form.reset();
        form.classList.add('hidden');
        options.classList.remove('hidden');
        selectedType = null;
    });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const value = field.value.trim();
        const submit = document.getElementById('btn-submit-device');
        const error = document.getElementById('device-form-error');
        const endpoint = selectedType === 'roku' ? '/roku/register' : '/tuya/sync-home-assistant';
        const body = selectedType === 'roku' ? { ip: value } : { ha_token: value };

        if (!submit || !error) return;

        submit.disabled = true;
        submit.textContent = 'Adicionando...';
        error.classList.add('hidden');

        try {
            const response = await fetch(`${SERVICE_BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF_TOKEN },
                body: JSON.stringify(body),
            });
            const result = await response.json();

            if (!response.ok || !result.success) {
                throw new Error(result.detail || result.message || 'Não foi possível cadastrar o dispositivo.');
            }

            showNotification(result.message, 'success');
            closeModal();
            await loadDashboardData();
        } catch (requestError) {
            error.textContent = requestError.message;
            error.classList.remove('hidden');
        } finally {
            submit.disabled = false;
            submit.textContent = 'Adicionar dispositivo';
        }
    });
}

async function loadDashboardData() {
    if (dashboardRequestInFlight) {
        dashboardRefreshPending = true;
        return;
    }
    dashboardRequestInFlight = true;
    try {
        const response = await fetch(`${API_BASE_URL}/dashboard/data`, {
            cache: 'no-store',
            headers: { 'Accept': 'application/json' },
        });
        if (!response.ok) throw new Error(`Dashboard retornou ${response.status}`);
        const data = await response.json();

        appState.devices = data.devices.list;
        appState.automations = data.automations;
        appState.presence = data.presence.users;
        appState.energy = data.energy;
        appState.actions = data.actions.recent;

        updateStats(data);
        renderDevicesGrid();
        renderDevicesList();
        renderActionsList();
        renderEnergyData();
        renderAutomationsList();
        renderPresenceList();
    } catch (error) {
        console.error('Erro ao carregar dados do dashboard:', error);
    } finally {
        dashboardRequestInFlight = false;
        if (dashboardRefreshPending) {
            dashboardRefreshPending = false;
            loadDashboardData();
        }
    }
}

function updateStats(data) {
    setText('stat-online', data.devices.online);
    setText('stat-total', `de ${data.devices.total}`);
    setText('stat-watts', `${Math.round(data.energy.total_watts)}W`);
    setText('stat-kwh', `${data.energy.total_kwh.toFixed(2)} kWh`);

    const presenceCount = Object.values(data.presence.users).filter(v => v).length;
    setText('stat-presence', presenceCount > 0 ? 'Sim' : 'Não');
    setText('stat-automations', data.automations.active);
    setText('stat-auto-info', `de ${data.automations.total}`);
}

function renderDevicesGrid() {
    const container = document.getElementById('devices-grid');
    if (!container) return;

    if (!appState.devices || appState.devices.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔌</div><div class="empty-state-title">Nenhum dispositivo</div><div class="empty-state-text">Cadastre seu primeiro dispositivo para começar</div></div>';
        return;
    }

    container.innerHTML = appState.devices.map(device => `
        <div class="device-card device-context-target ${device.status}" data-device-id="${device.id}">
            <div class="device-header">
                <div class="device-icon">${getDeviceIcon(device.type)}</div>
                <div class="device-header-status">
                    ${renderPowerState(device)}
                    ${renderPowerIndicator(device)}
                    <button class="context-trigger" type="button" data-device-menu-trigger="${device.id}" aria-label="Mais opções para ${escapeHtml(device.name)}">•••</button>
                </div>
            </div>
            <div class="device-name">${device.name}</div>
            <div class="device-type">${formatDeviceType(device.type)}</div>
            ${device.type === 'roku' && device.now_playing ? `<div class="device-room">🎬 ${formatNowPlaying(device.now_playing)}</div>` : ''}
            ${device.room ? `<div class="device-room">🏠 ${device.room}</div>` : ''}
            <div class="device-updated">${formatTime(new Date(device.updated_at))}</div>
            ${renderPowerActions(device)}
        </div>
    `).join('');
}

function renderDevicesList() {
    const container = document.getElementById('devices-list');
    if (!container) return;

    if (!appState.devices || appState.devices.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔌</div><div class="empty-state-title">Nenhum dispositivo</div></div>';
        return;
    }

    container.innerHTML = appState.devices.map(device => `
        <div class="device-list-item device-context-target" data-device-id="${device.id}">
            <div class="item-info">
                <div class="item-title">${device.name}</div>
                <div class="item-subtitle">${formatDeviceType(device.type)} • ${device.room || 'Sem cômodo'} • ${device.ip || 'Sem IP'}</div>
                ${device.type === 'roku' && device.now_playing ? `<div class="item-subtitle">Assistindo agora: ${formatNowPlaying(device.now_playing)}</div>` : ''}
            </div>
            <div class="item-actions">
                ${renderPowerBadge(device)}
                ${renderPowerState(device)}
                <button class="context-trigger" type="button" data-device-menu-trigger="${device.id}" aria-label="Mais opções para ${escapeHtml(device.name)}">•••</button>
            </div>
        </div>
    `).join('');
}

function renderActionsList() {
    const container = document.getElementById('actions-list');
    if (!container) return;

    if (!appState.actions || appState.actions.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📋</div><div class="empty-state-title">Nenhuma ação recente</div></div>';
        return;
    }

    container.innerHTML = appState.actions.map(action => `
        <div class="action-item">
            <div class="item-info">
                <div class="item-title">${action.device_name || `Dispositivo #${action.device_id}`}</div>
                <div class="item-subtitle">${action.action_label || formatActionLabel(action.action, action.params)} • ${formatTime(new Date(action.executed_at))}</div>
            </div>
            <span class="item-badge ${action.status === 'success' ? 'success' : 'danger'}">
                ${action.status === 'success' ? '✓ Sucesso' : '✗ Falha'}
            </span>
        </div>
    `).join('');
}

function renderEnergyData() {
    if (document.getElementById('energy-total')) {
        setText('energy-total', `${appState.energy.total_kwh?.toFixed(2)} kWh`);
        setText('energy-avg', `${Math.round(appState.energy.avg_watts)} W`);
        setText('energy-max', '-- W');
    }

    const container = document.getElementById('energy-by-device');
    if (!container) return;

    if (!appState.energy.by_device || appState.energy.by_device.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚡</div><div class="empty-state-title">Sem dados de energia</div></div>';
        return;
    }

    container.innerHTML = appState.energy.by_device.map(device => `
        <div class="energy-device-item">
            <div class="energy-device-name">${device.device_name}</div>
            <div class="energy-stat"><span class="energy-stat-label">Consumo:</span><span class="energy-stat-value">${device.total_kwh?.toFixed(3)} kWh</span></div>
            <div class="energy-stat"><span class="energy-stat-label">Potência:</span><span class="energy-stat-value">${Math.round(device.total_watts)} W</span></div>
            <div class="energy-stat"><span class="energy-stat-label">Leituras:</span><span class="energy-stat-value">${device.readings_count}</span></div>
        </div>
    `).join('');
}

function renderAutomationsList() {
    const container = document.getElementById('automations-list');
    if (!container) return;

    const automations = appState.automations?.automations || [];
    if (!automations.length) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚙️</div><div class="empty-state-title">Nenhuma automação</div></div>';
        return;
    }

    container.innerHTML = automations.map(auto => `
        <div class="automation-item">
            <div class="item-info">
                <div class="item-title">${auto.name}</div>
                <div class="item-subtitle">${auto.trigger} • ${auto.actions.length} ação(ões)</div>
            </div>
            <div class="item-actions">
                <span class="item-badge ${auto.active ? 'success' : 'warning'}">${auto.active ? '✓ Ativa' : '⊗ Inativa'}</span>
                <button class="btn btn-sm btn-danger-soft" type="button" data-automation-delete="${auto.id}">Excluir</button>
            </div>
        </div>
    `).join('');
}

function renderPresenceList() {
    const container = document.getElementById('presence-list');
    if (!container) return;

    if (!appState.presence || Object.keys(appState.presence).length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">👤</div><div class="empty-state-title">Nenhum usuário</div></div>';
        return;
    }

    container.innerHTML = Object.entries(appState.presence).map(([user, isHome]) => `
        <div class="presence-item">
            <div class="item-info">
                <div class="item-title">${user}</div>
                <div class="item-subtitle">${isHome ? 'Em casa' : 'Fora de casa'}</div>
            </div>
            <div class="item-actions">
                <button class="btn btn-small btn-on" type="button" data-presence-action="home" data-presence-user="${escapeHtml(user)}" ${isHome ? 'disabled' : ''}>Em Casa</button>
                <button class="btn btn-small btn-off" type="button" data-presence-action="away" data-presence-user="${escapeHtml(user)}" ${!isHome ? 'disabled' : ''}>Fora</button>
            </div>
        </div>
    `).join('');
}

async function executeAction(deviceId, action, params = null) {
    let result;
    try {
        const bodyData = { action };
        if (params) bodyData.params = params;

        const response = await fetch(`${SERVICE_BASE_URL}/devices/${deviceId}/action`, {
            method: 'POST',
            headers: { 'Accept': 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': CSRF_TOKEN },
            body: JSON.stringify(bodyData),
        });

        result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.detail || result.message || `Erro ao executar ${action}`);
        }
    } catch (error) {
        console.error('Erro ao executar ação:', error);
        showNotification(error.message || 'Erro ao executar ação', 'error');
        return;
    }

    try {
        updateDeviceStateAfterAction(deviceId, action, params);
    } catch (error) {
        console.error('Erro ao atualizar interface após executar ação:', error);
    }

    showNotification(result.message || `${action} executado com sucesso`, 'success');
    setTimeout(loadDashboardData, 700);
    setTimeout(loadDashboardData, 1800);
    setTimeout(loadDashboardData, 4000);
    setTimeout(loadDashboardData, 8000);
}

function updateDeviceStateAfterAction(deviceId, action, params = null) {
    const device = appState.devices.find(item => item.id === deviceId);
    if (!device) return;

    if (action === 'turn_on') device.power_state = 'on';
    if (action === 'turn_off') device.power_state = 'off';
    if (action === 'toggle' && ['on', 'off'].includes(device.power_state)) {
        device.power_state = device.power_state === 'on' ? 'off' : 'on';
    }
    if (action === 'set_brightness' && params?.brightness != null) {
        device.brightness = Number(params.brightness);
    }
    if (action === 'set_rgb_color' && Array.isArray(params?.rgb_color)) {
        device.rgb_color = params.rgb_color;
    }
    if (action === 'set_color_temp') {
        delete device.rgb_color;
    }

    renderDevicesGrid();
    renderDevicesList();

    const menu = document.getElementById('device-context-menu');
    const content = document.getElementById('device-context-content');
    if (menu && content && !menu.classList.contains('hidden')) {
        refreshDeviceContextContent(device);
    }
}

function refreshDeviceContextContent(device) {
    const content = document.getElementById('device-context-content');
    if (!content) return;

    const activeElement = document.activeElement;
    const activeId = content.contains(activeElement) ? activeElement.id : '';
    const selection = activeElement && typeof activeElement.selectionStart === 'number'
        ? { start: activeElement.selectionStart, end: activeElement.selectionEnd }
        : null;

    content.innerHTML = renderDeviceContextContent(device);

    if (!activeId) return;
    const nextActiveElement = document.getElementById(activeId);
    if (!nextActiveElement) return;
    nextActiveElement.focus();
    if (selection && typeof nextActiveElement.setSelectionRange === 'function') {
        nextActiveElement.setSelectionRange(selection.start, selection.end);
    }
}

async function deleteDevice(deviceId, deviceName) {
    const confirmed = await showSystemModal({
        title: 'Excluir dispositivo',
        message: `Deseja realmente excluir o dispositivo "${deviceName || deviceId}"?`,
        confirmText: 'Excluir',
        cancelText: 'Cancelar',
    });
    if (!confirmed) return;

    try {
        const response = await fetch(`${SERVICE_BASE_URL}/devices/${deviceId}`, {
            method: 'DELETE',
            headers: { 'Accept': 'application/json', 'X-CSRF-Token': CSRF_TOKEN },
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.detail || 'Falha ao excluir dispositivo.');
        }

        showNotification(result.message || 'Dispositivo excluído com sucesso.', 'success');
        await loadDashboardData();
    } catch (error) {
        console.error('Erro ao excluir dispositivo:', error);
        showNotification(error.message || 'Erro ao excluir dispositivo.', 'error');
    }
}

async function deleteAutomation(automationId) {
    const automation = (appState.automations?.automations || []).find(item => item.id === automationId);
    const confirmed = await showSystemModal({
        title: 'Excluir automação',
        message: `Deseja realmente excluir a automação "${automation?.name || automationId}"?`,
        confirmText: 'Excluir',
        cancelText: 'Cancelar',
    });
    if (!confirmed) return;

    try {
        const response = await fetch(`${SERVICE_BASE_URL}/automations/${automationId}`, {
            method: 'DELETE',
            headers: { 'Accept': 'application/json', 'X-CSRF-Token': CSRF_TOKEN },
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.detail || 'Falha ao excluir automação.');
        }

        showNotification(result.message || 'Automação excluída com sucesso.', 'success');
        await loadDashboardData();
    } catch (error) {
        console.error('Erro ao excluir automação:', error);
        showNotification(error.message || 'Erro ao excluir automação.', 'error');
    }
}

function updatePresenceStatus(user, isHome) {
    appState.presence[user] = isHome;
    renderPresenceList();
}

async function setPresence(user, isHome) {
    try {
        const endpoint = isHome ? 'home' : 'away';
        const response = await fetch(`${SERVICE_BASE_URL}/presence/${encodeURIComponent(user)}/${endpoint}`, {
            method: 'POST',
            headers: { 'Accept': 'application/json', 'X-CSRF-Token': CSRF_TOKEN },
        });
        if (response.ok) {
            showNotification(`${user} marcado como ${isHome ? 'em casa' : 'fora de casa'}`, 'success');
            updatePresenceStatus(user, isHome);
            return;
        }
        showNotification('Erro ao atualizar presença', 'error');
    } catch (error) {
        console.error('Erro ao atualizar presença:', error);
        showNotification('Erro ao atualizar presença', 'error');
    }
}

function showNotification(message, type = 'info') {
    const title = type === 'success' ? 'Sucesso' : type === 'error' ? 'Erro' : 'Aviso';
    showSystemModal({ title, message, confirmText: 'Fechar', hideCancel: true });
}

function updateCurrentTime() {
    const timeElement = document.getElementById('current-time');
    if (!timeElement) return;

    const time = new Date().toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit',
    });
    timeElement.textContent = time;
}

function getDeviceIcon(type) {
    const icons = {
        tuya: '💡',
        roku: '📺',
        android: '📱',
        pc_windows: '🖥️',
        pc_linux: '🐧',
        sensor: '📊',
        other: '⚙️',
    };
    return icons[type] || '⚙️';
}

function formatDeviceType(type) {
    const names = {
        tuya: 'Tuya',
        roku: 'Roku TV',
        android: 'Android',
        pc_windows: 'PC Windows',
        pc_linux: 'PC Linux',
        sensor: 'Sensor',
        other: 'Outro',
    };
    return names[type] || type;
}

function formatTime(date) {
    const now = new Date();
    const diff = now - date;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (seconds < 60) return 'agora';
    if (minutes < 60) return `há ${minutes}m`;
    if (hours < 24) return `há ${hours}h`;
    if (days < 7) return `há ${days}d`;

    return date.toLocaleDateString('pt-BR');
}

function formatNowPlaying(nowPlaying) {
    if (!nowPlaying || !nowPlaying.app_name) return 'Indisponível';
    if (nowPlaying.content_title) return `${nowPlaying.app_name} - ${nowPlaying.content_title}`;
    return nowPlaying.app_name;
}

function initializeDeviceContextMenu() {
    const menu = document.getElementById('device-context-menu');
    const closeButton = document.getElementById('device-context-close');
    const content = document.getElementById('device-context-content');
    if (!menu || !closeButton) return;

    let longPressTimer = null;
    let pointerStart = null;
    let suppressNextClick = false;

    document.addEventListener('contextmenu', event => {
        const target = event.target.closest('.device-context-target');
        if (!target) return;
        event.preventDefault();
        openDeviceContextMenu(Number(target.dataset.deviceId), event.clientX, event.clientY);
    });

    document.addEventListener('click', event => {
        if (suppressNextClick) {
            suppressNextClick = false;
            event.preventDefault();
            event.stopPropagation();
            return;
        }
        const trigger = event.target.closest('[data-device-menu-trigger]');
        if (trigger) {
            event.stopPropagation();
            const rect = trigger.getBoundingClientRect();
            openDeviceContextMenu(Number(trigger.dataset.deviceMenuTrigger), rect.right, rect.bottom + 6);
            return;
        }
        const contextAction = event.target.closest('[data-context-action]');
        if (contextAction && menu.contains(contextAction)) {
            event.stopPropagation();
            handleDeviceContextAction(contextAction);
            return;
        }
        if (!menu.contains(event.target)) closeDeviceContextMenu();
    });

    if (content) {
        content.addEventListener('input', event => {
            const input = event.target.closest('[data-tuya-brightness-input]');
            if (!input) return;
            updateTuyaBrightnessLabel(input.id, `${input.id}-value`);
        });

        content.addEventListener('change', event => {
            const target = event.target;
            if (target.matches('[data-tuya-brightness-input]')) {
                applyTuyaBrightness(Number(target.dataset.deviceId), target.id);
                return;
            }
            if (target.matches('[data-tuya-color-input]')) {
                applyTuyaColor(Number(target.dataset.deviceId), target.id);
                return;
            }
            if (target.matches('[data-tuya-color-temp-input]')) {
                applyTuyaColorTemp(Number(target.dataset.deviceId), target.id);
                return;
            }
            if (target.matches('[data-tuya-temperature-input]')) {
                applyTuyaTemperature(Number(target.dataset.deviceId), target.id);
                return;
            }
            if (target.matches('[data-tuya-fan-input]')) {
                applyTuyaFanMode(Number(target.dataset.deviceId), target.id);
                return;
            }
            if (target.matches('[data-tuya-preset-input]')) {
                applyTuyaPresetMode(Number(target.dataset.deviceId), target.id);
            }
        });
    }

    document.addEventListener('pointerdown', event => {
        const target = event.target.closest('.device-context-target');
        if (!target || event.pointerType === 'mouse' || event.target.closest('button, input, select, a')) return;
        pointerStart = { x: event.clientX, y: event.clientY };
        longPressTimer = setTimeout(() => {
            openDeviceContextMenu(Number(target.dataset.deviceId), event.clientX, event.clientY);
            longPressTimer = null;
            suppressNextClick = true;
            if (navigator.vibrate) navigator.vibrate(35);
        }, 560);
    });

    document.addEventListener('pointermove', event => {
        if (!longPressTimer || !pointerStart) return;
        if (Math.abs(event.clientX - pointerStart.x) > 10 || Math.abs(event.clientY - pointerStart.y) > 10) {
            clearLongPress();
        }
    });
    document.addEventListener('pointerup', clearLongPress);
    document.addEventListener('pointercancel', clearLongPress);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeDeviceContextMenu();
    });
    window.addEventListener('resize', closeDeviceContextMenu);
    window.addEventListener('scroll', event => {
        if (!menu.contains(event.target)) closeDeviceContextMenu();
    }, true);
    closeButton.addEventListener('click', closeDeviceContextMenu);

    function clearLongPress() {
        if (longPressTimer) clearTimeout(longPressTimer);
        longPressTimer = null;
        pointerStart = null;
    }
}

function openDeviceContextMenu(deviceId, x, y) {
    const menu = document.getElementById('device-context-menu');
    const content = document.getElementById('device-context-content');
    const title = document.getElementById('device-context-title');
    const device = appState.devices.find(item => item.id === deviceId);
    if (!menu || !content || !title || !device) return;

    title.textContent = device.name;
    content.innerHTML = renderDeviceContextContent(device);
    menu.classList.remove('hidden');

    const margin = 12;
    const menuRect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(margin, Math.min(x, window.innerWidth - menuRect.width - margin))}px`;
    menu.style.top = `${Math.max(margin, Math.min(y, window.innerHeight - menuRect.height - margin))}px`;
}

function closeDeviceContextMenu() {
    const menu = document.getElementById('device-context-menu');
    if (menu) menu.classList.add('hidden');
}

function handleDeviceContextAction(target) {
    const action = target.dataset.contextAction;
    const deviceId = Number(target.dataset.deviceId);
    if (!action || Number.isNaN(deviceId)) return;

    if (action === 'step_brightness') {
        stepTuyaBrightness(deviceId, target.dataset.inputId, Number(target.dataset.step || 0));
        return;
    }
    if (action === 'open_app') {
        executeAction(deviceId, action, { app_name: target.dataset.appName || 'netflix' });
        return;
    }
    if (action === 'set_rgb_color' && target.dataset.randomColor === 'true') {
        const rand = () => Math.floor(Math.random() * 256);
        executeAction(deviceId, action, { rgb_color: [rand(), rand(), rand()] });
        return;
    }
    if (action === 'set_rgb_color' && target.dataset.rgbColor) {
        executeAction(deviceId, action, { rgb_color: target.dataset.rgbColor.split(',').map(value => Number(value.trim())) });
        return;
    }
    if (action === 'set_brightness') {
        applyTuyaBrightness(deviceId, target.dataset.inputId);
        return;
    }
    if (action === 'set_rgb_color') {
        applyTuyaColor(deviceId, target.dataset.inputId);
        return;
    }
    if (action === 'set_color_temp') {
        if (target.dataset.colorTemp) {
            executeAction(deviceId, action, { color_temp: Number(target.dataset.colorTemp) });
            return;
        }
        applyTuyaColorTemp(deviceId, target.dataset.inputId);
        return;
    }
    if (action === 'set_temperature') {
        applyTuyaTemperature(deviceId, target.dataset.inputId);
        return;
    }
    if (action === 'set_fan_mode') {
        applyTuyaFanMode(deviceId, target.dataset.inputId);
        return;
    }
    if (action === 'set_preset_mode') {
        applyTuyaPresetMode(deviceId, target.dataset.inputId);
        return;
    }
    if (action === 'show_details') {
        showDeviceDetails(deviceId);
        return;
    }
    if (action === 'delete_device') {
        deleteDeviceFromContext(deviceId);
        return;
    }

    executeAction(deviceId, action);
}

function renderDeviceContextContent(device) {
    const disablePoweredOffControls = device.power_state === 'off' ? 'disabled' : '';
    if (isTuyaLamp(device)) return renderTuyaLampControls(device);

    const rokuActions = device.type === 'roku' ? `
        <div class="device-context-section">
            <div class="context-section-label">Atalhos da TV</div>
            <div class="device-actions">
                <button class="btn-small" type="button" data-context-action="open_app" data-device-id="${device.id}" data-app-name="netflix" ${disablePoweredOffControls}>Netflix</button>
                <button class="btn-small" type="button" data-context-action="open_app" data-device-id="${device.id}" data-app-name="youtube" ${disablePoweredOffControls}>YouTube</button>
                <button class="btn-small" type="button" data-context-action="close_app" data-device-id="${device.id}" ${disablePoweredOffControls}>Home</button>
            </div>
        </div>
    ` : '';
    const tuyaActions = device.type === 'tuya' ? renderTuyaControls(device) : '';

    return `
        ${tuyaActions}
        ${rokuActions}
        <div class="context-footer">
            <button class="btn btn-soft" type="button" data-context-action="show_details" data-device-id="${device.id}">Detalhes</button>
            <button class="btn btn-danger-soft" type="button" data-context-action="delete_device" data-device-id="${device.id}">Excluir</button>
        </div>
    `;
}

function isTuyaLamp(device) {
    return device.type === 'tuya' && (!device.entity_domain || device.entity_domain === 'light');
}

function deleteDeviceFromContext(deviceId) {
    const device = appState.devices.find(item => item.id === deviceId);
    closeDeviceContextMenu();
    deleteDevice(deviceId, device?.name || '');
}

function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    })[char]);
}

function renderTuyaControls(device) {
    const uid = `tuya-${device.id}-context`;
    const disablePoweredOffControls = device.power_state === 'off' ? 'disabled' : '';
    return `
        <div class="tuya-controls">
            <div class="context-section-label">Controles avançados</div>
            <div class="tuya-controls-row">
                <button class="btn-small" type="button" data-context-action="toggle" data-device-id="${device.id}" ${disablePoweredOffControls}>Alternar</button>
                <button class="btn-small" type="button" data-context-action="get_status" data-device-id="${device.id}" ${disablePoweredOffControls}>Status</button>
                <button class="btn-small" type="button" data-context-action="set_rgb_color" data-device-id="${device.id}" data-random-color="true" ${disablePoweredOffControls}>Cor aleatória</button>
            </div>
            <div class="tuya-controls-row">
                <label class="tuya-label" for="${uid}-brightness">Brilho</label>
                <input class="tuya-range" id="${uid}-brightness" data-tuya-brightness-input data-device-id="${device.id}" type="range" min="1" max="255" value="160" ${disablePoweredOffControls}>
                <button class="btn-small" type="button" data-context-action="set_brightness" data-device-id="${device.id}" data-input-id="${uid}-brightness" ${disablePoweredOffControls}>Aplicar</button>
            </div>
            <div class="tuya-controls-row">
                <label class="tuya-label" for="${uid}-ct">Temp. cor</label>
                <input class="tuya-range" id="${uid}-ct" data-tuya-color-temp-input data-device-id="${device.id}" type="range" min="153" max="500" value="300" ${disablePoweredOffControls}>
                <button class="btn-small" type="button" data-context-action="set_color_temp" data-device-id="${device.id}" data-input-id="${uid}-ct" ${disablePoweredOffControls}>Aplicar</button>
            </div>
            <div class="tuya-controls-row">
                <label class="tuya-label" for="${uid}-temp">Temperatura</label>
                <input class="tuya-input" id="${uid}-temp" data-tuya-temperature-input data-device-id="${device.id}" type="number" step="0.5" value="22" min="16" max="30" ${disablePoweredOffControls}>
                <button class="btn-small" type="button" data-context-action="set_temperature" data-device-id="${device.id}" data-input-id="${uid}-temp" ${disablePoweredOffControls}>Aplicar</button>
            </div>
            <div class="tuya-controls-row">
                <label class="tuya-label" for="${uid}-fan">Fan mode</label>
                <select class="tuya-select" id="${uid}-fan" data-tuya-fan-input data-device-id="${device.id}" ${disablePoweredOffControls}>
                    <option value="auto">auto</option>
                    <option value="low">low</option>
                    <option value="medium">medium</option>
                    <option value="high">high</option>
                </select>
                <button class="btn-small" type="button" data-context-action="set_fan_mode" data-device-id="${device.id}" data-input-id="${uid}-fan" ${disablePoweredOffControls}>Aplicar</button>
            </div>
            <div class="tuya-controls-row">
                <label class="tuya-label" for="${uid}-preset">Preset</label>
                <select class="tuya-select" id="${uid}-preset" data-tuya-preset-input data-device-id="${device.id}" ${disablePoweredOffControls}>
                    <option value="none">none</option>
                    <option value="eco">eco</option>
                    <option value="comfort">comfort</option>
                    <option value="sleep">sleep</option>
                    <option value="boost">boost</option>
                </select>
                <button class="btn-small" type="button" data-context-action="set_preset_mode" data-device-id="${device.id}" data-input-id="${uid}-preset" ${disablePoweredOffControls}>Aplicar</button>
            </div>
        </div>
    `;
}

function renderTuyaLampControls(device) {
    const uid = `tuya-${device.id}-context`;
    const parsedBrightness = Number(device.brightness);
    const brightness = device.brightness != null && Number.isFinite(parsedBrightness)
        ? Math.max(1, Math.min(255, parsedBrightness))
        : 160;
    const color = rgbToHex(device.rgb_color);
    return `
        <div class="lamp-controls">
            <div class="lamp-control">
                <div class="lamp-control-head">
                    <span class="lamp-control-icon">☀</span>
                    <span>
                        <strong>Brilho</strong>
                        <small>Aumentar ou diminuir intensidade</small>
                    </span>
                    <output class="lamp-brightness-value" id="${uid}-brightness-value">${Math.round(brightness / 255 * 100)}%</output>
                </div>
                <div class="lamp-brightness-row">
                    <button class="lamp-step-button" type="button" data-context-action="step_brightness" data-device-id="${device.id}" data-input-id="${uid}-brightness" data-step="-25" aria-label="Diminuir brilho">−</button>
                    <input class="lamp-range" id="${uid}-brightness" data-tuya-brightness-input data-device-id="${device.id}" type="range" min="1" max="255" value="${brightness}" aria-label="Brilho">
                    <button class="lamp-step-button" type="button" data-context-action="step_brightness" data-device-id="${device.id}" data-input-id="${uid}-brightness" data-step="25" aria-label="Aumentar brilho">+</button>
                </div>
            </div>
            <div class="lamp-control lamp-color-control">
                <label class="lamp-control-head" for="${uid}-color">
                    <span class="lamp-control-icon lamp-color-icon"></span>
                    <span>
                        <strong>Cor</strong>
                        <small>Mudar a cor da lâmpada</small>
                    </span>
                    <input class="lamp-color-input" id="${uid}-color" data-tuya-color-input data-device-id="${device.id}" type="color" value="${color}" aria-label="Cor da lâmpada">
                </label>
                <div class="lamp-color-actions">
                    <button class="btn-small" type="button" data-context-action="set_rgb_color" data-device-id="${device.id}" data-rgb-color="255,255,255" aria-label="Voltar para branco">Branco</button>
                </div>
            </div>
        </div>
    `;
}

function renderPowerState(device) {
    if (!device.power_state) return '';
    const isOn = device.power_state === 'on';
    return `<span class="power-state ${isOn ? 'on' : 'off'}">${isOn ? 'Ligada' : 'Desligada'}</span>`;
}

function renderPowerIndicator(device) {
    const isOn = device.power_state === 'on';
    const label = device.power_state === 'off' ? 'Desligado' : 'Estado desconhecido';
    return `<div class="device-status ${isOn ? 'on' : ''}" title="${isOn ? 'Ligado' : label}"></div>`;
}

function renderPowerBadge(device) {
    const isOn = device.power_state === 'on';
    const label = device.power_state === 'off' ? '⚫ Desligado' : '⚫ Estado desconhecido';
    return `<span class="item-badge ${isOn ? 'success' : ''}">${isOn ? '🟢 Ligado' : label}</span>`;
}

function renderPowerActions(device) {
    return `
        <div class="device-actions">
            <button class="btn-small btn-on" data-device-id="${device.id}" data-device-action="turn_on"><span class="action-dot"></span>Ligar</button>
            <button class="btn-small btn-off" data-device-id="${device.id}" data-device-action="turn_off"><span class="action-dot"></span>Desligar</button>
        </div>
    `;
}

function applyTuyaBrightness(deviceId, inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    executeAction(deviceId, 'set_brightness', { brightness: Number(input.value) });
}

function stepTuyaBrightness(deviceId, inputId, amount) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.value = Math.max(Number(input.min), Math.min(Number(input.max), Number(input.value) + amount));
    updateTuyaBrightnessLabel(inputId, `${inputId}-value`);
    applyTuyaBrightness(deviceId, inputId);
}

function updateTuyaBrightnessLabel(inputId, outputId) {
    const input = document.getElementById(inputId);
    const output = document.getElementById(outputId);
    if (input && output) output.textContent = `${Math.round(Number(input.value) / 255 * 100)}%`;
}

function applyTuyaColor(deviceId, inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    executeAction(deviceId, 'set_rgb_color', { rgb_color: hexToRgb(input.value) });
}

function hexToRgb(color) {
    return [
        parseInt(color.slice(1, 3), 16),
        parseInt(color.slice(3, 5), 16),
        parseInt(color.slice(5, 7), 16),
    ];
}

function rgbToHex(color) {
    if (!Array.isArray(color) || color.length < 3) return '#ff9800';
    return `#${color.slice(0, 3).map(value => Math.max(0, Math.min(255, Number(value) || 0)).toString(16).padStart(2, '0')).join('')}`;
}

function applyTuyaColorTemp(deviceId, inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    executeAction(deviceId, 'set_color_temp', { color_temp: Number(input.value) });
}

function setRandomTuyaColor(deviceId) {
    const rand = () => Math.floor(Math.random() * 256);
    executeAction(deviceId, 'set_rgb_color', { rgb_color: [rand(), rand(), rand()] });
}

function applyTuyaTemperature(deviceId, inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    executeAction(deviceId, 'set_temperature', { temperature: Number(input.value) });
}

function applyTuyaFanMode(deviceId, selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    executeAction(deviceId, 'set_fan_mode', { fan_mode: select.value });
}

function applyTuyaPresetMode(deviceId, selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    executeAction(deviceId, 'set_preset_mode', { preset_mode: select.value });
}

function formatActionLabel(action, params = null) {
    const normalized = (action || '').toLowerCase();
    if (normalized === 'turn_on') return 'Ligou dispositivo';
    if (normalized === 'turn_off') return 'Desligou dispositivo';
    if (normalized === 'restart') return 'Reiniciou dispositivo';
    if (normalized === 'lock') return 'Bloqueou dispositivo';
    if (normalized === 'unlock') return 'Desbloqueou dispositivo';
    if (normalized === 'open_app') return params?.app_name ? `Abriu app ${params.app_name}` : 'Abriu aplicativo';
    if (normalized === 'close_app') return 'Fechou app / voltou para Home';
    if (normalized === 'get_status') return 'Consultou status';
    return action || 'Ação executada';
}

function showDeviceDetails(deviceId) {
    showSystemModal({
        title: 'Detalhes do dispositivo',
        message: `Detalhes do dispositivo ${deviceId} em breve!`,
        confirmText: 'Fechar',
        hideCancel: true,
    });
}

function showSystemModal({ title, message, confirmText = 'OK', cancelText = 'Cancelar', hideCancel = false }) {
    const modalElement = document.getElementById('system-modal');
    const titleElement = document.getElementById('system-modal-title');
    const messageElement = document.getElementById('system-modal-message');
    const confirmButton = document.getElementById('system-modal-confirm');
    const cancelButton = document.getElementById('system-modal-cancel');

    if (!modalElement || !titleElement || !messageElement || !confirmButton || !cancelButton || !window.bootstrap) {
        return Promise.resolve(false);
    }

    titleElement.textContent = title;
    messageElement.textContent = message;
    confirmButton.textContent = confirmText;
    cancelButton.textContent = cancelText;
    cancelButton.style.display = hideCancel ? 'none' : '';

    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);

    return new Promise(resolve => {
        let resolved = false;

        const cleanup = () => {
            confirmButton.removeEventListener('click', onConfirm);
            modalElement.removeEventListener('hidden.bs.modal', onHidden);
        };

        const onConfirm = () => {
            resolved = true;
            cleanup();
            modal.hide();
            resolve(true);
        };

        const onHidden = () => {
            if (!resolved) {
                cleanup();
                resolve(false);
            }
        };

        confirmButton.addEventListener('click', onConfirm, { once: true });
        modalElement.addEventListener('hidden.bs.modal', onHidden, { once: true });
        modal.show();
    });
}
