(() => {
    const storageKey = 'smart-home-theme';
    const themeColor = () => document.querySelector('meta[name="theme-color"]');

    function preferredTheme() {
        const savedTheme = localStorage.getItem(storageKey);
        if (savedTheme === 'dark' || savedTheme === 'light') return savedTheme;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function applyTheme(theme, persist = false) {
        const normalizedTheme = theme === 'dark' ? 'dark' : 'light';
        document.documentElement.dataset.theme = normalizedTheme;
        if (persist) localStorage.setItem(storageKey, normalizedTheme);
        const color = themeColor();
        if (color) color.content = normalizedTheme === 'dark' ? '#101815' : '#f5f3ec';

        const button = document.getElementById('theme-toggle');
        if (!button) return;
        const isDark = normalizedTheme === 'dark';
        const icon = button.querySelector('.theme-toggle-icon');
        if (icon) icon.textContent = isDark ? '☀' : '☾';
        button.setAttribute('aria-label', isDark ? 'Ativar modo claro' : 'Ativar modo escuro');
        button.setAttribute('aria-pressed', String(isDark));
    }

    applyTheme(preferredTheme());

    document.addEventListener('DOMContentLoaded', () => {
        applyTheme(document.documentElement.dataset.theme);
        document.getElementById('theme-toggle')?.addEventListener('click', () => {
            applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true);
        });
    });
})();
