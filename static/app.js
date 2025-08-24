const api = {
  async post(url, body) {
    const res = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body || {}) });
    if(!res.ok){ const e = await res.json().catch(()=>({error:res.statusText})); throw new Error(e.error || 'Request failed'); }
    return res.json();
  },
  async del(url) {
    const res = await fetch(url, { method:'DELETE' });
    if(!res.ok){ const e = await res.json().catch(()=>({error:res.statusText})); throw new Error(e.error || 'Request failed'); }
    return res.json();
  },
  async get(url) {
    const res = await fetch(url);
    if(!res.ok){ const e = await res.json().catch(()=>({error:res.statusText})); throw new Error(e.error || 'Request failed'); }
    return res.json();
  }
};

const els = {
  newEvent: document.getElementById('new-event'),
  event: document.getElementById('event'),
  eventTitle: document.getElementById('event-title'),
  shareLink: document.getElementById('share-link'),
  copyLink: document.getElementById('copy-link'),
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
};

let currentEventId = null;
let state = null;

function showNewEvent(){
  els.newEvent.classList.remove('hidden');
  els.event.classList.add('hidden');
}

function showEvent(){
  els.newEvent.classList.add('hidden');
  els.event.classList.remove('hidden');
}

function setShareLink(eventId){
  const url = `${location.origin}/e/${eventId}`;
  els.shareLink.value = url;
  els.eventTitle.textContent = `Подія: ${state.name} (${state.currency})`;
}

els.copyLink.addEventListener('click', () => {
  els.shareLink.select();
  document.execCommand('copy');
  els.copyLink.textContent = 'Скопійовано!';
  setTimeout(() => els.copyLink.textContent = 'Копіювати посилання', 1200);
});

els.createEvent.addEventListener('click', async () => {
  const name = els.eventName.value.trim() || 'Нова подія';
  const currency = els.eventCurrency.value;
  const data = await api.post('/api/events', { name, currency });
  currentEventId = data.id;
  history.replaceState({}, '', `/e/${currentEventId}`);
  await loadEvent();
  showEvent();
  setShareLink(currentEventId);
});

els.addParticipant.addEventListener('click', async () => {
  const name = els.participantName.value.trim();
  if(!name) return;
  await api.post(`/api/events/${currentEventId}/participants`, { name });
  els.participantName.value = '';
  await loadEvent();
});

els.addExpense.addEventListener('click', async () => {
  const title = els.expenseTitle.value.trim() || 'Витрата';
  const amount = parseFloat(els.expenseAmount.value);
  if(!(amount > 0)) { alert('Вкажіть суму > 0'); return; }
  const paid_by = parseInt(els.expensePaidBy.value, 10);
  const selected = [...els.expenseParticipants.querySelectorAll('.chip.active')].map(ch => parseInt(ch.dataset.id,10));
  const payload = { title, amount, paid_by };
  if(selected.length > 0) payload.participants = selected;
  await api.post(`/api/events/${currentEventId}/expenses`, payload);
  els.expenseTitle.value = '';
  els.expenseAmount.value = '';
  await loadEvent();
});

function renderParticipants(){
  els.participantsList.innerHTML = '';
  state.participants.forEach(p => {
    const li = document.createElement('li');
    const left = document.createElement('div');
    left.textContent = p.name;
    li.appendChild(left);
    // Delete button (only allowed if they didn't pay)
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

  // Update "paid by" selector
  els.expensePaidBy.innerHTML = '';
  state.participants.forEach(p => {
    const opt = document.createElement('option');
    opt.value = String(p.id);
    opt.textContent = p.name;
    els.expensePaidBy.appendChild(opt);
  });

  // Update chips (involved participants)
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

function renderExpenses(){
  els.expensesList.innerHTML = '';
  state.expenses.forEach(ex => {
    const li = document.createElement('li');
    const left = document.createElement('div');
    const payer = state.participants.find(p => p.id === ex.paid_by)?.name || '—';
    left.innerHTML = `<strong>${ex.title}</strong> <span class="badge">${ex.amount} ${state.currency}</span> <span class="small">платив(ла): ${payer}</span>`;
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

async function loadEvent(){
  state = await api.get(`/api/events/${currentEventId}`);
  renderParticipants();
  renderExpenses();
  await renderSettlements();
  setShareLink(currentEventId);
}

async function boot(){
  const m = location.pathname.match(/^\/e\/([a-z0-9]{8})$/i);
  if(m){
    currentEventId = m[1];
    try{
      await loadEvent();
      showEvent();
      return;
    }catch(e){
      console.error(e);
      alert('Подію не знайдено. Створіть нову.');
    }
  }
  showNewEvent();
}
boot();
