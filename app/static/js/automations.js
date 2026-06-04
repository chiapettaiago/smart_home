document.addEventListener('DOMContentLoaded', () => {
    const openButton = document.getElementById('btn-add-automation');
    const addActionButton = document.getElementById('btn-add-automation-action');
    const addConditionButton = document.getElementById('btn-add-automation-condition');
    const actionsList = document.getElementById('automation-actions-list');
    const conditionsList = document.getElementById('automation-conditions-list');
    const conditionFields = document.getElementById('automation-condition-fields');
    const triggerSelect = document.getElementById('automation-trigger');
    const modalElement = document.getElementById('automation-modal');
    const form = document.getElementById('automation-form');
    const submitButton = document.getElementById('btn-submit-automation');
    const errorElement = document.getElementById('automation-form-error');

    if (!openButton || !addActionButton || !addConditionButton || !actionsList || !conditionsList || !conditionFields || !triggerSelect || !modalElement || !form || !submitButton || !errorElement || !window.bootstrap) return;

    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);
    let actionCatalog = [];
    let conditionCatalog = {};
    let nextActionRowId = 1;
    let nextConditionRowId = 1;

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
    addConditionButton.addEventListener('click', addConditionRow);
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
    conditionsList.addEventListener('click', event => {
        const removeButton = event.target.closest('[data-remove-automation-condition]');
        if (!removeButton) return;
        removeButton.closest('[data-automation-condition-row]')?.remove();
    });
    conditionsList.addEventListener('change', event => {
        const row = event.target.closest('[data-automation-condition-row]');
        if (!row) return;
        if (event.target.matches('[data-automation-condition-type]')) renderAdditionalConditionRow(row);
        if (event.target.matches('[data-additional-calendar-mode]')) renderAdditionalCalendarFields(row);
        if (event.target.matches('[data-additional-weather-field]')) renderAdditionalWeatherFields(row);
    });

    modalElement.addEventListener('hidden.bs.modal', () => {
        form.reset();
        document.getElementById('automation-active').checked = true;
        errorElement.classList.add('hidden');
        actionsList.innerHTML = '';
        conditionsList.innerHTML = '';
        conditionFields.innerHTML = '';
    });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        errorElement.classList.add('hidden');

        try {
            const condition = collectCondition();
            const conditions = collectAdditionalConditions();
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
                    conditions,
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

    function addConditionRow() {
        const row = document.createElement('div');
        row.className = 'automation-action-row';
        row.dataset.automationConditionRow = String(nextConditionRowId++);
        conditionsList.appendChild(row);
        renderAdditionalConditionRow(row);
    }

    function renderAdditionalConditionRow(row) {
        const rowId = row.dataset.automationConditionRow;
        const selectedType = row.querySelector('[data-automation-condition-type]')?.value || 'time';
        row.innerHTML = `
            <div class="automation-action-head">
                <strong>Condição</strong>
                <button class="btn btn-sm btn-danger-soft" data-remove-automation-condition type="button">Remover</button>
            </div>
            <div class="row g-2">
                <div class="col-md-4">
                    <label class="form-label small" for="automation-extra-condition-type-${rowId}">Tipo</label>
                    <select class="form-select form-select-sm" id="automation-extra-condition-type-${rowId}" data-automation-condition-type>
                        <option value="time" ${selectedType === 'time' ? 'selected' : ''}>Horário</option>
                        <option value="device_status" ${selectedType === 'device_status' ? 'selected' : ''}>Estado de dispositivo</option>
                        <option value="presence" ${selectedType === 'presence' ? 'selected' : ''}>Presença</option>
                        <option value="sun" ${selectedType === 'sun' ? 'selected' : ''}>Nascer/pôr do sol</option>
                        <option value="weather" ${selectedType === 'weather' ? 'selected' : ''}>Clima</option>
                        <option value="calendar" ${selectedType === 'calendar' ? 'selected' : ''}>Data e calendário</option>
                    </select>
                </div>
                <div class="col-md-8" data-additional-condition-fields></div>
            </div>
        `;
        renderAdditionalConditionFields(row, selectedType);
    }

    function renderAdditionalConditionFields(row, type) {
        const rowId = row.dataset.automationConditionRow;
        const container = row.querySelector('[data-additional-condition-fields]');
        if (!container) return;
        if (type === 'time') {
            container.innerHTML = `
                <label class="form-label small" for="automation-extra-time-${rowId}">Horário</label>
                <input class="form-control form-control-sm" id="automation-extra-time-${rowId}" data-additional-time type="time" required>
            `;
            return;
        }
        if (type === 'device_status') {
            container.innerHTML = `
                <div class="row g-2">
                    <div class="col-md-7">
                        <label class="form-label small" for="automation-extra-device-${rowId}">Dispositivo</label>
                        <select class="form-select form-select-sm" id="automation-extra-device-${rowId}" data-additional-device required>${renderDeviceOptions()}</select>
                    </div>
                    <div class="col-md-5">
                        <label class="form-label small" for="automation-extra-state-${rowId}">Estado</label>
                        <select class="form-select form-select-sm" id="automation-extra-state-${rowId}" data-additional-state required>
                            ${(conditionCatalog.device_states || []).map(state => `<option value="${escapeAutomationHtml(state.value)}">${escapeAutomationHtml(state.label)}</option>`).join('')}
                        </select>
                    </div>
                </div>
            `;
            return;
        }
        if (type === 'presence') {
            container.innerHTML = `
                <div class="row g-2">
                    <div class="col-md-7">
                        <label class="form-label small" for="automation-extra-user-${rowId}">Usuário</label>
                        <select class="form-select form-select-sm" id="automation-extra-user-${rowId}" data-additional-user required>
                            ${(conditionCatalog.presence_users || []).map(user => `<option value="${escapeAutomationHtml(user)}">${escapeAutomationHtml(user)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="col-md-5">
                        <label class="form-label small" for="automation-extra-presence-${rowId}">Presença</label>
                        <select class="form-select form-select-sm" id="automation-extra-presence-${rowId}" data-additional-presence required>
                            <option value="home">Em casa</option>
                            <option value="away">Fora de casa</option>
                        </select>
                    </div>
                </div>
            `;
            return;
        }
        if (type === 'sun') {
            container.innerHTML = `
                <div class="row g-2">
                    <div class="col-md-6">
                        <label class="form-label small" for="automation-extra-sun-event-${rowId}">Evento</label>
                        <select class="form-select form-select-sm" id="automation-extra-sun-event-${rowId}" data-additional-sun-event required>
                            <option value="sunset">Pôr do sol</option>
                            <option value="sunrise">Nascer do sol</option>
                        </select>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label small" for="automation-extra-sun-offset-${rowId}">Minutos</label>
                        <input class="form-control form-control-sm" id="automation-extra-sun-offset-${rowId}" data-additional-sun-offset type="number" min="-240" max="240" value="0" required>
                    </div>
                </div>
            `;
            return;
        }
        if (type === 'weather') {
            container.innerHTML = `
                <div class="row g-2">
                    <div class="col-md-5">
                        <label class="form-label small" for="automation-extra-weather-field-${rowId}">Medição</label>
                        <select class="form-select form-select-sm" id="automation-extra-weather-field-${rowId}" data-additional-weather-field required>
                            ${(conditionCatalog.weather_fields || []).map(field => `<option value="${escapeAutomationHtml(field.value)}">${escapeAutomationHtml(field.label)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label small" for="automation-extra-weather-operator-${rowId}">Comparação</label>
                        <select class="form-select form-select-sm" id="automation-extra-weather-operator-${rowId}" data-additional-weather-operator required>
                            ${(conditionCatalog.weather_operators || []).map(operator => `<option value="${escapeAutomationHtml(operator.value)}">${escapeAutomationHtml(operator.label)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label class="form-label small" for="automation-extra-weather-value-${rowId}">Valor</label>
                        <input class="form-control form-control-sm" id="automation-extra-weather-value-${rowId}" data-additional-weather-value type="number" step="0.1" value="25" required>
                    </div>
                </div>
            `;
            renderAdditionalWeatherFields(row);
            return;
        }
        container.innerHTML = `
            <div class="row g-2">
                <div class="col-md-5">
                    <label class="form-label small" for="automation-extra-calendar-mode-${rowId}">Tipo</label>
                    <select class="form-select form-select-sm" id="automation-extra-calendar-mode-${rowId}" data-additional-calendar-mode required>
                        <option value="day_type">Dia útil/fim de semana</option>
                        <option value="weekday">Dia da semana</option>
                        <option value="date">Data específica</option>
                        <option value="month_day">Dia do mês</option>
                    </select>
                </div>
                <div class="col-md-7" data-additional-calendar-fields></div>
            </div>
        `;
        renderAdditionalCalendarFields(row);
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
        if (trigger === 'presence') {
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
            renderWeatherModeFields();
            return;
        }
        if (trigger === 'sun') {
            const environment = conditionCatalog.environment || {};
            const sun = environment.sun || {};
            conditionFields.innerHTML = `
                <div class="row g-2">
                    <div class="col-md-5">
                        <label class="form-label small" for="automation-condition-sun-event">Evento</label>
                        <select class="form-select" id="automation-condition-sun-event" required>
                            <option value="sunset">Pôr do sol${sun.sunset_time ? ` (${escapeAutomationHtml(sun.sunset_time)})` : ''}</option>
                            <option value="sunrise">Nascer do sol${sun.sunrise_time ? ` (${escapeAutomationHtml(sun.sunrise_time)})` : ''}</option>
                        </select>
                    </div>
                    <div class="col-md-7">
                        <label class="form-label small" for="automation-condition-sun-offset">Minutos antes/depois</label>
                        <input class="form-control" id="automation-condition-sun-offset" type="number" min="-240" max="240" value="0" required>
                    </div>
                </div>
            `;
            return;
        }
        if (trigger === 'weather') {
            conditionFields.innerHTML = `
                <div class="row g-2">
                    <div class="col-md-5">
                        <label class="form-label small" for="automation-condition-weather-field">Medição</label>
                        <select class="form-select" id="automation-condition-weather-field" required>
                            ${(conditionCatalog.weather_fields || []).map(field => `<option value="${escapeAutomationHtml(field.value)}">${escapeAutomationHtml(field.label)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label small" for="automation-condition-weather-operator">Comparação</label>
                        <select class="form-select" id="automation-condition-weather-operator" required>
                            ${(conditionCatalog.weather_operators || []).map(operator => `<option value="${escapeAutomationHtml(operator.value)}">${escapeAutomationHtml(operator.label)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label class="form-label small" for="automation-condition-weather-value">Valor</label>
                        <input class="form-control" id="automation-condition-weather-value" type="number" step="0.1" value="25" required>
                    </div>
                </div>
            `;
            return;
        }
        conditionFields.innerHTML = `
            <div class="row g-2">
                <div class="col-md-4">
                    <label class="form-label small" for="automation-condition-calendar-mode">Tipo</label>
                    <select class="form-select" id="automation-condition-calendar-mode" required>
                        <option value="day_type">Dia útil/fim de semana</option>
                        <option value="weekday">Dia da semana</option>
                        <option value="date">Data específica</option>
                        <option value="month_day">Dia do mês</option>
                    </select>
                </div>
                <div class="col-md-8" id="automation-calendar-mode-fields"></div>
            </div>
        `;
        renderCalendarModeFields();
    }

    conditionFields.addEventListener('change', event => {
        if (event.target.matches('#automation-condition-calendar-mode')) renderCalendarModeFields();
        if (event.target.matches('#automation-condition-weather-field')) renderWeatherModeFields();
    });

    function renderWeatherModeFields() {
        const field = document.getElementById('automation-condition-weather-field')?.value;
        const operator = document.getElementById('automation-condition-weather-operator');
        const value = document.getElementById('automation-condition-weather-value');
        if (!operator || !value) return;
        const isRaining = field === 'is_raining';
        operator.disabled = isRaining;
        value.type = isRaining ? 'checkbox' : 'number';
        value.checked = true;
        value.value = isRaining ? 'true' : value.value || '25';
    }

    function renderCalendarModeFields() {
        const container = document.getElementById('automation-calendar-mode-fields');
        const mode = document.getElementById('automation-condition-calendar-mode')?.value;
        if (!container) return;
        if (mode === 'day_type') {
            container.innerHTML = `
                <label class="form-label small" for="automation-condition-day-type">Dia</label>
                <select class="form-select" id="automation-condition-day-type" required>
                    <option value="weekday">Dia útil</option>
                    <option value="weekend">Fim de semana</option>
                </select>
            `;
            return;
        }
        if (mode === 'weekday') {
            container.innerHTML = `
                <label class="form-label small" for="automation-condition-weekday">Dia da semana</label>
                <select class="form-select" id="automation-condition-weekday" required>
                    ${(conditionCatalog.weekdays || []).map(day => `<option value="${day.value}">${escapeAutomationHtml(day.label)}</option>`).join('')}
                </select>
            `;
            return;
        }
        if (mode === 'date') {
            container.innerHTML = `
                <label class="form-label small" for="automation-condition-date">Data</label>
                <input class="form-control" id="automation-condition-date" type="date" required>
            `;
            return;
        }
        container.innerHTML = `
            <div class="row g-2">
                <div class="col-6">
                    <label class="form-label small" for="automation-condition-month">Mês</label>
                    <input class="form-control" id="automation-condition-month" type="number" min="1" max="12" value="1" required>
                </div>
                <div class="col-6">
                    <label class="form-label small" for="automation-condition-day">Dia</label>
                    <input class="form-control" id="automation-condition-day" type="number" min="1" max="31" value="1" required>
                </div>
            </div>
        `;
    }

    function renderAdditionalWeatherFields(row) {
        const field = row.querySelector('[data-additional-weather-field]')?.value;
        const operator = row.querySelector('[data-additional-weather-operator]');
        const value = row.querySelector('[data-additional-weather-value]');
        if (!operator || !value) return;
        const isRaining = field === 'is_raining';
        operator.disabled = isRaining;
        value.type = isRaining ? 'checkbox' : 'number';
        value.checked = true;
        value.value = isRaining ? 'true' : value.value || '25';
    }

    function renderAdditionalCalendarFields(row) {
        const container = row.querySelector('[data-additional-calendar-fields]');
        const mode = row.querySelector('[data-additional-calendar-mode]')?.value;
        if (!container) return;
        if (mode === 'day_type') {
            container.innerHTML = `
                <label class="form-label small">Dia</label>
                <select class="form-select form-select-sm" data-additional-day-type required>
                    <option value="weekday">Dia útil</option>
                    <option value="weekend">Fim de semana</option>
                </select>
            `;
            return;
        }
        if (mode === 'weekday') {
            container.innerHTML = `
                <label class="form-label small">Dia da semana</label>
                <select class="form-select form-select-sm" data-additional-weekday required>
                    ${(conditionCatalog.weekdays || []).map(day => `<option value="${day.value}">${escapeAutomationHtml(day.label)}</option>`).join('')}
                </select>
            `;
            return;
        }
        if (mode === 'date') {
            container.innerHTML = `
                <label class="form-label small">Data</label>
                <input class="form-control form-control-sm" data-additional-date type="date" required>
            `;
            return;
        }
        container.innerHTML = `
            <div class="row g-2">
                <div class="col-6">
                    <label class="form-label small">Mês</label>
                    <input class="form-control form-control-sm" data-additional-month type="number" min="1" max="12" value="1" required>
                </div>
                <div class="col-6">
                    <label class="form-label small">Dia</label>
                    <input class="form-control form-control-sm" data-additional-day type="number" min="1" max="31" value="1" required>
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
        if (trigger === 'presence') {
            return {
                user: requireFieldValue('automation-condition-user', 'Cadastre um usuário para usar a condição de presença.'),
                is_home: requireFieldValue('automation-condition-presence', 'Escolha o estado de presença.') === 'home',
            };
        }
        if (trigger === 'sun') {
            return {
                event: requireFieldValue('automation-condition-sun-event', 'Escolha o evento solar.'),
                offset_minutes: Number(requireFieldValue('automation-condition-sun-offset', 'Informe o deslocamento solar.')),
            };
        }
        if (trigger === 'weather') {
            const field = requireFieldValue('automation-condition-weather-field', 'Escolha a medição de clima.');
            if (field === 'is_raining') {
                return {
                    field,
                    is_raining: document.getElementById('automation-condition-weather-value')?.checked !== false,
                };
            }
            return {
                field,
                operator: requireFieldValue('automation-condition-weather-operator', 'Escolha a comparação.'),
                value: Number(requireFieldValue('automation-condition-weather-value', 'Informe o valor de clima.')),
            };
        }
        const mode = requireFieldValue('automation-condition-calendar-mode', 'Escolha o tipo de calendário.');
        if (mode === 'day_type') return { mode, day_type: requireFieldValue('automation-condition-day-type', 'Escolha o tipo de dia.') };
        if (mode === 'weekday') return { mode, weekday: Number(requireFieldValue('automation-condition-weekday', 'Escolha o dia da semana.')) };
        if (mode === 'date') return { mode, date: requireFieldValue('automation-condition-date', 'Escolha a data.') };
        return {
            mode,
            month: Number(requireFieldValue('automation-condition-month', 'Informe o mês.')),
            day: Number(requireFieldValue('automation-condition-day', 'Informe o dia.')),
        };
    }

    function collectAdditionalConditions() {
        const rows = [...conditionsList.querySelectorAll('[data-automation-condition-row]')];
        return {
            mode: document.getElementById('automation-conditions-mode')?.value || 'all',
            items: rows.map(row => {
                const type = row.querySelector('[data-automation-condition-type]').value;
                return { type, condition: collectAdditionalCondition(row, type) };
            }),
        };
    }

    function collectAdditionalCondition(row, type) {
        if (type === 'time') return { time: requireRowValue(row, '[data-additional-time]', 'Informe o horário da condição adicional.') };
        if (type === 'device_status') {
            return {
                device_id: Number(requireRowValue(row, '[data-additional-device]', 'Escolha o dispositivo da condição adicional.')),
                state: requireRowValue(row, '[data-additional-state]', 'Escolha o estado da condição adicional.'),
            };
        }
        if (type === 'presence') {
            return {
                user: requireRowValue(row, '[data-additional-user]', 'Escolha o usuário da condição adicional.'),
                is_home: requireRowValue(row, '[data-additional-presence]', 'Escolha a presença da condição adicional.') === 'home',
            };
        }
        if (type === 'sun') {
            return {
                event: requireRowValue(row, '[data-additional-sun-event]', 'Escolha o evento solar da condição adicional.'),
                offset_minutes: Number(requireRowValue(row, '[data-additional-sun-offset]', 'Informe os minutos da condição adicional.')),
            };
        }
        if (type === 'weather') {
            const field = requireRowValue(row, '[data-additional-weather-field]', 'Escolha a medição de clima da condição adicional.');
            if (field === 'is_raining') {
                return { field, is_raining: row.querySelector('[data-additional-weather-value]')?.checked !== false };
            }
            return {
                field,
                operator: requireRowValue(row, '[data-additional-weather-operator]', 'Escolha a comparação de clima da condição adicional.'),
                value: Number(requireRowValue(row, '[data-additional-weather-value]', 'Informe o valor de clima da condição adicional.')),
            };
        }
        const mode = requireRowValue(row, '[data-additional-calendar-mode]', 'Escolha o tipo de calendário da condição adicional.');
        if (mode === 'day_type') return { mode, day_type: requireRowValue(row, '[data-additional-day-type]', 'Escolha o tipo de dia da condição adicional.') };
        if (mode === 'weekday') return { mode, weekday: Number(requireRowValue(row, '[data-additional-weekday]', 'Escolha o dia da semana da condição adicional.')) };
        if (mode === 'date') return { mode, date: requireRowValue(row, '[data-additional-date]', 'Escolha a data da condição adicional.') };
        return {
            mode,
            month: Number(requireRowValue(row, '[data-additional-month]', 'Informe o mês da condição adicional.')),
            day: Number(requireRowValue(row, '[data-additional-day]', 'Informe o dia da condição adicional.')),
        };
    }

    function requireRowValue(row, selector, message) {
        const value = row.querySelector(selector)?.value;
        if (!value) throw new Error(message);
        return value;
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
