// ============================================================
//  servidor_voz_airi.js  (v3.6 — DUAS ENGINES: Edge + Kokoro offline + proxy cerebro)
//  Ponte de voz local compatível com OpenAI — para o Project AIRI usar.
//
//  Engines:
//    edge   -> vozes Microsoft Edge (online, pitch ajustável)
//    kokoro -> Kokoro TTS v1.0 (OFFLINE, via kokoro-onnx; reaproveita o
//              venv/modelo baixados pelo botao "Instalar Kokoro" na interface)
//
//  Formato do campo Voice (entendido pelo servidor):
//    "pt-BR-ThalitaNeural:+30"      -> Edge, pitch +30Hz
//    "pt-BR-ThalitaNeural:+30@1.1"  -> Edge, pitch +30Hz e velocidade 1.1x
//    "kokoro:pf_dora@1.05"          -> Kokoro, voz pf_dora, 1.05x
//    (sem prefixo = Edge, retrocompatível)
//
//  Endpoints:
//    GET  /                    -> INTERFACE de configuração de voz
//    POST /v1/audio/speech     -> gera áudio (OpenAI-compatible)
//    GET  /v1/models           -> lista os modelos "edge-tts" e "kokoro"
//    GET  /v1/audio/voices     -> vozes recomendadas (Edge)
//    GET  /v1/audio/voices/all -> catálogo completo do Edge
//    GET  /config              -> padrão salvo (engine/voz/pitch/velocidade)
//    POST /config              -> salva padrão (botão 💾 da interface)
//    POST /kokoro/install      -> instala o Kokoro sozinho (venv+deps+modelos)
//    GET  /kokoro/status       -> progresso da instalação
//    GET  /health              -> verificação (inclui kokoro disponível?)
//    POST /v1/chat/completions -> resposta fake (validação do Airi)
//
//  Kokoro offline (opcional): botão "🦉 Instalar Kokoro" na interface faz
//  TUDO sozinho (cria venv, instala dependências, baixa ~360 MB dos modelos
//  uma única vez). Guarda tudo em kokoro-data/ ao lado deste arquivo, ou na
//  pasta KOKORO_DIR se definida. Requisito: Python instalado no PC.
//
//  Uso:
//    npm install msedge-tts
//    node servidor_voz_airi.js
//    -> abra http://localhost:9860/ no navegador para escolher a voz
// ============================================================
const http = require('http');
const https = require('https');
const os = require('os');
const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

// Procurar node_modules na pasta atual ou na pasta pai (quando o script esta em scripts/)
const _modulePaths = [__dirname, path.join(__dirname, '..')];
for (const _mp of _modulePaths) {
  const _nm = path.join(_mp, 'node_modules');
  if (fs.existsSync(_nm)) { require('module').globalPaths.push(_nm); break; }
}
const { MsEdgeTTS, OUTPUT_FORMAT } = require('msedge-tts');

const PORT = process.env.PORT || 9860;
const VERSION = '3.8';
const SOVITS_PORT = process.env.SOVITS_PORT || 9880;

// Vozes recomendadas (o servidor aceita QUALQUER voz que o Edge suporte)
const VOICES = [
  { id: 'pt-BR-ThalitaNeural',   name: 'Thalita',   desc: 'Jovem e fofa (recomendada!)', emoji: '🌸', gender: 'female', locale: 'pt-BR' },
  { id: 'pt-BR-GiovannaNeural',  name: 'Giovanna',  desc: 'Jovem-adulta, timbre brilhante', emoji: '🌟', gender: 'female', locale: 'pt-BR' },
  { id: 'pt-BR-BrendaNeural',    name: 'Brenda',    desc: 'Feminina jovem',              emoji: '✨', gender: 'female', locale: 'pt-BR' },
  { id: 'pt-BR-FranciscaNeural', name: 'Francisca', desc: 'Feminina clássica',           emoji: '🎩', gender: 'female', locale: 'pt-BR' },
  { id: 'pt-BR-AntonioNeural',   name: 'Antônio',   desc: 'Masculina clássica',          emoji: '🎙️', gender: 'male',   locale: 'pt-BR' },
  { id: 'pt-BR-DonatoNeural',    name: 'Donato',    desc: 'Masculina jovem',             emoji: '🎧', gender: 'male',   locale: 'pt-BR' },
  { id: 'ja-JP-NanamiNeural',    name: 'Nanami',    desc: 'Japonesa (sotaque anime!)',   emoji: '🇯🇵', gender: 'female', locale: 'ja-JP' },
  { id: 'ja-JP-AoiNeural',       name: 'Aoi',       desc: 'Japonesa jovem',              emoji: '🇯🇵', gender: 'female', locale: 'ja-JP' },
  { id: 'en-US-AriaNeural',      name: 'Aria',      desc: 'Inglesa (EUA)',               emoji: '🇺🇸', gender: 'female', locale: 'en-US' },
];

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

// Configuração persistente (voz padrão do launcher) — salva ao lado do script
// Pasta raiz do repo (um nivel acima se o script esta em scripts/)
const REPO_ROOT = fs.existsSync(path.join(__dirname, 'package.json')) ? __dirname : path.join(__dirname, '..');
const CONFIG_FILE = path.join(REPO_ROOT, 'voz_config.json');
function readConfig() {
  try { return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8')); } catch (e) { return null; }
}
function composeVoiceString(cfg) {
  if (!cfg || !cfg.voice) return null;
  let s = String(cfg.voice);
  if (cfg.engine === 'kokoro') {
    if (s.slice(0, 7).toLowerCase() !== 'kokoro:') s = 'kokoro:' + s;
  }
  const p = Number(cfg.pitch);
  if (cfg.pitch !== undefined && cfg.pitch !== null && cfg.pitch !== '' && !Number.isNaN(p) && p !== 0) {
    s += (p > 0 ? ':+' : ':') + p;
  }
  const sp = Number(cfg.speed);
  if (cfg.speed !== undefined && cfg.speed !== null && cfg.speed !== '' && !Number.isNaN(sp) && sp && sp !== 1) {
    s += '@' + sp.toFixed(2);
  }
  return s;
}

// ================= ENGINE KOKORO (offline, opcional) =================
// Instalacao automatica pelo botao da interface (POST /kokoro/install):
// guarda venv + modelos em KOKORO_DATA (kokoro-data/ ao lado deste arquivo).
// Guarda tudo em kokoro-data/ ao lado deste arquivo.
const KOKORO_VOICES = [
  { id: 'pf_dora',  name: 'Dora',  desc: 'Feminina pt-BR (a do teste)', emoji: '🌸', locale: 'pt-br' },
  { id: 'pm_santa', name: 'Santa', desc: 'Feminina pt-BR 2',            emoji: '✨', locale: 'pt-br' },
  { id: 'pm_alex',  name: 'Alex',  desc: 'Masculina pt-BR',             emoji: '🎧', locale: 'pt-br' },
];

// Onde mora o kokoro "oficial" do servidor (botao Instalar da interface)
const KOKORO_DATA = process.env.KOKORO_DIR || path.join(REPO_ROOT, 'kokoro-data');
const KOKORO_DL_BASE = process.env.KOKORO_URL_BASE
  || 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1';

function pyExe(venvDir) {
  const cands = (process.platform === 'win32')
    ? [path.join(venvDir, 'Scripts', 'python.exe')]
    : [path.join(venvDir, 'bin', 'python3'), path.join(venvDir, 'bin', 'python')];
  for (const c of cands) if (fs.existsSync(c)) return c;
  return null;
}

function findModelPair(dir, depth) {
  // acha kokoro-v1.0.onnx + voices-v1.0.bin em dir (ou 1 nivel abaixo)
  try {
    const onnx = path.join(dir, 'kokoro-v1.0.onnx');
    const voices = path.join(dir, 'voices-v1.0.bin');
    if (fs.existsSync(onnx) && fs.existsSync(voices)) return { onnx, voices };
    if (depth > 0) {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (!e.isDirectory()) continue;
        const r = findModelPair(path.join(dir, e.name), depth - 1);
        if (r) return r;
      }
    }
  } catch (e) { /* sem permissao etc. */ }
  return null;
}

function findVenvPython(dir) {
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    const dirs = entries.filter(e => e.isDirectory()).map(e => e.name);
    const venvs = dirs.filter(n => /^venv/i.test(n)).sort().reverse();
    for (const v of venvs) {
      const py = pyExe(path.join(dir, v));
      if (py) return py;
    }
    for (const d of dirs) {  // pastas sem nome "venv" tambem valem
      const py = pyExe(path.join(dir, d));
      if (py) return py;
    }
  } catch (e) { /* sem permissao etc. */ }
  return null;
}

let KOKORO_CHECKED = [];
function detectKokoro() {
  // Procurar kokoro apenas na pasta do kit (kokoro-data/ ao lado deste arquivo)
  const cands = [...new Set([KOKORO_DATA, process.env.KOKORO_DIR].filter(Boolean))];
  const checked = [];
  for (const dir of cands) {
    if (!fs.existsSync(dir)) { checked.push(dir + '  [pasta nao existe]'); continue; }
    const models = findModelPair(dir, 1);
    if (!models) { checked.push(dir + '  [pasta existe, mas sem kokoro-v1.0.onnx + voices-v1.0.bin]'); continue; }
    const modelDir = path.dirname(models.onnx);
    const py = findVenvPython(modelDir);
    if (!py) { checked.push(modelDir + '  [modelo achado, mas sem venv\\Scripts\\python.exe]'); continue; }
    checked.push(modelDir + '  [OK]');
    KOKORO_CHECKED = checked;
    return { dir: modelDir, onnx: models.onnx, voices: models.voices, py };
  }
  KOKORO_CHECKED = checked;
  return null;
}
let KOKORO = detectKokoro();
if (KOKORO) console.log('[kokoro] engine OFFLINE detectada em: ' + KOKORO.dir + ' (python: ' + KOKORO.py + ')');
else {
  console.log('[kokoro] NAO encontrado. Procurei nos lugares abaixo:');
  KOKORO_CHECKED.forEach(c => console.log('   - ' + c));
  console.log('[kokoro] -> clique em "Instalar Kokoro" na interface (http://localhost:' + PORT + '/) que eu instalo tudo sozinho');
}

// Worker python persistente (o modelo carrega 1x; pedidos via NDJSON no stdin)
let _kokoroProc = null;
let _kokoroSeq = 0;
const _kokoroPending = new Map(); // id -> {resolve, reject, timer}

const KOKORO_WORKER_PY = `
import sys, json, os
onnx_path, voices_path = sys.argv[1], sys.argv[2]
try:
    from espeakng_loader import get_library_path, get_data_path
    os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = get_library_path()
    os.environ["ESPEAK_DATA_PATH"] = get_data_path()
except Exception as e:
    print(json.dumps({"event": "warn", "msg": str(e)}), flush=True)

import numpy as np
from kokoro_onnx import Kokoro
import soundfile as sf

# [FIX WINDOWS] numpy int32: converge TODO input pro dtype declarado pelo modelo
_ONNX2NP = {"tensor(float)": np.float32, "tensor(double)": np.float64,
            "tensor(int64)": np.int64, "tensor(int32)": np.int32,
            "tensor(int16)": np.int16, "tensor(int8)": np.int8,
            "tensor(uint8)": np.uint8, "tensor(uint16)": np.uint16,
            "tensor(uint32)": np.uint32, "tensor(uint64)": np.uint64,
            "tensor(bool)": np.bool_}

class _SessProxy:
    def __init__(self, sess):
        self._sess = sess
        self._declared = {i.name: i.type for i in sess.get_inputs()}
        self._orig_run = sess.run
    def _npd(self, t):
        if t in _ONNX2NP:
            return np.dtype(_ONNX2NP[t])
        return np.dtype(str(t).replace("tensor(", "").rstrip(")"))
    def run(self, output_names, input_feed, *a, **k):
        fixed = {}
        for name, arr in input_feed.items():
            want = self._declared.get(name)
            if want is not None:
                wt = self._npd(want)
                if isinstance(arr, np.ndarray):
                    if arr.dtype != wt:
                        arr = arr.astype(wt)
                else:
                    arr = np.asarray(arr, dtype=wt)
            fixed[name] = arr
        return self._orig_run(output_names, fixed, *a, **k)
    def __getattr__(self, name):
        return getattr(self._sess, name)

kokoro = Kokoro(onnx_path, voices_path)
kokoro.sess = _SessProxy(kokoro.sess)
print(json.dumps({"event": "ready"}), flush=True)

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    rid, req = None, {}
    try:
        req = json.loads(line)
        rid = req.get("id")
        speed = float(req.get("speed", 1.0))
        pitch = float(req.get("pitch", 1.0))  # razao: >1 = mais agudo
        if pitch and pitch != 1.0:
            speed = max(0.5, min(2.0, speed / pitch))
        samples, sr = kokoro.create(
            req["text"],
            voice=req.get("voice", "pf_dora"),
            speed=speed,
            lang=req.get("lang", "pt-br"),
        )
        if pitch and pitch != 1.0:
            n = len(samples)
            idx = np.arange(0.0, n, pitch)
            samples = np.interp(idx, np.arange(n), samples).astype(np.float32)
        sf.write(req["out"], samples, sr)
        print(json.dumps({"event": "ok", "id": rid, "file": req["out"]}), flush=True)
    except Exception as e:
        try:
            print(json.dumps({"event": "error", "id": rid, "msg": str(e)}), flush=True)
        except Exception:
            pass
`;

function kokoroEnsureWorker() {
  if (!KOKORO) throw new Error('Kokoro nao esta disponivel: clique em "Instalar Kokoro" na interface (http://localhost:9860/) para instalar automaticamente.');
  if (_kokoroProc && !_kokoroProc.killed && _kokoroProc.exitCode === null) return _kokoroProc;

  const workerPath = path.join(KOKORO.dir, 'kokoro_worker_airi.py');
  fs.writeFileSync(workerPath, KOKORO_WORKER_PY, 'utf8');
  _kokoroProc = spawn(KOKORO.py, ['-X', 'utf8', '-u', workerPath, KOKORO.onnx, KOKORO.voices],
    { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
  console.log('[kokoro] worker iniciado (pid ' + _kokoroProc.pid + ') - carregando modelo...');

  let buf = '';
  _kokoroProc.stdout.on('data', (chunk) => {
    buf += chunk.toString('utf8');
    let idx;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      let msg = null;
      try { msg = JSON.parse(line); } catch (e) { console.log('[kokoro] (worker)', line.slice(0, 200)); continue; }
      if (msg.event === 'ready') { console.log('[kokoro] modelo carregado, pronto.'); continue; }
      if (msg.event === 'warn') { console.log('[kokoro] aviso:', msg.msg); continue; }
      if (msg.id != null && _kokoroPending.has(msg.id)) {
        const p = _kokoroPending.get(msg.id);
        _kokoroPending.delete(msg.id);
        clearTimeout(p.timer);
        if (msg.event === 'ok') p.resolve(msg.file);
        else p.reject(new Error(msg.msg || 'erro desconhecido no kokoro'));
      }
    }
  });
  _kokoroProc.stderr.on('data', (c) => {
    const s = c.toString().trim();
    if (s) console.log('[kokoro] stderr:', s.slice(0, 300));
  });
  _kokoroProc.on('exit', (code) => {
    console.log('[kokoro] worker saiu (code ' + code + ') - sera reiniciado sob demanda');
    for (const [id, p] of _kokoroPending) {
      clearTimeout(p.timer);
      p.reject(new Error('worker do kokoro morreu no meio da geracao'));
    }
    _kokoroPending.clear();
    _kokoroProc = null;
  });
  return _kokoroProc;
}

function kokoroGenerate(text, voice, speed, pitchRatio) {
  const proc = kokoroEnsureWorker();
  const id = 'k' + (++_kokoroSeq) + '_' + Date.now();
  const out = path.join(os.tmpdir(), 'kokoro_' + id + '.wav');
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      _kokoroPending.delete(id);
      reject(new Error('kokoro demorou demais (timeout 180s)'));
    }, 180000);
    _kokoroPending.set(id, { resolve, reject, timer });
    proc.stdin.write(JSON.stringify({ id, text, voice, speed, pitch: pitchRatio || 1, out }) + '\n');
  });
}

function sendWavFile(res, file) {
  let data;
  try { data = fs.readFileSync(file); } catch (e) {
    return sendJson(res, 500, { error: { message: 'kokoro nao gravou o audio: ' + e.message } });
  }
  setTimeout(() => { try { fs.unlinkSync(file); } catch (e) {} }, 15000);
  res.writeHead(200, { 'Content-Type': 'audio/wav', 'Content-Length': data.length, 'Cache-Control': 'no-cache', ...CORS });
  res.end(data);
}

// ---- Proxy do cerebro (AgentAI no Colab): URL fixa local -> tunel atual ----
// O Airi (principalmente o app desktop) aponta pra http://localhost:9860/cerebro/v1
// UMA vez; aqui repassa pro tunel atual lendo api_url.txt (Drive) / ultima_url.txt
// a CADA pedido - quando o tunel muda, nada precisa ser reconfigurado.
const CEREBRO_URL_FILES = [...new Set([
  process.env.CEREBRO_URL_FILE,
  'G:\\Meu Drive\\AgentAI\\memory\\api_url.txt',
  'G:\\My Drive\\AgentAI\\memory\\api_url.txt',
  'H:\\Meu Drive\\AgentAI\\memory\\api_url.txt',
  'H:\\My Drive\\AgentAI\\memory\\api_url.txt',
  path.join(REPO_ROOT, 'ultima_url.txt'),
  path.join(os.homedir(), 'voz-bridge', 'ultima_url.txt'),
].filter(Boolean))];

function readTunnelUrl() {
  for (const f of CEREBRO_URL_FILES) {
    try {
      if (!fs.existsSync(f)) continue;
      const line = fs.readFileSync(f, 'utf8').split(/\r?\n/).map(x => x.trim()).filter(Boolean)[0] || '';
      if (/^https?:\/\//.test(line)) return { url: line.replace(/\/+$/, ''), file: f };
    } catch (e) { /* tenta o proximo */ }
  }
  return null;
}

let _cerebroLast = null; // ultimo tunel conhecido (sobrevive a sumicos momentaneos)
function proxyCerebro(req, res, url) {
  // Lista de modelos: respondida AQUI, sem tunel. O check de provider do
  // Airi consulta /v1/models ao salvar - assim a configuracao valida e
  // salva mesmo com o Colab desligado (o modelo e sempre 'agentai').
  const sub = url.pathname.slice('/cerebro'.length);
  if (req.method === 'GET' && (sub === '/v1/models' || sub === '/models')) {
    return sendJson(res, 200, { object: 'list', data: [
      { id: 'agentai', object: 'model', created: 0, owned_by: 'local' },
    ] });
  }
  let t = readTunnelUrl();
  if (t) _cerebroLast = t;
  else t = _cerebroLast;
  if (!t) {
    return sendJson(res, 503, { error: { message: 'Cerebro (Colab) desligado: rode o START no Colab ate aparecer TUNEL ATIVO. A config no Airi pode ser salva com Continue Anyway - quando o Colab ligar, o chat funciona sem mexer em nada. (procurei em: ' + CEREBRO_URL_FILES.join(' | ') + ')' } });
  }
  const dest = t.url + sub + (url.search || '');
  const chunks = [];
  req.on('data', (c) => chunks.push(c));
  req.on('end', () => {
    const body = Buffer.concat(chunks);
    try {
      const mod = (dest.indexOf('https:') === 0) ? https : http;
      const preq = mod.request(dest, {
        method: req.method,
        headers: {
          'content-type': req.headers['content-type'] || 'application/json',
          'authorization': req.headers['authorization'] || '',
          'accept': req.headers['accept'] || '*/*',
          'content-length': body.length,
        },
        timeout: 300000,
      }, (pres) => {
        res.writeHead(pres.statusCode || 502, { ...pres.headers, ...CORS });
        pres.pipe(res);
      });
      preq.on('timeout', () => preq.destroy(new Error('timeout do tunel (300s)')));
      preq.on('error', (e) => {
        try { sendJson(res, 502, { error: { message: 'AgentAI (tunel) inacessivel: ' + e.message + ' - tunel: ' + t.url } }); } catch (x) {}
      });
      preq.end(body);
    } catch (e) {
      sendJson(res, 500, { error: { message: 'erro no proxy do cerebro: ' + e.message } });
    }
  });
}

// ---- Instalacao automatica do Kokoro (botao da interface) ----
const KOKORO_DEPS = ['kokoro-onnx', 'soundfile', 'espeakng-loader', 'phonemizer-fork'];
const _inst = { running: false, step: '', pct: 0, error: null, log: '' };

function instLog(line) {
  _inst.log = (_inst.log + '\n' + line).split('\n').slice(-12).join('\n');
  console.log('[kokoro:install] ' + line);
}

function findSystemPython() {
  for (const cmd of ['python', 'py', 'python3']) {
    try {
      const r = spawnSync(cmd, ['--version'], { encoding: 'utf8', timeout: 15000, windowsHide: true });
      const out = String(r.stdout || '') + String(r.stderr || '');
      if (r.status === 0 && /Python\s+\d/.test(out)) return { cmd, args: [], ver: out.trim() };
    } catch (e) { /* tenta o proximo */ }
  }
  return null;
}

function runCmd(cmd, args, label) {
  return new Promise((resolve, reject) => {
    instLog(label + '...');
    const p = spawn(cmd, args, { windowsHide: true });
    let out = '', err = '';
    p.stdout.on('data', (c) => { out += c; if (out.length > 6000) out = out.slice(-4000); });
    p.stderr.on('data', (c) => { err += c; if (err.length > 6000) err = err.slice(-4000); });
    p.on('error', (e) => reject(new Error(label + ': ' + e.message)));
    p.on('exit', (code) => {
      if (code === 0) return resolve({ out, err });
      const tail = (err || out || '').trim().split('\n').slice(-5).join(' | ');
      reject(new Error(label + ' falhou (codigo ' + code + '): ' + tail.slice(-400)));
    });
  });
}

// baixa com progresso e seguindo redirects (github releases redireciona)
function dlFile(url, dest, onPct) {
  return new Promise((resolve, reject) => {
    const get = (u, hops) => {
      if (hops > 6) return reject(new Error('muitos redirecionamentos ao baixar ' + u));
      const mod = (u.indexOf('https:') === 0) ? https : http;
      const req = mod.get(u, (res) => {
        const st = res.statusCode || 0;
        if (st >= 301 && st <= 308 && res.headers.location) {
          res.resume();
          return get(new URL(res.headers.location, u).toString(), hops + 1);
        }
        if (st !== 200) {
          res.resume();
          return reject(new Error('HTTP ' + st + ' ao baixar ' + u));
        }
        const total = Number(res.headers['content-length'] || 0);
        let done = 0, lastPct = -1;
        const ws = fs.createWriteStream(dest);
        res.on('data', (c) => {
          done += c.length;
          if (onPct && total) {
            const pr = done / total;
            if (pr - lastPct >= 0.01) { lastPct = pr; onPct(pr); }
          }
        });
        res.on('error', (e) => { try { fs.unlinkSync(dest); } catch (x) {} reject(e); });
        ws.on('error', (e) => reject(e));
        ws.on('finish', () => resolve(dest));
        res.pipe(ws);
      });
      req.on('error', (e) => { try { fs.unlinkSync(dest); } catch (x) {} reject(e); });
    };
    get(url, 0);
  });
}

async function installKokoro() {
  if (_inst.running) return;
  _inst.running = true; _inst.error = null; _inst.step = 'procurando python'; _inst.pct = 0; _inst.log = '';
  try {
    const py = findSystemPython();
    if (!py) {
      throw new Error('Python nao encontrado neste PC. Instale o Python (winget install Python.Python.3.12, ou pela Microsoft Store), reabra este servidor e clique de novo.');
    }
    instLog('Python encontrado: ' + py.ver + ' (' + py.cmd + ')');
    fs.mkdirSync(KOKORO_DATA, { recursive: true });
    const venvDir = path.join(KOKORO_DATA, 'venv');
    _inst.step = 'criando ambiente (1/4)'; _inst.pct = 0.03;
    await runCmd(py.cmd, py.args.concat(['-X', 'utf8', '-m', 'venv', venvDir]), 'criando venv');
    const venvPy = pyExe(venvDir);
    if (!venvPy) throw new Error('venv criado mas python.exe nao apareceu: ' + venvDir);
    _inst.step = 'instalando dependencias (2/4, pode demorar minutos)'; _inst.pct = 0.08;
    await runCmd(venvPy, ['-X', 'utf8', '-m', 'pip', 'install', '--disable-pip-version-check'].concat(KOKORO_DEPS),
      'pip install ' + KOKORO_DEPS.join(' '));
    _inst.step = 'baixando modelo kokoro-v1.0.onnx (3/4, ~330 MB)'; _inst.pct = 0.15;
    await dlFile(KOKORO_DL_BASE + '/kokoro-v1.0.onnx', path.join(KOKORO_DATA, 'kokoro-v1.0.onnx'),
      (pr) => { _inst.pct = 0.15 + 0.70 * pr; });
    _inst.step = 'baixando vozes voices-v1.0.bin (4/4, ~27 MB)'; _inst.pct = 0.87;
    await dlFile(KOKORO_DL_BASE + '/voices-v1.0.bin', path.join(KOKORO_DATA, 'voices-v1.0.bin'),
      (pr) => { _inst.pct = 0.87 + 0.10 * pr; });
    _inst.step = 'finalizando'; _inst.pct = 0.99;
    KOKORO = detectKokoro();
    if (!KOKORO) throw new Error('instalou tudo mas a deteccao nao achou (estranho) - reinicie o servidor');
    instLog('PRONTO! Kokoro disponivel em ' + KOKORO.dir);
    _inst.pct = 1; _inst.step = 'pronto';
  } catch (e) {
    _inst.error = e.message;
    _inst.step = 'erro';
    instLog('ERRO: ' + e.message);
  }
  _inst.running = false;
}

// Catálogo completo do Edge (buscado sob demanda, com cache em memória)
let _allVoicesCache = null;
let _allVoicesAt = 0;
async function getAllVoices() {
  if (_allVoicesCache && Date.now() - _allVoicesAt < 24 * 3600 * 1000) {
    return { catalog: 'edge', voices: _allVoicesCache };
  }
  try {
    const tts = new MsEdgeTTS();
    const list = await tts.getVoices();
    // [FIX] vozes "Deprecated" quase sempre NÃO sintetizam (áudio vazio)
    _allVoicesCache = list
      .filter(v => v.Status !== 'Deprecated')
      .map(v => ({
        id: v.ShortName,
        name: v.FriendlyName ? v.FriendlyName.replace(/^Microsoft.*Online \(Natural\)? - /, '') : v.ShortName,
        desc: '',
        emoji: v.Locale === 'pt-BR' ? '🇧🇷' : '',
        gender: (v.Gender || '').toLowerCase(),
        locale: v.Locale,
      }));
    _allVoicesAt = Date.now();
    return { catalog: 'edge', voices: _allVoicesCache };
  } catch (e) {
    return { catalog: 'curated', error: e.message, voices: VOICES };
  }
}

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body), ...CORS });
  res.end(body);
}

function sendHtml(res, html) {
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Content-Length': Buffer.byteLength(html), ...CORS });
  res.end(html);
}

// [FIX v3.1] Só envia os headers de áudio quando o PRIMEIRO chunk chegar.
// Assim, voz que falha/volta vazia vira um erro JSON limpo (HTTP 500/502)
// em vez de um "áudio" vazio que o navegador não consegue tocar
// ("Failed to load because no supported source was found").
function sendAudio(res, stream, voiceLabel) {
  let started = false;
  res.on('close', () => { try { stream.destroy(); } catch (e) {} });
  stream.on('data', (chunk) => {
    if (!started) {
      res.writeHead(200, { 'Content-Type': 'audio/mpeg', 'Cache-Control': 'no-cache', ...CORS });
      started = true;
    }
    res.write(chunk);
  });
  stream.on('end', () => {
    if (!started) {
      console.error(`[voz] "${voiceLabel}" nao retornou audio (indisponivel?)`);
      sendJson(res, 502, {
        error: { message: `A voz "${voiceLabel}" não retornou áudio — provavelmente está INDISPONÍVEL no Edge TTS gratuito. Use uma das recomendadas (elas sempre funcionam) ou teste outra.` },
      });
    } else {
      res.end();
    }
  });
  stream.on('error', (err) => {
    console.error('[voz] erro no stream:', err.message);
    if (!started) {
      sendJson(res, 500, { error: { message: 'Falha ao gerar áudio: ' + err.message } });
    } else {
      try { res.end(); } catch (e) {}
    }
  });
}

// ================= ENGINE GPT-SoVITS (custom voice) =================
// Proxy para GPT-SoVITS API (porta 9880)
// Formato: sovits:nome_do_modelo:texto_referencia

// O GPT-SoVITS exige um áudio de REFERÊNCIA de 3 a 10 segundos. O que a gente
// importa como "fonte" pode ser um áudio longo (ex.: 13 min). Então geramos
// automaticamente um ref_audio.wav (~6s) na pasta do modelo, recortando um
// trecho do áudio-fonte usando o venv (librosa + soundfile). Se já existir
// ref_audio.wav, usamos direto.
function ensureSovitsRefAudio(modelDir) {
  const refWav = path.join(modelDir, 'ref_audio.wav');
  if (fs.existsSync(refWav)) return refWav;

  // encontra um áudio-fonte
  let src = null;
  try {
    for (const f of fs.readdirSync(modelDir)) {
      if (/\.(wav|mp3|flac|ogg|m4a)$/i.test(f) && f.toLowerCase() !== 'ref_audio.wav') {
        src = path.join(modelDir, f); break;
      }
    }
  } catch (e) { return null; }
  if (!src) return null;

  const py = pyExe(path.join(REPO_ROOT, 'sovits-data', 'venv'));
  if (!py) return null;

  const CROP_PY = `
import sys, numpy as np
import librosa, soundfile as sf
src, sr = librosa.load(sys.argv[1], sr=None, mono=True)
dur = len(src) / sr
target = 6.0
if dur > 10.0:
    start = max(0, int((dur/2 - target/2)*sr))
    clip = src[start:start+int(target*sr)]
elif dur < 3.0:
    reps = int(3.0/dur)+1
    clip = np.tile(src, reps)[:int(5*sr)]
else:
    clip = src
sf.write(sys.argv[2], clip, sr)
print('OK', len(clip)/sr)
`;
  try {
    const r = spawnSync(py, ['-c', CROP_PY, src, refWav], { encoding: 'utf8', timeout: 120000, windowsHide: true });
    if (r.error) { console.log('[voz:sovits] ffmpeg/ref erro: ' + r.error.message); return null; }
    return fs.existsSync(refWav) ? refWav : null;
  } catch (e) {
    console.log('[voz:sovits] erro ao recortar ref_audio.wav: ' + e.message);
    return null;
  }
}

function sovitsGenerate(text, voice, speed) {
  return new Promise((resolve, reject) => {
    // voice = "nome_do_modelo" (pasta em sovits-data/)
    const sovitsDir = path.join(REPO_ROOT, 'sovits-data');
    const modelDir = path.join(sovitsDir, voice);

    // Referência: o GPT-SoVITS precisa de 3-10s. Prioriza um ref_audio.wav já
    // recortado; senão recorta automaticamente um trecho (~6s) do áudio-fonte.
    let refPath = ensureSovitsRefAudio(modelDir);
    if (!refPath) {
      try {
        const files = fs.readdirSync(modelDir);
        const refAudio = files.find(f => /\.(wav|mp3|ogg)$/i.test(f));
        if (refAudio) refPath = path.join(modelDir, refAudio);
      } catch (e) { /* pasta nao existe */ }
    }
    if (!refPath) {
      return reject(new Error(`Modelo SoVITS "${voice}" nao encontrado ou sem audio de referencia em ${modelDir}`));
    }
    console.log(`[voz:sovits] ref_audio=${refPath} (modelo=${voice})`);

    // Construir URL da API GPT-SoVITS
    // O suporte a 'pt' foi adicionado pelo patch scripts/patch_sovits_pt.py
    // (G2P pt-BR instalado em GPT_SoVITS/text/portuguese.py + text_lang aceito
    // no cleaner/TTS/TextPreprocessor). Agora enviamos 'pt' para que o texto
    // seja fonemizado com REGRAS DE PORTUGUÊS. Se o patch não tiver sido
    // aplicado, o /tts responde HTTP 400 "text_lang: pt is not supported".
    const params = new URLSearchParams({
      text: text,
      text_lang: 'pt',
      ref_audio_path: refPath,
      prompt_lang: 'pt',
      text_split_method: 'cut5',
      speed_factor: String(speed || 1.0),
      media_type: 'wav'
      // Sem 'streaming_mode': o default do GET /tts já é False. Enviar a string
      // 'false' poderia cair no `else` do tts_handle e devolver HTTP 400
      // ("streaming_mode must be 0,1,2,3 or true/false") dependendo da versão do pydantic.
    });

    const apiUrl = `http://127.0.0.1:${SOVITS_PORT}/tts?${params.toString()}`;
    console.log('[voz:sovits] chamando /tts em ' + SOVITS_PORT + ' ...');

    const req = http.get(apiUrl, (res) => {
      if (res.statusCode !== 200) {
        let errBody = '';
        res.on('data', c => errBody += c);
        res.on('end', () => reject(new Error(`SoVITS retornou HTTP ${res.statusCode}: ${errBody.slice(0, 200)}`)));
        return;
      }

      const out = path.join(os.tmpdir(), 'sovits_' + Date.now() + '.wav');
      const ws = fs.createWriteStream(out);
      res.pipe(ws);
      ws.on('finish', () => resolve(out));
      ws.on('error', reject);
    });
    req.setTimeout(180000, () => {
      req.destroy(new Error('SoVITS demorou demais (timeout 180s)'));
    });
    req.on('error', (e) => {
      reject(new Error(`SoVITS inacessivel (porta ${SOVITS_PORT}): ${e.message}. Inicie o GPT-SoVITS primeiro.`));
    });
  });
}

// Listar modelos SoVITS disponiveis
function listSovitsModels() {
  const sovitsDir = path.join(REPO_ROOT, 'sovits-data');
  const models = [];
  try {
    if (fs.existsSync(sovitsDir)) {
      for (const d of fs.readdirSync(sovitsDir, { withFileTypes: true })) {
        if (!d.isDirectory() || d.name === 'venv' || d.name === 'GPT-SoVITS' || d.name === '__pycache__') continue;
        const modelPath = path.join(sovitsDir, d.name);
        const files = fs.readdirSync(modelPath);
        const hasAudio = files.some(f => /\.(wav|mp3|ogg)$/i.test(f));
        const hasModel = files.some(f => /\.(pth|ckpt)$/i.test(f));
        if (hasAudio || hasModel) {
          models.push({ id: d.name, name: d.name, desc: 'Voz custom (GPT-SoVITS)', emoji: '🎤', gender: 'custom', locale: 'custom' });
        }
      }
    }
  } catch (e) { /* ignore */ }
  return models;
}

// Verificar se SoVITS esta rodando
function checkSovits() {
  return new Promise((resolve) => {
    http.get(`http://127.0.0.1:${SOVITS_PORT}/`, (res) => {
      resolve(true);
    }).on('error', () => resolve(false));
  });
}

// ---- parâmetros de prosódia -------------------------------
// pitch: número (Hz) ou string "+30Hz" | rate: multiplicador (1.0 = normal)
async function generateSpeech(input, voice, speed, pitch, volume) {
  const tts = new MsEdgeTTS();
  await tts.setMetadata(voice || 'pt-BR-ThalitaNeural', OUTPUT_FORMAT.AUDIO_24KHZ_48KBITRATE_MONO_MP3);
  const opts = {};
  if (speed && Number(speed) > 0 && Number(speed) !== 1) {
    opts.rate = Number(speed); // multiplicador: 0.5 = metade, 1.5 = 1.5x
  }
  if (pitch != null && pitch !== '') {
    if (typeof pitch === 'number') {
      opts.pitch = (pitch >= 0 ? '+' : '') + pitch + 'Hz';
    } else if (typeof pitch === 'string' && pitch.trim()) {
      const p = pitch.trim();
      if (/^[+-]?\d+(\.\d+)?$/.test(p)) {
        opts.pitch = (Number(p) >= 0 ? '+' : '') + p + 'Hz';
      } else {
        opts.pitch = p; // já veio "+30Hz"
      }
    }
  }
  if (volume != null && volume !== '' && Number(volume) !== 100) {
    opts.volume = Number(volume);
  }
  const { audioStream } = await tts.toStream(input, opts);
  return audioStream;
}

// ---- interface web (embutida, sem dependências externas) ----
const UI_HTML = `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🎛️ Voz da Waifu</title>
<style>
  :root { --bg:#0d0d12; --card:#17171f; --card2:#1e1e29; --txt:#ececf1; --mut:#9a9aad; --pink:#ff7eb6; --purple:#b28bff; --ok:#7be3a2; --warn:#ffcc66; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--txt); font-family:'Segoe UI',system-ui,sans-serif; padding:24px; }
  .wrap { max-width:860px; margin:0 auto; }
  h1 { font-size:26px; background:linear-gradient(90deg,var(--pink),var(--purple)); -webkit-background-clip:text; background-clip:text; color:transparent; }
  .sub { color:var(--mut); font-size:13px; margin:6px 0 20px; }
  .card { background:var(--card); border:1px solid #262633; border-radius:14px; padding:18px; margin-bottom:16px; }
  .card h2 { font-size:14px; text-transform:uppercase; letter-spacing:.08em; color:var(--mut); margin-bottom:12px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:10px; }
  .vcard { background:var(--card2); border:2px solid transparent; border-radius:12px; padding:12px; cursor:pointer; transition:all .15s; }
  .vcard:hover { border-color:#3a3a4d; }
  .vcard.sel { border-color:var(--pink); background:#241a24; }
  .vcard .vname { font-weight:600; font-size:15px; }
  .vwarn { color:var(--warn); font-size:13px; }
  .vcard .vdesc { color:var(--mut); font-size:12px; margin-top:3px; }
  .vcard .vid { color:#6c6c80; font-size:10px; margin-top:6px; font-family:monospace; word-break:break-all; display:flex; align-items:center; gap:8px; justify-content:space-between; }
  .vtest { padding:1px 8px; font-size:12px; line-height:1.6; }
  .row { display:flex; gap:14px; align-items:center; flex-wrap:wrap; margin:10px 0; }
  label.sl { min-width:90px; color:var(--mut); font-size:13px; }
  input[type=range] { flex:1; accent-color:var(--pink); min-width:160px; }
  .val { min-width:64px; text-align:right; font-family:monospace; color:var(--pink); font-size:14px; }
  .presets { display:flex; gap:8px; flex-wrap:wrap; margin-top:6px; }
  button { background:var(--card2); color:var(--txt); border:1px solid #34344a; border-radius:10px; padding:8px 14px; font-size:13px; cursor:pointer; transition:all .15s; }
  button:hover { border-color:var(--pink); }
  button.primary { background:linear-gradient(90deg,var(--pink),var(--purple)); border:none; font-weight:600; color:#fff; padding:11px 22px; font-size:15px; }
  button.primary:disabled { opacity:.5; cursor:wait; }
  textarea { width:100%; background:var(--card2); color:var(--txt); border:1px solid #34344a; border-radius:10px; padding:10px; font-size:14px; min-height:64px; resize:vertical; }
  .cfg { display:flex; gap:10px; align-items:center; background:#101018; border:1px dashed #3a3a55; border-radius:10px; padding:12px; flex-wrap:wrap; }
  .cfg code { font-family:Consolas,monospace; font-size:14px; color:var(--ok); word-break:break-all; }
  .hint { color:var(--mut); font-size:12.5px; line-height:1.6; margin-top:10px; }
  .hint b { color:var(--txt); }
  #status { font-size:12px; color:var(--mut); }
  #playmsg { font-size:13px; margin-top:8px; }
  .ok { color:var(--ok); } .err { color:#ff8a8a; }
  select, input[type=text] { background:var(--card2); color:var(--txt); border:1px solid #34344a; border-radius:8px; padding:8px; font-size:13px; }
  details summary { cursor:pointer; color:var(--mut); font-size:13px; }
  details .alllist { max-height:260px; overflow-y:auto; margin-top:10px; border:1px solid #262633; border-radius:8px; }
  .opt { padding:7px 12px; font-size:13px; cursor:pointer; display:flex; justify-content:space-between; gap:10px; }
  .opt:hover { background:var(--card2); }
  .opt small { color:var(--mut); }
</style>
</head>
<body>
<div class="wrap">
  <h1>🎛️ Voz da Waifu</h1>
  <div class="sub">Servidor de voz local · v__VER__ · duas engines: 🌐 Edge (Microsoft, online) e 🦉 Kokoro (offline) — escolha, ajuste, teste e copie a configuração pro Airi</div>

  <div class="card">
    <h2>1 · Escolha a voz</h2>
    <div class="row">
      <label class="sl">Engine</label>
      <select id="engine">
        <option value="edge">🌐 Edge (Microsoft, online)</option>
        <option value="kokoro">🦉 Kokoro (offline)</option>
      </select>
      <span id="engmsg" style="color:var(--mut);font-size:12px"></span>
      <button id="installKokoro" style="display:none">🦉 Instalar Kokoro offline (~360 MB, 1x)</button>
    </div>
    <div class="grid" id="vgrid"></div>
    <div class="row" id="loadallrow" style="margin-top:12px">
      <button id="loadAll">🌍 Carregar todas as vozes do Edge (400+)</button>
      <span id="allcount" style="color:var(--mut);font-size:12px"></span>
    </div>
    <details style="margin-top:10px" id="alldetails">
      <summary>Ver lista completa / buscar voz específica</summary>
      <div class="row"><input type="text" id="vsearch" placeholder="filtrar por nome, idioma, gênero..." style="flex:1"></div>
      <div class="alllist" id="alllist"></div>
    </details>
    <div class="hint">💡 Dica: use o <b>🔊</b> de cada card pra testar a voz na hora. Se aparecer <span style="color:var(--warn)">⚠️</span>, essa voz está indisponível — escolha outra.</div>
  </div>

  <div class="card">
    <h2>2 · Ajuste o tom (pitch) e a velocidade</h2>
    <div id="pitchwrap">
    <div class="row">
      <label class="sl">Pitch 🎚️</label>
      <input type="range" id="pitch" min="-50" max="50" step="1" value="0">
      <span class="val" id="pitchval">0 Hz</span>
    </div>
    <div class="presets">
      <button data-p="0">Normal</button>
      <button data-p="15">Fofinha +15</button>
      <button data-p="30">🌸 Super fofa +30</button>
      <button data-p="45">🐻 Fofa demais +45</button>
      <button data-p="-15">Grave -15</button>
    </div>
    </div>
    <div class="row" style="margin-top:16px">
      <label class="sl">Velocidade</label>
      <input type="range" id="speed" min="0.5" max="2" step="0.05" value="1">
      <span class="val" id="speedval">1.00x</span>
    </div>
  </div>

  <div class="card">
    <h2>3 · Teste</h2>
    <textarea id="txt">Oi! Eu sou a sua waifu~ Testando um, dois, três... está boa assim?</textarea>
    <div class="row" style="margin-top:10px">
      <button class="primary" id="play">▶️ Ouvir teste</button>
      <span id="playmsg"></span>
    </div>
  </div>

  <div class="card">
    <h2>4 · Configuração pro Airi</h2>
    <div class="cfg">
      <code id="cfgstr">pt-BR-ThalitaNeural</code>
      <button id="copy">📋 Copiar</button>
    </div>
    <div class="row" style="margin-top:12px">
      <button id="saveDef">💾 Salvar como padrão do launcher</button>
      <span id="defstatus" style="color:var(--mut);font-size:12px"></span>
    </div>
    <div class="row">
      <input type="text" id="tunnel" placeholder="URL do túnel do AgentAI (a mesma do Colab: TÚNEL ATIVO)" style="flex:1;min-width:240px">
      <button id="applyAiri">🚀 Aplicar no Airi agora</button>
    </div>
    <div class="hint">
      <b>📋 Copiar:</b> cola no Airi (Settings → Providers → Speech → OpenAI Compatible → campo <b>Voice</b>).<br>
      <b>💾 Padrão do launcher:</b> salva no servidor; o <b>atualizar_airi.ps1</b> atualizado usa essa voz sozinho (patch de 1 bloco, veja no LEIA-ME).<br>
      <b>🚀 Aplicar agora:</b> reabre o Airi já injetando a voz escolhida — cole a URL do túnel acima (fica salva aqui).<br>      <b>🖥️ Airi desktop (janela na tela):</b> no app do AIRI, configure o cérebro com a URL FIXA <code>http://localhost:9860/cerebro/v1</code> (este servidor repassa pro túnel do Colab sozinho, mesmo ele mudando todo dia) e a voz com <code>http://localhost:9860/v1</code>.<br>
      Sua seleção fica salva automaticamente neste navegador. 💾
    </div>
  </div>

  <div id="status">servidor de voz rodando · <a style="color:var(--mut)" href="/health">/health</a></div>
</div>

<script>
(function () {
  var CURATED = __VOICES__;
  var KOKORO_LIST = __KOKORO__;
  var KOKORO_OK = __KOKORO_OK__;
  var KOKORO_CHK = __KOKORO_CHK__;
  var state = { engine: 'edge', voice: 'pt-BR-ThalitaNeural', pitch: 0, speed: 1 };
  try {
    var s = JSON.parse(localStorage.getItem('waifuVoice') || 'null');
    if (s && s.voice) state = s;
  } catch (e) {}
  if (state.engine !== 'kokoro') state.engine = 'edge';

  var vgrid = document.getElementById('vgrid');
  var pitchEl = document.getElementById('pitch');
  var speedEl = document.getElementById('speed');
  var playBtn = document.getElementById('play');
  var playMsg = document.getElementById('playmsg');
  var cfgEl = document.getElementById('cfgstr');
  var audio = null;

  function card(v) {
    var d = document.createElement('div');
    d.className = 'vcard' + (v.id === state.voice ? ' sel' : '');
    d.setAttribute('data-id', v.id);
    d.innerHTML = '<div class="vname">' + (v.emoji ? v.emoji + ' ' : '') + v.name
      + ' <span class="vwarn" style="display:none" title="Esta voz falhou no teste">⚠️</span></div>'
      + '<div class="vdesc">' + (v.desc || v.locale || '') + '</div>'
      + '<div class="vid"><span>' + v.id + '</span><button class="vtest" title="Testar esta voz">🔊</button></div>';
    d.onclick = function (e) {
      if (e.target && e.target.classList && e.target.classList.contains('vtest')) return;
      state.voice = v.id; markSel(); update();
    };
    d.querySelector('.vtest').onclick = function (ev) {
      ev.stopPropagation();
      testVoice(v.id, this);
    };
    return d;
  }
  function markSel() {
    var cards = vgrid.querySelectorAll('.vcard');
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.toggle('sel', cards[i].getAttribute('data-id') === state.voice);
    }
  }
  function renderCards() {
    vgrid.innerHTML = '';
    var list = (state.engine === 'kokoro') ? KOKORO_LIST : CURATED;
    list.forEach(function (v) { vgrid.appendChild(card(v)); });
  }

  // ---- seletor de engine (Edge | Kokoro) + instalacao automatica ----
  var engineEl = document.getElementById('engine');
  var engmsg = document.getElementById('engmsg');
  var installBtn = document.getElementById('installKokoro');
  if (!KOKORO_OK) {
    var kopt = engineEl.querySelector('option[value="kokoro"]');
    if (kopt) { kopt.disabled = true; kopt.textContent = '🦉 Kokoro (não instalado — clique ao lado)'; }
    engmsg.textContent = 'engine offline não instalada (procurou em: ' + (KOKORO_CHK.join(' | ') || 'nenhum lugar') + ')';
    installBtn.style.display = '';
  }
  installBtn.onclick = function () {
    installBtn.disabled = true;
    engmsg.className = '';
    engmsg.textContent = '⏳ iniciando instalação...';
    fetch('/kokoro/install', { method: 'POST' }).then(function () {
      var t = setInterval(function () {
        fetch('/kokoro/status').then(function (r) { return r.json(); }).then(function (st) {
          if (st.available) {
            clearInterval(t);
            engmsg.className = 'ok';
            engmsg.textContent = '✅ Kokoro instalado! recarregando...';
            setTimeout(function () { location.reload(); }, 900);
          } else if (st.error) {
            clearInterval(t);
            engmsg.className = 'err';
            engmsg.textContent = '❌ ' + st.error;
            installBtn.disabled = false;
          } else {
            engmsg.textContent = '⏳ ' + st.step + ' — ' + Math.round((st.pct || 0) * 100) + '%';
          }
        }).catch(function () {});
      }, 1500);
    }).catch(function (e) {
      engmsg.className = 'err';
      engmsg.textContent = '❌ ' + e.message;
      installBtn.disabled = false;
    });
  };
  if (state.engine === 'kokoro' && !KOKORO_OK) state.engine = 'edge';
  engineEl.value = state.engine;
  function applyEngineVis() {
    var kok = state.engine === 'kokoro';
    document.getElementById('loadallrow').style.display = kok ? 'none' : '';
    document.getElementById('alldetails').style.display = kok ? 'none' : '';
    if (kok) engmsg.textContent = '💡 no Kokoro o pitch é aproximado (reamostragem do áudio)';
    else if (!KOKORO_OK) engmsg.textContent = 'engine offline não instalada (procurou em: ' + (KOKORO_CHK.join(' | ') || 'nenhum lugar') + ')';
    else engmsg.textContent = '';
  }
  engineEl.onchange = function () {
    state.engine = engineEl.value;
    applyEngineVis(); renderCards(); update();
  };

  // voz completa enviada ao servidor: sempre com prefixo da engine
  function fullVoice(vid) {
    var v = String(vid || state.voice);
    var low = v.toLowerCase();
    if (low.slice(0, 7) === 'kokoro:') v = v.slice(7);
    else if (low.slice(0, 5) === 'edge:') v = v.slice(5);
    return (state.engine === 'kokoro' ? 'kokoro:' : 'edge:') + v;
  }

  function setWarn(vid, on) {
    var el = vgrid.querySelector('.vcard[data-id="' + vid + '"] .vwarn');
    if (el) el.style.display = on ? 'inline' : 'none';
  }

  function friendlyError(msg) {
    msg = msg || '';
    if (/no supported source|NotSupported|format|demuxer|MediaError/i.test(msg)) {
      return 'sem áudio utilizável — esta voz provavelmente está INDISPONÍVEL no Edge TTS grátis. Tente outra (as recomendadas sempre funcionam).';
    }
    if (/INDISPONÍVEL|não retornou áudio/i.test(msg)) return msg;
    if (/WebSocket|ECONN|network|socket|TLS/i.test(msg)) {
      return 'falha de conexão com o serviço da Microsoft (verifique a internet).';
    }
    return msg;
  }

  // função única de síntese + playback; cb(ok, mensagem)
  function playAudio(voice, text, cb) {
    fetch('/v1/audio/speech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: text, voice: fullVoice(voice), pitch: state.pitch, speed: state.speed })
    }).then(function (r) {
      if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) {
        throw new Error((j.error && j.error.message) || ('HTTP ' + r.status));
      });
      return r.blob();
    }).then(function (blob) {
      if (blob.size < 512) {
        // resposta 200 minúscula -> provavelmente não é áudio
        return blob.text().then(function (t) {
          var m = null;
          try { m = (JSON.parse(t) || {}).error; } catch (e) {}
          throw new Error((m && m.message) || 'a voz não devolveu áudio (indisponível no Edge TTS grátis?)');
        });
      }
      if (audio) { audio.pause(); }
      audio = new Audio(URL.createObjectURL(blob));
      return audio.play();
    }).then(function () { cb(true, 'tocando'); })
      .catch(function (e) { cb(false, friendlyError(e.message || String(e))); });
  }

  function testVoice(vid, btn) {
    var old = btn.textContent;
    btn.disabled = true; btn.textContent = '⏳';
    playMsg.className = ''; playMsg.textContent = 'Testando ' + vid + '...';
    playAudio(vid, 'Oi! Esta é a minha voz, tudo bem?', function (ok, msg) {
      btn.disabled = false; btn.textContent = ok ? '🔊' : '⚠️';
      setTimeout(function () { btn.textContent = old; }, 2500);
      playMsg.className = ok ? 'ok' : 'err';
      playMsg.textContent = (ok ? '🔊 ' : '❌ ') + vid + (ok ? ' funciona!' : ' → ' + msg);
      setWarn(vid, !ok);
    });
  }

  // lista completa sob demanda
  var allLoaded = null;
  document.getElementById('loadAll').onclick = function () {
    var btn = this; btn.disabled = true; btn.textContent = '⏳ carregando...';
    fetch('/v1/audio/voices/all').then(function (r) { return r.json(); }).then(function (data) {
      allLoaded = data.voices || CURATED;
      document.getElementById('allcount').textContent =
        allLoaded.length + ' vozes ' + (data.catalog === 'edge' ? '(catálogo do Edge, deprecadas removidas)' : '(lista recomendada — catálogo indisponível)');
      renderAll('');
      btn.textContent = '🌍 Recarregar catálogo';
      btn.disabled = false;
      var det = document.querySelector('details'); if (det) det.open = true;
    }).catch(function (e) {
      btn.textContent = '🌍 Carregar todas as vozes do Edge (400+)'; btn.disabled = false;
      playMsg.className = 'err'; playMsg.textContent = 'Falha ao buscar catálogo: ' + e.message;
    });
  };
  function renderAll(filter) {
    var box = document.getElementById('alllist');
    box.innerHTML = '';
    if (!allLoaded) return;
    var f = (filter || '').toLowerCase();
    var shown = 0;
    allLoaded.forEach(function (v) {
      var hay = (v.id + ' ' + v.name + ' ' + (v.locale || '') + ' ' + (v.gender || '')).toLowerCase();
      if (f && hay.indexOf(f) < 0) return;
      if (shown++ > 500) return;
      var o = document.createElement('div');
      o.className = 'opt';
      o.innerHTML = '<span>' + (v.emoji ? v.emoji + ' ' : '') + v.id + '</span><small>' + (v.name || '') + '</small>';
      o.onclick = function () { state.voice = v.id; markSel(); update(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
      box.appendChild(o);
    });
    if (!shown) box.innerHTML = '<div class="opt"><small>nada encontrado</small></div>';
  }
  document.getElementById('vsearch').oninput = function (e) { renderAll(e.target.value); };

  function update() {
    document.getElementById('pitchval').textContent = (state.pitch > 0 ? '+' : '') + state.pitch + ' Hz';
    document.getElementById('speedval').textContent = Number(state.speed).toFixed(2) + 'x';
    pitchEl.value = state.pitch; speedEl.value = state.speed;
    var s;
    if (state.engine === 'kokoro') {
      s = 'kokoro:' + state.voice;
    } else {
      s = state.voice;
    }
    if (Number(state.pitch) !== 0) s += (state.pitch > 0 ? ':+' : ':') + state.pitch;
    if (Number(state.speed) !== 1) s += '@' + Number(state.speed).toFixed(2);
    cfgEl.textContent = s;
    try { localStorage.setItem('waifuVoice', JSON.stringify(state)); } catch (e) {}
  }
  pitchEl.oninput = function () { state.pitch = Number(pitchEl.value); update(); };
  speedEl.oninput = function () { state.speed = Number(speedEl.value); update(); };
  var presetBtns = document.querySelectorAll('[data-p]');
  for (var i = 0; i < presetBtns.length; i++) {
    presetBtns[i].onclick = function () { state.pitch = Number(this.getAttribute('data-p')); update(); };
  }
  document.getElementById('copy').onclick = function () {
    var t = cfgEl.textContent;
    var done = function () { var b = document.getElementById('copy'); b.textContent = '✅ Copiado!'; setTimeout(function () { b.textContent = '📋 Copiar'; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(done).catch(function () { fallbackCopy(t); done(); });
    } else { fallbackCopy(t); done(); }
  };
  function fallbackCopy(t) {
    var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta);
    ta.select(); try { document.execCommand('copy'); } catch (e) {} document.body.removeChild(ta);
  }

  playBtn.onclick = function () {
    var txt = document.getElementById('txt').value.trim() || 'Teste de voz.';
    playBtn.disabled = true; playBtn.textContent = '⏳ gerando...';
    playMsg.className = ''; playMsg.textContent = '';
    playAudio(state.voice, txt, function (ok, msg) {
      playBtn.disabled = false; playBtn.textContent = '▶️ Ouvir teste';
      playMsg.className = ok ? 'ok' : 'err';
      playMsg.textContent = ok ? '✅ tocando...' : '❌ ' + msg;
      setWarn(state.voice, !ok);
    });
  };

  // ---- salvar padrão do launcher + aplicar no Airi agora ----
  var defstatus = document.getElementById('defstatus');
  var tunnelEl = document.getElementById('tunnel');
  try { tunnelEl.value = localStorage.getItem('waifuTunnel') || ''; } catch (e) {}

  fetch('/config').then(function (r) { return r.json(); }).then(function (c) {
    defstatus.textContent = c.saved ? ('padrão atual: ' + c.voiceString) : 'nenhum padrão salvo (launcher usa Thalita)';
  }).catch(function () { defstatus.textContent = ''; });

  document.getElementById('saveDef').onclick = function () {
    defstatus.className = ''; defstatus.textContent = '⏳ salvando...';
    fetch('/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice: state.voice, pitch: state.pitch, speed: state.speed })
    }).then(function (r) { return r.json(); }).then(function (c) {
      defstatus.className = c.ok ? 'ok' : 'err';
      defstatus.textContent = c.ok ? ('✅ salvo! o launcher usará ' + c.voiceString) : ('❌ ' + ((c.error || {}).message || 'erro'));
    }).catch(function (e) { defstatus.className = 'err'; defstatus.textContent = '❌ ' + e.message; });
  };

  document.getElementById('applyAiri').onclick = function () {
    var base = tunnelEl.value.trim();
    while (base.endsWith('/')) { base = base.slice(0, -1); }  // sem regex: dentro do template JS, a barra invertida some e quebrava a pagina inteira
    if (!base) {
      playMsg.className = 'err';
      playMsg.textContent = '❌ cole a URL do túnel do AgentAI acima (aparece no Colab no bloco TÚNEL ATIVO).';
      return;
    }
    try { localStorage.setItem('waifuTunnel', base); } catch (e) {}
    var boot = 'http://localhost:5173/agentai-boot.html?url=' + encodeURIComponent(base + '/v1/')
      + '&model=agentai&voice=' + encodeURIComponent(cfgEl.textContent)
      + '&voiceBase=' + encodeURIComponent('http://localhost:9860/v1');
    playMsg.className = 'ok';
    playMsg.textContent = '🚀 abrindo o Airi com a voz ' + cfgEl.textContent + '...';
    window.open(boot, '_blank');
  };

  applyEngineVis();
  renderCards();
  update();
})();
</script>
</body>
</html>`;

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;

  if (req.method === 'OPTIONS') {
    res.writeHead(204, CORS);
    return res.end();
  }

  // Interface de configuração
  if (req.method === 'GET' && path === '/') {
    return sendHtml(res, UI_HTML
      .replace('__VER__', VERSION)
      .replace('__VOICES__', JSON.stringify(VOICES))
      .replace('__KOKORO__', JSON.stringify(KOKORO_VOICES))
      .replace('__KOKORO_OK__', JSON.stringify(!!KOKORO))
      .replace('__KOKORO_CHK__', JSON.stringify(KOKORO_CHECKED)));
  }

  // Raiz em JSON (compatibilidade)
  if (req.method === 'GET' && path === '/v1') {
    return sendJson(res, 200, { status: 'ok', service: 'edge-tts-voice', version: VERSION, endpoints: ['/ (interface)', '/health', '/v1/models', '/v1/audio/speech', '/v1/audio/voices', '/v1/audio/voices/all', '/v1/chat/completions'] });
  }

  // Health
  if (req.method === 'GET' && path === '/health') {
    const sovitsOk = await checkSovits();
    const engines = ['edge'];
    if (KOKORO) engines.push('kokoro');
    if (sovitsOk) engines.push('sovits');
    return sendJson(res, 200, { status: 'ok', version: VERSION, model: 'edge-tts + kokoro + sovits', engines, kokoroChecked: KOKORO_CHECKED, sovits: sovitsOk });
  }

  // Lista de modelos
  if (req.method === 'GET' && path === '/v1/models') {
    const data = [{ id: 'edge-tts', object: 'model', created: 0, owned_by: 'local' }];
    if (KOKORO) data.push({ id: 'kokoro', object: 'model', created: 0, owned_by: 'local' });
    // Adicionar modelos SoVITS
    const sovitsModels = listSovitsModels();
    for (const m of sovitsModels) {
      data.push({ id: 'sovits-' + m.id, object: 'model', created: 0, owned_by: 'local' });
    }
    return sendJson(res, 200, { object: 'list', data });
  }

  // Vozes recomendadas
  if (req.method === 'GET' && path === '/v1/audio/voices') {
    return sendJson(res, 200, VOICES);
  }

  // Catálogo completo do Edge (sob demanda, com fallback)
  if (req.method === 'GET' && path === '/v1/audio/voices/all') {
    return sendJson(res, 200, await getAllVoices());
  }

  // Config persistente (voz padrão que o launcher usa)
  if (req.method === 'GET' && path === '/config') {
    const c = readConfig();
    return sendJson(res, 200, {
      saved: !!c,
      ...((c && { voice: c.voice, pitch: c.pitch, speed: c.speed }) || { voice: 'pt-BR-ThalitaNeural', pitch: 0, speed: 1 }),
      engine: (c && c.engine) || 'edge',
      voiceString: composeVoiceString(c) || 'pt-BR-ThalitaNeural',
      kokoro: { available: !!KOKORO, dir: KOKORO ? KOKORO.dir : null, checked: KOKORO_CHECKED },
    });
  }
  if (req.method === 'POST' && path === '/config') {
    let raw = '';
    req.on('data', (c) => { raw += c; if (raw.length > 100000) req.destroy(); });
    req.on('end', () => {
      try {
        const body = JSON.parse(raw || '{}');
        if (!body.voice || !String(body.voice).trim()) {
          return sendJson(res, 400, { error: { message: 'Campo "voice" é obrigatório.' } });
        }
        const cfg = {
          engine: (body.engine === 'kokoro') ? 'kokoro' : 'edge',
          voice: String(body.voice).trim(),
          pitch: Number(body.pitch) || 0,
          speed: Number(body.speed) || 1,
          savedAt: new Date().toISOString(),
        };
        fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2), 'utf8');
        console.log('[config] padrao salvo: engine=' + cfg.engine + ' voz=' + composeVoiceString(cfg));
        return sendJson(res, 200, { ok: true, saved: true, ...cfg, voiceString: composeVoiceString(cfg) });
      } catch (err) {
        sendJson(res, 500, { error: { message: 'Erro ao salvar config: ' + err.message } });
      }
    });
    return;
  }
  // Proxy do cerebro: status local + repasse pro tunel
  if (req.method === 'GET' && path === '/cerebro/_status') {
    const t = readTunnelUrl();
    return sendJson(res, 200, { configured: !!t, tunnel: t ? t.url : null, file: t ? t.file : null, proxyBase: '/cerebro/v1' });
  }
  if (path === '/cerebro' || path.indexOf('/cerebro/') === 0) {
    return proxyCerebro(req, res, url);
  }

  // Kokoro: instalacao automatica (botao da interface)
  if (req.method === 'GET' && path === '/kokoro/status') {
    return sendJson(res, 200, {
      available: !!KOKORO,
      dir: KOKORO ? KOKORO.dir : null,
      running: _inst.running,
      step: _inst.step,
      pct: _inst.pct,
      error: _inst.error,
      logTail: _inst.log.split('\n').slice(-4),
    });
  }
  if (req.method === 'POST' && path === '/kokoro/install') {
    if (KOKORO) return sendJson(res, 200, { ok: true, alreadyAvailable: true });
    if (_inst.running) return sendJson(res, 409, { error: { message: 'Instalacao ja em andamento: ' + _inst.step } });
    installKokoro().catch(() => {});
    return sendJson(res, 202, { ok: true, started: true });
  }

  // Chat completions "fake" — só para a validação do Airi ficar verde
  if (req.method === 'POST' && path === '/v1/chat/completions') {
    return sendJson(res, 200, {
      id: 'chatcmpl-local',
      object: 'chat.completion',
      created: Math.floor(Date.now() / 1000),
      model: 'edge-tts',
      choices: [{ index: 0, message: { role: 'assistant', content: 'ok' }, finish_reason: 'stop' }],
      usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
    });
  }

  // Geração de áudio (OpenAI-compatible)
  if (req.method === 'POST' && path === '/v1/audio/speech') {
    let raw = '';
    req.on('data', (c) => { raw += c; if (raw.length > 2_000_000) req.destroy(); });
    req.on('end', async () => {
      try {
        const body = JSON.parse(raw || '{}');
        const input = String(body.input || '').trim();
        if (!input) return sendJson(res, 400, { error: { message: 'Campo "input" (texto) é obrigatório.' } });
        let voice = String(body.voice || 'pt-BR-ThalitaNeural').trim();
        let speed = body.speed;
        let pitch = body.pitch ?? body.pitchHz;
        let volume = body.volume;

        // Engine: prefixo "kokoro:"/"/edge:"/"/sovits:" no nome, ou o padrao salvo
        let engine = null;
        const em = voice.match(/^(edge|kokoro|sovits):(.*)$/i);
        if (em) { engine = em[1].toLowerCase(); voice = em[2].trim(); }
        if (!engine) {
          const saved = readConfig();
          engine = (saved && saved.engine === 'kokoro') ? 'kokoro' : 'edge';
        }

        // Truque: sufixos no nome da voz
        //   ":NUM"     ajusta o tom em Hz       ex.: "pt-BR-ThalitaNeural:+30"
        //   "@NUM"     ajusta a velocidade (x)  ex.: "pt-BR-ThalitaNeural:+30@1.1"
        const mRate = voice.match(/@([+-]?\d+(?:\.\d+)?)$/);
        if (mRate) { speed = Number(mRate[1]); voice = voice.slice(0, mRate.index).trim(); }
        const mPitch = voice.match(/:([+-]?\d+(?:\.\d+)?)$/);
        if (mPitch) { pitch = Number(mPitch[1]); voice = voice.slice(0, mPitch.index).trim(); }

        if (engine === 'kokoro') {
          if (!KOKORO) {
            return sendJson(res, 503, { error: { message: 'Engine Kokoro nao disponivel: clique em "Instalar Kokoro" na interface (http://localhost:9860/) para instalar automaticamente.' } });
          }
          const ratio = Math.max(0.7, Math.min(1.5, 1 + (Number(pitch) || 0) / 200));
          console.log('[voz:kokoro] "' + input.slice(0, 60) + '..." -> ' + voice + ' (rate: ' + (speed ?? 'normal') + ', pitch: ' + (pitch || 0) + 'Hz ~x' + ratio.toFixed(3) + ')');
          try {
            const file = await kokoroGenerate(input, voice || 'pf_dora', Number(speed) > 0 ? Number(speed) : 1.0, ratio);
            return sendWavFile(res, file);
          } catch (err) {
            console.error('[voz:kokoro] erro:', err.message);
            return sendJson(res, 500, { error: { message: 'Kokoro: ' + err.message } });
          }
        }

        if (engine === 'sovits') {
          console.log('[voz:sovits] "' + input.slice(0, 60) + '..." -> ' + voice + ' (speed: ' + (speed ?? 'normal') + ')');
          try {
            const file = await sovitsGenerate(input, voice, Number(speed) > 0 ? Number(speed) : 1.0);
            return sendWavFile(res, file);
          } catch (err) {
            console.error('[voz:sovits] erro:', err.message);
            return sendJson(res, 500, { error: { message: 'GPT-SoVITS: ' + err.message } });
          }
        }

        console.log('[voz:edge] "' + input.slice(0, 60) + '..." -> ' + voice + ' (pitch: ' + (pitch ?? 'normal') + ', rate: ' + (speed ?? 'normal') + ')');
        const stream = await generateSpeech(input, voice, speed, pitch, volume);
        sendAudio(res, stream, voice);
      } catch (err) {
        console.error('[voz] erro:', err.message);
        sendJson(res, 500, { error: { message: 'Erro: ' + err.message } });
      }
    });
    return;
  }

  sendJson(res, 404, { error: { message: 'Not found' } });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log('');
  console.log('==========================================');
  console.log('  SERVIDOR DE VOZ (Edge' + (KOKORO ? ' + Kokoro' : '') + ')  v' + VERSION);
  console.log('==========================================');
  console.log(`  Interface : http://localhost:${PORT}/   <-- ESCOLHA A VOZ AQUI`);
  console.log(`  API       : http://localhost:${PORT}/v1`);
  console.log('  Engines   : edge (online)' + (KOKORO ? ' + kokoro (offline, ' + KOKORO.dir + ')' : ' | kokoro: nao instalado (botao na interface instala tudo)'));
  console.log('  Cerebro   : http://localhost:' + PORT + '/cerebro/v1  <- URL FIXA pro Airi (aponta pro tunel atual sozinha)');
  console.log('  Voz padrao: pt-BR-ThalitaNeural');
  console.log('');
  console.log('  No Airi, configure o provider:');
  console.log('  Settings -> Providers -> Speech -> OpenAI Compatible (Speech)');
  console.log(`    Base URL: http://localhost:${PORT}/v1`);
  console.log('    API Key : local  (qualquer valor)');
  console.log('    Model   : edge-tts');
  console.log('    Voice   : pt-BR-ThalitaNeural:+30        (Edge)');
  console.log('              kokoro:pf_dora@1.05            (Kokoro, offline)');
  console.log('              (ou a que voce escolher na interface e copiar de la)');
  console.log('==========================================');
  console.log('');
});
