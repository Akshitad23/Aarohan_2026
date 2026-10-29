// Run with node tests/frontend_smoke.cjs. Exercises page controllers without network calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this._text = ''; this.value = ''; this.dataset = {}; this.className = ''; this.hidden = false; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
  append(...items) { this.children.push(...items.map(item => typeof item === 'string' ? Object.assign(new Element('#text'), {textContent:item}) : item)); }
  replaceChildren(...items) { this._text = ''; this.children = []; this.append(...items); }
  querySelectorAll(selector) {
    const matches = node => selector.split(',').some(part => part.startsWith('.') ? node.className.split(' ').includes(part.slice(1)) : node.tagName === part);
    return this.children.flatMap(child => [...(matches(child) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  setAttribute(name, value) { this[name] = value; }
  focus() {} scrollIntoView() {} select() {} click() { this.clicked = true; }
}

function page(script, access = {}) {
  const elements = new Map(), listeners = {}, timers = [], redirects = [], downloads = [];
  const document = {hidden:false, createElement:tag => new Element(tag), createTextNode:text => Object.assign(new Element('#text'), {textContent:text}), getElementById:id => {
    if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id);
  }, addEventListener:(name, fn) => { listeners[name] = fn; }};
  const location = {assign:url => redirects.push(url), replace:url => redirects.push(url)};
  const window = {addEventListener() {}, confirm:() => true, location};
  const context = vm.createContext({window, document, location, performance, Date, console, AbortController, setTimeout:() => 0, clearTimeout() {}, setInterval:(fn, ms) => timers.push({fn, ms}), localStorage:{getItem:() => null, setItem() {}, removeItem() {}}, navigator:{}, URL:{createObjectURL:() => 'blob:test', revokeObjectURL() {}}, fetch:async url => { downloads.push(url); return {ok:true, blob:async () => ({})}; }});
  const source = name => fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', name), 'utf8');
  vm.runInContext(source('api.js'), context);
  context.EventAPI = window.EventAPI;
  context.EventAPI.team = () => access.team;
  context.EventAPI.admin = () => access.admin;
  return {get:id => document.getElementById(id), api:context.EventAPI, window, listeners, timers, redirects, downloads, run:() => vm.runInContext(source(script), context)};
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const event = (batch_id, status) => ({batch_id, name:batch_id === 'morning' ? 'Morning' : 'Afternoon', status});
const state = (phase = 'round2', reviewed = false) => ({phase, event:event('morning','running'), team_id:'T1', team_name:'Test team', objective_score:4, quality_status:reviewed ? 'reviewed' : 'pending', final_score:reviewed ? 7 : null, total_score:reviewed ? 7 : 4, round1:{score:2}, round2:{remaining_seconds:600, prompt_count:0, quality_marks:reviewed ? 3 : null, words:[{index:1,ciphertext:'TEST',solved:true,score:2},{index:2,ciphertext:'OTHER',solved:false,score:0}]}, prompt_history:[]});

async function gameChecks() {
  const test = page('timeglitch.js', {team:{token:'private-test-token', team:{team_id:'T1', team_name:'Test team'}}});
  let latest = state(), rejectPrompt = true;
  test.api.request = async route => {
    if (route.endsWith('/prompt') && rejectPrompt) { const error = new Error('Both AI providers are unavailable.'); error.state = latest; error.details = {retryable:true, ai_retry_after_seconds:5}; throw error; }
    return route.endsWith('/prompt') ? {state:latest} : latest;
  };
  test.run(); await settle();
  assert.match(test.get('liveScores').textContent, /4 \/ 6/);
  assert.match(test.get('qualitySummary').textContent, /pending/i);
  assert.equal(test.get('liveScores').children.at(-1).children[0].textContent, 'Pending');
  test.get('promptInput').value = 'Keep this prompt when both AI providers fail.';
  await test.get('promptForm').onsubmit({preventDefault() {}});
  assert.equal(test.get('promptInput').value, 'Keep this prompt when both AI providers fail.');
  assert.match(test.get('gameError').textContent, /Retry in 5 seconds/);
  rejectPrompt = false;
  latest = {...state(), prompt_history:[{turn:1,prompt:'Explain this protocol.',response:'An actual provider response.',ai_mode:'live',ai_provider:'ollama_backup',ai_primary_failure_reason:'budget_rpm'}]};
  await test.get('promptForm').onsubmit({preventDefault() {}});
  assert.equal(test.get('promptInput').value, '');
  assert.match(test.get('chatHistory').textContent, /Ollama backup/);
  latest = state('finished', true); latest.prompt_history = [];
  test.listeners.visibilitychange(); await settle();
  assert.match(test.get('finalScores').textContent, /7 \/ 10/);
  console.log('Game: pending marks, failed-provider draft retention, backup identity, and reviewed final score pass.');
}

async function registrationChecks() {
  const test = page('registration.js', {team:{token:'old-morning-code', team:{team_id:'M1', team_name:'Morning team', batch_id:'morning'}}});
  test.get('teamSize').value = '2';
  let registrationBody;
  test.api.saveTeam = (team, token) => { assert.equal(team.batch_id, 'afternoon'); assert.equal(token, 'new-afternoon-code'); };
  test.api.request = async (route, options) => {
    if (route === '/api/event/status') return {event:event('afternoon','waiting')};
    if (route.startsWith('/api/tg/session/status')) return {phase:'finished', event:event('morning','ended')};
    registrationBody = options.body; return {team:{team_id:'A1',batch_id:'afternoon'}, team_token:'new-afternoon-code'};
  };
  test.run(); await settle();
  assert.match(test.get('registrationBatch').textContent, /Afternoon/);
  assert.match(test.get('savedTeamStatus').textContent, /Morning/);
  test.get('teamName').value = 'Afternoon team'; test.get('schoolName').value = 'Test school';
  test.get('participantsContainer').querySelectorAll('input').forEach(input => { input.value = 'Participant'; });
  test.get('participantsContainer').querySelectorAll('select').forEach(select => { select.value = '10'; });
  await test.get('registrationForm').onsubmit({preventDefault() {}});
  assert.equal(registrationBody.batch_id, 'afternoon');
  assert.equal(test.redirects.at(-1), '/game');
  console.log('Registration: Morning access remains identified and new registration binds explicitly to Afternoon.');
}

async function adminChecks() {
  const test = page('admin.js', {admin:{token:'admin-test-token'}});
  const batchList = [event('morning','ended'),event('afternoon','waiting')];
  const morningSession = {...state('finished'), event:event('morning','ended')};
  test.api.request = async route => {
    if (route === '/api/event/status') return {event:batchList[1], batches:batchList};
    if (route === '/api/health') return {ai:{configured:true,ollama_backup_configured:true}};
    if (route.startsWith('/api/admin/log')) { const morning = route.includes('morning'); return {event:batchList[morning ? 0 : 1], total:morning ? 1 : 0, sessions:morning ? [{session_id:'S1',team_id:'T1',phase:'finished',objective_score:4,quality_score:null,final_score:null,quality_status:'pending'}] : []}; }
    if (route.startsWith('/api/admin/teams')) return {teams:route.includes('morning') ? [{team_id:'T1',team_name:'Test team',school_name:'School',team_size:2,batch_id:'morning'}] : []};
    if (route.includes('/api/admin/session/')) return {session:morningSession, messages:[{turn:1,timestamp:'2026-10-29T10:00:00',prompt:'A successful prompt',response:'A provider response',ai_provider:'groq'}], failed_requests:[{id:1,timestamp:1793268001,prompt:'A failed prompt',error:'Both providers failed',provider_details:{reason:'provider_timeout'}}]};
    throw new Error(`Unexpected route: ${route}`);
  };
  test.run(); await settle();
  assert.match(test.get('eventState').textContent, /Afternoon/);
  test.get('batchSelect').value = 'morning'; test.get('batchSelect').onchange(); await settle();
  assert.equal(test.get('startEvent').hidden, true);
  assert.match(test.get('teamsTable').textContent, /Pending/);
  await test.get('teamsTable').children[0].children.at(-1).children.at(-1).onclick();
  assert.match(test.get('transcript').textContent, /A successful prompt/);
  assert.match(test.get('transcript').textContent, /A failed prompt/);
  assert.match(test.get('transcript').textContent, /Provider details/);
  assert.equal(test.get('qualityScore').value, '');
  assert.equal(test.get('saveReview').disabled, false);
  await test.get('exportExcel').onclick();
  assert.equal(test.downloads.at(-1), '/api/admin/export.xlsx?batch_id=morning');
  console.log('Admin: batch filtering, historical controls, all requests, pending grading, and selected-session Excel export pass.');
}

(async () => { await gameChecks(); await registrationChecks(); await adminChecks(); })().catch(error => { console.error(error); process.exitCode = 1; });
