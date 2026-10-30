'use strict';
(() => {
  const api = EventAPI;
  const $ = id => document.getElementById(id);
  const access = api.team();
  let current = null;
  let busy = false;
  let polling = false;
  let mutationVersion = 0;
  let renderVersion = 0;
  let accessChanged = false;
  let nextPollAt = 0;
  let remainingAt = 0;
  let receivedAt = performance.now();
  let draft = [];
  let cards = [];
  let historySignature = '';
  let wordsSignature = '';
  const draftKey = `aarohan_timeline_draft_${access?.team?.team_id || 'team'}`;
  const cooldownKey = `aarohan_prompt_cooldown_${access?.team?.team_id || 'team'}`;
  let promptReadyAt = Number(localStorage.getItem(cooldownKey)) || 0;
  function setPromptReadyAt(timestamp) {
    promptReadyAt = timestamp;
    localStorage.setItem(cooldownKey, String(timestamp));
  }
  const format = seconds => `${Math.floor(Math.max(0, seconds) / 60).toString().padStart(2, '0')}:${Math.ceil(Math.max(0, seconds) % 60).toString().padStart(2, '0')}`;
  const unwrap = result => result.state || result;
  if (!access?.token) { location.replace('/'); return; }
  const teamToken = access.token;
  $('teamName').textContent = access.team?.team_name || 'Your team';

  function renderTimeline() {
    $('timeline').replaceChildren();
    draft.forEach((id, index) => {
      const card = cards.find(item => item.id === id);
      if (!card) return;
      const row = api.node('li'); const copy = api.node('div', undefined, 'card-copy');
      copy.append(api.node('strong', card.title));
      if (card.description) copy.append(api.node('p', card.description));
      const controls = api.node('div', undefined, 'move');
      for (const [offset, label] of [[-1, 'Up'], [1, 'Down']]) {
        const button = api.node('button', label, 'secondary'); button.type = 'button';
        button.setAttribute('aria-label', `Move ${card.title} ${label.toLowerCase()}`);
        button.disabled = busy || index + offset < 0 || index + offset >= draft.length;
        button.onclick = () => {
          [draft[index], draft[index + offset]] = [draft[index + offset], draft[index]];
          localStorage.setItem(draftKey, JSON.stringify(draft)); renderTimeline();
          $('timeline').children[index + offset]?.querySelector(`button[aria-label$="${label.toLowerCase()}"]`)?.focus();
        };
        controls.append(button);
      }
      row.append(copy, controls); $('timeline').append(row);
    });
  }
  function transcript(target, history) {
    target.replaceChildren();
    for (const entry of history) {
      for (const [label, content, className] of [['Your team', entry.prompt || entry.user_message, 'user'], ['CHRONOS', entry.response || entry.aria_response, '']]) {
        if (!content) continue;
        const message = api.node('div', undefined, `chat-message ${className}`);
        message.append(api.node('strong', label), document.createTextNode(content));
        target.append(message);
      }
    }
    target.scrollTop = target.scrollHeight;
  }
  function renderWords(words) {
    const answers = Object.fromEntries(Array.from($('words').querySelectorAll('input')).map(input => [input.id, input.value]));
    $('words').replaceChildren();
    words.forEach((word, offset) => {
      const index = word.index || offset + 1;
      const card = api.node('section', undefined, 'word-card');
      card.append(api.node('h3', `Word ${index} ${word.solved ? '(decoded)' : ''}`), api.node('div', word.ciphertext || '', 'ciphertext'));
      if (word.hint) card.append(api.node('p', typeof word.hint === 'string' ? word.hint : [word.hint.name, word.hint.instructions, word.hint.example].filter(Boolean).join('\n'), 'message'));
      if (word.solved) card.append(api.node('p', 'Correctly decoded', 'success'));
      else {
        const form = api.node('form'); const label = api.node('label', `Decoded word ${index}`); label.htmlFor = `answer${index}`;
        const input = api.node('input'); input.id = label.htmlFor; input.required = true; input.maxLength = 80; input.autocomplete = 'off'; input.spellcheck = false; input.value = answers[input.id] || '';
        const action = api.node('div', undefined, 'actions'); const button = api.node('button', `Submit word ${index}`); button.type = 'submit'; action.append(button);
        form.append(label, input, action); form.onsubmit = async event => { event.preventDefault(); await mutate('/api/tg/round2/answer', {word_index:index, answer:input.value.trim()}, result => {
          const updated = unwrap(result).round2?.words?.find(item => item.index === index);
          $('answerFeedback').textContent = result.message || (updated?.solved || result.correct ? `Word ${index} is correct.` : `Word ${index} is not correct yet. Try again.`);
        }); };
        card.append(form);
      }
      $('words').append(card);
    });
  }
  function updateControls() {
    const expired = current && current.phase !== 'waiting' && current.phase !== 'finished' && remainingAt - (performance.now() - receivedAt) / 1000 <= 0;
    $('submitTimeline').disabled = busy || expired || !cards.length;
    const wait = Math.max(0, Math.ceil((promptReadyAt - Date.now()) / 1000));
    $('sendPrompt').disabled = busy || expired || wait > 0 || accessChanged;
    $('sendPrompt').textContent = wait > 0 ? `Send in ${wait}s` : 'Send prompt';
    $('promptInterval').textContent = wait > 0 ? `Next prompt available in ${wait} seconds.` : 'You can send one prompt every 60 seconds.';
    $('finishGame').disabled = busy;
    $('words').querySelectorAll('button,input').forEach(element => { element.disabled = busy || expired; });
    $('promptInput').disabled = busy || expired;
    $('timeline').querySelectorAll('button').forEach(button => { if (busy || expired) button.disabled = true; });
  }
  function render(state) {
    if (accessChanged) return;
    if (!state?.phase) throw new Error('The server returned an invalid game state. Contact the organiser.');
    renderVersion++;
    state.prompt_history = api.mergeHistory(current?.prompt_history || [], state.prompt_history || state.round2?.prompt_history || [], state.prompt_history_complete !== false);
    const oldPhase = current?.phase; current = state;
    if (state.phase === 'finished') {
      api.clearTeam(teamToken);
      localStorage.removeItem(draftKey);
      localStorage.removeItem(cooldownKey);
      $('teamName').textContent = '';
      $('chatHistory').replaceChildren();
      $('words').replaceChildren();
      $('promptInput').value = '';
      state.prompt_history = [];
      if (state.round2) state.round2.prompt_history = [];
      accessChanged = true;
    }
    receivedAt = performance.now(); remainingAt = Number((state.phase === 'round1' ? state.round1 : state.round2)?.remaining_seconds || 0);
    for (const phase of ['waiting', 'round1', 'round2', 'finished']) $(phase).hidden = state.phase !== phase;
    if (state.phase !== 'finished' && (state.team?.team_name || state.team_name)) $('teamName').textContent = [state.team?.team_name || state.team_name, state.event?.name].filter(Boolean).join(' / ');
    const r1 = state.round1 || {}; const r2 = state.round2 || {};
    if (state.phase === 'round1') {
      cards = r1.milestones || [];
      if (!draft.length) {
        try { draft = JSON.parse(localStorage.getItem(draftKey) || '[]'); } catch { draft = []; }
        if (!draft.length && r1.placed_ids?.every(id => id)) draft = [...r1.placed_ids];
        if (draft.length !== cards.length || new Set(draft).size !== cards.length || draft.some(id => !cards.some(card => card.id === id))) draft = cards.map(card => card.id);
        renderTimeline();
      }
      $('attempts').textContent = `${r1.attempts_left ?? 3 - (r1.attempts || 0)} attempts left`;
    }
    if (state.phase === 'round2') {
      const nextWords = JSON.stringify(r2.words || []);
      if (nextWords !== wordsSignature || oldPhase !== 'round2') { wordsSignature = nextWords; renderWords(r2.words || []); }
    }
    const history = state.prompt_history || r2.prompt_history || [];
    const signature = JSON.stringify(history);
    if (signature !== historySignature || oldPhase !== state.phase) { historySignature = signature; transcript($('chatHistory'), history); }
    updateControls(); tick();
    if (oldPhase !== state.phase) $(`${state.phase}Heading`).focus();
  }
  async function refresh(force = false) {
    if (accessChanged || polling || busy || document.hidden || !force && Date.now() < nextPollAt) return;
    polling = true;
    nextPollAt = Date.now() + (current?.phase === 'finished' ? 15000 : 2500);
    const version = mutationVersion;
    const lastTurn = Math.max(0, ...(current?.prompt_history || []).map(entry => Number(entry.turn) || 0));
    try { const result = await api.request(`/api/tg/session/status?history_after=${lastTurn}`, {token:teamToken}); if (!accessChanged && version === mutationVersion) { render(unwrap(result)); $('connection').textContent = ''; } }
    catch (error) { $('connection').textContent = error.status === 401 ? 'This team access code is no longer valid. Return to Team details to resume with the correct code.' : `${error.message} Reconnecting automatically.`; }
    finally { polling = false; }
  }
  async function mutate(path, body = {}, onSuccess) {
    if (accessChanged || busy) return;
    busy = true; mutationVersion++; $('gameError').textContent = ''; updateControls();
    try {
      const result = await api.request(path, {method:'POST', body, token:teamToken});
      if (accessChanged) return false;
      if (result.ai_available === false) {
        const error = new Error(result.error || 'Neither AI provider could answer. Your prompt is saved in the input. Retry shortly.');
        error.state = result.state; error.details = result; throw error;
      }
      render(unwrap(result)); if (onSuccess) onSuccess(result); $('connection').textContent = ''; return true;
    } catch (error) {
      if (error.state) render(error.state);
      const delay = Number(error.details?.ai_retry_after_seconds) || 0;
      const reason = error.details?.ai_primary_failure_reason || error.details?.ai_fallback_reason;
      const explanation = {
        team_pacing: 'Please wait before sending your next prompt.',
        fair_turn: 'Another team has the next turn. Please retry shortly.',
        concurrency: 'CHRONOS is answering other teams. Please retry shortly.',
        budget_rpm: 'Chat capacity is busy. Please retry shortly.',
        budget_tpm: 'Chat capacity is busy. Please retry shortly.',
        provider_429: 'CHRONOS is temporarily busy. Please retry shortly.',
        rejected_output: 'CHRONOS could not return a valid reply. Please retry your prompt.'
      }[reason] || error.message;
      const feedback = explanation + (error.details?.retryable && delay > 0 ? ` Retry in ${Math.ceil(delay)} seconds.` : '');
      if (path.endsWith('/prompt')) {
        if (error.details?.retryable && delay > 0) setPromptReadyAt(Date.now() + delay * 1000);
        $('promptStatus').textContent = feedback;
        $('promptStatus').className = 'error';
      } else {
        $('gameError').textContent = feedback;
      }
      return false;
    } finally { busy = false; updateControls(); if (current?.phase === 'round1') renderTimeline(); }
  }
  function tick() {
    if (!current || !['round1','round2'].includes(current.phase)) return;
    updateControls();
    const remaining = Math.max(0, remainingAt - (performance.now() - receivedAt) / 1000);
    $(`${current.phase}Timer`).textContent = format(Math.ceil(remaining));
    if (!remaining) { updateControls(); refresh(); }
  }
  $('submitTimeline').onclick = () => mutate('/api/tg/round1/submit', {placed_ids:draft}, result => {
    $('timelineFeedback').textContent = result.message || (current.phase === 'round1' ? 'The order is not correct. Rearrange the events and try again.' : 'Round 1: Part A complete.');
  });
  $('promptForm').onsubmit = async event => {
    event.preventDefault(); const message = $('promptInput').value.trim(); if (!message) return;
    if (busy || accessChanged || Date.now() < promptReadyAt) { updateControls(); return; }
    const sentAt = Date.now();
    $('promptStatus').className = 'muted';
    $('promptStatus').textContent = 'CHRONOS is responding...';
    const ok = await mutate('/api/tg/round2/prompt', {message});
    if (ok) { setPromptReadyAt(sentAt + 60000); $('promptInput').value = ''; $('promptStatus').textContent = ''; }
    updateControls();
    if (current?.phase === 'round2' && !accessChanged) $('promptInput').focus();
  };
  $('finishGame').onclick = () => {
    if (window.confirm('Finish Round 1: Part B now? Your responses will be saved and you cannot send more prompts or word answers.')) mutate('/api/tg/round2/finish');
  };
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(true); });
  window.addEventListener('pageshow', event => {
    if (event.persisted && api.team()?.token !== teamToken) location.replace('/');
  });
  window.addEventListener('online', () => refresh(true));
  window.addEventListener('storage', event => {
    if ((event.key === 'aarohan_team_access' || event.key === null) && api.team()?.token !== teamToken) {
      accessChanged = true; mutationVersion++;
      location.reload();
    }
  });
  setInterval(refresh, 2500); setInterval(tick, 250);
  (async () => {
    const version = renderVersion;
    const mutation = mutationVersion;
    try {
      const result = await api.request('/api/tg/session/start', {method:'POST', body:{team_id:access.team?.team_id}, token:teamToken});
      if (!accessChanged && renderVersion === version && mutationVersion === mutation) render(unwrap(result));
    }
    catch (error) { if (!accessChanged && renderVersion === version) $('connection').textContent = `${error.message} Retrying automatically.`; }
  })();
})();
