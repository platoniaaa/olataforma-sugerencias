# ============================================================
#  extract_powerbi_desktop.ps1
#  Lee la tabla del sugerido desde un Power BI Desktop ABIERTO
#  (instancia local de Analysis Services) y la escribe en un CSV temporal.
#
#  Escribe a CSV (rapido) en vez de ConvertTo-Json, que es lentisimo en
#  PowerShell 5.1 con muchas filas.
#
#  Salida (stdout): JSON { ok, error, port, rows, csv } donde csv = ruta del archivo.
# ============================================================
param(
    [string]$Dax = "EVALUATE 'Sugerido por Sucursal'",
    [int]$Port = 0
)
$ErrorActionPreference = "Stop"
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Find-PbiPorts {
    $procs = Get-Process -Name msmdsrv -ErrorAction SilentlyContinue
    $ports = @()
    foreach ($p in $procs) {
        try {
            $conns = Get-NetTCPConnection -OwningProcess $p.Id -State Listen -ErrorAction SilentlyContinue
            foreach ($c in $conns) {
                if ($c.LocalAddress -in @("127.0.0.1", "::1", "0.0.0.0", "::")) {
                    $ports += [int]$c.LocalPort
                }
            }
        }
        catch {}
    }
    return ($ports | Sort-Object -Unique)
}

function Get-Catalog($port) {
    $cs = "Provider=MSOLAP;Data Source=localhost:$port;"
    $conn = New-Object System.Data.OleDb.OleDbConnection($cs)
    $conn.Open()
    try {
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"
        $r = $cmd.ExecuteReader()
        $cat = $null
        if ($r.Read()) { $cat = $r.GetValue(0) }
        $r.Close()
        return $cat
    }
    finally { $conn.Close() }
}

function CsvEscape($v) {
    if ($null -eq $v -or $v -is [System.DBNull]) { return '""' }
    if ($v -is [double] -or $v -is [decimal] -or $v -is [single]) {
        return '"' + $v.ToString([Globalization.CultureInfo]::InvariantCulture) + '"'
    }
    $s = [string]$v
    return '"' + $s.Replace('"', '""') + '"'
}

# Extrae el nombre limpio de columna: "Tabla[Columna]" o "[Medida]" -> "Columna"
function CleanName($name) {
    if ($name -match '\[([^\]]+)\]\s*$') { return $matches[1] }
    return $name
}

function Invoke-DaxToCsv($port, $catalog, $dax, $csvPath) {
    $cs = "Provider=MSOLAP;Data Source=localhost:$port;Initial Catalog=$catalog;"
    $conn = New-Object System.Data.OleDb.OleDbConnection($cs)
    $conn.Open()
    $writer = New-Object System.IO.StreamWriter($csvPath, $false, (New-Object System.Text.UTF8Encoding $false))
    $count = 0
    try {
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = $dax
        $cmd.CommandTimeout = 600
        $r = $cmd.ExecuteReader()
        $n = $r.FieldCount
        # Cabeceras limpias
        $headers = New-Object System.Collections.Generic.List[string]
        for ($i = 0; $i -lt $n; $i++) { $headers.Add((CsvEscape (CleanName $r.GetName($i)))) }
        $writer.WriteLine([string]::Join(",", $headers))
        # Filas
        $vals = New-Object string[] $n
        while ($r.Read()) {
            for ($i = 0; $i -lt $n; $i++) { $vals[$i] = CsvEscape $r.GetValue($i) }
            $writer.WriteLine([string]::Join(",", $vals))
            $count++
        }
        $r.Close()
    }
    finally {
        $writer.Close()
        $conn.Close()
    }
    return $count
}

$result = [ordered]@{ ok = $false; error = $null; port = 0; rows = 0; csv = $null }
try {
    $ports = if ($Port -gt 0) { @($Port) } else { Find-PbiPorts }
    if (-not $ports -or @($ports).Count -eq 0) {
        throw "No se detecto Power BI Desktop abierto. Abre el archivo del sugerido en Power BI Desktop y vuelve a intentar."
    }
    $csvPath = [System.IO.Path]::Combine($env:TEMP, "sugerido_pbi_$([System.Guid]::NewGuid().ToString('N')).csv")
    $lastErr = $null
    foreach ($p in $ports) {
        try {
            $cat = Get-Catalog $p
            if (-not $cat) { continue }
            $rows = Invoke-DaxToCsv $p $cat $Dax $csvPath
            $result.ok = $true
            $result.port = $p
            $result.rows = $rows
            $result.csv = $csvPath
            break
        }
        catch { $lastErr = $_.Exception.Message }
    }
    if (-not $result.ok) {
        throw ("No se pudo consultar el modelo abierto. Detalle: " + $lastErr)
    }
}
catch {
    $result.ok = $false
    $result.error = $_.Exception.Message
}

$result | ConvertTo-Json -Compress
