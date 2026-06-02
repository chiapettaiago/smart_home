document.addEventListener('DOMContentLoaded', () => {
    const openButton = document.getElementById('btn-add-automation');
    const addActionButton = document.getElementById('btn-add-automation-action');
    const actionsList = document.getElementById('automation-actions-list');
    const conditionFields = document.getElementById('automation-condition-fields');
    const triggerSelect = document.getElementById('automation-trigger');
    const modalElement = document.getElementById('automation-modal');
    const form = document.getElementById('automation-form');
    const submitButton = document.getElementById('btn-submit-automation');
    const errorElement = document.getElementById('automation-form-error');

    if (!openButton || !addActionButton || !actionsList || !conditionFields || !triggerSelect || !modalElement || !form || !submitButton || !errorElement || !window.bootstrap) return;

    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    let actionCatalog = [];
    let conditionCatalog = {};
    let nextActionRowId = 1;

    openButton.addEventListener('click', async () => {
        modal.show();
        if (actionCatalog.length) {
            renderConditionFields();
            if (!actionsList.children.length) addActionRow();
            return;
        }
        actionsList.innerHTML = '<div class="automation-actions-empty">Carregando dispositivos...</div>';
        try {
            const response = await fetch('/automations/action-catalog', {
                cache: 'no-store',
                headers: { 'Accept': 'application/json' },
            });
            const result = await readJsonResponse(response);
            if (!response.ok) throw new Error(result.detail || 'Não foi possível carregar os dispositivos.');
            actionCatalog = result.devices || [];
            conditionCatalog = result.conditions || {};
            actionsList.innerHTML = '';
            renderConditionFields();
            addActionRow();
        } catch (error) {
            actionsList.innerHTML = `<div class="automation-actions-empty text-danger">${escapeAutomationHtml(error.message)}</div>`;
        }
    });

    addActionButton.addEventListener('click', addActionRow);
    triggerSelect.addEventListener('change', renderConditionFields);
    actionsList.addEventListener('click', event => {
        const removeButton = event.target.closest('[data-remove-automation-action]');
        if (!removeButton) return;
        removeButton.closest('[data-automation-action-row]')?.remove();
        if (!actionsList.querySelector('[data-automation-action-row]')) addActionRow();
    });
    actionsList.addEventListener('change', event => {
        const row = event.target.closest('[data-automation-action-row]');
        if (!row) return;
        if (event.target.matches('[data-automation-device]')) renderActionRow(row, Number(event.target.value));
        if (event.target.matches('[data-automation-action]')) renderActionParams(row);
    });

    modalElement.addEventListener('hidden.bs.modal', () => {
        form.reset();
        document.getElementById('automation-active').checked = true;
        errorElement.classList.add('hidden');
        actionsList.innerHTML = '';
        conditionFields.innerHTML = '';
    });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        errorElement.classList.add('hidden');

        try {
            const condition = collectCondition();
            const actions = collectActions();

            submitButton.disabled = true;
            submitButton.textContent = 'Adicionando...';

            const response = await fetch('/automations', {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || '',
                },
                body: JSON.stringify({
                    name: document.getElementById('automation-name').value.trim(),
                    trigger: document.getElementById('automation-trigger').value,
                    condition,
                    actions,
                    active: document.getElementById('automation-active').checked,
                }),
            });
            const result = await readJsonResponse(response);
            if (!response.ok) throw new Error(result.detail || 'Não foi possível adicionar a automação.');

            modal.hide();
            await loadDashboardData();
            showNotification('Automação adicionada com sucesso.', 'success');
        } catch (error) {
            errorElement.textContent = error.message;
            errorElement.classList.remove('hidden');
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = 'Adicionar automação';
        }
    });

    function addActionRow() {
        if (!actionCatalog.length) {
            actionsList.innerHTML = '<div class="automation-actions-empty">Cadastre um dispositivo para adicionar ações.</div>';
            return;
        }
        actionsList.querySelector('.automation-actions-empty')?.remove();
        const row = document.createElement('div');
        row.className = 'automation-action-row';
        row.dataset.automationActionRow = String(nextActionRowId++);
        actionsList.appendChild(row);
        renderActionRow(row, actionCatalog[0].id);
    }

    function renderConditionFields() {
        const trigger = triggerSelect.value;
        if (trigger === 'manual') {
            conditionFields.innerHTML = '<div class="automation-actions-empty">A execução manual não exige condição.</div>';
            return;
        }
        if (trigger === 'time') {
            conditionFields.innerHTML = `
                <label class="form-label small" for="automation-condition-time">Horário</label>
                <input class="form-control" id="automation-condition-time" type="time" required>
            `;
            return;
        }
        if (trigger === 'device_status') {
            conditionFields.innerHTML = `
                <div class="row g-2">
                    <div class="col-md-7">
                        <label class="form-label small" for="automation-condition-device">Dispositivo ou entidade</label>
                        <select class="form-select" id="automation-condition-device" required>${renderDeviceOptions()}</select>
                    </div>
                    <div class="col-md-5">
                        <label class="form-label small" for="automation-condition-state">Estado</label>
                        <select class="form-select" id="automation-condition-state" required>
                            ${(conditionCatalog.device_states || []).map(state => `<option value="${escapeAutomationHtml(state.value)}">${escapeAutomationHtml(state.label)}</option>`).join('')}
                        </select>
                    </div>
                </div>
            `;
            return;
        }
        conditionFields.innerHTML = `
            <div class="row g-2">
                <div class="col-md-7">
                    <label class="form-label small" for="automation-condition-user">Usuário</label>
                    <select class="form-select" id="automation-condition-user" required>
                        ${(conditionCatalog.presence_users || []).map(user => `<option value="${escapeAutomationHtml(user)}">${escapeAutomationHtml(user)}</option>`).join('')}
                    </select>
                </div>
                <div class="col-md-5">
                    <label class="form-label small" for="automation-condition-presence">Presença</label>
                    <select class="form-select" id="automation-condition-presence" required>
                        <option value="home">Em casa</option>
                        <option value="away">Fora de casa</option>
                    </select>
                </div>
            </div>
        `;
    }

    function collectCondition() {
        const trigger = triggerSelect.value;
        if (trigger === 'manual') return {};
        if (trigger === 'time') {
            return { time: requireFieldValue('automation-condition-time', 'Informe o horário da condição.') };
        }
        if (trigger === 'device_status') {
            return {
                device_id: Number(requireFieldValue('automation-condition-device', 'Escolha o dispositivo da condição.')),
                state: requireFieldValue('automation-condition-state', 'Escolha o estado da condição.'),
            };
        }
        return {
            user: requireFieldValue('automation-condition-user', 'Cadastre um usuário para usar a condição de presença.'),
            is_home: requireFieldValue('automation-condition-presence', 'Escolha o estado de presença.') === 'home',
        };
    }

    function requireFieldValue(id, message) {
        const value = document.getElementById(id)?.value;
        if (!value) throw new Error(message);
        return value;
    }

    function renderDeviceOptions(selectedDeviceId = null) {
        return actionCatalog.map(item => `
            <option value="${item.id}" ${item.id === selectedDeviceId ? 'selected' : ''}>
                ${escapeAutomationHtml(item.name)}${item.entity_id ? ` (${escapeAutomationHtml(item.entity_id)})` : ''}
            </option>
        `).join('');
    }

    function renderActionRow(row, selectedDeviceId) {
        const device = getDevice(selectedDeviceId) || actionCatalog[0];
        const deviceOptions = renderDeviceOptions(device.id);
        const actionOptions = device.actions.map(action => `
            <option value="${escapeAutomationHtml(action.name)}">${escapeAutomationHtml(action.label)}</option>
        `).join('');

        row.innerHTML = `
            <div class="automation-action-head">
                <strong>Ação</strong>
                <button class="btn btn-sm btn-danger-soft" data-remove-automation-action type="button">Remover</button>
            </div>
            <div class="row g-2">
                <div class="col-md-7">
                    <label class="form-label small" for="automation-device-${row.dataset.automationActionRow}">Dispositivo ou entidade</label>
                    <select class="form-select form-select-sm" id="automation-device-${row.dataset.automationActionRow}" data-automation-device>${deviceOptions}</select>
                </div>
                <div class="col-md-5">
                    <label class="form-label small" for="automation-action-${row.dataset.automationActionRow}">Comando</label>
                    <select class="form-select form-select-sm" id="automation-action-${row.dataset.automationActionRow}" data-automation-action>${actionOptions}</select>
                </div>
            </div>
            <div class="row g-2 mt-1" data-automation-params></div>
        `;
        renderActionParams(row);
    }

    function renderActionParams(row) {
        const device = getDevice(Number(row.querySelector('[data-automation-device]').value));
        const actionName = row.querySelector('[data-automation-action]').value;
        const action = device.actions.find(item => item.name === actionName);
        const paramsContainer = row.querySelector('[data-automation-params]');
        paramsContainer.innerHTML = (action.params || []).map(param => `
            <div class="col-md-6">
                <label class="form-label small" for="automation-param-${row.dataset.automationActionRow}-${escapeAutomationHtml(param.name)}">${escapeAutomationHtml(param.label)}</label>
                ${renderParamInput(row, param)}
            </div>
        `).join('');
    }

    function renderParamInput(row, param) {
        const id = `automation-param-${row.dataset.automationActionRow}-${escapeAutomationHtml(param.name)}`;
        if (param.type === 'select') {
            return `<select class="form-select form-select-sm" id="${id}" data-automation-param="${escapeAutomationHtml(param.name)}" data-param-type="select">
                ${(param.options || []).map(option => `<option value="${escapeAutomationHtml(option)}">${escapeAutomationHtml(option)}</option>`).join('')}
            </select>`;
        }
        return `<input class="form-control form-control-sm" id="${id}" data-automation-param="${escapeAutomationHtml(param.name)}" data-param-type="${escapeAutomationHtml(param.type)}" type="${escapeAutomationHtml(param.type)}" value="${escapeAutomationHtml(param.value ?? '')}" ${param.min !== undefined ? `min="${param.min}"` : ''} ${param.max !== undefined ? `max="${param.max}"` : ''} ${param.step !== undefined ? `step="${param.step}"` : ''} required>`;
    }

    function collectActions() {
        const rows = [...actionsList.querySelectorAll('[data-automation-action-row]')];
        if (!rows.length) throw new Error('Adicione pelo menos uma ação.');
        return rows.map(row => {
            const params = {};
            row.querySelectorAll('[data-automation-param]').forEach(input => {
                params[input.dataset.automationParam] = coerceParamValue(input.value, input.dataset.paramType);
            });
            const result = {
                device_id: Number(row.querySelector('[data-automation-device]').value),
                action: row.querySelector('[data-automation-action]').value,
            };
            if (Object.keys(params).length) result.params = params;
            return result;
        });
    }

    function getDevice(deviceId) {
        return actionCatalog.find(device => device.id === deviceId);
    }
});

function coerceParamValue(value, type) {
    if (type === 'number') return Number(value);
    if (type === 'color') {
        const hex = value.replace('#', '');
        return [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16));
    }
    return value;
}

async function readJsonResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) return response.json();

    const body = await response.text();
    if (response.status === 401 || response.redirected) {
        throw new Error('Sua sessão expirou. Atualize a página e entre novamente.');
    }
    if (response.status >= 500) {
        throw new Error('O servidor não conseguiu salvar a automação. Tente novamente ou consulte os logs do servidor.');
    }
    if (body.toLowerCase().includes('<!doctype html')) {
        throw new Error('O servidor retornou uma página inesperada. Atualize a página e tente novamente.');
    }
    throw new Error(`O servidor retornou uma resposta inválida (${response.status}).`);
}

function escapeAutomationHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    })[char]);
}
