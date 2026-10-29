'use strict';
(() => {
  const $ = id => document.getElementById(id);
  $('loginForm').onsubmit = async event => {
    event.preventDefault(); $('loginButton').disabled = true; $('loginError').textContent = '';
    try {
      const result = await EventAPI.request('/api/admin/login', {method:'POST', body:{username:$('username').value.trim(), password:$('password').value}});
      if (!result.token) throw new Error('The server returned no administrator session.');
      EventAPI.saveAdmin(result.token); location.assign('/admin');
    } catch (error) { $('loginError').textContent = error.message; }
    finally { $('loginButton').disabled = false; }
  };
})();
