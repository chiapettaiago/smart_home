document.addEventListener('DOMContentLoaded', () => {
    const list = document.getElementById('users-list');
    const count = document.getElementById('users-count');
    const form = document.getElementById('user-form');
    const title = document.getElementById('user-form-title');
    const error = document.getElementById('user-form-error');
    const idInput = document.getElementById('user-id');
    const usernameInput = document.getElementById('user-username');
    const displayNameInput = document.getElementById('user-display-name');
    const phoneMacInput = document.getElementById('user-phone-mac');
    const passwordInput = document.getElementById('user-password');
    const passwordHelp = document.getElementById('user-password-help');
    const adminInput = document.getElementById('user-is-admin');
    const activeInput = document.getElementById('user-is-active');
    const newButton = document.getElementById('btn-new-user');
    const cancelButton = document.getElementById('btn-cancel-user');
    if (!list || !form) return;

    let users = [];

    loadUsers();
    newButton?.addEventListener('click', resetForm);
    cancelButton?.addEventListener('click', resetForm);
    form.addEventListener('submit', saveUser);
    list.addEventListener('click', handleUserAction);

    async function loadUsers() {
        try {
            const response = await fetch('/users', {
                cache: 'no-store',
                headers: { 'Accept': 'application/json' },
            });
            const result = await readJsonResponse(response);
            if (!response.ok) throw new Error(result.detail || 'Não foi possível carregar usuários.');
            users = result.users || [];
            renderUsers();
        } catch (loadError) {
            list.innerHTML = `<div class="empty-state"><div class="empty-state-title">Falha ao carregar usuários</div><div class="empty-state-text">${escapeHtml(loadError.message)}</div></div>`;
        }
    }

    function renderUsers() {
        count.textContent = `${users.length} ${users.length === 1 ? 'usuário' : 'usuários'}`;
        if (!users.length) {
            list.innerHTML = '<div class="empty-state"><div class="empty-state-title">Nenhum usuário cadastrado</div><div class="empty-state-text">Crie o primeiro acesso pelo formulário ao lado.</div></div>';
            return;
        }
        list.innerHTML = users.map(user => `
            <article class="user-list-item">
                <div class="item-info">
                    <div class="item-title">${escapeHtml(user.display_name || user.username)}</div>
                    <div class="item-subtitle">@${escapeHtml(user.username)}${user.phone_mac ? ` · celular ${escapeHtml(user.phone_mac)}` : ' · sem MAC do celular'}${user.last_login_at ? ` · último login ${formatDate(user.last_login_at)}` : ''}</div>
                </div>
                <div class="item-actions">
                    <span class="item-badge ${user.is_active ? 'success' : 'danger'}">${user.is_active ? 'Ativo' : 'Inativo'}</span>
                    ${user.is_admin ? '<span class="item-badge warning">Admin</span>' : '<span class="item-badge">Usuário</span>'}
                    <a class="btn btn-sm btn-soft" href="/profiles/${encodeURIComponent(user.username)}">Perfil</a>
                    <button class="btn btn-sm btn-soft" type="button" data-user-action="edit" data-user-id="${user.id}">Editar</button>
                    <button class="btn btn-sm btn-danger-soft" type="button" data-user-action="delete" data-user-id="${user.id}">Remover</button>
                </div>
            </article>
        `).join('');
    }

    async function saveUser(event) {
        event.preventDefault();
        setFormError('');
        const userId = idInput.value;
        const payload = {
            username: usernameInput.value.trim(),
            display_name: displayNameInput.value.trim(),
            phone_mac: phoneMacInput.value.trim(),
            password: passwordInput.value,
            is_admin: adminInput.checked,
            is_active: activeInput.checked,
        };
        if (userId && !payload.password) delete payload.password;
        try {
            const response = await fetch(userId ? `/users/${userId}` : '/users', {
                method: userId ? 'PUT' : 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || '',
                },
                body: JSON.stringify(payload),
            });
            const result = await readJsonResponse(response);
            if (!response.ok) throw new Error(result.detail || 'Não foi possível salvar usuário.');
            resetForm();
            await loadUsers();
        } catch (saveError) {
            setFormError(saveError.message);
        }
    }

    async function handleUserAction(event) {
        const button = event.target.closest('[data-user-action]');
        if (!button) return;
        const user = users.find(item => String(item.id) === button.dataset.userId);
        if (!user) return;
        if (button.dataset.userAction === 'edit') {
            editUser(user);
            return;
        }
        if (button.dataset.userAction === 'delete') {
            const confirmed = await showSystemModal({
                title: 'Remover usuário',
                message: `Remover o usuário "${user.username}"?`,
                confirmText: 'Remover',
            });
            if (!confirmed) return;
            try {
                const response = await fetch(`/users/${user.id}`, {
                    method: 'DELETE',
                    headers: {
                        'Accept': 'application/json',
                        'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || '',
                    },
                });
                const result = await readJsonResponse(response);
                if (!response.ok) throw new Error(result.detail || 'Não foi possível remover usuário.');
                await loadUsers();
            } catch (deleteError) {
                showSystemModal({ title: 'Erro', message: deleteError.message, confirmText: 'Fechar', hideCancel: true });
            }
        }
    }

    function editUser(user) {
        idInput.value = user.id;
        usernameInput.value = user.username || '';
        displayNameInput.value = user.display_name || '';
        phoneMacInput.value = user.phone_mac || '';
        passwordInput.value = '';
        adminInput.checked = Boolean(user.is_admin);
        activeInput.checked = Boolean(user.is_active);
        title.textContent = 'Editar usuário';
        passwordHelp.textContent = 'Deixe em branco para manter a senha atual.';
        usernameInput.focus();
    }

    function resetForm() {
        form.reset();
        idInput.value = '';
        activeInput.checked = true;
        title.textContent = 'Novo usuário';
        passwordHelp.textContent = 'Obrigatória para novos usuários. Mínimo de 8 caracteres.';
        setFormError('');
    }

    function setFormError(message) {
        error.textContent = message;
        error.classList.toggle('hidden', !message);
    }
});

async function readJsonResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) return response.json();
    throw new Error(`O servidor retornou uma resposta inválida (${response.status}).`);
}

function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    })[char]);
}
