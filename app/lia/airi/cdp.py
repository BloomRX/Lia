"""
lia/airi/cdp.py — Execução de JavaScript via CDP (Chrome DevTools Protocol).

O AIRI (Electron/Tamagotchi) expõe um endpoint de remote-debugging em
`settings:CDP_PORT` (default 9222). Para injetar no localStorage do app,
avaliamos um script na página via `Runtime.evaluate` e depois recarregamos
com `Page.reload`.

Como o app roda no Windows e a stack já usa PowerShell para o WebSocket (o
`ClientWebSocket` do .NET não exige dependência extra), mantemos o transporte
em PowerShell: geramos um `.ps1` + o JS em arquivos temporários (evita os
problemas de escaping ao embutir código no PS) e o executamos. O JS em si é
gerado por `lia/airi/inject.py` — fonte única e testável.

Sequência de um run:
    1. Conecta no CDP.
    2. Avalia o JS de injeção (providers + speech + consciousness + vision).
    3. Recarrega a página (Page.reload) e espera o app subir.
    4. Lê de volta o localStorage (build_verify_js) → confirma o que o AIRI
       realmente reconheceu.

Resultado: `CdpResult` com o status de cada bloco e o dump dos valores lidos.
"""

from __future__ import annotations

import json
import subprocess
import sys
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
# PowerShell helper (usa o WebSocket nativo do .NET)
# --------------------------------------------------------------------------
_PS_TEMPLATE = r"""
$ErrorActionPreference = 'Continue'
$cdpPort  = {cdp_port}
$injFile  = '{inj_file}'
$verFile  = '{ver_file}'
$reload   = $true

function Send-Cdp($ws, $ct, $js) {{
    $msg = @{{ id = 1; method = 'Runtime.evaluate'; params = @{{ expression = $js; returnByValue = $true }} }} | ConvertTo-Json -Depth 10
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $ws.SendAsync([System.ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $buf = New-Object byte[] 65536
    $result = ""
    do {{
        $r = $ws.ReceiveAsync([System.ArraySegment[byte]]::new($buf), $ct).Result
        $result += [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
    }} while (-not $r.EndOfMessage)
    $obj = $result | ConvertFrom-Json
    return $obj.result.result.value
}}

function Send-Raw($ws, $ct, $json) {{
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $ws.SendAsync([System.ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $buf = New-Object byte[] 65536
    $result = ""
    do {{
        $r = $ws.ReceiveAsync([System.ArraySegment[byte]]::new($buf), $ct).Result
        $result += [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
    }} while (-not $r.EndOfMessage)
    return $result
}}

try {{
    $targets = Invoke-RestMethod -Uri "http://127.0.0.1:${{cdpPort}}/json" -TimeoutSec 3
    $page = $targets | Where-Object {{ $_.type -eq 'page' -and $_.webSocketDebuggerUrl }} | Select-Object -First 1
    if (-not $page) {{ Write-Host "ERRO: Nenhuma pagina encontrada no CDP"; exit 1 }}

    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $ct = New-Object System.Threading.CancellationToken($false)
    $ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, $ct).Wait()

    # 1) Injeta (providers + speech + consciousness + vision) e lê o status de cada bloco
    $injJs = Get-Content $injFile -Raw
    $injValue = Send-Cdp $ws $ct $injJs
    Write-Host ("INJECT: " + $injValue)

    # 2) Recarrega e deixa o app subir
    $reloadMsg = @{{ id = 2; method = 'Page.reload'; params = @{{ ignoreCache = $false }} }} | ConvertTo-Json
    Send-Raw $ws $ct $reloadMsg | Out-Null
    Write-Host "RELOAD: enviado"
    Start-Sleep -Seconds 3

    # 3) Lê de volta o localStorage (confirma o que o AIRI reconheceu)
    $verJs = Get-Content $verFile -Raw
    $verValue = Send-Cdp $ws $ct $verJs
    Write-Host ("VERIFY: " + $verValue)

    $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
    Write-Host "OK: injecao + reload + verificacao concluidos"
}} catch {{
    Write-Host ("ERRO: " + $_)
}}
"""


def _run_powershell(ps_script: str, timeout: int = 90) -> tuple[int, str]:
    """Roda um script PowerShell e devolve (returncode, stdout+stderr)."""
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
    kwargs = {"capture_output": True, "text": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, **kwargs)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return -1, "powershell não encontrado (só Windows)"
    except subprocess.TimeoutExpired:
        return -1, f"timeout após {timeout}s"
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
# API pública
# --------------------------------------------------------------------------
def inject_all(
    active_model: str,
    voice: str,
    pitch: int = 0,
    rate: float = 1.0,
    reload: bool = True,
    port: int = _airi_cfg.CDP_PORT,
) -> CdpResult:
    """Gera o JS completo (injeção + verificação) e o executa via CDP.

    Args:
        active_model: modelo TTS (ex.: 'edge-tts', 'sovits').
        voice: string de voz já composta (ex.: 'pt-BR-ThalitaNeural', 'kokoro:pf_dora@1.05').
        pitch: pitch (inteiro).
        rate: velocidade (float).
        reload: se True, recarrega a página após injetar.
        port: porta do CDP.

    Returns:
        CdpResult com status, valores lidos de volta e saída p/ depuração.
    """
    inj_js = _inject.build_all_js(active_model, voice, pitch, rate)
    ver_js = _inject.build_verify_js()

    # Guarda os JS em arquivos temporários (logs/ p/ depuração) e o .ps1 também.
    log_dir = _cfg.LOGS_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = _inject._timestamp()
    inj_file = log_dir / f"airi-inject-{stamp}.js"
    ver_file = log_dir / f"airi-verify-{stamp}.js"
    ps_file = log_dir / f"airi-cdp-{stamp}.ps1"

    inj_file.write_text(inj_js, encoding="utf-8")
    ver_file.write_text(ver_js, encoding="utf-8")

    ps_script = _PS_TEMPLATE.format(
        cdp_port=port,
        inj_file=str(inj_file).replace("'", "''"),
        ver_file=str(ver_file).replace("'", "''"),
    )
    ps_file.write_text(ps_script, encoding="utf-8")

    _log.write(f"[AIRI] CDP: JS de injeção → {inj_file}")
    _log.write(f"[AIRI] CDP: JS de verificação → {ver_file}")
    _log.write(f"[AIRI] CDP: script PowerShell → {ps_file}")

    rc, output = _run_powershell(ps_script, timeout=90)
    _log.write(f"[AIRI] CDP saída (rc={rc}):\n{output.strip()}")

    inject_value = _extract("INJECT", output)
    verify_value = _extract("VERIFY", output)
    verify = _parse_verify(verify_value)
    ok = ("OK:" in output) and ("ERRO:" not in output.split("OK:")[-1])

    result = CdpResult(
        ok=ok,
        summary="injeção + verificação OK" if ok else "injeção falhou",
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
    """Retorna a URL do WebSocket da primeira página 'page' no CDP."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as resp:
            targets = json.loads(resp.read().decode("utf-8", "replace"))
        for t in targets:
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                return t["webSocketDebuggerUrl"]
    except Exception as e:
        _log.write(f"[AIRI] CDP /json falhou: {e}")
    return None
