'use strict';

window.EventAPI = (() => {
  const TEAM_KEY = 'aarohan_team_access';
  const ADMIN_KEY = 'aarohan_admin_access';
  const read = key => { try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch { return null; } };
  async function request(path, {method = 'GET', body, admin = false, token, timeout = 40000} = {}) {
    const access = admin ? read(ADMIN_KEY) : read(TEAM_KEY);
    const headers = {'Content-Type': 'application/json'};
    if (token || access?.token) headers[admin ? 'X-Admin-Key' : 'X-Team-Token'] = token || access.token;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, {method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, cache: 'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const error = new Error(data.error || `Request failed (${response.status}).`);
        error.status = response.status;
        error.state = data.state;
        error.details = data;
        throw error;
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The server took too long to respond. Check your connection, then retry.');
      if (error instanceof TypeError) throw new Error('Cannot reach the server. Your saved progress remains on the server. Reconnect and retry.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function saveTeam(team, token) { localStorage.setItem(TEAM_KEY, JSON.stringify({team, token})); }
  function saveAdmin(token) { localStorage.setItem(ADMIN_KEY, JSON.stringify({token})); }
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function aiLabel(entry) {
    if (entry.ai_provider === 'groq') return 'CHRONOS (API)';
    if (entry.ai_provider === 'ollama_backup') return 'CHRONOS (Ollama backup)';
    if (entry.ai_mode === 'unavailable') return 'CHRONOS (unavailable)';
    const mode = entry.ai_mode || (entry.chronos_api_fallback === true ? 'fallback' : entry.chronos_api_fallback === false ? 'live' : null);
    return mode === 'live' || mode === 'fallback' ? `CHRONOS (${mode})` : 'CHRONOS';
  }
  function aiNote(entry) {
    const reasons = {
      not_configured: 'The live provider is not configured.',
      budget_rpm: 'The event minute request budget was reached.',
      budget_tpm: 'The event estimated minute token budget was reached.',
      budget_rpd: 'The event daily request budget was reached.',
      budget_tpd: 'The event estimated daily token budget was reached.',
      team_pacing: 'Your team is waiting for its next live request slot.',
      fair_turn: 'Another waiting team has the next live request slot.',
      org_cooldown: 'The live provider is cooling down.',
      concurrency: 'All live request slots are busy.',
      provider_429: 'The provider rate limit was reached.',
      provider_timeout: 'The live provider timed out.',
      provider_error: 'The live provider request failed.',
      rejected_output: 'The live reply did not meet the game rules.',
      invalid_response: 'The live provider returned an unusable reply.',
      budget_unavailable: 'The live request budget is temporarily unavailable.'
    };
    if (entry.ai_provider === 'ollama_backup') return `${reasons[entry.ai_primary_failure_reason] || 'The primary API was unavailable.'} Ollama answered this prompt.`;
    const reason = reasons[entry.ai_fallback_reason] || (entry.ai_mode === 'unavailable' ? 'No AI provider could answer this request.' : '');
    if (!reason) return '';
    const delay = Math.ceil(Number(entry.ai_retry_after_seconds) || 0);
    return reason + (delay > 0 ? ` Retry delay at the time of this reply: ${delay}s.` : '');
  }
  function mergeHistory(previous, incoming, complete = true) {
    if (complete) return [...incoming];
    const turns = new Map(previous.map(entry => [entry.turn, entry]));
    incoming.forEach(entry => turns.set(entry.turn, entry));
    return [...turns.values()].sort((a, b) => a.turn - b.turn);
  }
  return {request, saveTeam, saveAdmin, team: () => read(TEAM_KEY), admin: () => read(ADMIN_KEY), logout: () => localStorage.removeItem(ADMIN_KEY), node, aiLabel, aiNote, mergeHistory};
})();
