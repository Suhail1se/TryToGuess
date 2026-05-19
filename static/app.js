// /static/app.js
// Shared JS for index and lobby pages

async function api(path, opts) {
  const res = await fetch(path, Object.assign({headers:{'Content-Type':'application/json'}}, opts));
  return res.json();
}

/* ---------- Index page uses inline handlers in templates. ----------
   This file contains lobby logic used by /room/<code> page.
*/

if (typeof ROOM !== 'undefined' && ROOM) {
  // Lobby page logic
  const playersList = document.getElementById('playersList');
  const messagesEl = document.getElementById('messages');
  const chatInput = document.getElementById('chatInput');
  const askBtn = document.getElementById('askBtn');
  const guessBtn = document.getElementById('guessBtn');
  const responseRow = document.getElementById('responseRow');
  const yesBtn = document.getElementById('yesBtn');
  const noBtn = document.getElementById('noBtn');
  const turnInfo = document.getElementById('turnInfo');
  const yourItemBox = document.getElementById('yourItemBox');
  const hostControls = document.getElementById('hostControls');
  const startGameBtn = document.getElementById('startGame');
  const endLobbyBtn = document.getElementById('endLobby');
  const hostTheme = document.getElementById('hostTheme');

  let state = null;
  let isHost = false;

  function el(k, cls) { const d = document.createElement(k); if (cls) d.className = cls; return d; }

  function renderPlayers(list) {
    playersList.innerHTML = '';
    list.forEach(p=>{
      const li = el('li');
      li.textContent = p.name + (p.role==='host' ? ' (host)' : '');
      playersList.appendChild(li);
    });
    // show host controls only if current user is host
    const host = list.find(x=>x.role==='host');
    isHost = host && host.name === NAME;
    if (hostControls) hostControls.classList.toggle('hidden', !isHost);
  }

  function appendMessage(m) {
    const div = el('div','msg');
    const who = el('div','who'); who.textContent = m.sender;
    const txt = el('div','txt'); txt.textContent = m.text;
    div.appendChild(who); div.appendChild(txt);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  async function refreshState() {
    try {
      const j = await api('/state/'+ROOM);
      if (!j.ok) return;
      state = j.room;
      renderPlayers(j.players);
      messagesEl.innerHTML = '';
      j.messages.forEach(appendMessage);
      // turn info
      let turnText = 'Lobby';
      if (state.state === 'playing') {
        const turnName = (state.turn === 1 ? state.host_name : (j.players.find(p=>p.role==='guest')||{}).name) || '...';
        turnText = `Turn: ${turnName}`;
      } else if (state.state === 'finished') {
        turnText = 'Round finished';
      }
      turnInfo.textContent = turnText;
      // show own item if playing or finished
      if (state.state === 'playing' || state.state === 'finished') {
        const it = await api(`/get_items/${ROOM}?name=${encodeURIComponent(NAME)}`);
        if (it.ok) yourItemBox.textContent = 'Your item: ' + (it.your_item || '---');
      } else {
        yourItemBox.textContent = '';
      }
    } catch (e) {
      console.error(e);
    }
  }

  // polling
  refreshState();
  setInterval(refreshState, 1500);

  // ask action: adds a message of type 'ask' and toggles turn
  askBtn && askBtn.addEventListener('click', async ()=>{
    const text = chatInput.value.trim();
    if (!text) return alert('Write a question');
    const res = await api('/turn_action', {method:'POST', body: JSON.stringify({code:ROOM, actor:NAME, action:'ask', text})});
    if (!res.ok) return alert(res.error || 'Not allowed');
    chatInput.value = '';
    await refreshState();
  });

  // guess action
  guessBtn && guessBtn.addEventListener('click', async ()=>{
    const text = chatInput.value.trim();
    if (!text) return alert('Write your guess (exact)');
    const res = await api('/turn_action', {method:'POST', body: JSON.stringify({code:ROOM, actor:NAME, action:'guess', text})});
    if (!res.ok) return alert(res.error || 'Error');
    if (res.result === 'correct') {
      alert('Correct! You won. Item: ' + res.item);
    } else {
      alert('Wrong guess');
    }
    chatInput.value = '';
    await refreshState();
  });

  // when it's your opponent's turn they must respond yes/no using response row.
  // Show response buttons only when it's your turn to respond (i.e., you are not the asking role and last message type is 'ask')
  setInterval(async ()=>{
    // quick heuristic: show response row if last message type is 'ask' and it's current user's turn to respond
    try {
      const j = await api('/state/'+ROOM);
      if (!j.ok) return;
      const msgs = j.messages || [];
      const last = msgs.length ? msgs[msgs.length-1] : null;
      const turn = j.room.turn;
      const hostName = j.room.host_name;
      const guest = (j.players.find(p=>p.role==='guest')||{}).name;
      const actorRole = (NAME === hostName) ? 'host' : ((NAME === guest) ? 'guest' : null);
      // If last was an 'ask' by the other player AND it's your turn to respond -> show yes/no
      let showResp = false;
      if (last && last.type === 'ask') {
        const lastBy = last.sender;
        if (lastBy !== NAME) {
          // determine whose turn it is in room (turn indicates who should act next after previous move)
          // Response should be allowed when it's actor_role's turn (we rely on server validation too)
          showResp = true;
        }
      }
      if (responseRow) responseRow.classList.toggle('hidden', !showResp);
    } catch(e){console.error(e)}
  }, 800);

  // yes/no buttons
  yesBtn && yesBtn.addEventListener('click', async ()=> {
    const res = await api('/turn_action', {method:'POST', body: JSON.stringify({code:ROOM, actor:NAME, action:'respond', text:'yes'})});
    if (!res.ok) return alert(res.error || 'Error');
    await refreshState();
  });
  noBtn && noBtn.addEventListener('click', async ()=> {
    const res = await api('/turn_action', {method:'POST', body: JSON.stringify({code:ROOM, actor:NAME, action:'respond', text:'no'})});
    if (!res.ok) return alert(res.error || 'Error');
    await refreshState();
  });

  // host controls
  startGameBtn && startGameBtn.addEventListener('click', async ()=>{
    // only host can call start_game; server checks presence of second player
    const res = await api('/start_game', {method:'POST', body: JSON.stringify({code:ROOM, starter:NAME})});
    if (!res.ok) return alert(res.error || 'Error starting game');
    await refreshState();
  });
  endLobbyBtn && endLobbyBtn.addEventListener('click', async ()=>{
    if (!confirm('End lobby for everyone?')) return;
    const res = await api('/reset_round', {method:'POST', body: JSON.stringify({code:ROOM, action:'end'})});
    if (!res.ok) return alert('Error');
    await refreshState();
    alert('Lobby closed');
    window.location.href = '/';
  });

  // make messages clickable to copy (optional)
  messagesEl && messagesEl.addEventListener('click', (e)=>{
    const t = e.target;
    if (t && t.className === 'txt') {
      navigator.clipboard?.writeText(t.textContent).then(()=>{/*copied*/});
    }
  });
}
