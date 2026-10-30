'use strict';
(() => {
  const api = EventAPI;
  const $ = id => document.getElementById(id);
  if (!api.admin()?.token) { location.replace('/admin-login'); return; }
  let teams = [], sessions = [], batches = [];
  let event = {}, registrationEvent = {};
  let selectedBatchId = null;
  let selectionVersion = 0;
  let refreshing = false, changingEvent = false, rosterLoaded = false;
  let reviewId = null, rosterTeam = null, tableSignature = '';
  let reviewVersion = 0, rosterVersion = 0, reviewSaving = false;
  const batchPath = path => `${path}?batch_id=${encodeURIComponent(selectedBatchId || '')}`;
  const checkAuth = error => { if (error.status === 401 || error.status === 403) { api.logout(); location.replace('/admin-login'); } };
  const statistic = (value, label) => { const card = api.node('div', undefined, 'score'); card.append(api.node('strong', String(value)), api.node('span', label)); return card; };
  const batchName = id => batches.find(batch => batch.batch_id === id)?.name || id || 'session';
  const phaseName = phase => ({round1:'Round 1: Part A', round2:'Round 1: Part B', waiting:'Waiting', finished:'Finished'})[phase] || phase || 'Registered';
  function renderTable() {
    const query = $('teamSearch').value.trim().toLowerCase();
    $('teamsTable').replaceChildren();
    for (const team of teams) {
      if (query && ![team.team_name, team.school_name, team.team_id].join(' ').toLowerCase().includes(query)) continue;
      const session = sessions.find(item => item.team_id === team.team_id);
      const row = api.node('tr');
      const title = api.node('td'); title.append(api.node('strong', team.team_name), api.node('br'), api.node('small', team.team_id)); row.append(title);
      const values = [team.school_name, phaseName(session?.phase), session?.round1_score ?? '-', session?.word1_score ?? '-', session?.word2_score ?? '-', session?.quality_score ?? 'Pending', session?.objective_score ?? '-', session?.final_score ?? 'Pending'];
      values.forEach(value => row.append(api.node('td', String(value))));
      const actions = api.node('td');
      const details = api.node('button', 'Details', 'secondary'); details.type = 'button'; details.onclick = () => openRoster(team); actions.append(details);
      if (session) {
        const review = api.node('button', session.quality_status === 'reviewed' ? 'Reviewed' : event.status === 'ended' ? 'Grade' : 'Transcript', 'secondary'); review.type = 'button';
        review.onclick = () => openReview(session.session_id); actions.append(document.createTextNode(' '), review);
      }
      row.append(actions); $('teamsTable').append(row);
    }
    if (!$('teamsTable').children.length) { const row = api.node('tr'); const cell = api.node('td', teams.length ? 'No matching teams.' : 'No teams registered for this session.'); cell.colSpan = 10; row.append(cell); $('teamsTable').append(row); }
  }
  function reviewAccess() {
    const allowed = Boolean(reviewId && event.status === 'ended' && !reviewSaving);
    ['qualityScore', 'qualityReason', 'saveReview'].forEach(id => { $(id).disabled = !allowed; });
  }
  function renderEvent() {
    $('batchSelect').disabled = changingEvent;
    const active = selectedBatchId === registrationEvent.batch_id;
    const waiting = event.status === 'waiting';
    const running = event.status === 'running';
    const ended = event.status === 'ended';
    $('eventState').textContent = `${batchName(selectedBatchId)} / ${waiting ? 'Waiting for teams' : running ? 'In progress' : ended ? 'Ended' : 'Loading'}`;
    $('eventDetail').textContent = ended ? 'Results are saved. Grade prompt quality from the complete transcript or export this session.' : running ? 'Teams share the start time. They continue to Round 1: Part B when the timeline part ends.' : active ? 'Start this session once its teams have registered.' : 'Open registration for this session before teams join.';
    $('activeBatchStatus').textContent = `Registration session: ${registrationEvent.name || 'loading'}`;
    $('activateBatch').hidden = active || ended;
    $('activateBatch').disabled = changingEvent || !waiting || registrationEvent.status === 'running';
    $('newTest').hidden = !ended || !(selectedBatchId === 'test' || selectedBatchId.startsWith('test-'));
    $('newTest').disabled = changingEvent || registrationEvent.status === 'running';
    $('startEvent').hidden = !active || !waiting;
    $('startEvent').disabled = changingEvent || !active || !waiting;
    $('startEvent').textContent = `Start ${batchName(selectedBatchId)} for all teams`;
    $('endEvent').hidden = !active || ended || !event.status;
    $('endEvent').disabled = changingEvent;
    $('endEvent').textContent = `End ${batchName(selectedBatchId)}`;
    $('lateRegistration').hidden = !active || !running;
    $('lateRegistration').disabled = changingEvent;
    $('lateRegistration').textContent = event.registration_open ? 'Extend registration by 2 minutes' : 'Open registration for 2 minutes';
    reviewAccess();
  }
  function renderHealth(health) {
    $('aiBudgetStatus').hidden = true;
    if (!health) { $('aiStatus').textContent = 'AI status unavailable'; return; }
    const ai = health.ai || {};
    const backup = ai.backup || {};
    const backupConfigured = ai.ollama_backup_configured ?? ai.ollama_configured ?? ai.backup_configured ?? backup.configured;
    $('aiStatus').textContent = `API ${ai.configured ? 'configured' : 'not configured'}${ai.live_verified ? ', reply verified on this worker' : ''}. Ollama backup ${backupConfigured ? 'configured' : 'not configured'}${ai.ollama_backup_verified ? ', reply verified on this worker' : ''}.${ai.last_error ? ` Last API error: ${ai.last_error}.` : ''}`;
    const budget = ai.budget;
    if (budget?.limits && budget.remaining) {
      $('aiBudgetStatus').hidden = false;
      $('aiBudgetStatus').textContent = `API budget remaining: ${budget.remaining.rpm}/${budget.limits.rpm} calls per minute, ${budget.remaining.tpm}/${budget.limits.tpm} estimated tokens per minute, ${budget.remaining.rpd} calls today.${budget.cooldown_seconds > 0 ? ` Cooldown: ${Math.ceil(budget.cooldown_seconds)}s.` : ''}`;
    }
  }
  async function refresh() {
    if (refreshing || document.hidden) return;
    refreshing = true;
    const requested = selectedBatchId;
    const version = selectionVersion;
    try {
      const [log, registry, health] = await Promise.all([
        api.request(requested ? batchPath('/api/admin/log') : '/api/admin/log', {admin:true}),
        api.request('/api/event/status'),
        api.request('/api/health', {timeout:5000}).catch(() => null)
      ]);
      if (version !== selectionVersion) return;
      registrationEvent = registry.event || {}; batches = registry.batches || [];
      selectedBatchId ||= log.event?.batch_id || registrationEvent.batch_id;
      const optionSignature = JSON.stringify(batches.map(batch => [batch.batch_id, batch.name]));
      if ($('batchSelect').dataset.options !== optionSignature) {
        $('batchSelect').replaceChildren(...batches.map(batch => { const option = api.node('option', batch.name); option.value = batch.batch_id; return option; }));
        $('batchSelect').dataset.options = optionSignature;
      }
      $('batchSelect').value = selectedBatchId; $('batchSelect').disabled = false;
      if (!rosterLoaded || teams.length !== log.total) {
        const roster = await api.request(batchPath('/api/admin/teams'), {admin:true});
        if (version !== selectionVersion) return;
        teams = roster.teams || []; rosterLoaded = true;
      }
      sessions = log.sessions || []; event = log.event || {};
      renderHealth(health);
      $('adminStats').replaceChildren(statistic(teams.length, 'Registered teams'), statistic(teams.reduce((sum, team) => sum + Number(team.team_size || 0), 0), 'Participants'), statistic(sessions.filter(item => item.phase === 'waiting').length, 'In waiting room'), statistic(sessions.filter(item => item.phase === 'finished').length, 'Finished'));
      renderEvent();
      const signature = JSON.stringify([teams, sessions, event.status]);
      if (signature !== tableSignature) { tableSignature = signature; renderTable(); }
      $('adminError').textContent = ''; $('syncStatus').textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (error) { checkAuth(error); $('adminError').textContent = `${error.message} Retrying automatically.`; $('syncStatus').textContent = 'Connection interrupted'; }
    finally { refreshing = false; if (version !== selectionVersion) refresh(); }
  }
  async function changeEvent(action) {
    if (changingEvent || !selectedBatchId) return;
    changingEvent = true; renderEvent();
    try { await api.request(`/api/admin/event/${action}`, {method:'POST', admin:true, body:{batch_id:selectedBatchId}}); rosterLoaded = false; await refresh(); }
    catch (error) { checkAuth(error); $('adminError').textContent = error.message; }
    finally { changingEvent = false; renderEvent(); }
  }
  const timeValue = entry => { const timestamp = entry.submitted_at ?? entry.timestamp; return typeof timestamp === 'number' ? timestamp * 1000 : Date.parse(timestamp || '') || 0; };
  async function openReview(id) {
    const version = ++reviewVersion;
    const batch = selectedBatchId;
    $('reviewPanel').hidden = false; $('reviewError').textContent = ''; $('reviewTeam').textContent = 'Loading transcript'; $('transcript').replaceChildren(); reviewId = null; reviewAccess();
    try {
      const result = await api.request(`/api/admin/session/${encodeURIComponent(id)}`, {admin:true});
      if (version !== reviewVersion || batch !== selectedBatchId) return;
      const session = result.session || {};
      if (session.event?.batch_id && session.event.batch_id !== selectedBatchId) return;
      reviewId = id; $('reviewTeam').textContent = `${session.team_name || session.team_id} / ${batchName(selectedBatchId)}`;
      const accepted = result.messages || result.prompts || [];
      const failed = (result.failed_requests || []).map(entry => ({...entry, failed:true, ai_mode:'unavailable'}));
      $('reviewMetadata').textContent = `${accepted.length} answered prompts, ${failed.length} failed requests. ${event.status !== 'ended' ? 'Grading opens when this session ends.' : session.quality_status === 'reviewed' ? 'Prompt quality reviewed.' : 'Prompt quality pending.'}`;
      $('qualityScore').value = session.round2?.quality_marks ?? session.quality_score ?? '';
      $('qualityReason').value = session.quality_reason || '';
      const messages = [...accepted, ...failed].sort((a, b) => timeValue(a) - timeValue(b));
      messages.forEach((entry, index) => {
        const item = api.node('article', undefined, 'review-entry');
        item.append(api.node('h3', entry.failed ? `Failed request ${entry.id || index + 1}` : `Turn ${entry.turn || index + 1}`));
        const meta = [entry.timestamp ? new Date(timeValue(entry)).toLocaleString() : '', entry.target ? `Target: ${entry.target}` : '', entry.detected_technique ? `Technique: ${entry.detected_technique}` : ''].filter(Boolean).join(' / ');
        if (meta) item.append(api.node('small', meta));
        item.append(api.node('pre', entry.prompt || entry.user_message || entry.message || ''));
        item.append(api.node('strong', api.aiLabel(entry)), api.node('pre', entry.failed ? entry.error || 'The AI providers could not answer this request.' : entry.response || entry.aria_response || ''));
        if (api.aiNote(entry)) item.append(api.node('p', api.aiNote(entry), 'muted'));
        if (entry.provider_details) { const details = api.node('details'); details.append(api.node('summary', 'Provider details'), api.node('pre', JSON.stringify(entry.provider_details, null, 2))); item.append(details); }
        $('transcript').append(item);
      });
      if (!messages.length) $('transcript').append(api.node('p', 'No prompts recorded.', 'muted'));
      reviewAccess(); $('reviewPanel').scrollIntoView({behavior:'smooth', block:'start'});
    } catch (error) { checkAuth(error); if (version === reviewVersion && batch === selectedBatchId) $('reviewError').textContent = error.message; }
  }
  function openRoster(team) {
    rosterVersion++;
    rosterTeam = team; $('rosterPanel').hidden = false; $('rosterTitle').textContent = `${team.team_name} / ${batchName(team.batch_id || selectedBatchId)}`;
    $('rosterDetails').replaceChildren(api.node('p', `${team.team_id} / ${team.school_name}`));
    const list = api.node('ol'); (team.participants || []).forEach(member => list.append(api.node('li', `${member.name}, grade ${member.grade}`))); $('rosterDetails').append(list);
    $('recoveryArea').hidden = true; $('recoveryCode').value = ''; $('recoveryError').textContent = ''; $('rosterPanel').scrollIntoView({behavior:'smooth', block:'start'});
  }
  $('batchSelect').onchange = () => {
    selectionVersion++;
    reviewVersion++; rosterVersion++;
    selectedBatchId = $('batchSelect').value; teams = []; sessions = []; event = {}; rosterLoaded = false; tableSignature = '';
    reviewId = null; rosterTeam = null; $('reviewPanel').hidden = true; $('rosterPanel').hidden = true; $('recoveryCode').value = '';
    renderEvent(); renderTable(); refresh();
  };
  $('reviewForm').onsubmit = async submit => {
    submit.preventDefault(); if (reviewSaving || !reviewId || event.status !== 'ended') return;
    const id = reviewId, batch = selectedBatchId, version = reviewVersion;
    const body = {score:Number($('qualityScore').value), reason:$('qualityReason').value.trim()};
    reviewSaving = true; reviewAccess(); $('reviewError').textContent = '';
    try {
      await api.request(`/api/admin/session/${encodeURIComponent(id)}/quality`, {method:'PATCH', admin:true, body});
      if (reviewVersion === version && selectedBatchId === batch && reviewId === id) $('reviewMetadata').textContent = 'Reviewed score saved.';
      await refresh();
    }
    catch (error) { checkAuth(error); if (reviewVersion === version && selectedBatchId === batch && reviewId === id) $('reviewError').textContent = error.message; }
    finally { reviewSaving = false; reviewAccess(); }
  };
  async function download(path, extension) {
    if (!selectedBatchId) return;
    const batch = selectedBatchId;
    const token = api.admin().token;
    try {
      const response = await fetch(`${path}?batch_id=${encodeURIComponent(batch)}`, {headers:{'X-Admin-Key':token}, cache:'no-store'});
      if (!response.ok) { const error = new Error('Export failed. Refresh and try again.'); error.status = response.status; throw error; }
      const url = URL.createObjectURL(await response.blob()); const link = api.node('a'); link.href = url; link.download = `aarohan-${batch}-${extension}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { checkAuth(error); $('adminError').textContent = error.message; }
  }
  $('activateBatch').onclick = () => changeEvent('activate');
  $('newTest').onclick = async () => {
    if (!window.confirm('Open a new test session? Previous test records will remain available.')) return;
    $('newTest').disabled = true;
    try {
      const result = await api.request('/api/admin/event/new-test', {method:'POST', admin:true, body:{}});
      selectedBatchId = result.event.batch_id;
      selectionVersion++; rosterLoaded = false; teams = []; sessions = []; event = {}; tableSignature = '';
      reviewVersion++; rosterVersion++; reviewId = null; rosterTeam = null;
      $('reviewPanel').hidden = true; $('rosterPanel').hidden = true;
      await refresh();
    } catch (error) { checkAuth(error); $('adminError').textContent = error.message; $('newTest').disabled = false; }
  };
  $('startEvent').onclick = () => changeEvent('start');
  $('lateRegistration').onclick = () => changeEvent('late-registration');
  $('endEvent').onclick = () => { if (window.confirm(`End the ${batchName(selectedBatchId)} session? Its teams cannot continue, and its results will be available for grading.`)) changeEvent('end'); };
  $('refresh').onclick = refresh; $('teamSearch').oninput = renderTable;
  $('closeReview').onclick = () => { reviewVersion++; $('reviewPanel').hidden = true; reviewId = null; };
  $('closeRoster').onclick = () => { rosterVersion++; $('rosterPanel').hidden = true; rosterTeam = null; $('recoveryCode').value = ''; };
  $('recoverTeam').onclick = async () => {
    if (!rosterTeam || !window.confirm(`Generate a one-time 5-character transfer code for ${rosterTeam.team_name}? It expires after 10 minutes.`)) return;
    const teamId = rosterTeam.team_id, version = rosterVersion;
    $('recoverTeam').disabled = true; $('recoveryError').textContent = '';
    try { const result = await api.request(`/api/admin/teams/${encodeURIComponent(teamId)}/resume-code`, {method:'POST', admin:true, body:{}}); if (version === rosterVersion && rosterTeam?.team_id === teamId) { $('recoveryCode').value = result.resume_code; $('recoveryArea').hidden = false; } }
    catch (error) { checkAuth(error); if (version === rosterVersion && rosterTeam?.team_id === teamId) $('recoveryError').textContent = error.message; }
    finally { $('recoverTeam').disabled = false; }
  };
  $('exportScores').onclick = () => download('/api/admin/export', 'scores.csv');
  $('exportExcel').onclick = () => download('/api/admin/export.xlsx', 'results.xlsx');
  $('exportTeams').onclick = () => download('/api/admin/teams/export', 'registrations.csv');
  $('logout').onclick = async () => { try { await api.request('/api/admin/logout', {method:'POST', admin:true, body:{}}); } finally { api.logout(); location.assign('/admin-login'); } };
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('online', refresh); setInterval(refresh, 3000); refresh();
})();
