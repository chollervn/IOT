# Requires an Administrator PowerShell. Only opens MQTT from the local subnet.
#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskBroker = Join-Path $taskRoot '.tools\mosquitto\mosquitto.exe'
$taskConnection = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime\connection.json') -Raw | ConvertFrom-Json
$taskRuleName = 'IOT-ESP32-MQTT-' + $taskConnection.port
if (Get-NetFirewallRule -Name $taskRuleName -ErrorAction SilentlyContinue) {
    Set-NetFirewallRule -Name $taskRuleName -Enabled True -Profile Any -Action Allow
    Get-NetFirewallRule -Name $taskRuleName | Get-NetFirewallAddressFilter |
        Set-NetFirewallAddressFilter -LocalAddress $taskConnection.host -RemoteAddress LocalSubnet
} else {
    New-NetFirewallRule -Name $taskRuleName -DisplayName 'IoT ESP32 MQTT (local subnet)' `
        -Direction Inbound -Action Allow -Enabled True -Profile Any -Protocol TCP -LocalPort $taskConnection.port `
        -LocalAddress $taskConnection.host -RemoteAddress LocalSubnet -Program $taskBroker | Out-Null
}
Write-Host 'MQTT firewall rule enabled for the local subnet only.'
