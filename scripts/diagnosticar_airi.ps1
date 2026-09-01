# ============================================================
#  diagnosticar_airi.ps1 - Diagnostica o estado do AIRI
#  Convia via CDP e le localStorage + store do Pinia
# ============================================================
[CmdletBinding()]
param(
    [int]$CdpPort = 9222
)

Write-Host ""
Write-Host "================================================"
Write-Host "  DIAGNOSTICO DO AIRI"
Write-Host "================================================"
Write-Host ""

# ---------- 1. Conectar ao CDP ----------
function Get-CdpTargets($port) {
    try { return Invoke-RestMethod -Uri "http://127.0.0.1:${port}/json" -TimeoutSec 3 }
    catch { return $null }
}

function Invoke-CdpEval($wsUrl, $js) {
    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $ct = New-Object System.Threading.CancellationToken($false)
    $ws.ConnectAsync([Uri]$wsUrl, $ct).Wait()
    $msg = @{ id = 1; method = 'Runtime.evaluate'; params = @{ expression = $js; returnByValue = $true; awaitPromise = $true } } | ConvertTo-Json -Depth 10
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $ws.SendAsync([System.ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $buf = New-Object byte[] 65536
    $result = ""
    do {
        $r = $ws.ReceiveAsync([System.ArraySegment[byte]]::new($buf), $ct).Result
        $result += [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
    } while (-not $r.EndOfMessage)
    $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
    return ($result | ConvertFrom-Json)
}

$targets = Get-CdpTargets $CdpPort
if (-not $targets) {
    Write-Host "[ERRO] AIRI nao esta rodando com CDP na porta $CdpPort"
    Write-Host "       Inicie o Tamagotchi primeiro."
    exit 1
}

$page = $targets | Where-Object { $_.type -eq 'page' -and $_.webSocketDebuggerUrl } | Select-Object -First 1
if (-not $page) {
    Write-Host "[ERRO] Nenhuma pagina encontrada"
    exit 1
}

Write-Host "[OK] Pagina: $($page.title)"
Write-Host "[OK] URL: $($page.url)"
Write-Host ""

# ---------- 2. Ler localStorage ----------
Write-Host "=== LOCALSTORAGE ==="

$keys = @(
    'settings/providers/configured',
    'settings/providers/added',
    'settings/speech/active-provider',
    'settings/speech/active-model',
    'settings/speech/voice',
    'settings/speech/pitch',
    'settings/speech/rate'
)

foreach ($key in $keys) {
    $js = "localStorage.getItem('$key')"
    $resp = Invoke-CdpEval $page.webSocketDebuggerUrl $js
    $val = $resp.result.result.value
    if ($val) {
        # Truncar valores longos
        if ($val.Length -gt 200) { $val = $val.Substring(0, 200) + "..." }
        Write-Host "  $key = $val"
    } else {
        Write-Host "  $key = (vazio)"
    }
}

Write-Host ""

# ---------- 3. Verificar providers configurados ----------
Write-Host "=== PROVIDERS CONFIGURADOS ==="

$js = @"
(function() {
  try {
    var configured = JSON.parse(localStorage.getItem('settings/providers/configured') || '{}');
    var added = JSON.parse(localStorage.getItem('settings/providers/added') || '{}');
    var result = [];
    for (var id in configured) {
      var p = configured[id];
      result.push({
        id: id,
        definitionId: p.definitionId,
        status: p.status,
        baseUrl: p.config ? p.config.baseUrl : '(sem)',
        apiKey: p.config ? (p.config.apiKey ? '***' : '(vazio)') : '(sem)',
        added: !!added[id]
      });
    }
    return JSON.stringify(result, null, 2);
  } catch(e) { return 'ERRO: ' + e.message; }
})();
"@

$resp = Invoke-CdpEval $page.webSocketDebuggerUrl $js
$val = $resp.result.result.value
Write-Host $val

Write-Host ""

# ---------- 4. Verificar modulo de speech ----------
Write-Host "=== MODULO DE SPEECH ==="

$js = @"
(function() {
  try {
    var provider = localStorage.getItem('settings/speech/active-provider') || '(vazio)';
    var model = localStorage.getItem('settings/speech/active-model') || '(vazio)';
    var voice = localStorage.getItem('settings/speech/voice') || '(vazio)';
    var pitch = localStorage.getItem('settings/speech/pitch') || '(vazio)';
    var rate = localStorage.getItem('settings/speech/rate') || '(vazio)';
    return JSON.stringify({ provider: provider, model: model, voice: voice, pitch: pitch, rate: rate }, null, 2);
  } catch(e) { return 'ERRO: ' + e.message; }
})();
"@

$resp = Invoke-CdpEval $page.webSocketDebuggerUrl $js
$val = $resp.result.result.value
Write-Host $val

Write-Host ""

# ---------- 5. Verificar se o Pinia store esta lendo ----------
Write-Host "=== PINIA STORE (se acessivel) ==="

$js = @"
(function() {
  try {
    // Tentar acessar o Pinia store via Vue devtools
    var app = document.querySelector('#app');
    if (!app || !app.__vue_app__) return 'Vue app nao encontrado';

    var pinia = app.__vue_app__.config.globalProperties.$pinia;
    if (!pinia) return 'Pinia nao encontrado';

    var stores = Object.keys(pinia.state.value);
    var result = { stores: stores };

    // Verificar store de speech
    if (pinia.state.value.speech) {
      result.speech = pinia.state.value.speech;
    }

    // Verificar store de provider-config
    if (pinia.state.value['provider-config']) {
      result.providerConfig = {
        providers: Object.keys(pinia.state.value['provider-config'].providers || {}),
        addedProviders: pinia.state.value['provider-config'].addedProviders
      };
    }

    return JSON.stringify(result, null, 2);
  } catch(e) { return 'ERRO: ' + e.message; }
})();
"@

$resp = Invoke-CdpEval $page.webSocketDebuggerUrl $js
$val = $resp.result.result.value
Write-Host $val

Write-Host ""

# ---------- 6. Verificar erros no console ----------
Write-Host "=== ERROS RECENTES NO CONSOLE ==="

$js = @"
(function() {
  try {
    // Capturar erros dos ultimos logs
    var errors = [];
    if (window.__consoleErrors) {
      errors = window.__consoleErrors.slice(-5);
    }
    return JSON.stringify(errors.length > 0 ? errors : 'Nenhum erro capturado', null, 2);
  } catch(e) { return 'ERRO: ' + e.message; }
})();
"@

$resp = Invoke-CdpEval $page.webSocketDebuggerUrl $js
$val = $resp.result.result.value
Write-Host $val

Write-Host ""
Write-Host "================================================"
Write-Host "  FIM DO DIAGNOSTICO"
Write-Host "================================================"
Write-Host ""
