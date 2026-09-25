const PRESETS = [
  { id: "conservative", label: "Conservative", looseness: 18, aggression: 34, bluff: 3, blurb: "Few hands, small bets, almost no bluffs." },
  { id: "super_casual", label: "Super casual", looseness: 80, aggression: 22, bluff: 8, blurb: "Lots of calls, small raises, in it for the company." },
  { id: "balanced", label: "Balanced", looseness: 44, aggression: 60, bluff: 12, blurb: "A normal mix of folds, calls, and bets." },
  { id: "reckless", label: "Reckless", looseness: 90, aggression: 94, bluff: 40, blurb: "Wide hands, large bets, frequent bluffs." },
];
const NAMES = ["June", "Ellis", "Marlow", "Ada", "Ned", "Ivo"];
const SUITS = [["s", "♠"], ["h", "♥"], ["d", "♦"], ["c", "♣"]];
const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const LAYOUT = {
  1: [[50, 78]],
  2: [[50, 82], [50, 16]],
  3: [[50, 82], [18, 30], [82, 30]],
  4: [[50, 84], [14, 48], [50, 14], [86, 48]],
  5: [[50, 84], [12, 58], [22, 18], [78, 18], [88, 58]],
  6: [[50, 84], [12, 62], [18, 24], [50, 10], [82, 24], [88, 62]],
};

let models = [
  model("June", "conservative"),
  model("Ellis", "super_casual"),
  model("Marlow", "reckless"),
];
let dealerSeats = [
  { name: "You", hero: true },
  { name: "Alex", hero: false },
  { name: "Sam", hero: false },
];
let socket = null;
let tableMessage = null;
let raiseDraft = null;
let dealerId = null;
let dealerState = null;
let pickedRank = "A";
let pickedSuit = "s";
let pendingScan = null;
let listening = false;
let recognition = null;

function model(name, style) {
  const preset = PRESETS.find((item) => item.id === style);
  return { name, style, looseness: preset.looseness, aggression: preset.aggression, bluff: preset.bluff };
}

function styleLabel(id) {
  return (PRESETS.find((item) => item.id === id) || { label: "Custom" }).label;
}

function show(view) {
  for (const id of ["salon", "models", "friends", "table", "dealer"]) {
    document.getElementById(id).hidden = id !== view;
  }
  document.getElementById("nav-table").hidden = !tableMessage;
  if (view === "models") renderModels();
  if (view === "dealer") renderDealerSetup();
}

document.body.addEventListener("click", (event) => {
  const go = event.target.closest("[data-go]");
  if (go) show(go.dataset.go);
});

function toast(text) {
  const node = document.getElementById("toast");
  node.hidden = false;
  node.textContent = text;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 3200);
}

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : "Check the names, blinds, and seats, then try again.");
  }
  return data;
}

let backend = null;
let pyodide = null;
let localPlay = false;
let localDealer = false;
let pumpGen = 0;

async function hasBackend() {
  if (backend !== null) return backend;
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    backend = response.ok;
  } catch {
    backend = false;
  }
  return backend;
}

async function loadEngine(status) {
  if (pyodide) return;
  if (status) status.textContent = "Loading the table engine…";
  pyodide = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/" });
  pyodide.FS.mkdirTree("/app");
  for (const name of ["__init__.py", "engine.py", "ai.py", "dealer.py", "rooms.py", "solo.py"]) {
    const text = await (await fetch(`app/${name}`)).text();
    pyodide.FS.writeFile(`/app/${name}`, text);
  }
  pyodide.runPython(`
import sys
sys.path.insert(0, "/")
from app.solo import DealerBridge, TableSession
table = TableSession()
dealer = DealerBridge()
`);
}

function engineCall(source, value) {
  if (value !== undefined) pyodide.globals.set("__arg", value);
  return JSON.parse(pyodide.runPython(source));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function showState(message) {
  tableMessage = message;
  raiseDraft = keepRaise(message);
  renderTable();
  show("table");
}

async function pump() {
  const gen = ++pumpGen;
  while (gen === pumpGen && localPlay) {
    const pending = pyodide.runPython("table.pending()");
    if (pending === "bot") {
      await sleep(850);
      if (gen !== pumpGen) return;
      showState(engineCall("table.act_bot()"));
    } else if (pending === "deal") {
      await sleep(2600);
      if (gen !== pumpGen) return;
      showState(engineCall("table.auto_deal()"));
    } else {
      break;
    }
  }
}

function renderModels() {
  const root = document.getElementById("model-list");
  root.innerHTML = models.map((item, index) => {
    const preset = PRESETS.find((entry) => entry.id === item.style);
    const custom = !preset || preset.looseness !== item.looseness || preset.aggression !== item.aggression || preset.bluff !== item.bluff;
    const shown = custom ? "custom" : item.style;
    return `<article class="model">
      <div class="model-head">
        <input data-name="${index}" value="${escapeAttr(item.name)}" maxlength="18">
        <button type="button" class="text-btn" data-remove="${index}">Remove</button>
      </div>
      <div class="styles">${PRESETS.map((entry) => `<button type="button" data-style="${entry.id}" data-index="${index}" class="${shown === entry.id ? "on" : ""}">${entry.label}</button>`).join("")}</div>
      <p class="blurb">${custom ? "Custom sliders." : preset.blurb}</p>
      <div class="sliders">
        ${slider(index, "looseness", "Looseness", item.looseness)}
        ${slider(index, "aggression", "Aggression", item.aggression)}
        ${slider(index, "bluff", "Bluff", item.bluff)}
      </div>
    </article>`;
  }).join("");
  document.getElementById("add-model").disabled = (document.getElementById("i-play").checked ? 1 : 0) + models.length >= 6;
}

function slider(index, key, label, value) {
  return `<label>${label} ${value}<input type="range" min="0" max="100" value="${value}" data-key="${key}" data-index="${index}"></label>`;
}

document.getElementById("model-list").addEventListener("input", (event) => {
  if (event.target.dataset.name !== undefined && event.target.dataset.name !== "") {
    models[Number(event.target.dataset.name)].name = event.target.value;
    return;
  }
  const index = Number(event.target.dataset.index);
  if (Number.isNaN(index) || !event.target.dataset.key) return;
  models[index][event.target.dataset.key] = Number(event.target.value);
  renderModels();
});
document.getElementById("model-list").addEventListener("click", (event) => {
  const remove = event.target.dataset.remove;
  if (remove !== undefined) {
    models.splice(Number(remove), 1);
    renderModels();
  }
  if (event.target.dataset.style) {
    const index = Number(event.target.dataset.index);
    const preset = PRESETS.find((item) => item.id === event.target.dataset.style);
    models[index].style = preset.id;
    models[index].looseness = preset.looseness;
    models[index].aggression = preset.aggression;
    models[index].bluff = preset.bluff;
    renderModels();
  }
});
document.getElementById("add-model").addEventListener("click", () => {
  models.push(model(NAMES[models.length % NAMES.length], "balanced"));
  renderModels();
});
document.getElementById("i-play").addEventListener("change", renderModels);
document.getElementById("open-table").addEventListener("click", async () => {
  const error = document.getElementById("models-error");
  error.textContent = "";
  const body = {
    mode: "models",
    play: document.getElementById("i-play").checked,
    your_name: document.getElementById("your-name").value,
    stack: Number(document.getElementById("buy-in").value),
    sb: Number(document.getElementById("sb").value),
    bb: Number(document.getElementById("bb").value),
    models: models.map(liveStyle),
  };
  try {
    if (!(await hasBackend())) {
      await loadEngine(error);
      localPlay = true;
      error.textContent = "";
      showState(engineCall("table.create(__arg)", body));
      pump();
      return;
    }
    const created = await api("/api/tables", body);
    connect(created.code, created.player_id);
  } catch (err) {
    error.textContent = err.message;
  }
});

function liveStyle(item) {
  const preset = PRESETS.find((entry) => entry.id === item.style);
  const custom = !preset || preset.looseness !== item.looseness || preset.aggression !== item.aggression || preset.bluff !== item.bluff;
  return { name: item.name, style: custom ? "custom" : item.style, looseness: item.looseness, aggression: item.aggression, bluff: item.bluff };
}

document.getElementById("host-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!(await hasBackend())) {
    document.getElementById("friends-error").textContent = "A friends table needs the Python server. This domain can deal a models table in your browser, not a shared room.";
    return;
  }
  try {
    const created = await api("/api/tables", {
      mode: "friends",
      your_name: document.getElementById("host-name").value,
      stack: Number(document.getElementById("host-stack").value),
      sb: Number(document.getElementById("host-sb").value),
      bb: Number(document.getElementById("host-bb").value),
      models: [],
    });
    connect(created.code, created.player_id);
  } catch (err) {
    document.getElementById("friends-error").textContent = err.message;
  }
});
document.getElementById("join-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!(await hasBackend())) {
    document.getElementById("friends-error").textContent = "A friends table needs the Python server. This domain can deal a models table in your browser, not a shared room.";
    return;
  }
  try {
    const code = document.getElementById("join-code").value.trim().toUpperCase();
    const joined = await api(`/api/tables/${code}/join`, { name: document.getElementById("join-name").value });
    connect(joined.code, joined.player_id);
  } catch (err) {
    document.getElementById("friends-error").textContent = err.message;
  }
});

function connect(code, playerId) {
  if (socket) {
    socket.onclose = null;
    socket.close();
  }
  sessionStorage.setItem("poker-project", JSON.stringify({ code, playerId }));
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws/${code}/${playerId}`);
  socket.onmessage = (event) => {
    tableMessage = JSON.parse(event.data);
    raiseDraft = keepRaise(tableMessage);
    renderTable();
    show("table");
  };
  socket.onclose = () => toast("The connection dropped. Refresh to sit back down.");
}

function keepRaise(message) {
  const legal = message.state && message.state.legal;
  if (!legal || message.state.actor_id !== message.you) return null;
  if (raiseDraft == null) return null;
  return Math.min(legal.max_raise_to, Math.max(legal.min_raise_to, raiseDraft));
}

function send(payload) {
  if (localPlay) {
    showState(engineCall("table.handle(__arg)", payload));
    pump();
    return;
  }
  if (socket && socket.readyState === 1) socket.send(JSON.stringify(payload));
}

function renderTable() {
  const message = tableMessage;
  if (!message) return;
  const game = message.state;
  const you = message.you;
  const ordered = orderPlayers(game.players, you);
  const spots = LAYOUT[ordered.length] || LAYOUT[6];
  const wins = new Set();
  const highlight = (game.last_result && game.last_result.highlight) || {};
  Object.values(highlight).forEach((codes) => codes.forEach((code) => wins.add(code)));
  const seats = ordered.map((player, index) => {
    const [x, y] = spots[index] || [50, 50];
    const won = game.last_result && game.last_result.won && game.last_result.won[player.id];
    return `<div class="seat ${player.folded ? "folded" : ""} ${game.actor_id === player.id ? "turn" : ""}" style="left:${x}%;top:${y}%">
      <div class="cards">${(player.hole.length ? player.hole : ["", ""]).slice(0, 2).map((code) => cardHTML(code || "??", wins.has(code))).join("")}</div>
      <div class="meta">
        <strong>${player.id === game.button ? '<span class="dealer-chip">D</span>' : ""}${escapeHTML(player.name)}</strong>
        <span class="stack">${player.stack}${player.bet ? ` · bet ${player.bet}` : ""}${won ? ` · +${won}` : ""}</span>
        ${player.style ? `<span class="tag">${styleLabel(player.style)}</span>` : ""}
        ${player.hand_name ? `<div class="hand-label">${escapeHTML(player.hand_name)}</div>` : ""}
        ${player.all_in ? `<div class="hand-label">All in</div>` : ""}
      </div>
    </div>`;
  }).join("");
  const board = Array.from({ length: 5 }, (_, index) => cardHTML(game.board[index] || "", wins.has(game.board[index]), true));
  const banner = game.last_result ? `<div class="result">${game.last_result.lines.map(escapeHTML).join("<br>")}</div>` : "";
  const lobby = game.street === "waiting" ? `<div class="lobby"><div><p class="eyebrow">Table</p><strong>${message.code}</strong><p>${game.players.map((player) => escapeHTML(player.name)).join(", ") || "Waiting"}</p>${message.can_deal ? `<button type="button" class="gold" id="deal">Deal</button>` : "<p>Waiting for another player.</p>"}</div></div>` : "";
  document.getElementById("table-root").innerHTML = `
    <div class="table-top">
      <span>Table ${message.code} · blinds ${game.sb_amount}/${game.bb_amount}</span>
      <button type="button" class="text-btn" id="copy-code">Copy invite</button>
    </div>
    <div class="table-layout">
      <div>
        <div class="stage">
          <div class="felt"></div>
          ${seats}
          <div class="center">
            <div class="street">${escapeHTML(game.street_label)}</div>
            <div class="pot">Pot <strong>${game.pot}</strong></div>
            <div class="board">${board.join("")}</div>
            ${banner}
          </div>
          ${lobby}
        </div>
        <div class="dock">
          <div class="cards">${heroCards(game, you, wins)}</div>
          <div class="actions">${actionsHTML(message)}</div>
        </div>
      </div>
      <ol class="log" id="log">${game.log.map((line) => `<li>${escapeHTML(line)}</li>`).join("")}</ol>
    </div>`;
  const log = document.getElementById("log");
  if (log) log.scrollTop = log.scrollHeight;
  const range = document.getElementById("raise-range");
  if (range && raiseDraft != null) range.value = String(raiseDraft);
}

function heroCards(game, you, wins) {
  const hero = game.players.find((player) => player.id === you);
  if (!hero || !hero.hole.length) return "";
  return hero.hole.map((code) => cardHTML(code, wins.has(code))).join("");
}

function actionsHTML(message) {
  const game = message.state;
  if (message.game_over) return `<span>The chips have a home.</span>`;
  if (game.street === "waiting" || game.street === "showdown" || game.street === "complete") {
    const deal = message.can_deal ? `<button type="button" class="gold" id="deal">Next hand</button>` : "";
    const auto = message.mode === "models" ? `<button type="button" class="ghost" id="auto">${message.auto_next ? "Pause the models" : "Let them deal"}</button>` : "";
    return deal + auto;
  }
  const legal = game.legal;
  if (!legal || game.actor_id !== message.you) return `<span>${actorName(game)} to act</span>`;
  const buttons = [];
  if (!legal.check) buttons.push(`<button type="button" class="ghost" id="fold">Fold</button>`);
  if (legal.check) buttons.push(`<button type="button" class="solid" id="check">Check</button>`);
  if (legal.call) buttons.push(`<button type="button" class="solid" id="call">${legal.call_amount === game.players.find((player) => player.id === message.you).stack ? "All in" : `Call ${legal.call_amount}`}</button>`);
  if (legal.can_raise) {
    const value = raiseDraft || legal.min_raise_to;
    buttons.push(`<div class="raise"><input id="raise-range" type="range" min="${legal.min_raise_to}" max="${legal.max_raise_to}" value="${value}"><button type="button" class="gold" id="raise-btn">${game.current_bet ? "Raise to" : "Bet"} <span id="raise-label">${value}</span></button></div>`);
  }
  return buttons.join("");
}

function actorName(game) {
  const actor = game.players.find((player) => player.id === game.actor_id);
  return actor ? escapeHTML(actor.name) : "Someone";
}

document.getElementById("table-root").addEventListener("click", (event) => {
  const id = event.target.closest("button") && event.target.closest("button").id;
  if (id === "deal") send({ type: "start" });
  if (id === "fold") send({ type: "action", action: "fold" });
  if (id === "check") send({ type: "action", action: "check" });
  if (id === "call") send({ type: "action", action: "call" });
  if (id === "raise-btn") {
    const value = Number(document.getElementById("raise-range").value);
    send({ type: "action", action: "raise", amount: value });
  }
  if (id === "auto") send({ type: "auto", on: !tableMessage.auto_next });
  if (id === "copy-code") {
    const link = `${location.origin}/?room=${tableMessage.code}`;
    navigator.clipboard.writeText(link).then(() => toast("Invite copied.")).catch(() => toast(tableMessage.code));
  }
});
document.getElementById("table-root").addEventListener("input", (event) => {
  if (event.target.id === "raise-range") {
    raiseDraft = Number(event.target.value);
    const label = document.getElementById("raise-label");
    if (label) label.textContent = event.target.value;
  }
});

function orderPlayers(players, you) {
  const index = players.findIndex((player) => player.id === you);
  if (index < 0) return players;
  return players.slice(index).concat(players.slice(0, index));
}

function cardHTML(code, win, slot) {
  if (!code) return `<div class="card slot"></div>`;
  if (code === "??") return `<div class="card back"></div>`;
  const rank = code[0] === "T" ? "10" : code[0];
  const suit = code.slice(-1);
  const red = suit === "h" || suit === "d";
  const symbol = { s: "♠", h: "♥", d: "♦", c: "♣" }[suit] || "";
  return `<div class="card ${red ? "red" : "black"} ${win ? "win" : ""}"><b>${rank}</b><i>${symbol}</i></div>`;
}

function renderDealerSetup() {
  document.getElementById("dealer-players").innerHTML = dealerSeats.map((seat, index) => `
    <div class="seat-setup ${seat.hero ? "is-hero" : ""}">
      <label class="seat-pick">
        <input type="radio" name="hero" ${seat.hero ? "checked" : ""} data-hero="${index}" aria-label="Advice for ${escapeAttr(seat.name)}">
      </label>
      <input class="seat-name" data-seat="${index}" value="${escapeAttr(seat.name)}" maxlength="18" aria-label="Seat name">
      ${seat.hero ? `<span class="seat-note">Advice for this seat</span>` : ""}
    </div>`).join("");
}

document.getElementById("dealer-players").addEventListener("input", (event) => {
  if (event.target.dataset.seat !== undefined) dealerSeats[Number(event.target.dataset.seat)].name = event.target.value;
});
document.getElementById("dealer-players").addEventListener("change", (event) => {
  if (event.target.dataset.hero !== undefined) {
    dealerSeats.forEach((seat, index) => { seat.hero = index === Number(event.target.dataset.hero); });
    renderDealerSetup();
  }
});
document.getElementById("add-seat").addEventListener("click", () => {
  if (dealerSeats.length >= 6) return;
  dealerSeats.push({ name: NAMES[dealerSeats.length % NAMES.length], hero: false });
  renderDealerSetup();
});
document.getElementById("open-station").addEventListener("click", async () => {
  const error = document.getElementById("dealer-error");
  error.textContent = "";
  try {
    const hero = Math.max(0, dealerSeats.findIndex((seat) => seat.hero));
    if (!(await hasBackend())) {
      await loadEngine(error);
      localDealer = true;
      dealerState = engineCall("dealer.create(__arg)", {
        names: dealerSeats.map((seat) => seat.name),
        hero,
        stack: Number(document.getElementById("dealer-stack").value),
        sb: Number(document.getElementById("dealer-sb").value),
        bb: Number(document.getElementById("dealer-bb").value),
      });
      if (dealerState.error) throw new Error(dealerState.error);
      dealerId = "local";
      error.textContent = "";
      document.getElementById("dealer-setup").hidden = true;
      document.getElementById("dealer-station").hidden = false;
      renderStation();
      startCamera();
      buildPicker();
      return;
    }
    dealerState = await api("/api/dealer", {
      names: dealerSeats.map((seat) => seat.name),
      hero,
      stack: Number(document.getElementById("dealer-stack").value),
      sb: Number(document.getElementById("dealer-sb").value),
      bb: Number(document.getElementById("dealer-bb").value),
    });
    dealerId = dealerState.id;
    sessionStorage.setItem("north-dealer", dealerId);
    document.getElementById("dealer-setup").hidden = true;
    document.getElementById("dealer-station").hidden = false;
    renderStation();
    startCamera();
    buildPicker();
  } catch (err) {
    error.textContent = err.message;
  }
});

function renderStation() {
  const state = dealerState;
  if (!state) return;
  const advice = state.advice || {};
  const equity = advice.equity == null ? "" : `${Math.round(advice.equity * 100)}% win chance`;
  document.getElementById("advice").innerHTML = `<p class="suggestion">${escapeHTML(advice.suggestion || "")}</p><p>${escapeHTML(advice.reason || "")}</p><p>${equity}</p>`;
  const board = (state.board || []).map((code) => cardHTML(code)).join("") || `<div class="card slot"></div>`;
  document.getElementById("dealer-table").innerHTML = `
    <p class="street">${escapeHTML(state.street_label)} · pot ${state.pot} · to call ${state.to_call}</p>
    <div class="board">${board}</div>
    ${(state.players || []).map((player, index) => `<div class="seat-row"><div><strong>${index === state.button ? "D " : ""}${escapeHTML(player.name)}</strong> ${player.hero && player.name.toLowerCase() !== "you" ? "· you" : ""} ${player.folded ? "· folded" : ""}<div class="cards">${player.hole.map((code) => cardHTML(code)).join("")}</div></div><div>${player.stack} · bet ${player.bet}</div></div>`).join("")}
    <ol class="log">${(state.log || []).map((line) => `<li>${escapeHTML(line)}</li>`).join("")}</ol>`;
  if (state.heard) document.getElementById("heard").textContent = state.heard;
}

async function dealerCommand(body) {
  if (localDealer) {
    const data = engineCall("dealer.command(__arg)", body);
    if (data.error) {
      toast(data.error);
      return;
    }
    dealerState = data;
    renderStation();
    return;
  }
  const response = await fetch(`/api/dealer/${dealerId}/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    toast(typeof data.detail === "string" ? data.detail : "I didn't catch that.");
    return;
  }
  dealerState = data;
  renderStation();
}

document.getElementById("command-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("command");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  dealerCommand({ text });
});
document.getElementById("new-hand").addEventListener("click", () => dealerCommand({ event: { type: "new_hand" } }));
document.getElementById("undo").addEventListener("click", () => dealerCommand({ event: { type: "undo" } }));
document.getElementById("clear-hole").addEventListener("click", () => dealerCommand({ event: { type: "clear_hole" } }));
document.getElementById("clear-board").addEventListener("click", () => dealerCommand({ event: { type: "clear_board" } }));
document.getElementById("pick-hero").addEventListener("click", () => dealerCommand({ event: { type: "add_card", card: pickedRank + pickedSuit, target: "hero" } }));
document.getElementById("pick-board").addEventListener("click", () => dealerCommand({ event: { type: "add_card", card: pickedRank + pickedSuit, target: "board" } }));

function buildPicker() {
  document.getElementById("ranks").innerHTML = RANKS.map((rank) => `<button type="button" data-rank="${rank}" class="${rank === pickedRank ? "on" : ""}">${rank === "T" ? "10" : rank}</button>`).join("");
  document.getElementById("suits").innerHTML = SUITS.map(([suit, symbol]) => `<button type="button" data-suit="${suit}" class="${suit === pickedSuit ? "on" : ""}">${symbol}</button>`).join("");
}
document.getElementById("ranks").addEventListener("click", (event) => {
  if (!event.target.dataset.rank) return;
  pickedRank = event.target.dataset.rank;
  buildPicker();
});
document.getElementById("suits").addEventListener("click", (event) => {
  if (!event.target.dataset.suit) return;
  pickedSuit = event.target.dataset.suit;
  buildPicker();
});

async function startCamera() {
  if (!navigator.mediaDevices) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    document.getElementById("cam").srcObject = stream;
  } catch {
    toast("The camera is blocked. You can still speak or tap cards.");
  }
}

document.getElementById("scan").addEventListener("click", async () => {
  if (localDealer) {
    toast("Card scanning needs the Python server. Type the card, or tap it below.");
    return;
  }
  const video = document.getElementById("cam");
  if (!video.videoWidth) {
    toast("The camera has no picture yet.");
    return;
  }
  const canvas = document.getElementById("snap");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  const body = new FormData();
  body.append("frame", blob, "card.jpg");
  const response = await fetch(`/api/dealer/${dealerId}/scan`, { method: "POST", body });
  const data = await response.json().catch(() => ({}));
  if (!data.ok) {
    toast(data.error || data.detail || "I couldn't read that card.");
    return;
  }
  pendingScan = data.card;
  document.getElementById("scan-name").textContent = data.name;
  document.getElementById("scan-confirm").hidden = false;
});
document.getElementById("scan-hero").addEventListener("click", () => confirmScan("hero"));
document.getElementById("scan-board").addEventListener("click", () => confirmScan("board"));
document.getElementById("scan-dismiss").addEventListener("click", () => {
  document.getElementById("scan-confirm").hidden = true;
});

function confirmScan(target) {
  if (!pendingScan) return;
  document.getElementById("scan-confirm").hidden = true;
  dealerCommand({ event: { type: "add_card", card: pendingScan, target } });
  pendingScan = null;
}

document.getElementById("mic").addEventListener("click", () => {
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Speech) {
    toast("Listening works in Chrome or Edge. You can type the action instead.");
    return;
  }
  if (listening && recognition) {
    listening = false;
    recognition.stop();
    document.getElementById("mic").textContent = "Listen";
    return;
  }
  recognition = new Speech();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";
  recognition.onresult = (event) => {
    let finalText = "";
    let interim = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const text = event.results[index][0].transcript;
      if (event.results[index].isFinal) finalText += text;
      else interim += text;
    }
    if (interim) document.getElementById("heard").textContent = interim;
    if (finalText.trim()) dealerCommand({ text: finalText.trim() });
  };
  recognition.onend = () => {
    if (listening) recognition.start();
  };
  recognition.start();
  listening = true;
  document.getElementById("mic").textContent = "Stop";
});

function escapeHTML(value) {
  return String(value).replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[char]));
}
function escapeAttr(value) {
  return escapeHTML(value).replace(/"/g, "&quot;");
}

document.addEventListener("keydown", (event) => {
  if (event.target.matches("input, textarea") || document.getElementById("table").hidden || !tableMessage) return;
  const legal = tableMessage.state.legal;
  if (!legal || tableMessage.state.actor_id !== tableMessage.you) return;
  const key = event.key.toLowerCase();
  if (key === "f" && !legal.check) send({ type: "action", action: "fold" });
  if (key === "c" && legal.check) send({ type: "action", action: "check" });
  if (key === "c" && legal.call) send({ type: "action", action: "call" });
});

const params = new URLSearchParams(location.search);
if (params.get("room")) {
  document.getElementById("join-code").value = params.get("room").toUpperCase();
  show("friends");
} else {
  const saved = sessionStorage.getItem("poker-project");
  if (saved) {
    hasBackend().then((ok) => {
      if (!ok) return;
      try {
        const { code, playerId } = JSON.parse(saved);
        connect(code, playerId);
      } catch {
        show("salon");
      }
    });
  }
}
renderModels();
renderDealerSetup();
