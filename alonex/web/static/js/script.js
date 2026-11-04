// alonex/web/static/js/script.js
// Clean, minimal room client. No speed control here on purpose —
// speed is a group /speed command only (see alonex/plugins/speed.py),
// never a website control.

const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const tgUser = tg?.initDataUnsafe?.user;
const userId = tgUser?.id || 0;
const username = tgUser?.username || tgUser?.first_name || "Guest";

// ── chat_id comes from the clean short startapp param: just the
// chat_id (e.g. "N1003247919384"), nothing else encoded in it.
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
let socket = null;
let isAdmin = false;
let localPlaying = false;
let progressTimer = null;
let lastState = null;

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

// ── Join screen: fetch the room once (REST) just to show the real
// group name immediately — like Playeon does — before the socket
// even connects.
async function loadJoinInfo() {
  if (!chatId) {
    $("join-chat-name").textContent = "Invalid room link";
    $("join-sub").textContent = "Open this from a song card in your group.";
    return;
  }
  try {
    const res = await fetch(`/api/room/${chatId}`);
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
  workspace.focus(); // skip-link target — moves focus in for keyboard/screen-reader users
  connect();
});

function setConnection(state) {
  // state: "connecting" | "live" | "offline"
  const dot = $("connection-dot");
  const label = $("connection-label");
  dot.dataset.state = state;
  label.textContent = state === "live" ? "Live" : state === "connecting" ? "Connecting…" : "Reconnecting…";
}

function connect() {
  setConnection("connecting");
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws/${chatId}/${userId || 0}`);
  socket.onopen = () => setConnection("live");
  socket.onmessage = (ev) => render(JSON.parse(ev.data));
  socket.onclose = () => { setConnection("offline"); setTimeout(connect, 2500); };
  socket.onerror = () => socket.close();

  // keep-alive ping every 20s so the socket doesn't idle out
  setInterval(() => {
    if (socket?.readyState === WebSocket.OPEN) socket.send("ping");
  }, 20000);
}

function render(data) {
  lastState = data;
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
    return;
  }

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

function startProgressTimer(seek, duration, playing) {
  stopProgressTimer();
  let pos = seek;
  const started = Date.now();
  progressTimer = setInterval(() => {
    const elapsed = playing ? (Date.now() - started) / 1000 : 0;
    const cur = Math.min(seek + elapsed, duration || seek + elapsed);
    $("time-cur").textContent = fmtTime(cur);
    $("progress-fill").style.width = duration ? `${Math.min(100, (cur / duration) * 100)}%` : "0%";
  }, 500);
}
function stopProgressTimer() {
  if (progressTimer) clearInterval(progressTimer);
}

// ── Admin controls — POST to the same admin-gated endpoint the
// Telegram inline buttons ultimately call into.
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

loadJoinInfo();
