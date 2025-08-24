// ===== HTTP утиліти =====
const api = {
  async post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type':'application/json' },
      body: JSON.stringify(body || {})
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(e.error || 'Request failed');
    }
    return res.json();
  },
  async del(url) {
    const res = await fetch(url, { method: 'DELETE' });
    if (!res.ok) {
      const e = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(e.error || 'Request failed');
    }
    return res.json();
  },
  async get(url) {
    const res = await fetch(url);
    if (!res.ok) {
      const e = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(e.error || 'Request failed');
    }
    return res.json();
  }
};

// ===== посилання на DOM =====
const els = {
  newEvent: document.getElementById('new-event'),
  event: document.getElementById('event'),

  eventTitle: document.getElementById('event-title'),
  shareLink: document.getElementById('share-link'),
  copyLink: document.getElementById('copy-link'),
  deleteEvent: document.getElementById('delete-event'),

  createEvent: document.getElementById('create-event'),
  eventName: document.getElementById('event-name'),
  eventCurrency: document.getElementById('event-currency'),

  participantName: document.getElementById('participant-name'),
  addParticipant: document.getElementById('add-participant'),
  participantsList: document.getElementById('participants'),

  expenseTitle: document.getElementById('expense-title'),
  expenseAmount: document.getElementById('expense-amount'),
  expensePaidBy: document.getElementById('expense-paid-by'),
  expenseParticipants: document.getElementById('expense-participants'),
  addExpense: document.getElementById('add-expense'),

  expensesList: document.getElementById('expenses'),
  balances: document.getElementById('balances'),
  transfers: document.getElementById('transfers'),

  myEventsTbody: document.querySelector('#my-events tbody'),
  teamEventsTbody: document.querySelector('#team-events tbody'),
  searchEvents: document.getElementById('search-events'),
  refreshEvents: document.getElementById('refresh-events'),
};

let currentEventId = null;
let state = null;

// ===== навігація екранів =====
function showNewEvent(){
  els.newEvent?.classList.remove('hidden');
  els.event?.classList.add('hidden');
}
function showEvent(){
  els.newEvent?.classList.add('hidden');
  els.event?.classList.remove('hidden');
}

// ===== шарінг =====
function setShareLink(eventId){
  const url = `${location.origin}/e/${eventId}`;
  if (els.shareLink) els.shareLink.value = url;
  if (els.eventTitle && state) els.eventTitle.textContent = `Подія: ${state.name} (${state.currency})`;
}
els.copyLink?.addEventListener('click', () => {
  if (!els.shareLink) return;
  els.shareLink.select();
  document.execCommand('copy');
  els.copyLink.textContent = 'Скопійовано!';
  setTimeout(() => els.copyLink.textContent = 'Копіювати посилання', 1200);
});

// ===== локальні події =====
const LS_KEY = 'my_events_v1';
const escapeHtml = (s='') => String(s)
  .replaceAll('&','&amp;').replaceAll('<','&lt;')
  .replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'", '&#39;');

function rememberEvent(ev) {
  try {
    const list = JSON.parse(localStorage.getItem(LS_KEY) || '[]');
    const filtered = list.filter(x => x.id !== ev.id);
    filtered.unshift({
      id: ev.id,
      name: ev.name,
      currency: ev.currency,
      created_at: ev.created_at || new Date().toISOString()
    });
    localStorage.setItem(LS_KEY, JSON.stringify(filtered.slice(0, 50)));
  } catch (_) {}
}
function forgetEvent(eventId) {
  try {
    const list = JSON.parse(localStorage.getItem(LS_KEY) || '[]');
    const filtered = list.filter(x => x.id !== eventId);
    localStorage.setItem(LS_KEY, JSON.stringify(filtered));
  } catch (_) {}
}
function loadMyEvents() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); }
  catch(_) { return []; }
}
function fmtDate(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso || ''; }
}
function rowHtml(ev) {
  return `
    <tr>
      <td data-label="Назва">${escapeHtml(ev.name || ev.id)}</td>
      <td data-label="Валюта">${escapeHtml(ev.currency || '')}</td>
      <td data-label="Створено">${fmtDate(ev.created_at)}</td>
      <td data-label="">
        <a class="btn" href="/e/${encodeURIComponent(ev.id)}">Відкрити</a>
        <button class="btn secondary" data-copy="/e/${encodeURIComponent(ev.id)}">Копіювати лінк</button>
      </td>
    </tr>
  `;
}
function attachCopyButtons(scopeSel) {
  document.querySelectorAll(`${scopeSel} [data-copy]`).forEach(btn => {
    btn.onclick = () => {
      const path = btn.getAttribute('data-copy');
      navigator.clipboard.writeText(location.origin + path);
      const old = btn.textContent;
      btn.textContent = 'Скопійовано!';
      setTimeout(() => btn.textContent = old, 1200);
    };
  });
}
function renderMyEvents() {
  if (!els.myEventsTbody) return;
  const data = loadMyEvents();
  els.myEventsTbody.innerHTML = data.length
    ? data.map(rowHtml).join('')
    : `<tr><td colspan="4">Поки порожньо</td></tr>`;
  attachCopyButtons('#my-events');
}

// ===== «Останні події в команді» =====
async function loadTeamEvents(q='') {
  const url = q ? `/api/events?q=${encodeURIComponent(q)}` : '/api/events';
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to load events');
  return res.json();
}
async function renderTeamEvents(q='') {
  if (!els.teamEventsTbody) return;
  try {
    const data = await loadTeamEvents(q);
    els.teamEventsTbody.innerHTML = data.length
      ? data.map(rowHtml).join('')
      : `<tr><td colspan="4">Нічого не знайдено</td></tr>`;
    attachCopyButtons('#team-events');
  } catch {
    els.teamEventsTbody.innerHTML = `<tr><td colspan="4">Помилка завантаження</td></tr>`;
  }
}

// ===== учасники/витрати/баланси =====
function renderParticipants(){
  if (!els.participantsList || !state) return;
  els.participantsList.innerHTML = '';
  state.participants.forEach(p => {
    const li = document.createElement('li');
    const left = document.createElement('div');
    left.textContent = p.name;
    li.appendChild(left);

    const del = document.createElement('button');
    del.textContent = '✕';
    del.title = 'Видалити учасника';
    del.onclick = async () => {
      try {
        await api.del(`/api/events/${currentEventId}/participants/${p.id}`);
        await loadEvent();
      } catch (e) {
        alert(e.message);
      }
    };
    li.appendChild(del);
    els.participantsList.appendChild(li);
  });

  if (els.expensePaidBy) {
    els.expensePaidBy.innerHTML = '';
    state.participants.forEach(p => {
      const opt = document.createElement('option');
      opt.value = String(p.id);
      opt.textContent = p.name;
      els.expensePaidBy.appendChild(opt);
    });
  }

  if (els.expenseParticipants) {
    els.expenseParticipants.innerHTML = '';
    state.participants.forEach(p => {
      const chip = document.createElement('span');
      chip.className = 'chip';
      chip.textContent = p.name;
      chip.dataset.id = String(p.id);
      chip.onclick = () => chip.classList.toggle('active');
      els.expenseParticipants.appendChild(chip);
    });
  }
}

function renderExpenses(){
  if (!els.expensesList || !state) return;
  els.expensesList.innerHTML = '';
  state.expenses.forEach(ex => {
    const li = document.createElement('li');
    const left = document.createElement('div');
    const payer = state.participants.find(p => p.id === ex.paid_by)?.name || '—';
    left.innerHTML = `<strong>${escapeHtml(ex.title)}</strong> ` +
                     `<span class="badge">${escapeHtml(ex.amount)} ${escapeHtml(state.currency)}</span> ` +
                     `<span class="small">платив(ла): ${escapeHtml(payer)}</span>`;
    li.appendChild(left);
    const del = document.createElement('button');
    del.textContent = '✕';
    del.title = 'Видалити витрату';
    del.onclick = async () => {
      await api.del(`/api/events/${currentEventId}/expenses/${ex.id}`);
      await loadEvent();
    };
    li.appendChild(del);
    els.expensesList.appendChild(li);
  });
}

async function renderSettlements(){
  if (!els.balances || !els.transfers) return;
  const s = await api.get(`/api/events/${currentEventId}/settlements`);
  els.balances.innerHTML = '';
  s.balances.forEach(b => {
    const p = document.createElement('p');
    const v = parseFloat(b.balance);
    const sign = v > 0 ? '+' : '';
    p.textContent = `${b.name}: ${sign}${b.balance} ${s.currency}`;
    els.balances.appendChild(p);
  });
  els.transfers.innerHTML = '';
  s.transfers.forEach(t => {
    const li = document.createElement('li');
    li.textContent = `${t['from']} → ${t['to']}: ${t.amount} ${s.currency}`;
    els.transfers.appendChild(li);
  });
}

// ===== завантаження події =====
async function loadEvent(){
  state = await api.get(`/api/events/${currentEventId}`);
  renderParticipants();
  renderExpenses();
  await renderSettlements();
  setShareLink(currentEventId);
  rememberEvent({
    id: currentEventId,
    name: state.name,
    currency: state.currency,
    created_at: state.created_at
  });
}

// ===== події UI =====
els.createEvent?.addEventListener('click', async () => {
  const name = (els.eventName?.value || '').trim() || 'Нова подія';
  const currency = els.eventCurrency?.value || 'UAH';
  const data = await api.post('/api/events', { name, currency });
  currentEventId = data.id;

  rememberEvent({
    id: data.id, name: data.name, currency: data.currency, created_at: data.created_at
  });

  history.replaceState({}, '', `/e/${currentEventId}`);
  await loadEvent();
  showEvent();
  setShareLink(currentEventId);
});

els.addParticipant?.addEventListener('click', async () => {
  const name = (els.participantName?.value || '').trim();
  if(!name) return;
  await api.post(`/api/events/${currentEventId}/participants`, { name });
  if (els.participantName) els.participantName.value = '';
  await loadEvent();
});

els.addExpense?.addEventListener('click', async () => {
  const title = (els.expenseTitle?.value || '').trim() || 'Витрата';
  const amount = parseFloat(els.expenseAmount?.value || '0');
  if(!(amount > 0)) { alert('Вкажіть суму > 0'); return; }
  const paid_by = parseInt(els.expensePaidBy?.value || '0', 10);
  const selected = [...(els.expenseParticipants?.querySelectorAll('.chip.active') || [])]
                    .map(ch => parseInt(ch.dataset.id,10));
  const payload = { title, amount, paid_by };
  if(selected.length > 0) payload.participants = selected;
  await api.post(`/api/events/${currentEventId}/expenses`, payload);
  if (els.expenseTitle) els.expenseTitle.value = '';
  if (els.expenseAmount) els.expenseAmount.value = '';
  await loadEvent();
});

// *** Видалення події ***
els.deleteEvent?.addEventListener('click', async () => {
  if (!currentEventId) return;
  if (!confirm('Точно видалити цю подію? Це незворотно.')) return;

  try {
    await api.del(`/api/events/${currentEventId}`);
    forgetEvent(currentEventId);
    alert('Подію видалено');

    history.replaceState({}, '', '/');
    showNewEvent();
    renderMyEvents();
    if (els.teamEventsTbody) renderTeamEvents();
  } catch (e) {
    alert('Помилка при видаленні: ' + e.message);
  }
});

// ===== копіювання карток =====
document.addEventListener('click', e => {
  if (e.target.classList.contains('copy-card')) {
    const row = e.target.closest('.card-row');
    const input = row.querySelector('input');
    if (input) {
      input.select();
      document.execCommand('copy');
      e.target.textContent = 'Скопійовано!';
      setTimeout(() => e.target.textContent = 'Скопіювати', 1200);
    }
  }
});

// ===== boot =====
async function boot(){
  renderMyEvents();
  if (els.refreshEvents) {
    els.refreshEvents.addEventListener('click', () => {
      const q = (els.searchEvents?.value || '').trim();
      renderTeamEvents(q);
    });
  }
  if (els.searchEvents) {
    els.searchEvents.addEventListener('keyup', e => {
      if (e.key === 'Enter') {
        renderTeamEvents(els.searchEvents.value.trim());
      }
    });
  }
  if (els.teamEventsTbody) {
    renderTeamEvents();
  }

  const m = location.pathname.match(/^\/e\/([a-z0-9]{8})$/i);
  if (m) {
    currentEventId = m[1];
    try{
      await loadEvent();
      showEvent();
      return;
    }catch(e){
      console.error(e);
      // 🔧 нове: прибираємо "биту" подію зі списку та повертаємо на головну
      forgetEvent(currentEventId);
      alert('Подію не знайдено (ймовірно видалена або база була скинута). Я прибрав її зі списку.');
      history.replaceState({}, '', '/');
      renderMyEvents();
      showNewEvent();
      return;
    }
  }
  showNewEvent();
}
boot();
