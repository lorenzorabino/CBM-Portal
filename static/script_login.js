// Login form logic wired to backend /api/login
(function(){
    const form = document.getElementById('loginForm');
    if (!form) return;
    const empInput = document.getElementById('employeeNumber');
    const pwdInput = document.getElementById('password');
    const empErr = document.getElementById('employeeNumberError');
    const pwdErr = document.getElementById('passwordError');
    const toggle = document.getElementById('passwordToggle');
    const success = document.getElementById('successMessage');

    // Password toggle
    if (toggle && pwdInput) {
        toggle.addEventListener('click', function(){
            const t = pwdInput.getAttribute('type') === 'password' ? 'text' : 'password';
            pwdInput.setAttribute('type', t);
        });
    }

    function setError(el, msg) {
        if (!el) return;
        el.textContent = msg || '';
        const group = el.closest('.form-group');
        if (msg) {
            el.classList.add('show');
            if (group) group.classList.add('error');
        } else {
            el.classList.remove('show');
            if (group) group.classList.remove('error');
        }
    }

    async function doLogin(emp, pwd) {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ employeeNumber: emp, password: pwd })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.ok) {
            throw new Error(data.message || 'Login failed');
        }
        return data;
    }

    form.addEventListener('submit', async function(e){
        e.preventDefault();
        setError(empErr, ''); setError(pwdErr, '');
        const emp = (empInput && empInput.value || '').trim();
        const pwd = (pwdInput && pwdInput.value || '').trim();
        let bad = false;
        if (!emp) { setError(empErr, 'Employee number is required'); bad = true; }
        if (!pwd) { setError(pwdErr, 'Password is required'); bad = true; }
        if (bad) return;

        const btn = form.querySelector('.login-btn');
        if (btn) btn.classList.add('loading');
        try {
            const data = await doLogin(emp, pwd);
            // Success: hide form, show success message and redirect
            form.style.display = 'none';
            if (success) success.classList.add('show');
            setTimeout(() => { window.location.href = '/'; }, 1000);
        } catch (err) {
            // Prefer password field error, but show at employee number if not present
            const message = err.message || 'Invalid credentials';
            if (pwdErr) setError(pwdErr, message);
            else if (empErr) setError(empErr, message);
        } finally {
            if (btn) btn.classList.remove('loading');
        }
    });
})();