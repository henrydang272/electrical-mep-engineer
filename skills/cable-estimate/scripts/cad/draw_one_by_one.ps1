# draw_one_by_one.ps1 -Root <drawing folder> -Work <folder with draw_plan.json> [-TraySrc <tray drawing.dwg>] [-ClearDoc <doc.dwg>]
# For each plan entry {doc, tsv, n, off}: open ONE drawing, copy tray+panel layers from TraySrc shifted by -off
# (CTCOPYD), draw routes (CTDRAW2), save, close. progeCAD hangs if many drawings are open at once. Resumable via draw_done.txt.
param([Parameter(Mandatory)][string]$Root, [Parameter(Mandatory)][string]$Work, [string]$TraySrc = '', [string]$ClearDoc = '')
$ErrorActionPreference = 'Stop'
$s = $Work; $root = $Root
$log = "$s\draw_log.txt"
function Log($m) { "$(Get-Date -Format HH:mm:ss) $m" | Out-File $log -Append -Encoding ascii }
$cfg = Get-Content "$s\draw_plan.json" -Raw | ConvertFrom-Json
$done = @(); if (Test-Path "$s\draw_done.txt") { $done = Get-Content "$s\draw_done.txt" }
Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices;
public class Dlg { public delegate bool EP(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool EnumWindows(EP f, IntPtr l);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
public static int Close(uint pid, string t){ int n=0; EnumWindows((h,l)=>{ uint p; GetWindowThreadProcessId(h,out p); var s=new StringBuilder(256); GetWindowText(h,s,256); if(p==pid && IsWindowVisible(h) && s.ToString().Contains(t)){ SendMessage(h,0x0010,IntPtr.Zero,IntPtr.Zero); n++; } return true; }, IntPtr.Zero); return n; } }
"@
if (-not (Get-Process pcad -ErrorAction SilentlyContinue)) {
Start-Process "C:\Program Files\PSOFT\progeCAD 2026 Professional ENG\pcad.exe"
for ($i = 0; $i -lt 60; $i++) { Start-Sleep 2; $pc = Get-Process pcad -ErrorAction SilentlyContinue; if ($pc) { if ([Dlg]::Close([uint32]$pc.Id, 'association') -gt 0) { Log "closed association dialog"; Start-Sleep 3; break } } }
Start-Sleep 5 }
$app = [Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application')
$TRAY = 'E-CABL-TRAY,E-CABL-TRAY-CNTR,E-CABL-TRAY-ANNO,E-CABL-TRAY-IDEN,E-ELE-QPM-IDEN'
$SRC = $TraySrc
function PathOf($name) { (Get-ChildItem -Recurse $root -Filter $name | Select-Object -First 1).FullName }
function WaitIdle($d, $max) {
  Start-Sleep 2
  for ($i = 0; $i -lt $max; $i++) { try { if ([int]$d.GetVariable('CMDACTIVE') -eq 0) { return } } catch {}; Start-Sleep 1 }
  Log "  WARN command still active after $max s"
}
$loaded = $false
foreach ($p in $cfg.plan) {
  if ($done -contains $p.doc) { continue }
  Log "== $($p.doc)"
  $src = $null
  $needTray = $SRC -and $p.off -and $p.doc -ne $SRC
  if ($needTray) { $src = $app.Documents.Open((PathOf $SRC), $true); WaitIdle $src 60 }
  $d = $null; for ($k = 0; $k -lt 5 -and -not $d; $k++) { try { $d = $app.Documents.Open((PathOf $p.doc), $false) } catch { Log "  open retry: $($_.Exception.Message)"; Start-Sleep 10 } }
  if ($d.Name -ne $p.doc) { Log "  ERROR opened [$($d.Name)]"; break }
  $d.Activate(); WaitIdle $d 120
  if (-not $loaded) { $d.SendCommand("NETLOAD`n$PSScriptRoot\CtDraw2.dll`n"); Start-Sleep 8; $loaded = $true }
  $n0 = $d.ModelSpace.Count
  if ($ClearDoc -and $p.doc -eq $ClearDoc) {
    $d.SendCommand("CTCLEARL`n" + ($cfg.clear2000 -join '|') + "`n"); WaitIdle $d 120
    Log "  cleared: $($d.ModelSpace.Count - $n0)"; $n0 = $d.ModelSpace.Count
  }
  if ($needTray) {
    $ci = [Globalization.CultureInfo]::InvariantCulture
    $d.SendCommand("CTCOPYD`n$SRC|$TRAY|" + (-[double]$p.off[0]).ToString($ci) + "," + (-[double]$p.off[1]).ToString($ci) + "`n"); WaitIdle $d 300
    Log "  tray+panels copied: $($d.ModelSpace.Count - $n0)"; $n0 = $d.ModelSpace.Count
  }
  $d.SendCommand("CTDRAW2`n$($p.tsv -replace '/','\')`n"); WaitIdle $d 120
  Log "  routes drawn: $($d.ModelSpace.Count - $n0) / $($p.n)"
  $d.Save(); WaitIdle $d 300; $d.Close($false); Start-Sleep 2
  if ($src) { $src.Close($false); Start-Sleep 2 }
  $p.doc | Out-File "$s\draw_done.txt" -Append -Encoding ascii
  Log "  saved + closed"
}
Log "DONE"
