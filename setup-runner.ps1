& {
# ================================================================
#  stock-buzz：在這台 Windows 電腦安裝 GitHub self-hosted runner
#  請在「系統管理員」PowerShell 貼上整段後按 Enter
# ================================================================
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$RepoUrl   = 'https://github.com/YH-13-fabio/stock-buzz'
$RunnerDir = 'C:\actions-runner'
$PyExe     = 'C:\Program Files\Python312\python.exe'
$GitExe    = 'C:\Program Files\Git\cmd\git.exe'
function Step($t) { Write-Host ''; Write-Host "== $t ==" -ForegroundColor Cyan }
function RefreshPath { $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User') }
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host '請用「以系統管理員身分執行」開啟 PowerShell 後再貼一次。' -ForegroundColor Red; return }
Step '1/4 安裝 Python 3.12 與 Git（已安裝會自動略過）'
$hasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)
if (-not (Test-Path $PyExe)) {
  if (-not $hasWinget) { Write-Host '找不到 winget，請先到 Microsoft Store 安裝「應用程式安裝程式」(App Installer)。' -ForegroundColor Red; return }
  winget install -e --id Python.Python.3.12 --scope machine --accept-source-agreements --accept-package-agreements --override '/quiet InstallAllUsers=1 PrependPath=1 Include_test=0'
} else { Write-Host 'Python 3.12 已安裝' }
if (-not (Test-Path $GitExe)) {
  if (-not $hasWinget) { Write-Host '找不到 winget，請先到 Microsoft Store 安裝「應用程式安裝程式」(App Installer)。' -ForegroundColor Red; return }
  winget install -e --id Git.Git --scope machine --accept-source-agreements --accept-package-agreements
} else { Write-Host 'Git 已安裝' }
RefreshPath
if (-not (Test-Path $PyExe)) { Write-Host "Python 安裝失敗：找不到 $PyExe" -ForegroundColor Red; return }
if (-not (Test-Path $GitExe)) { Write-Host "Git 安裝失敗：找不到 $GitExe" -ForegroundColor Red; return }
& $PyExe --version
& $GitExe --version
Step '2/4 下載 GitHub Actions runner'
if (Test-Path "$RunnerDir\config.cmd") {
  Write-Host "已存在 $RunnerDir，沿用"
} else {
  New-Item -ItemType Directory -Force -Path $RunnerDir | Out-Null
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'win-arm64' } else { 'win-x64' }
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $rel = Invoke-RestMethod -UseBasicParsing 'https://api.github.com/repos/actions/runner/releases/latest'
  $asset = $rel.assets | Where-Object { $_.name -like "actions-runner-$arch-*.zip" } | Select-Object -First 1
  Write-Host "下載 $($asset.name) ..."
  $zip = Join-Path $env:TEMP $asset.name
  & curl.exe -L --fail --retry 3 -o $zip $asset.browser_download_url
  if ($LASTEXITCODE -ne 0) { throw "下載失敗（curl 代碼 $LASTEXITCODE）" }
  Write-Host '解壓縮中...'
  & tar.exe -xf $zip -C $RunnerDir
  if ($LASTEXITCODE -ne 0) { throw "解壓縮失敗（tar 代碼 $LASTEXITCODE）" }
  Remove-Item $zip
}
Step '3/4 連結到你的 GitHub repo'
Write-Host '請到 GitHub 的「New self-hosted runner」頁面，複製含有 --token 的那一整行（或只複製 token），貼在下面後按 Enter：' -ForegroundColor Yellow
$in = Read-Host 'token'
$m = [regex]::Match($in, '--token\s+(\S+)')
$token = if ($m.Success) { $m.Groups[1].Value } else { $in.Trim() }
if (-not $token) { Write-Host '沒有輸入 token，已停止。' -ForegroundColor Red; return }
Push-Location $RunnerDir
try {
  & .\config.cmd --unattended --url $RepoUrl --token $token --name "$env:COMPUTERNAME-stock-buzz" --labels stock-buzz --runasservice --replace
  if ($LASTEXITCODE -ne 0) { throw "config.cmd 失敗（代碼 $LASTEXITCODE）" }
} finally { Pop-Location }
Step '4/4 確認服務狀態'
Get-Service 'actions.runner.*' | Format-Table Status, Name -AutoSize
Write-Host ''
Write-Host '完成！runner 已設為 Windows 服務，開機會自動啟動。可以關掉這個視窗了。' -ForegroundColor Green
}
