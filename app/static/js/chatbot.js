document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('chatbot-form');
    const input = document.getElementById('chatbot-input');
    const messages = document.getElementById('chatbot-messages');
    const sendButton = document.getElementById('chatbot-send');
    const status = document.getElementById('chatbot-status');
    if (!form || !input || !messages || !sendButton || !status) return;

    const history = [];
    loadStatus();

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const message = input.value.trim();
        if (!message) return;

        appendMessage('user', message);
        history.push({ role: 'user', text: message });
        input.value = '';
        setLoading(true);

        try {
            const response = await fetch('/chatbot/message', {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.content || '',
                },
                body: JSON.stringify({ message, history: history.slice(-6, -1) }),
            });
            const result = await readJsonResponse(response);
            if (!response.ok) throw new Error(result.detail || 'Não foi possível consultar o assistente.');
            appendMessage('assistant', result.reply || 'Pedido processado.');
            history.push({ role: 'model', text: result.reply || 'Pedido processado.' });
            if (result.commands?.length) setTimeout(loadDashboardData, 700);
        } catch (error) {
            appendMessage('assistant', error.message, true);
        } finally {
            setLoading(false);
            input.focus();
        }
    });

    input.addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    async function loadStatus() {
        try {
            const response = await fetch('/chatbot/status', {
                cache: 'no-store',
                headers: { 'Accept': 'application/json' },
            });
            const result = await readJsonResponse(response);
            status.classList.toggle('ready', result.configured);
            status.innerHTML = `<span></span>${result.configured ? `Gemini ativo · ${escapeChatHtml(result.model)}` : 'Configure GEMINI_API_KEY'}`;
        } catch {
            status.innerHTML = '<span></span>Status indisponível';
        }
    }

    function appendMessage(role, text, isError = false) {
        const article = document.createElement('article');
        article.className = `chat-message ${role}${isError ? ' error' : ''}`;
        article.innerHTML = `
            <div class="chat-avatar">${role === 'assistant' ? '✦' : 'EU'}</div>
            <div class="chat-bubble">
                <strong>${role === 'assistant' ? 'Assistente da casa' : 'Você'}</strong>
                <p>${escapeChatHtml(text).replace(/\n/g, '<br>')}</p>
            </div>
        `;
        messages.appendChild(article);
        messages.scrollTop = messages.scrollHeight;
    }

    function setLoading(isLoading) {
        sendButton.disabled = isLoading;
        input.disabled = isLoading;
        sendButton.textContent = isLoading ? 'Pensando...' : 'Enviar';
    }
});

async function readJsonResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) return response.json();
    if (response.status === 401 || response.redirected) {
        throw new Error('Sua sessão expirou. Atualize a página e entre novamente.');
    }
    throw new Error(`O servidor retornou uma resposta inválida (${response.status}).`);
}

function escapeChatHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
    })[char]);
}
