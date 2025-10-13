(function() {
    const loginForm = document.getElementById('loginForm');
    const tokenInput = document.getElementById('tokenInput');
    const errorMessage = document.getElementById('errorMessage');

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const token = tokenInput.value.trim();
        if (!token) {
            errorMessage.textContent = '请输入密钥。';
            return;
        }

        errorMessage.textContent = ''; // 清除旧错误

        try {
            const response = await fetch('/api/health', {
                headers: { 'X-Auth-Token': token }
            });

            if (response.ok) {
                // 验证成功
                localStorage.setItem('tg-button-auth-token', token);
                // 重定向到主页
                window.location.href = '/';
            } else {
                // 验证失败
                errorMessage.textContent = '密钥错误或无效。';
            }
        } catch (error) {
            console.error('Login request failed:', error);
            errorMessage.textContent = '无法连接到服务器。';
        }
    });
})();
