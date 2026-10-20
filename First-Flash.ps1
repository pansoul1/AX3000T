<#
.SYNOPSIS
Prepare an RD03 running official 1.0.98 for its first custom web upgrade.
.DESCRIPTION
Validates both images, enables SSH through a pinned XMiR-Patcher smartcontroller
adapter if needed, then temporarily mounts the native ROM verifier patch.
The firmware upload remains a manual step in the Xiaomi web interface.
CheckOnly validates local files without downloading or contacting a router.
#>
[CmdletBinding()]
param(
    [string]$Router = '192.168.31.1',
    [string]$Rom,
    [string]$Firmware,
    [string]$Python,
    [string]$SshPath,
    [switch]$SkipSshUnlock,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$repoRoot = $PSScriptRoot
$stockHash = '042ba08949e547007710caa43830e574a7a7f5964119af4c457409b2fa8b4bce'
$stockUrl = 'https://cdn.cnbj1.fds.api.mi-img.com/xiaoqiang/rom/rd03/miwifi_rd03_firmware_48abd_1.0.98.bin'
$xmirRevision = '16a46e350e3de2cb3415ab2cb652df53783998dc'
$xmirHash = 'b33edcf1b5a6406d12428d681e0e117a86826a56fae7ed03ac99c1fc556bdc56'
$routerAddress = $null
if (-not [Net.IPAddress]::TryParse($Router, [ref]$routerAddress) -or
    $routerAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
    throw 'Router must be the IPv4 address of your own RD03.'
}
if (-not $Firmware) {
    $Firmware = Join-Path $repoRoot 'firmware\pansoul-2.1\RD03-1.0.98-pansoul2.1-web.bin'
}
$firmwarePath = (Resolve-Path -LiteralPath $Firmware).Path
if (-not $Rom) {
    $Rom = Join-Path $repoRoot '.work\cache\miwifi_rd03_firmware_48abd_1.0.98.bin'
}
if (-not (Test-Path -LiteralPath $Rom)) {
    if ($CheckOnly) { throw 'CheckOnly requires a local official ROM. Pass -Rom.' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $romFullPath = [IO.Path]::GetFullPath($Rom)
    New-Item -ItemType Directory -Path (Split-Path $romFullPath -Parent) -Force | Out-Null
    Write-Host 'Downloading the pinned official RD03 1.0.98 ROM...'
    Invoke-WebRequest -UseBasicParsing -Uri $stockUrl -OutFile ($romFullPath + '.part')
    if ((Get-FileHash -LiteralPath ($romFullPath + '.part') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $stockHash) {
        throw 'Official ROM checksum differs. Download retained as .part; router untouched.'
    }
    Move-Item -LiteralPath ($romFullPath + '.part') -Destination $romFullPath
}
$romPath = (Resolve-Path -LiteralPath $Rom).Path
if ((Get-FileHash -LiteralPath $romPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $stockHash) {
    throw 'Only the pinned official RD03 1.0.98 ROM is supported; router untouched.'
}

$venvPython = Join-Path $repoRoot '.work\venv\Scripts\python.exe'
if (-not $Python) {
    if (Test-Path -LiteralPath $venvPython) { $Python = $venvPython }
    else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pythonCommand) { $Python = $pythonCommand.Source }
    }
}
if (-not $Python) { throw 'Install Python 3.10+ or pass -Python with the full python.exe path.' }
& $Python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'The builder requires a working Python 3.10+.' }
if (-not $CheckOnly -and -not (Test-Path -LiteralPath $venvPython)) {
    & $Python -m venv (Join-Path $repoRoot '.work\venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
    $Python = $venvPython
}
& $Python -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('dissect') and all(u.find_spec('dissect.' + n) for n in ('squashfs', 'cstruct', 'util')) else 1)"
if ($LASTEXITCODE -ne 0) {
    if ($CheckOnly) { throw 'Install requirements.txt first; CheckOnly does not install dependencies.' }
    & $Python -m pip install -r (Join-Path $repoRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed; router untouched.' }
}
Write-Host 'Validating official input, custom firmware, model, CRC and unchanged kernel...'
& $Python -X utf8 (Join-Path $repoRoot 'build.py') verify --image $firmwarePath --stock $romPath
if ($LASTEXITCODE -ne 0) { throw 'Local firmware validation failed; router untouched.' }
if ($CheckOnly) {
    Write-Host 'CHECK PASSED: local images only. No downloads, SSH unlock, router connection or ROM preparation.'
    return
}

if (-not $SshPath) {
    $sshCommand = Get-Command ssh.exe -ErrorAction SilentlyContinue
    if ($sshCommand) { $SshPath = $sshCommand.Source }
    else {
        $sshCandidates = @(
            "$env:WINDIR\System32\OpenSSH\ssh.exe",
            "$env:ProgramFiles\Git\usr\bin\ssh.exe"
        )
        $gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
        if ($gitCommand) { $sshCandidates += Join-Path (Split-Path $gitCommand.Source -Parent) '..\usr\bin\ssh.exe' }
        $SshPath = $sshCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
}
if (-not $SshPath -or -not (Test-Path -LiteralPath $SshPath)) { throw 'Install OpenSSH/Git, or pass -SshPath; router untouched.' }
if (-not (Test-Path -LiteralPath (Join-Path (Split-Path $SshPath -Parent) 'scp.exe'))) {
    throw 'scp.exe must be installed beside ssh.exe; router untouched.'
}

function Test-SshBanner {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync($Router, 22)
        if (-not $task.Wait(3000) -or -not $client.Connected) { return $false }
        $stream = $client.GetStream()
        $stream.ReadTimeout = 3000
        $buffer = New-Object byte[] 256
        $count = $stream.Read($buffer, 0, $buffer.Length)
        return [Text.Encoding]::ASCII.GetString($buffer, 0, $count).StartsWith('SSH-')
    }
    catch { return $false }
    finally { $client.Dispose() }
}

if (-not $SkipSshUnlock -and -not (Test-SshBanner)) {
    $cacheRoot = Join-Path $repoRoot '.work\cache'
    New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
    $archive = Join-Path $cacheRoot ('xmir-patcher-' + $xmirRevision + '.zip')
    if (-not (Test-Path -LiteralPath $archive)) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        Write-Host ('Downloading XMiR-Patcher snapshot ' + $xmirRevision + '...')
        Invoke-WebRequest -UseBasicParsing -Uri ('https://codeload.github.com/openwrt-xiaomi/xmir-patcher/zip/' + $xmirRevision) -OutFile ($archive + '.part')
        if ((Get-FileHash -LiteralPath ($archive + '.part') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $xmirHash) {
            throw 'XMiR-Patcher download checksum differs; no upstream code executed.'
        }
        Move-Item -LiteralPath ($archive + '.part') -Destination $archive
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $xmirHash) {
        throw 'Cached XMiR-Patcher checksum differs; no upstream code executed.'
    }
    # Always extract a verified copy; previous gateway config/output is never reused.
    $sessionRoot = Join-Path $cacheRoot ('first-flash-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $archive -DestinationPath $sessionRoot
    $toolRoot = Join-Path $sessionRoot ('xmir-patcher-' + $xmirRevision)
    $unlockPython = Join-Path $toolRoot 'python\python.exe'
    Write-Host 'SSH is closed. Starting the RD03 1.0.98 smartcontroller adapter.'
    Write-Host 'Enter the Xiaomi WEB ADMIN password at the hidden prompt.'
    Write-Host 'The adapter will replace the upstream temporary root password with this admin password.'
    Push-Location -LiteralPath $toolRoot
    try {
        & $unlockPython -u (Join-Path $repoRoot 'src\scripts\unlock-stock-ssh.py') --router $Router
        $unlockExit = $LASTEXITCODE
    }
    finally { Pop-Location }
    if ($unlockExit -ne 0) {
        throw 'SSH unlock did not pass. ROM preparation was not run. Read the output; do not upload the custom image yet.'
    }
    if (-not (Test-SshBanner)) { throw 'No SSH server after unlock; ROM preparation was not run.' }
}
else {
    Write-Host 'Using the existing SSH service. Enter its CURRENT working password when asked.'
}

& (Join-Path $repoRoot 'src\scripts\Prepare-WebUpgrade.ps1') -Router $Router -Rom $romPath -Firmware $firmwarePath -Python $Python -SshPath $SshPath
Write-Host ('Firmware to upload in the Xiaomi web interface: ' + $firmwarePath)
Write-Host 'Keep the router powered on until the manual upload. This script has not flashed or rebooted it.'
