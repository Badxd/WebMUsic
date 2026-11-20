// www/static/js/script.js
// This backend has no websocket server (raw-socket HTTP only, see
// Bad/net/httpserver.cpp) — so unlike the Python sibling projects,
// this polls /api/room every ~2s instead of holding a live socket
// open. Same experience, simpler/safer transport for this codebase.
// No speed control here on purpose — speed would be a group command,
// gated the same way every other transport control is.
// Chat/People/Profile are intentionally ephemeral: nothing here is
// written to a database, it all lives only as long as the room does.

const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const tgUser  = tg?.initDataUnsafe?.user;
const userId  = tgUser?.id || 0;
const myName  = tgUser?.first_name || "Guest";
const myUser  = tgUser?.username || "";
const myPhoto = tgUser?.photo_url || "";

function decodeChatId(enc) {
  if (!enc) return 0;
  if (enc.startsWith("N")) return -parseInt(enc.slice(1), 10);
  return parseInt(enc, 10);
}
const startParam = tg?.initDataUnsafe?.start_param || new URLSearchParams(location.search).get("startapp");
const chatId = decodeChatId(startParam || "");

const $ = (id) => document.getElementById(id);
const joinScreen = $("join-screen");
const workspace = $("workspace");
let isAdmin = false;
let localPlaying = false;
let progressTimer = null;
let pollTimer = null;
let roomStartedAt = 0;
let profileTimer = null;
let lastChatTs = 0;
let prevPeopleIds = new Set();
let firstPoll = true;

function showToast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.add("hidden"), 2200);
}

function fmtTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  const m = Math.floor(s / 60), sec = s % 60;
  return `${m}:${String(sec).padStart(2, "0")}`;
}
function avatarEl(person) {
  if (person.photo_url) {
    const img = document.createElement("img");
    img.src = person.photo_url;
    img.alt = "";
    img.className = "avatar-img";
    return img;
  }
  const span = document.createElement("span");
  span.className = "avatar-fallback";
  span.textContent = (person.name || "?").trim().charAt(0).toUpperCase() || "?";
  return span;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ── Tabs ─────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("hidden", p.dataset.tab !== btn.dataset.tab));
  });
});

// ── Join screen ──────────────────────────────────────────
function roomQuery() {
  return new URLSearchParams({ user_id: userId || 0, name: myName, username: myUser, photo: myPhoto });
}

async function loadJoinInfo() {
  if (!chatId) {
    $("join-chat-name").textContent = "Invalid room link";
    $("join-sub").textContent = "Open this from a song card in your group.";
    return;
  }
  try {
    const res = await fetch(`/api/room/${chatId}?${roomQuery()}`);
    const data = await res.json();
    $("join-chat-name").textContent = data.chat_name || "Room";
    $("join-sub").textContent = data.active
      ? `🎵 ${data.song?.title || "Something"} is playing now`
      : "Nothing playing right now";
    $("join-btn").disabled = false;
  } catch (e) {
    $("join-chat-name").textContent = "Room";
    $("join-sub").textContent = "Could not reach the server — try again.";
  }
}

$("join-btn").addEventListener("click", () => {
  joinScreen.classList.add("hidden");
  workspace.classList.remove("hidden");
  document.body.dataset.view = "room";
  workspace.focus();
  roomStartedAt = Date.now();
  $("profile-room").textContent = $("join-chat-name").textContent;
  profileTimer = setInterval(() => {
    $("profile-time").textContent = fmtTime((Date.now() - roomStartedAt) / 1000);
  }, 1000);
  renderProfileIdentity();
  startPolling();
});

function renderProfileIdentity() {
  $("profile-name").textContent = myName;
  $("profile-username").textContent = myUser ? `@${myUser}` : "";
  const av = $("profile-avatar");
  av.innerHTML = "";
  if (myPhoto) {
    av.appendChild(avatarEl({ photo_url: myPhoto, name: myName }));
  } else {
    av.textContent = myName.charAt(0).toUpperCase() || "🙂";
  }
}

function setConnection(state) {
  const dot = $("connection-dot");
  const label = $("connection-label");
  dot.dataset.state = state;
  label.textContent = state === "live" ? "Live" : state === "connecting" ? "Connecting…" : "Reconnecting…";
}

function startPolling() {
  setConnection("connecting");
  const poll = async () => {
    try {
      const res = await fetch(`/api/room/${chatId}?${roomQuery()}`);
      if (!res.ok) throw new Error("bad status");
      const data = await res.json();
      setConnection("live");
      render(data);
    } catch (e) {
      setConnection("offline");
    }
  };
  poll();
  pollTimer = setInterval(poll, 2000);
}

// ── Player + People + Chat (one combined poll response) ───
function render(data) {
  $("chat-name").textContent = data.chat_name || "Room";
  $("listener-count").textContent = data.listeners ?? 0;

  isAdmin = !!data.is_admin;
  $("controls").hidden = !isAdmin;
  $("listener-note").hidden = isAdmin;

  if (!data.active || !data.song) {
    $("song-title").textContent = "Nothing playing";
    $("song-by").textContent = "Use /play in the group to start";
    $("art").textContent = "🎵";
    $("art").style.backgroundImage = "none";
    $("progress-fill").style.width = "0%";
    $("time-cur").textContent = "0:00";
    $("time-dur").textContent = "0:00";
    stopProgressTimer();
  } else {
    const song = data.song;
    $("song-title").textContent = song.title;
    $("song-by").textContent = song.requested_by ? `Requested by ${song.requested_by}` : "";
    $("time-dur").textContent = fmtTime(song.duration_sec);
    if (song.thumbnail) {
      $("art").style.backgroundImage = `url(${song.thumbnail})`;
      $("art").style.backgroundSize = "cover";
      $("art").textContent = "";
    }
    localPlaying = song.playing;
    $("btn-playpause").textContent = localPlaying ? "⏸" : "▶";
    startProgressTimer(song.seek, song.duration_sec, song.playing);
  }

  renderQueue(data.queue || []);
  renderPeople(data.listener_people || []);
  renderNewChat(data.chat_log || []);
  firstPoll = false;
}

function renderQueue(queue) {
  const el = $("queue-preview");
  if (!queue.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<h4 class="section-title">Up next</h4>` + queue.slice(0, 5).map(
    (q) => `<div class="queue-item"><span class="q-title">${escapeHtml(q.title)}</span><span class="q-dur muted">${escapeHtml(q.duration || "")}</span></div>`
  ).join("");
}

function renderPeople(people) {
  const ids = new Set(people.map((p) => p.user_id));
  if (!firstPoll) {
    for (const p of people) {
      if (p.user_id !== userId && !prevPeopleIds.has(p.user_id)) showToast(`${p.name} joined 👋`);
    }
    for (const id of prevPeopleIds) {
      if (id !== userId && !ids.has(id)) showToast("Someone left");
    }
  }
  prevPeopleIds = ids;

  const el = $("people-list");
  el.innerHTML = "";
  if (!people.length) {
    el.innerHTML = `<li class="muted empty-note">Nobody's joined with their Telegram account yet.</li>`;
    return;
  }
  people.forEach((p) => {
    const li = document.createElement("li");
    li.className = "people-item";
    const av = document.createElement("div");
    av.className = "avatar";
    av.appendChild(avatarEl(p));
    const name = document.createElement("span");
    name.textContent = p.username ? `${p.name} · @${p.username}` : p.name;
    li.append(av, name);
    el.appendChild(li);
  });
}

function startProgressTimer(seek, duration, playing) {
  stopProgressTimer();
  const started = Date.now();
  progressTimer = setInterval(() => {
    const elapsed = playing ? (Date.now() - started) / 1000 : 0;
    const cur = Math.min(seek + elapsed, duration || seek + elapsed);
    $("time-cur").textContent = fmtTime(cur);
    $("progress-fill").style.width = duration ? `${Math.min(100, (cur / duration) * 100)}%` : "0%";
  }, 500);
}
function stopProgressTimer() { if (progressTimer) clearInterval(progressTimer); }

async function sendControl(action) {
  if (!chatId || !userId) return;
  try {
    const res = await fetch(`/api/control/${chatId}?action=${action}&user_id=${userId}`, { method: "POST" });
    const data = await res.json();
    if (!data.ok) showToast(data.error === "not_admin" ? "Admins only" : "Action failed");
  } catch (e) {
    showToast("Network error");
  }
}
$("btn-playpause").addEventListener("click", () => sendControl(localPlaying ? "pause" : "resume"));
$("btn-skip").addEventListener("click", () => sendControl("skip"));

// ── Chat (polled as part of /api/room, deduped by timestamp) ──
function renderNewChat(log) {
  const fresh = log.filter((m) => m.ts > lastChatTs);
  if (fresh.length) lastChatTs = fresh[fresh.length - 1].ts;
  fresh.forEach(appendChatMessage);
}
function appendChatMessage(msg) {
  const log = $("chat-log");
  const li = document.createElement("li");
  li.className = "chat-bubble" + (msg.person?.user_id === userId ? " mine" : "");
  const av = document.createElement("div");
  av.className = "avatar avatar-sm";
  av.appendChild(avatarEl(msg.person || {}));
  const body = document.createElement("div");
  body.className = "chat-body";
  body.innerHTML = `<span class="chat-name">${escapeHtml(msg.person?.name || "Someone")}</span><p>${escapeHtml(msg.text)}</p>`;
  li.append(av, body);
  log.appendChild(li);
  log.scrollTop = log.scrollHeight;
}
$("chat-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text) return;
  if (!userId) { showToast("Open this from Telegram to chat"); return; }
  input.value = "";
  try {
    await fetch(`/api/chat/${chatId}?${roomQuery()}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } catch (e) {
    showToast("Could not send — try again");
  }
});

loadJoinInfo();
