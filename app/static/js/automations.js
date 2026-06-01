document.addEventListener('DOMContentLoaded', () => {
    const openButton = document.getElementById('btn-add-automation');
    const modalElement = document.getElementById('automation-modal');
    const form = document.getElementById('automation-form');
    const submitButton = document.getElementById('btn-submit-automation');
    const errorElement = document.getElementById('automation-form-error');

    if (!openButton || !modalElement || !form || !submitButton || !errorElement || !window.bootstrap) return;

    const modal = window.bootstrap.Modal.getOrCreateInstance(modalElement);

    openButton.addEventListener('click', () => modal.show());
    modalElement.addEventListener('hidden.bs.modal', () => {
        form.reset();
        document.getElementById('automation-active').checked = true;
        errorElement.classList.add('hidden');
    });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        errorElement.classList.add('hidden');

        try {
            const condition = parseJsonField('automation-condition', {}, 'A condição');
            const actions = parseJsonField('automation-actions', null, 'As ações');
            if (!condition || Array.isArray(condition) || typeof condition !== 'object') {
                throw new Error('A condição deve ser um objeto JSON.');
            }
            if (!Array.isArray(actions) || actions.length === 0) {
                throw new Error('Informe pelo menos uma ação em uma lista JSON.');
            }

            submitButton.disabled = true;
            submitButton.textContent = 'Adicionando...';

            const response = await fetch('/automations', {
                method: 'POST',
                headers: {
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
            const result = await response.json();
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
});

function parseJsonField(id, defaultValue, label) {
    const value = document.getElementById(id).value.trim();
    if (!value) return defaultValue;
    try {
        return JSON.parse(value);
    } catch {
        throw new Error(`${label} deve usar JSON válido.`);
    }
}
