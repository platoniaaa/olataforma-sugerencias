# ============================================================
#  sincronizar_diario.ps1 - Wrapper para la tarea programada de Windows.
#
#  Se ejecuta a las 10:00 AM cada dia (tarea programada). Comportamiento:
#    1. Verifica que Power BI Desktop este abierto (msmdsrv corriendo).
#       Si no esta, escribe en el log y sale sin error visible.
#    2. Ejecuta push_to_cloud.ps1 pero SIN Read-Host al final (modo silencioso).
#    3. Loggea cada corrida en logs\sincronizar_diario.log para auditoria.
# ============================================================
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$logDir = "$root\logs"
$logFile = "$logDir\sincronizar_diario.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-Log($msg, $level = "INFO") {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts [$level] $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
}

Write-Log "=== Sincronizacion diaria iniciada ==="

# 1. Verificar Power BI Desktop
$pbi = Get-Process -Name msmdsrv -ErrorAction SilentlyContinue
if (-not $pbi) {
    Write-Log "Power BI Desktop no esta abierto. Saltando sincronizacion." "WARN"
    exit 0
}
Write-Log "Power BI Desktop detectado (PID $($pbi.Id))."

# 2. Verificar entorno Python
$venvPy = "$root\apps\api\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Log "No encuentro el entorno de Python en $venvPy" "ERROR"
    exit 1
}

# 3. Ejecutar push
Write-Log "Ejecutando sync_powerbi_desktop..."
Push-Location "$root\apps\api"
try {
    $output = & $venvPy -m src.jobs.sync_powerbi_desktop 2>&1
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}

# Loggear cada linea del output
foreach ($line in $output) {
    Write-Log "  $line"
}

if ($code -eq 0) {
    Write-Log "=== Sincronizacion OK ===" "OK"
}
else {
    Write-Log "=== Sincronizacion FALLO (exit code $code) ===" "ERROR"
}

exit $code
