# phase5-windows.ps1 - the machine-side half of row 5.10 of plan.md (s13-gopro-auth), so the
# person at the Windows 11 laptop only does what a person must: press a button, close a window,
# sign in, paste. Run it in PowerShell from the folder that holds cast-tv-windows-x64.exe:
#
#   powershell -ExecutionPolicy Bypass -File .\phase5-windows.ps1
#
# It checks the artifact's hash, prints --version, starts cast-tv in its own console window,
# reads GET /api/sources/gopro and GET /api/errors (metadata only: the status never carries the
# token), watches for browser processes on cast-tv's own profile, walks rows 5.4, 5.5, 5.7, 5.3
# with 5.9, and 5.6 in that order (the gate must show for 5.4-5.7, and after 5.3 the tab lists),
# and writes everything it sees, with timestamps, to phase5-windows.log. Send that file back.
# No token value is read, printed or stored by this script. ASCII only, for Windows PowerShell 5.1.

param(
  [string]$Exe = ".\cast-tv-windows-x64.exe",
  [string]$Base = "http://localhost:8895",
  [string]$Log = ".\phase5-windows.log",
  [string]$ExpectedSha256 = "0d22f1d7caff48e8413817098bfbf6d0ce21a72046100c651240aaef27809317"
)

$ErrorActionPreference = 'Continue'
$script:App = $null

function Log([string]$msg) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"), $msg
  Write-Host $line
  Add-Content -Path $Log -Value $line
}
function Say([string]$msg) { Write-Host ""; Write-Host (">>> " + $msg) -ForegroundColor Yellow; Log ("  (asked: " + $msg + ")") }
function Ask([string]$q) { Write-Host ""; $a = Read-Host (">>> " + $q); Log ("  owner, '" + $q + "': " + $a); return $a }

function Status {
  try { return Invoke-RestMethod -Uri ($Base + "/api/sources/gopro") -TimeoutSec 3 } catch { return $null }
}
function ErrorCount {
  try { return @((Invoke-RestMethod -Uri ($Base + "/api/errors") -TimeoutSec 3).errors).Count } catch { return "n/a" }
}
function Summ($s) {
  if ($null -eq $s) { return "(server not answering)" }
  $d = $s.detail
  $fe = "-"; if ($d.flow_error) { $fe = $d.flow_error.code }
  $fb = "-"; if ($d.fallback) { $fb = "yes" }
  return ("state=" + $s.state + " step=" + $d.step + " stored=" + $d.stored + " age='" + $d.age +
          "' captured_by=" + $d.captured_by + " flow_error=" + $fe + " fallback=" + $fb + " errors=" + (ErrorCount))
}
function WaitFor([scriptblock]$cond, [int]$seconds, [string]$what) {
  $deadline = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $deadline) {
    $s = Status
    if (& $cond $s) { Log ("  -> " + $what + ": " + (Summ $s)); return $s }
    Start-Sleep -Milliseconds 500
  }
  Log ("  !! timed out after " + $seconds + " s waiting for " + $what + "; last seen: " + (Summ (Status)))
  return $null
}
function AppBrowsers {
  # browser processes running on cast-tv's own profile; the person's own Edge or Chrome never matches
  return @(Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'msedge.exe' -or $_.Name -eq 'chrome.exe') -and $_.CommandLine -like '*gopro-browser*' })
}
function LogBrowsers([string]$when) {
  $b = AppBrowsers
  $main = @($b | Where-Object { $_.CommandLine -like '*--user-data-dir=*' -and $_.CommandLine -notlike '*--type=*' })
  $who = ""; if ($main.Count -gt 0) { $who = " " + $main[0].Name + " pid=" + $main[0].ProcessId }
  Log ("  browser processes on the app profile " + $when + ": " + $b.Count + " (main: " + $main.Count + ")" + $who)
}
function WaitBrowsersGone([int]$seconds) {
  $deadline = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $deadline) { if ((AppBrowsers).Count -eq 0) { return $true }; Start-Sleep -Milliseconds 500 }
  return $false
}
function StartApp {
  $extra = ""; if ($env:CAST_TV_BROWSER) { $extra = " with CAST_TV_BROWSER=" + $env:CAST_TV_BROWSER }
  $p = Start-Process -FilePath $script:ExeFull -PassThru
  Log ("started " + $script:ExeFull + " pid=" + $p.Id + " in its own console window" + $extra)
  $null = WaitFor { param($s) $null -ne $s } 40 "server answering"
  $script:App = $p
}
function StopApp([string]$why) {
  $p = $script:App
  if ($null -eq $p -or $p.HasExited) { Log ("  cast-tv already gone (" + $why + ")"); return }
  Say ("In the black cast-tv console window press Ctrl+C (it prints Stopped.) - " + $why)
  $p.WaitForExit(60000) | Out-Null
  Log ("  cast-tv exited=" + $p.HasExited + " (" + $why + ")")
}
function DisconnectGoPro {
  try {
    $r = Invoke-RestMethod -Method Post -Uri ($Base + "/api/sources/gopro/disconnect") -TimeoutSec 5
    Log ("  POST /api/sources/gopro/disconnect -> state=" + $r.state + " stored=" + $r.detail.stored)
  } catch { Log ("  POST disconnect failed: " + $_) }
}
function Iso([double]$t) { if ($t) { return [DateTimeOffset]::FromUnixTimeMilliseconds([long]($t * 1000)).ToString("u") } else { return "-" } }

# ---------------------------------------------------------------- 0. the artifact and the machine
Set-Content -Path $Log -Value ("log started " + (Get-Date -Format "u")) -Encoding ascii
Log "=== s13-gopro-auth, plan row 5.10, the Windows side ==="
$os = Get-CimInstance Win32_OperatingSystem
Log ("machine: " + $env:COMPUTERNAME + ", " + $os.Caption + " " + $os.Version + ", PowerShell " + $PSVersionTable.PSVersion)
if (-not (Test-Path $Exe)) { Log ("!! " + $Exe + " not found in " + (Get-Location) + "; put the exe next to this script"); exit 1 }
$script:ExeFull = (Resolve-Path $Exe).Path
$h = (Get-FileHash -Algorithm SHA256 $script:ExeFull).Hash.ToLower()
$hashNote = "!! DOES NOT MATCH the expected " + $ExpectedSha256
if ($h -eq $ExpectedSha256) { $hashNote = "= the artifact of release run 36049997670 (OK)" }
Log ("exe: " + (Get-Item $script:ExeFull).Length + " bytes, sha256 " + $h + " " + $hashNote)
$v = & $script:ExeFull --version 2>&1
Log ("--version:`n" + ($v -join "`n"))
$candidates = @(
  @("Edge",   "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"),
  @("Edge",   "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"),
  @("Chrome", "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"),
  @("Chrome", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"),
  @("Chrome", "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"))
foreach ($c in $candidates) {
  if (Test-Path $c[1]) { Log ($c[0] + " at " + $c[1] + ": version " + (Get-Item $c[1]).VersionInfo.ProductVersion) }
}
$tok = Join-Path $env:APPDATA "cast-tv\gopro-token"
$tokNote = "none"
if (Test-Path $tok) { $tokNote = "present, last written " + (Get-Item $tok).LastWriteTime + "; the disconnect below removes it so the gate shows" }
Log ("old token file on this laptop (" + $tok + "): " + $tokNote)
LogBrowsers "before anything"

# ---------------------------------------------------------------- 1. start; the gate must show
StartApp
$s = Status
if ($s -and $s.detail.stored) { Log "  a token is stored here: disconnecting so the gate shows (the row starts from the gate)"; DisconnectGoPro }
Log ("  start state: " + (Summ (Status)))
Say "cast-tv opened its UI tab in your browser. In that tab open the GoPro tab."
$null = Ask "Does the GoPro tab show 'Connect GoPro', ONE button 'Open gopro.com' and NO token field? (y/n)"

# ---------------------------------------------------------------- 2. row 5.4: Cancel
Log "--- row 5.4: Cancel ---"
Say "Press 'Open gopro.com' in the GoPro tab. A gopro.com window opens on this laptop. Do nothing in it."
$s = WaitFor { param($s) $s -and $s.state -eq 'connecting' } 180 "round running"
Start-Sleep -Seconds 2
LogBrowsers "while the window is open"
$null = Ask "Does the page show the waiting block ('A gopro.com window is open on the computer running cast-tv...', 'valid 5 min', a Cancel button)? (y/n)"
Say "Press 'Cancel' on the page (do not close the window yourself)."
$s = WaitFor { param($s) $s -and $s.state -ne 'connecting' } 180 "round ended"
Log ("  browser processes gone within 10 s: " + (WaitBrowsersGone 10))
$null = Ask "Does the gate show the button alone: no token field, no message under it? (y/n)"

# ---------------------------------------------------------------- 3. row 5.5: the window closed with its X
Log "--- row 5.5: the window closed by hand ---"
Say "Press 'Open gopro.com' again."
$s = WaitFor { param($s) $s -and $s.state -eq 'connecting' } 180 "round running"
Say "Close the gopro.com window with its own X (top-right corner), WITHOUT signing in."
$s = WaitFor { param($s) $s -and $s.state -ne 'connecting' } 180 "round ended"
Log ("  browser processes gone within 10 s: " + (WaitBrowsersGone 10))
$null = Ask "Does the page show 'The gopro.com window was closed before a session appeared.' under the button, and no token field? (y/n)"

# ---------------------------------------------------------------- 4. row 5.7: the console closed mid-round
Log "--- row 5.7: closing the console window while the round runs ---"
Say "Press 'Open gopro.com' again."
$s = WaitFor { param($s) $s -and $s.state -eq 'connecting' } 180 "round running"
Start-Sleep -Seconds 2
LogBrowsers "before closing the console"
Say "Now close the black cast-tv console window (its title is cast-tv-windows-x64.exe) with its X, while the gopro.com window is open. This PowerShell window stays."
$script:App.WaitForExit(180000) | Out-Null
Log ("  cast-tv process exited: " + $script:App.HasExited + "; server still answering: " + ($null -ne (Status)))
Log ("  browser processes gone within 15 s: " + (WaitBrowsersGone 15))
LogBrowsers "after the console closed"
$null = Ask "Did the gopro.com window close together with the console? (y/n)"

# ---------------------------------------------------------------- 5. rows 5.3 and 5.9: the hand-off
Log "--- rows 5.3 and 5.9: the hand-off with a sign-in ---"
StartApp
Say "cast-tv opened a fresh UI tab. GoPro tab: the gate again. Press 'Open gopro.com' and sign in in the window the way you normally do. This script watches by itself; come back here when the window has closed."
$s = WaitFor { param($s) $s -and $s.state -eq 'connecting' } 300 "round running (window open)"
$tOpen = Get-Date
$s = WaitFor { param($s) $s -and $s.state -ne 'connecting' } 310 "round ended"
$tEnd = Get-Date
Log ("  window open -> round ended: " + [math]::Round(($tEnd - $tOpen).TotalSeconds, 1) + " s")
if ($s -and $s.state -eq 'connected') {
  $d = $s.detail
  Log ("  captured_at=" + $d.captured_at + " (" + (Iso $d.captured_at) + ") captured_by=" + $d.captured_by +
       " cookie.session=" + $d.cookie.session + " cookie.expires=" + $d.cookie.expires + " (" + (Iso $d.cookie.expires) + ")" +
       " last_success_at=" + $d.last_success_at + " first_401_at=" + $d.first_401_at + " age='" + $d.age + "' errors=" + (ErrorCount))
  if ($d.cookie.expires -and $d.captured_at) { Log ("  cookie lifetime from capture: " + [math]::Round(($d.cookie.expires - $d.captured_at) / 86400, 2) + " days") }
}
Log ("  browser processes gone within 15 s: " + (WaitBrowsersGone 15))
$null = Ask "How did you sign in (password / Google / Apple), and was 2FA asked?"
$null = Ask "Roughly how many seconds from your last sign-in click until the window closed?"
$null = Ask "Row 5.9: did the window show a 'Save password?' bubble after the sign-in? (y/n)"
$null = Ask "Does the tab list your library, with 'session captured just now' in the header, and is the Diagnostics counter unchanged? (y/n)"

# ---------------------------------------------------------------- 6. row 5.6: the fallback and a paste
Log "--- row 5.6: the fallback with CAST_TV_BROWSER=C:\nonexistent.exe, then a paste ---"
DisconnectGoPro
StopApp "to restart with CAST_TV_BROWSER set"
$env:CAST_TV_BROWSER = 'C:\nonexistent.exe'
$v = & $script:ExeFull --version 2>&1
Log ("--version with CAST_TV_BROWSER set:`n" + ($v -join "`n"))
StartApp
Say "In the (re)opened UI tab, GoPro tab, press 'Open gopro.com'. No window can open; a fallback block should appear under the button."
$s = WaitFor { param($s) $s -and $s.detail.fallback } 180 "fallback shown"
if ($s) { Log ("  reason: " + $s.detail.fallback.reason + " | numbered steps: " + @($s.detail.fallback.steps).Count) }
LogBrowsers "after the failed launch (nothing should have started)"
$null = Ask "Does the page show the reason, three numbered steps, and a token field with 'Save token'? (y/n)"
Say "Paste a token from your own signed-in browser (F12 -> Application -> Storage -> Cookies -> https://gopro.com -> gp_access_token) into that field and press 'Save token'. The script waits."
$s = WaitFor { param($s) $s -and $s.state -eq 'connected' } 600 "connected after the paste"
if ($s) { Log ("  captured_by=" + $s.detail.captured_by + " age='" + $s.detail.age + "' fallback still present=" + ($null -ne $s.detail.fallback) + " errors=" + (ErrorCount)) }
$null = Ask "Does the tab list, with 'token stored just now' in the header? (y/n)"

# ---------------------------------------------------------------- done
Log "--- done ---"
StopApp "end of the run"
Remove-Item Env:CAST_TV_BROWSER -ErrorAction SilentlyContinue
LogBrowsers "at the end (Task Manager should agree: none)"
Say ("Finished. Send back the file " + (Resolve-Path $Log).Path)
