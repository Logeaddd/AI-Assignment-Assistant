$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Get-PythonCommand {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) { return "py" }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return "python" }
  throw "Python was not found. Please install Python 3.11+ and try again."
}

function Test-PortFree([int]$Port) {
  $conn = Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue
  if ($conn) {
    try {
      $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
      if ($listeners) { return $false }
    } catch {
      # Fall back to binding tests below.
    }
  }

  $listener = $null
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    if ($listener) { $listener.Stop() }
  }
}

function Get-FreePort {
  foreach ($port in 8501..8599) {
    if (Test-PortFree $port) { return $port }
  }
  throw "No free port found between 8501 and 8599."
}

$pythonCmd = Get-PythonCommand

if (-not (Test-Path ".venv")) {
  & $pythonCmd -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

$port = Get-FreePort
$url = "http://localhost:$port"
Write-Host "Starting AI Assignment Assistant at $url"

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
  "-NoProfile",
  "-Command",
  "Start-Sleep -Seconds 4; Start-Process '$url'"
)

.\.venv\Scripts\python.exe -m streamlit run app.py --server.port $port --server.headless false
