$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

function Start-StreamlitApp {
    param(
        [int]$Port,
        [string]$Script
    )

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        return
    }

    Start-Process `
        -FilePath $Python `
        -ArgumentList @("-m", "streamlit", "run", $Script, "--server.port", "$Port") `
        -WorkingDirectory $ProjectDir `
        -WindowStyle Hidden | Out-Null
}

Start-StreamlitApp -Port 8501 -Script "main.py"
Start-StreamlitApp -Port 8502 -Script "pc_input_page.py"
Start-Sleep -Seconds 4

$hostName = $env:COMPUTERNAME
$addresses = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254*" } |
    Select-Object -ExpandProperty IPAddress

Write-Host "대시보드: http://$hostName`:8501"
Write-Host "PC 입력 페이지: http://$hostName`:8502"
foreach ($address in $addresses) {
    Write-Host "대시보드(IP): http://$address`:8501"
    Write-Host "PC 입력 페이지(IP): http://$address`:8502"
}
