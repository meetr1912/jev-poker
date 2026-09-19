const SUITS = { s: "♠", h: "♥", d: "♦", c: "♣" };
const RED = new Set(["h", "d"]);

function card(face) {
  const el = document.createElement("div");
  el.className = "card";
  if (face === "??" || face == null) {
    el.classList.add("back");
    el.textContent = "?";
    return el;
  }
  if (RED.has(face[1])) el.classList.add("red");
  el.innerHTML = `<span>${face[0]}</span><span class="suit">${SUITS[face[1]] || ""}</span>`;
  return el;
}

function renderCards(node, faces) {
  node.replaceChildren(...(faces || []).map(card));
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function renderDecision(decision) {
  const bars = document.getElementById("bars");
  setText("brain-model", decision.model || "–");
  setText("confidence", decision.confidence == null ? "–" : `${Math.round(decision.confidence * 100)}%`);
  setText("latency", decision.latency_ms ? `${decision.latency_ms} ms` : "–");
  setText("brain-street", (decision.view && decision.view.street) || "–");

  const summary = document.getElementById("brain-summary");
  summary.textContent = decision.summary || "–";
  if (decision.fallback) {
    const warn = document.createElement("div");
    warn.className = "fallback";
    warn.textContent = "⚠ fallback action (Jev API unavailable)";
    summary.appendChild(warn);
  }
  const probs = Object.entries(decision.probabilities || {}).sort((a, b) => b[1] - a[1]);
  bars.replaceChildren(
    ...probs.map(([name, p]) => {
      const row = document.createElement("div");
      row.className = "bar-row" + (name === decision.choice ? " chosen" : "");
      row.innerHTML = `
        <span class="label">${name}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${(p * 100).toFixed(1)}%"></span></span>
        <span class="pct">${(p * 100).toFixed(0)}%</span>`;
      return row;
    })
  );
}

function renderLog(entries) {
  const log = document.getElementById("log");
  log.replaceChildren(
    ...entries.map((entry) => {
      const li = document.createElement("li");
      li.className = `${entry.kind}${entry.actor != null ? " actor-" + entry.actor : ""}`;
      li.textContent = entry.text;
      return li;
    })
  );
}

function describe(state) {
  if (state.running) {
    if (state.actor === 0) return "Jev is deciding…";
    if (state.actor === 1) return "HouseBot is deciding…";
    return `${state.street} · dealing…`;
  }
  if (state.finished) return "Match complete.";
  return "Press “Run match”.";
}

async function poll() {
  let state;
  try {
    state = await (await fetch("/api/state")).json();
  } catch {
    return;
  }
  setText("hand", state.hand_no ? `hand ${state.hand_no}/${state.total_hands}` : "hand –");
  setText("street", state.street || "–");
  const a = state.player_a || "Jev";
  const scores = state.score || {};
  setText("score", `${a} ${scores[a] ?? 0} · Bot ${scores["HouseBot"] ?? 0}`);
  setText("pot", `$${state.pot ?? 0}`);
  setText("jev-stack", `$${state.stacks[0]}`);
  setText("bot-stack", `$${state.stacks[1]}`);
  setText("status", describe(state));
  renderCards(document.getElementById("board"), state.board);
  renderCards(document.getElementById("jev-cards"), state.jev_cards);
  renderCards(document.getElementById("bot-cards"), state.bot_cards);
  if (state.decision) renderDecision(state.decision);
  renderLog(state.log || []);
  document.getElementById("start").disabled = state.running;
  document.getElementById("stop").disabled = !state.running;
}

document.getElementById("start").addEventListener("click", () => fetch("/api/start", { method: "POST" }));
document.getElementById("stop").addEventListener("click", () => fetch("/api/stop", { method: "POST" }));
poll();
setInterval(poll, 600);
