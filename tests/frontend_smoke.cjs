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
  focus() { this.focusCount = (this.focusCount || 0) + 1; } scrollIntoView() {} select() {} click() { this.clicked = true; }
}

function page(script, access = {}) {
  const elements = new Map(), listeners = {}, windowListeners = {}, timers = [], redirects = [], downloads = [], created = [];
  const document = {hidden:false, createElement:tag => { const element = new Element(tag); created.push(element); return element; }, createTextNode:text => Object.assign(new Element('#text'), {textContent:text}), getElementById:id => {
    if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id);
  }, addEventListener:(name, fn) => { listeners[name] = fn; }};
  const location = {assign:url => redirects.push(url), replace:url => redirects.push(url), reload:() => redirects.push('reload')};
  const window = {addEventListener:(name, fn) => { windowListeners[name] = fn; }, confirm:() => true, location};
  const context = vm.createContext({window, document, location, performance, Date, console, AbortController, setTimeout:() => 0, clearTimeout() {}, setInterval:(fn, ms) => timers.push({fn, ms}), localStorage:{getItem:() => null, setItem() {}, removeItem() {}}, navigator:{}, URL:{createObjectURL:() => 'blob:test', revokeObjectURL() {}}, fetch:async url => { downloads.push(url); return {ok:true, blob:async () => ({})}; }});
  const source = name => fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', name), 'utf8');
  vm.runInContext(source('api.js'), context);
  context.EventAPI = window.EventAPI;
  context.EventAPI.team = () => access.team;
  context.EventAPI.admin = () => access.admin;
  return {get:id => document.getElementById(id), api:context.EventAPI, context, window, listeners, windowListeners, timers, redirects, downloads, created, run:() => vm.runInContext(source(script), context)};
}
const settle = () => new Promise(resolve => setImmediate(resolve));

function copyChecks() {
  const frontend = path.join(__dirname, '..', 'frontend');
  for (const name of ['index.html', 'admin-login.html', 'admin.html', 'game.html']) {
    const html = fs.readFileSync(path.join(frontend, name), 'utf8');
    assert.match(html, /AI: Think\. Hack\. Create\./, `${name} must use the event name.`);
    assert.doesNotMatch(html, /Round 2|ROUND 2/, `${name} must use the updated part label.`);
  }
  const game = fs.readFileSync(path.join(frontend, 'game.html'), 'utf8');
  assert.match(game, /Round 1: Part A/);
  assert.match(game, /Round 1: Part B/);
  const admin = fs.readFileSync(path.join(frontend, 'js', 'admin.js'), 'utf8');
  assert.match(admin, /round1:'Round 1: Part A'/);
  assert.match(admin, /round2:'Round 1: Part B'/);
  console.log('UI copy: event name and Round 1 part labels are present on all pages.');
}
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return {promise, resolve}; };
const event = (batch_id, status) => ({batch_id, name:({test:'Test',morning:'Morning',afternoon:'Afternoon'})[batch_id] || batch_id, status});
const state = (phase = 'round2', reviewed = false) => ({phase, event:event('morning','running'), team_id:'T1', team_name:'Test team', objective_score:4, quality_status:reviewed ? 'reviewed' : 'pending', final_score:reviewed ? 7 : null, total_score:reviewed ? 7 : 4, round1:{score:2,remaining_seconds:300}, round2:{remaining_seconds:900, prompt_count:0, quality_marks:reviewed ? 3 : null, words:[{index:1,ciphertext:'TEST',solved:true,score:2},{index:2,ciphertext:'OTHER',solved:false,score:0}]}, prompt_history:[]});

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
  assert.equal(test.get('round2Timer').textContent, '15:00');
  assert.equal(test.get('round2Heading').focusCount, 1);
  test.listeners.visibilitychange(); await settle();
  assert.equal(test.get('round2Heading').focusCount, 1, 'A same-phase status poll must not steal focus.');
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
  assert.equal(test.get('finishedHeading').focusCount, 1, 'A new phase should focus its heading once.');
  console.log('Game: pending marks, failed-provider draft retention, backup identity, and reviewed final score pass.');
}

async function timelineChecks() {
  const test = page('timeglitch.js', {team:{token:'timeline-code',team:{team_id:'T1'}}});
  const milestones = Array.from({length:5}, (_, index) => ({id:`card-${index}`,title:`Event ${index}`,description:'An event card'}));
  const round1 = {...state('round1'),round1:{score:0,remaining_seconds:300,attempts_left:3,milestones}};
  let submitted;
  test.api.request = async (route, options) => {
    if (route.endsWith('/submit')) { submitted = options.body.placed_ids; return {correct:true,state:state('round2')}; }
    return round1;
  };
  test.run(); await settle();
  assert.equal(test.get('round1Timer').textContent, '05:00');
  assert.equal(test.get('round1Heading').focusCount, 1);
  assert.equal(test.get('attempts').textContent, '3 attempts left');
  assert.equal(test.get('timeline').children.length, 5);
  test.get('timeline').children[0].children[1].children[1].onclick();
  await test.get('submitTimeline').onclick();
  assert.equal(submitted[0], 'card-1');
  assert.equal(submitted[1], 'card-0');
  assert.equal(test.get('round2').hidden, false, 'A correct Part A submission should open Part B immediately.');
  assert.equal(test.get('round2Timer').textContent, '15:00');
  assert.equal(test.get('round2Heading').focusCount, 1);
  console.log('Timeline: five-minute clock, three attempts, accessible reorder, and immediate fifteen-minute Part B pass.');
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
  const batchList = [event('test','ended'),event('morning','ended'),event('afternoon','waiting')];
  const morningSession = {...state('finished'), event:event('morning','ended')};
  test.api.request = async route => {
    if (route === '/api/event/status') return {event:batchList[2], batches:batchList};
    if (route === '/api/health') return {ai:{configured:true,ollama_backup_configured:true}};
    if (route.startsWith('/api/admin/log')) { const morning = route.includes('morning'); return {event:batchList[morning ? 1 : 2], total:morning ? 1 : 0, sessions:morning ? [{session_id:'S1',team_id:'T1',phase:'finished',objective_score:4,quality_score:null,final_score:null,quality_status:'pending'}] : []}; }
    if (route.startsWith('/api/admin/teams')) return {teams:route.includes('morning') ? [{team_id:'T1',team_name:'Test team',school_name:'School',team_size:2,batch_id:'morning'}] : []};
    if (route.includes('/api/admin/session/')) return {session:morningSession, messages:[{turn:1,timestamp:'2026-10-29T10:00:00',prompt:'A successful prompt',response:'A provider response',ai_provider:'groq'}], failed_requests:[{id:1,timestamp:1793268001,prompt:'A failed prompt',error:'Both providers failed',provider_details:{reason:'provider_timeout'}}]};
    throw new Error(`Unexpected route: ${route}`);
  };
  test.run(); await settle();
  assert.match(test.get('eventState').textContent, /Afternoon/);
  assert.equal(test.get('batchSelect').children.find(option => option.value === 'test')?.textContent, 'Test');
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

async function delayedGameChecks() {
  const test = page('timeglitch.js', {team:{token:'original-team-code',team:{team_id:'T1'}}});
  const initial = deferred(); const calls = [];
  let currentAccess = {token:'original-team-code',team:{team_id:'T1'}};
  test.api.team = () => currentAccess;
  test.api.request = async (route, options) => {
    calls.push({route, token:options?.token});
    if (route.endsWith('/start')) return initial.promise;
    return route.endsWith('/prompt') ? {state:state('round2')} : state('round2');
  };
  test.run(); await settle();
  test.listeners.visibilitychange(); await settle();
  assert.equal(test.get('round2').hidden, false);
  test.get('promptInput').value = 'A request made after the newer status response.';
  await test.get('promptForm').onsubmit({preventDefault() {}});
  initial.resolve({phase:'waiting',event:event('morning','waiting'),round1:{},round2:{},prompt_history:[]});
  await settle();
  assert.equal(test.get('round2').hidden, false, 'A delayed start response must not restore an old waiting screen.');
  currentAccess = {token:'another-team-code',team:{team_id:'T2'}};
  test.get('promptInput').value = 'The open page must still send only its original private code.';
  await test.get('promptForm').onsubmit({preventDefault() {}});
  assert(calls.every(call => call.token === 'original-team-code'), 'Every game request must explicitly use the captured team token.');
  const before = calls.length;
  test.windowListeners.storage({key:'aarohan_team_access'});
  assert.equal(test.redirects.at(-1), 'reload');
  await test.get('promptForm').onsubmit({preventDefault() {}});
  assert.equal(calls.length, before, 'A page whose stored team changed must stop sending requests before reload.');
  console.log('Game races: delayed initial response ignored; captured team token retained; cross-tab access change reloads without a cross-team request.');
}

async function delayedAdminChecks() {
  const test = page('admin.js', {admin:{token:'admin-test-token'}});
  const recovery = deferred(), detailA = deferred(), exported = deferred();
  const batchList = [event('morning','ended'),event('afternoon','waiting')];
  const teamRows = [{team_id:'A',team_name:'Team A',participants:[]},{team_id:'B',team_name:'Team B',participants:[]}];
  let useDelayedDetail = false;
  test.api.request = async route => {
    if (route === '/api/event/status') return {event:batchList[0],batches:batchList};
    if (route === '/api/health') return {ai:{}};
    if (route.startsWith('/api/admin/log')) return {event:route.includes('afternoon') ? batchList[1] : batchList[0],total:2,sessions:teamRows.map(team => ({team_id:team.team_id,session_id:team.team_id,phase:'finished'}))};
    if (route.endsWith('/resume-code')) return recovery.promise;
    if (route.startsWith('/api/admin/teams')) return {teams:teamRows};
    if (route === '/api/admin/session/A' && useDelayedDetail) return detailA.promise;
    if (route.startsWith('/api/admin/session/')) return {session:{team_id:'B',team_name:'Team B',event:batchList[0],round2:{}},messages:[]};
    throw new Error(`Unexpected route: ${route}`);
  };
  test.context.fetch = async () => exported.promise;
  test.run(); await settle();
  const action = (row, index) => test.get('teamsTable').children[row].children.at(-1).children[index].onclick();
  action(0,0);
  const recovering = test.get('recoverTeam').onclick(); await settle();
  action(1,0);
  recovery.resolve({resume_code:'ABCDE'}); await recovering;
  assert.match(test.get('rosterTitle').textContent, /Team B/);
  assert.equal(test.get('recoveryCode').value, '', 'A token issued for Team A must not appear under Team B.');
  assert.equal(test.get('recoveryArea').hidden, true);
  useDelayedDetail = true;
  const firstReview = action(0,2); await settle();
  await action(1,2);
  detailA.resolve({session:{team_id:'A',team_name:'Team A',event:batchList[0],round2:{}},messages:[]}); await firstReview;
  assert.match(test.get('reviewTeam').textContent, /Team B/, 'A delayed transcript must not replace the latest selected team.');
  const download = test.get('exportExcel').onclick(); await settle();
  test.get('batchSelect').value = 'afternoon'; test.get('batchSelect').onchange(); await settle();
  exported.resolve({ok:true,blob:async () => ({})}); await download;
  const link = test.created.find(element => element.tagName === 'a' && element.download);
  assert.equal(link.download, 'aarohan-morning-results.xlsx', 'The filename must identify the batch that produced the downloaded workbook.');
  console.log('Admin races: stale private-code and transcript responses ignored; export filename retains its requested batch.');
}

(async () => { copyChecks(); await gameChecks(); await timelineChecks(); await registrationChecks(); await adminChecks(); await delayedGameChecks(); await delayedAdminChecks(); })().catch(error => { console.error(error); process.exitCode = 1; });
