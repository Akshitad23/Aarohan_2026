'use strict';
(() => {
  const api = EventAPI;
  const $ = id => document.getElementById(id);
  const saved = api.team();
  let registrationEvent = null;
  let submitting = false;
  let savedBatchName = saved?.team?.batch_name || saved?.team?.batch_id || '';
  function showRegistration(event) {
    registrationEvent = event;
    const name = event.name || event.batch_id;
    $('registrationBatch').textContent = event.status === 'waiting' ? `Registering for the ${name} session` : `${name} registration is closed.`;
    $('submitButton').disabled = submitting || event.status !== 'waiting';
  }
  async function refreshRegistration() {
    if (submitting || document.hidden) return;
    try { showRegistration((await api.request('/api/event/status')).event); }
    catch (error) { $('registrationBatch').textContent = error.message; $('submitButton').disabled = true; }
  }
  if (saved?.token) {
    $('savedTeam').hidden = false;
    $('savedTeamName').textContent = saved.team?.team_name || 'Your registered team';
    $('resumeCode').value = saved.token;
    api.request('/api/tg/session/status?history_after=1000000', {token:saved.token}).then(state => {
      savedBatchName = state.event?.name || state.event?.batch_id || savedBatchName;
      $('savedTeamStatus').textContent = `This private code belongs to the ${savedBatchName} session. Another session requires a new registration.`;
      $('continueTeam').textContent = state.phase === 'finished' ? `View ${savedBatchName} results` : `Continue ${savedBatchName}`;
    }).catch(() => { $('savedTeamStatus').textContent = 'Resume with this private code or ask the organiser to recover access.'; });
  }
  $('copyCode').onclick = async () => {
    try { await navigator.clipboard.writeText($('resumeCode').value); $('copyCode').textContent = 'Copied'; }
    catch { $('resumeCode').select(); $('copyCode').textContent = 'Select and copy the code above'; }
  };
  function participants() {
    const old = Array.from($('participantsContainer').querySelectorAll('.participant')).map(card => ({name:card.querySelector('input').value, grade:card.querySelector('select').value}));
    $('participantsContainer').replaceChildren();
    for (let i = 0; i < Number($('teamSize').value); i++) {
      const card = api.node('div', undefined, 'participant');
      card.append(api.node('h3', `Participant ${i + 1}`));
      const grid = api.node('div', undefined, 'grid');
      const nameWrap = api.node('div'); const gradeWrap = api.node('div');
      const nameLabel = api.node('label', 'Full name'); nameLabel.htmlFor = `memberName${i}`;
      const name = api.node('input'); name.id = nameLabel.htmlFor; name.required = true; name.maxLength = 100; name.value = old[i]?.name || '';
      const gradeLabel = api.node('label', 'Grade'); gradeLabel.htmlFor = `memberGrade${i}`;
      const grade = api.node('select'); grade.id = gradeLabel.htmlFor; grade.required = true;
      const empty = api.node('option', 'Select grade'); empty.value = ''; grade.append(empty);
      for (let n = 1; n <= 12; n++) { const option = api.node('option', `Grade ${n}`); option.value = String(n); grade.append(option); }
      const other = api.node('option', 'Other'); other.value = 'Other'; grade.append(other); grade.value = old[i]?.grade || '';
      nameWrap.append(nameLabel, name); gradeWrap.append(gradeLabel, grade); grid.append(nameWrap, gradeWrap); card.append(grid); $('participantsContainer').append(card);
    }
  }
  $('teamSize').onchange = participants; participants();
  $('registrationForm').onsubmit = async event => {
    event.preventDefault(); $('formMessage').textContent = ''; submitting = true; $('submitButton').disabled = true;
    try {
      if (!registrationEvent || registrationEvent.status !== 'waiting') throw new Error('Registration is not open.');
      const selectedBatch = registrationEvent.batch_id;
      const latest = (await api.request('/api/event/status')).event;
      if (latest.batch_id !== selectedBatch || latest.status !== 'waiting') {
        showRegistration(latest);
        throw new Error('The registration session changed. Check the session shown above before submitting again.');
      }
      if (saved?.token && !window.confirm(`This laptop has a saved ${savedBatchName || 'previous'} team. Registering for ${registrationEvent.name} will replace its saved access. Keep its resume code if you need the results later. Continue?`)) return;
      const roster = Array.from($('participantsContainer').querySelectorAll('.participant')).map(card => ({name:card.querySelector('input').value.trim(), grade:card.querySelector('select').value}));
      const result = await api.request('/api/teams/register', {method:'POST', body:{teamName:$('teamName').value.trim(), schoolName:$('schoolName').value.trim(), teamSize:roster.length, participants:roster, batch_id:selectedBatch}});
      if (!result.team_token) throw new Error('Registration returned no team access code. Contact the organiser before registering again.');
      api.saveTeam(result.team, result.team_token); location.assign('/game');
    } catch (error) { $('formMessage').textContent = error.message; }
    finally { submitting = false; $('submitButton').disabled = registrationEvent?.status !== 'waiting'; }
  };
  $('resumeForm').onsubmit = async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true; $('resumeError').textContent = '';
    try {
      const token = $('privateCode').value.trim();
      const state = await api.request('/api/tg/session/start', {method:'POST', token, body:{}});
      api.saveTeam(state.team || state.state?.team || {team_id:state.team_id, team_name:state.team_name, batch_id:state.event?.batch_id, batch_name:state.event?.name}, token); location.assign('/game');
    } catch (error) { $('resumeError').textContent = error.message; }
    finally { button.disabled = false; }
  };
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshRegistration(); });
  setInterval(refreshRegistration, 10000); refreshRegistration();
})();
