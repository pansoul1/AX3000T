param(
    [Parameter(Mandatory=$true)][string]$Router,
    [Parameter(Mandatory=$true)][string]$Rom,
    [Parameter(Mandatory=$true)][string]$Firmware,
    [string]$Python,
    [string]$SshPath
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $Python) {
    $venvPython = Join-Path $repoRoot '.work\venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { $Python = $venvPython }
    else { $Python = (Get-Command python.exe -ErrorAction Stop).Source }
}
if ($Router -notmatch '^[a-zA-Z0-9][a-zA-Z0-9.:-]*$') { throw 'Invalid router hostname/IP.' }
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
if (-not $SshPath -or -not (Test-Path -LiteralPath $SshPath)) { throw 'Install Windows OpenSSH/Git, or pass -SshPath.' }
$scpPath = Join-Path (Split-Path $SshPath -Parent) 'scp.exe'
if (-not (Test-Path -LiteralPath $scpPath)) { throw 'scp.exe must be installed beside ssh.exe.' }
$firmwarePath = (Resolve-Path -LiteralPath $Firmware).Path
$romPath = (Resolve-Path -LiteralPath $Rom).Path
# Check the complete system-only image locally before connecting to the router.
& $Python -X utf8 (Join-Path $repoRoot 'build.py') verify --image $firmwarePath --stock $romPath
if ($LASTEXITCODE -ne 0) { throw 'Local firmware validation failed.' }
$operationId = [guid]::NewGuid().ToString('N')
$localOutput = Join-Path $repoRoot ('.work\cache\web-prepare-' + $operationId)
& $Python -X utf8 (Join-Path $repoRoot 'build.py') prepare-web --rom $romPath --output $localOutput
if ($LASTEXITCODE -ne 0) { throw 'Could not generate preparation files.' }
$remoteDirectory = '/tmp/rd03-web-prepare-' + $operationId
$remoteHost = 'root@' + $Router
$sshOptions = @('-o', 'HostKeyAlgorithms=+ssh-rsa')
$minimumKiB = [math]::Ceiling((Get-Item -LiteralPath $firmwarePath).Length / 1024) + 32768
Write-Host ('SSH client: ' + $SshPath)
Write-Host 'One-time RAM preparation. No flash, reboot, persistent hook or firewall change.'
Write-Host 'Enter the CURRENT working SSH password when prompted.'
$preflight = 'avail=$(awk ''/^MemAvailable:/ {print $2}'' /proc/meminfo); [ "${avail:-0}" -ge ' + $minimumKiB + ' ] || { echo "Stop ShellCrash and free router memory before preparing."; exit 1; }; mkdir -m 700 ' + $remoteDirectory
& $SshPath @sshOptions $remoteHost $preflight
if ($LASTEXITCODE -ne 0) { throw 'Router memory preflight or SSH failed.' }
& $scpPath '-O' @sshOptions $firmwarePath ($remoteHost + ':' + $remoteDirectory + '/firmware.bin')
if ($LASTEXITCODE -ne 0) { throw 'Firmware transfer failed.' }
& $scpPath '-O' @sshOptions (Join-Path $localOutput 'mkxqimage.patched') (Join-Path $localOutput 'prepare.sh') ($remoteHost + ':' + $remoteDirectory + '/')
if ($LASTEXITCODE -ne 0) { throw 'Preparation transfer failed.' }
$firmwareHash = (Get-FileHash -LiteralPath $firmwarePath -Algorithm SHA256).Hash.ToLowerInvariant()
& $SshPath @sshOptions $remoteHost ('sh ' + $remoteDirectory + '/prepare.sh ' + $firmwareHash)
if ($LASTEXITCODE -ne 0) { throw 'Router preparation failed. Keep the full output for diagnosis.' }
Write-Host 'READY. Upload the same firmware file in the Xiaomi web management interface.'
