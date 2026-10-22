/** Shorthand for `document.querySelector`. */
const $ = (s) => document.querySelector(s);
/** Base path of the REST API. */
const api = "/api/transcriptions";
/** Escape `& < > "` so user text can be inserted into HTML safely. */
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------------------------------------------------------------- history / CRUD
/** Fetch transcriptions (filtered by the search box) and render the history list. */
async function load() {
  const q = $("#search").value.trim();
  const res = await fetch(api + (q ? `?q=${encodeURIComponent(q)}` : ""));
  const rows = await res.json();
  $("#list").innerHTML = rows.length
    ? rows.map((r) => `
      <div class="item" data-id="${r.id}">
        <h4>${esc(r.title)}</h4>
        <p>${esc(r.text) || '<span class="muted">(empty)</span>'}</p>
        <div class="meta">${new Date(r.created_at).toLocaleString()} · ${esc(r.language)} · ${r.duration_sec}s</div>
        <div class="actions"><button data-act="edit">Edit</button><button data-act="del" class="danger">Delete</button></div>
      </div>`).join("")
    : '<p class="muted">No transcriptions yet. Record one above!</p>';
}

/** Row being edited in the dialog, or `null` when creating a new one. */
let editing = null;
/**
 * Open the create/edit dialog.
 * @param {object|null} row Transcription to edit, or `null` for a new one.
 */
function openDialog(row) {
  editing = row;
  $("#dlgTitle").textContent = row ? "Edit transcription" : "New transcription";
  const f = $("#form");
  f.title.value = row?.title ?? "";
  f.language.value = row?.language ?? "auto";
  f.text.value = row?.text ?? "";
  $("#dlg").showModal();
}
$("#new").onclick = () => openDialog(null);
$("#cancel").onclick = () => $("#dlg").close();
// Save the dialog: PUT when editing, POST when creating, then reload the list.
$("#form").onsubmit = async () => {
  const f = $("#form");
  const body = JSON.stringify({ title: f.title.value, language: f.language.value || "auto", text: f.text.value });
  await fetch(editing ? `${api}/${editing.id}` : api, {
    method: editing ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body,
  });
  load();
};
// Event delegation for each row's Edit and Delete buttons.
$("#list").onclick = async (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  const id = btn.closest(".item").dataset.id;
  if (btn.dataset.act === "del") {
    if (confirm("Delete this transcription?")) { await fetch(`${api}/${id}`, { method: "DELETE" }); load(); }
  } else openDialog(await (await fetch(`${api}/${id}`)).json());
};
// Debounced search: reload 250 ms after the user stops typing.
let t; $("#search").oninput = () => { clearTimeout(t); t = setTimeout(load, 250); };

// ---------------------------------------------------------------- live recording
/**
 * AudioWorklet processor source. Runs on the audio thread, converts each 128-sample Float32
 * block to Int16 PCM and posts the buffer to the main thread (transferred, not copied).
 */
const workletSrc = `
class PCM extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0][0];
    if (ch) {
      const out = new Int16Array(ch.length);
      for (let i = 0; i < ch.length; i++) out[i] = Math.max(-1, Math.min(1, ch[i])) * 32767;
      this.port.postMessage(out.buffer, [out.buffer]);
    }
    return true;
  }
}
registerProcessor('pcm', PCM);`;

/*
 * Recording state:
 *   ws        WebSocket to /ws/transcribe
 *   ctx       AudioContext running at 16 kHz
 *   stream    MediaStream from the microphone
 *   node      AudioWorkletNode producing PCM
 *   recording true while capturing audio
 *   finals    final text segments received this session
 */
let ws, ctx, stream, node, recording = false, finals = [];
/** Show a short status message next to the record button. */
const setStatus = (s) => ($("#status").textContent = s);

/**
 * Render the live transcript: final segments in normal text, then the partial one in grey.
 * @param {string} [partial] Latest provisional text.
 */
function renderLive(partial = "") {
  $("#live").innerHTML = (finals.map((f) => esc(f)).join(" ") + (partial ? ` <span class="partial">${esc(partial)}</span>` : "")) ||
    '<span class="muted">Listening… start speaking.</span>';
}

/**
 * Start a session: ask for the microphone, open the WebSocket, then start streaming PCM from
 * an AudioWorklet. Incoming messages update the live view; `saved` refreshes the history.
 */
async function start() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  } catch { return setStatus("Microphone permission denied"); }
  finals = []; renderLive();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/transcribe?language=${$("#lang").value}`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === "partial") renderLive(m.text);
    else if (m.type === "final") { finals.push(m.text); renderLive(); }
    else if (m.type === "saved") { setStatus(m.transcription ? "Saved ✔" : "Nothing recognised"); load(); cleanup(); }
    else if (m.type === "error") setStatus("Error: " + m.message);
  };
  ws.onclose = () => { if (recording) stop(); };
  await new Promise((r) => (ws.onopen = r));

  ctx = new AudioContext({ sampleRate: 16000 });
  await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([workletSrc], { type: "application/javascript" })));
  node = new AudioWorkletNode(ctx, "pcm");
  node.port.onmessage = (e) => ws.readyState === 1 && ws.send(e.data);
  ctx.createMediaStreamSource(stream).connect(node);
  recording = true;
  $("#rec").textContent = "■ Stop & save"; $("#rec").classList.add("rec");
  setStatus("Recording…");
}

/** Release the microphone and audio graph. */
function cleanup() {
  stream?.getTracks().forEach((t) => t.stop());
  node?.disconnect(); ctx?.close();
  stream = node = ctx = null;
}

/** Stop capturing and send "stop" so the server flushes and saves the transcript. */
function stop() {
  recording = false;
  $("#rec").textContent = "● Start recording"; $("#rec").classList.remove("rec");
  setStatus("Finishing transcription…");
  stream?.getTracks().forEach((t) => t.stop());
  if (ws?.readyState === 1) ws.send("stop");
}

$("#rec").onclick = () => (recording ? stop() : start());
load();
