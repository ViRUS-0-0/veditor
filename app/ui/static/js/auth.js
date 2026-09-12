// ── Client-side Authentication Form Validation ──────────────────

function validateSignup(form) {
  const errorEl = document.getElementById('client-error');
  const password = form.password ? form.password.value : '';
  const passwordConfirm = form.password_confirm ? form.password_confirm.value : '';

  if (password.length < 8) {
    if (errorEl) {
      errorEl.textContent = 'Password must be at least 8 characters long.';
      errorEl.classList.remove('auth-error-hidden');
    }
    if (form.password) form.password.focus();
    return false;
  }

  if (password.length > 256) {
    if (errorEl) {
      errorEl.textContent = 'Password must not exceed 256 characters.';
      errorEl.classList.remove('auth-error-hidden');
    }
    if (form.password) form.password.focus();
    return false;
  }

  if (password !== passwordConfirm) {
    if (errorEl) {
      errorEl.textContent = 'Passwords do not match.';
      errorEl.classList.remove('auth-error-hidden');
    }
    if (form.password_confirm) form.password_confirm.focus();
    return false;
  }

  if (errorEl) {
    errorEl.classList.add('auth-error-hidden');
  }
  return true;
}

window.validateSignup = validateSignup;

document.addEventListener('DOMContentLoaded', () => {
  const signupForm = document.querySelector('form.auth-form[action="/signup"]');
  if (signupForm) {
    signupForm.addEventListener('submit', (e) => {
      if (!validateSignup(signupForm)) {
        e.preventDefault();
      }
    });
  }
});
