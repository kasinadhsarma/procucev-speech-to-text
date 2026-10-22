const $ = (s) => document.querySelector(s);
const api = "/api/transcriptions";
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------------------------------------------------------------- history / CRUD
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

let editing = null;
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
$("#form").onsubmit = async () => {
  const f = $("#form");
  const body = JSON.stringify({ title: f.title.value, language: f.language.value || "auto", text: f.text.value });
  await fetch(editing ? `${api}/${editing.id}` : api, {
    method: editing ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body,
  });
  load();
};
$("#list").onclick = async (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  const id = btn.closest(".item").dataset.id;
  if (btn.dataset.act === "del") {
    if (confirm("Delete this transcription?")) { await fetch(`${api}/${id}`, { method: "DELETE" }); load(); }
  } else openDialog(await (await fetch(`${api}/${id}`)).json());
};
let t; $("#search").oninput = () => { clearTimeout(t); t = setTimeout(load, 250); };

// ---------------------------------------------------------------- live recording
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

let ws, ctx, stream, node, recording = false, finals = [];
const setStatus = (s) => ($("#status").textContent = s);

function renderLive(partial = "") {
  $("#live").innerHTML = (finals.map((f) => esc(f)).join(" ") + (partial ? ` <span class="partial">${esc(partial)}</span>` : "")) ||
    '<span class="muted">Listening… start speaking.</span>';
}

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

function cleanup() {
  stream?.getTracks().forEach((t) => t.stop());
  node?.disconnect(); ctx?.close();
  stream = node = ctx = null;
}

function stop() {
  recording = false;
  $("#rec").textContent = "● Start recording"; $("#rec").classList.remove("rec");
  setStatus("Finishing transcription…");
  stream?.getTracks().forEach((t) => t.stop());
  if (ws?.readyState === 1) ws.send("stop");
}

$("#rec").onclick = () => (recording ? stop() : start());
load();
