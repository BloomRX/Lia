"""
lia/airi/cdp.py — Execução de JavaScript via CDP (Chrome DevTools Protocol).

O AIRI (Electron/Tamagotchi) expõe um endpoint de remote-debugging em
`settings:CDP_PORT` (default 9222). Para injetar no localStorage do app,
avaliamos um script na página via `Runtime.evaluate` e depois recarregamos
com `Page.reload`.

Transporte: como o app roda no Windows e a stack já usa PowerShell para o
WebSocket (o `ClientWebSocket` do .NET não exige dependência extra), geramos
um `.ps1` + o JS em arquivos temporários e o executamos. O JS em si é gerado
por `lia/airi/inject.py` — fonte única e testável.

Importante (Windows PowerShell 5.1): para operações **void** de
`ClientWebSocket`, use `.Wait()` (não vaza nada p/ o stream de saída). Para
`Task<T>` use `.Result` (devolve o valor). Usar `.GetAwaiter().GetResult()`
em Tasks void vaza o sentinela `System.Threading.Tasks.VoidTaskResult` na
stdout, o que corromperia a captura do `INJECT:`/`VERIFY:`.

Sequência de um run:
    1. Conecta no CDP e injeta (providers + speech + consciousness + vision).
    2. Dispara `Page.reload` (fire-and-forget) — o app recarrega e lê o novo
       localStorage.
    3. Aguarda a página subir e verifica num socket NOVO (o reload destrói o
       contexto de execução anterior; verificar no mesmo socket pendurava).

Resultado: `CdpResult` com o status de cada bloco e o dump dos valores lidos.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

from .. import config as _cfg
from .. import log as _log
from . import config as _airi_cfg
from . import inject as _inject


@dataclass
class CdpResult:
    ok: bool
    summary: str            # mensagem curta p/ log
    inject_value: str = ""  # status dos blocos retornado pelo evaluate
    verify: dict = None     # dicionário lido de volta do localStorage
    output: str = ""        # saída bruta do PowerShell (p/ depuração)

    def __post_init__(self):
        if self.verify is None:
            self.verify = {}


# --------------------------------------------------------------------------
# PowerShell helpers (ClientWebSocket do .NET; placeholders via .replace)
# --------------------------------------------------------------------------
# Helper comum: escolhe a página da app (prefere localhost:5173 à about:blank)
# e avalia JS por id (ignora events; acumula frames até EndOfMessage; deadline).
_PS_COMMON = r"""
$ErrorActionPreference = 'Continue'

function Get-Page {
    $targets = Invoke-RestMethod -Uri "http://127.0.0.1:$cdpPort/json" -TimeoutSec 3
    $pages = @($targets | Where-Object { $_.type -eq 'page' -and $_.webSocketDebuggerUrl })
    if (-not $pages) { return $null }
    $real = @($pages | Where-Object { $_.url -and $_.url -notmatch '^about:blank' })
    if ($real) { $pages = $real }
    $dev = @($pages | Where-Object { $_.url -match 'localhost:5173|127.0.0.1:5173' })
    if ($dev) { return $dev[0] }
    return $pages[0]
}

function Invoke-Eval($ws, $ct, $id, $js) {
    $msg = @{ id = $id; method = 'Runtime.evaluate'; params = @{ expression = $js; returnByValue = $true } } | ConvertTo-Json -Depth 20
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $ws.SendAsync([System.ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $buf = New-Object byte[] 262144
    $accum = ''
    $deadline = [DateTime]::UtcNow.AddSeconds(25)
    while ([DateTime]::UtcNow -lt $deadline) {
        $r = $ws.ReceiveAsync([System.ArraySegment[byte]]::new($buf), $ct).Result
        $accum += [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
        if ($r.EndOfMessage) {
            try {
                $o = $accum | ConvertFrom-Json
                $accum = ''
                if ($o.id -eq $id) { return $o }
            } catch { $accum = '' }
        }
    }
    return $null
}
"""


_PS_INJECT_TEMPLATE = _PS_COMMON + r"""
$cdpPort = <CDP_PORT>
$injFile  = '<INJ_FILE>'

$page = Get-Page
if (-not $page) { Write-Host "NO_PAGE"; exit 1 }

$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ct = New-Object System.Threading.CancellationToken($false)
try {
    $ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, $ct).Wait()
    $js = Get-Content $injFile -Raw
    $resp = Invoke-Eval $ws $ct 100 $js
    if ($null -eq $resp) { Write-Host "ERRO: sem resposta do Runtime.evaluate"; exit 1 }
    Write-Host ("INJECT: " + $resp.result.result.value)

    # Dispara o reload (fire-and-forget): a página recarrega e lê o novo localStorage.
    $reload = @{ id = 200; method = 'Page.reload'; params = @{ ignoreCache = $true } } | ConvertTo-Json
    [void]$ws.SendAsync([System.ArraySegment[byte]]::new([System.Text.Encoding]::UTF8.GetBytes($reload)), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    Write-Host "RELOAD: enviado"
    try { $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait() } catch { }
} catch {
    Write-Host ("ERRO: " + $_)
} finally {
    if ($ws) { try { $ws.Dispose() } catch { } }
}
"""


_PS_VERIFY_TEMPLATE = _PS_COMMON + r"""
$cdpPort = <CDP_PORT>
$verFile  = '<VER_FILE>'

$page = Get-Page
if (-not $page) { Write-Host "NO_PAGE"; exit 1 }

$ws = New-Object System.Net.WebSockets.ClientWebSocket
$ct = New-Object System.Threading.CancellationToken($false)
try {
    $ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, $ct).Wait()
    $js = Get-Content $verFile -Raw
    $resp = Invoke-Eval $ws $ct 300 $js
    if ($null -eq $resp) { Write-Host "ERRO: sem resposta do Runtime.evaluate"; exit 1 }
    Write-Host ("VERIFY: " + $resp.result.result.value)
    try { $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait() } catch { }
    Write-Host "OK: verificacao concluida"
} catch {
    Write-Host ("ERRO: " + $_)
} finally {
    if ($ws) { try { $ws.Dispose() } catch { } }
}
"""


def _run_powershell(ps_script: str, timeout: int = 90) -> tuple[int, str]:
    """Roda um script PowerShell e devolve (returncode, stdout+stderr).

    Em caso de timeout, tenta devolver o que já foi impresso (p/ diagnóstico),
    em vez de só 'timeout'.
    """
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
    kwargs = {"capture_output": True, "text": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, **kwargs)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return -1, "powershell não encontrado (só Windows)"
    except subprocess.TimeoutExpired as e:
        partial = ""
        for buf in (e.stdout, e.stderr):
            if isinstance(buf, str):
                partial += buf
            elif buf:
                partial += buf.decode("utf-8", errors="replace")
        return -1, (partial.strip() or f"timeout após {timeout}s")
    except Exception as e:
        return -1, str(e)


# --------------------------------------------------------------------------
# Parsing de saída
# --------------------------------------------------------------------------
def _extract(label: str, output: str) -> str:
    """Extrai o texto após 'LABEL:' da saída do PowerShell."""
    for line in output.splitlines():
        if line.startswith(label + ":"):
            return line[len(label) + 1:].strip()
    return ""


# --------------------------------------------------------------------------
# Seleção de página (evita pegar a about:blank do Electron)
# --------------------------------------------------------------------------
def _pick_page(targets) -> Optional[dict]:
    """Pick a 'page' target com webSocketDebuggerUrl; prefere a da app (Vite)."""
    if not isinstance(targets, list):
        return None
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        return None
    real = [t for t in pages if t.get("url") and not t.get("url", "").startswith("about:blank")]
    if real:
        pages = real
    dev = [t for t in pages if "localhost:" in t.get("url", "")]
    if dev:
        return dev[0]
    return pages[0]


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------
def inject_all(
    active_model: str,
    voice: str,
    pitch: int = 0,
    rate: float = 1.0,
    reload: bool = True,
    port: int = _airi_cfg.CDP_PORT,
    brain_provider_id: Optional[str] = None,
    brain_model: Optional[str] = None,
) -> CdpResult:
    """Gera o JS completo (injeção + verificação) e o executa via CDP.

    Args:
        active_model: modelo TTS (ex.: 'edge-tts', 'sovits').
        voice: string de voz já composta (ex.: 'pt-BR-ThalitaNeural', 'kokoro:pf_dora@1.05').
        pitch: pitch (inteiro).
        rate: velocidade (float).
        reload: se True, recarrega a página após injetar (e re-verifica).
        port: porta do CDP.
        brain_provider_id: provider de CÉREBRO a ativar (Groq/Cerebras). Default
            = primário (definido em lia/airi/config.py).
        brain_model: modelo de cérebro. Default = BRAIN_MODEL.

    Returns:
        CdpResult com status, valores lidos de volta e saída p/ depuração.
    """
    inj_js = _inject.build_all_js(
        active_model, voice, pitch, rate,
        brain_provider_id=brain_provider_id, brain_model=brain_model,
    )
    ver_js = _inject.build_verify_js()

    # Guarda os JS em arquivos temporários (logs/ p/ depuração) e os .ps1 também.
    log_dir = _cfg.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = _inject._timestamp()
    inj_file = log_dir / f"airi-inject-{stamp}.js"
    ver_file = log_dir / f"airi-verify-{stamp}.js"
    ps_inj_file = log_dir / f"airi-cdp-inject-{stamp}.ps1"
    ps_ver_file = log_dir / f"airi-cdp-verify-{stamp}.ps1"

    inj_file.write_text(inj_js, encoding="utf-8")
    ver_file.write_text(ver_js, encoding="utf-8")

    ps_inj = (_PS_INJECT_TEMPLATE
              .replace("<CDP_PORT>", str(port))
              .replace("<INJ_FILE>", str(inj_file).replace("'", "''")))
    ps_ver = (_PS_VERIFY_TEMPLATE
              .replace("<CDP_PORT>", str(port))
              .replace("<VER_FILE>", str(ver_file).replace("'", "''")))
    ps_inj_file.write_text(ps_inj, encoding="utf-8")
    ps_ver_file.write_text(ps_ver, encoding="utf-8")

    _log.write(f"[AIRI] CDP: JS de injeção → {inj_file}")
    _log.write(f"[AIRI] CDP: JS de verificação → {ver_file}")
    _log.write(f"[AIRI] CDP: script de injeção → {ps_inj_file}")
    _log.write(f"[AIRI] CDP: script de verificação → {ps_ver_file}")

    # 1) Injeta (escreve localStorage + dispara o reload).
    rc1, out1 = _run_powershell(ps_inj, timeout=90)
    _log.write(f"[AIRI] CDP injeção (rc={rc1}):\n{out1.strip()}")
    inject_value = _extract("INJECT", out1)
    output = out1

    # 2) Se for pra recarregar, espera a página subir e verifica num socket novo.
    verify_value = ""
    if reload:
        time.sleep(8)
        rc2, out2 = _run_powershell(ps_ver, timeout=90)
        _log.write(f"[AIRI] CDP verificação (rc={rc2}):\n{out2.strip()}")
        output += "\n" + out2
        verify_value = _extract("VERIFY", output)

    verify = _parse_verify(verify_value)

    # ok = a injeção retornou status dos blocos sem ERRO.
    inj_clean = inject_value or ""
    ok = bool(inj_clean.strip()) and ("ERRO" not in inj_clean.upper())
    if ok and reload:
        summary = "injeção + verificação OK" if verify_value else "injeção OK (sem verificação)"
    elif ok:
        summary = "injeção OK"
    else:
        summary = "injeção falhou"

    result = CdpResult(
        ok=ok,
        summary=summary,
        inject_value=inject_value,
        verify=verify,
        output=output.strip(),
    )
    return result


def _parse_verify(raw: str) -> dict:
    """Tenta converter o JSON lido de volta em dict; tolera falhas."""
    if not raw:
        return {}
    if raw.startswith("ERRO:"):
        return {}
    try:
        # O evaluate pode devolver o JSON como string com aspas extras.
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"_raw": data}
    except Exception:
        try:
            data = json.loads(json.loads(raw))  # string dentro de string
            return data if isinstance(data, dict) else {"_raw": data}
        except Exception:
            return {"_raw": raw}


def is_port_open(port: int = _airi_cfg.CDP_PORT, host: str = "127.0.0.1", timeout: float = 2.0) -> bool:
    """Verifica se o CDP do Electron está respondendo na porta."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    except Exception:
        return False
    finally:
        sock.close()


def cdp_page_ws_url(port: int = _airi_cfg.CDP_PORT) -> Optional[str]:
    """Retorna a URL do WebSocket da página da app (prefere a do Vite)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as resp:
            targets = json.loads(resp.read().decode("utf-8", "replace"))
        page = _pick_page(targets)
        if page:
            return page.get("webSocketDebuggerUrl")
    except Exception as e:
        _log.write(f"[AIRI] CDP /json falhou: {e}")
    return None
