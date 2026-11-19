# Recalculate an SOL workbook in Excel (COM) and report formula errors + SUMMARY checks (cables A+B, conduits C).
# usage: powershell -File check_sol.ps1 "C:\path\file.xlsx"   (opens a copy-free read; never saves)
param([Parameter(Mandatory=$true)][string]$Path)
$xl = New-Object -ComObject Excel.Application; $xl.Visible = $false; $xl.DisplayAlerts = $false
try {
  $wb = $xl.Workbooks.Open((Resolve-Path $Path).Path, 0, $true); $xl.CalculateFull()
  $errs = 0
  foreach ($sh in $wb.Worksheets) { foreach ($c in $sh.UsedRange.Cells) {
    if ($c.HasFormula -and ($c.Text -like "#*")) { $errs++; if ($errs -le 10) { "ERR " + $sh.Name + "!" + $c.Address(0,0) + " " + $c.Text } } } }
  "formula errors = $errs"
  $cs = $wb.Worksheets.Item("SUMMARY"); $n = $cs.UsedRange.Rows.Count + $cs.UsedRange.Row
  $tot = $null; $chk = $null; $dif = $null; $ctot = $null; $cdif = $null
  for ($r = 4; $r -le $n; $r++) { $b = $cs.Cells.Item($r, 2).Text
    if ($b -like "*TOTAL (A + B)*") { $tot = $r } elseif ($b -like "*(AI+AJ+AK)*") { $chk = $r } elseif ($b -like "*Difference*") { if ($dif) { $cdif = $r } else { $dif = $r } } elseif ($b -like "*SOL (AB)*") { $ctot = $r } }  # ASCII only: PS 5.1 misreads UTF-8 without BOM
  "blank lengths: total=" + $cs.Cells.Item($tot,4).Text + " (must be 0)"
  # put a test length on the first way row that has a cable, recalc, confirm summary follows and diff = 0
  $ws = $wb.Worksheets.Item("SOL"); $last = $ws.UsedRange.Rows.Count + 5
  for ($r = 6; $r -le $last; $r++) { if ($ws.Cells.Item($r, 19).Text -and ($ws.Cells.Item($r,1).Text -ne "INCOMING")) { break } }
  $ws.Cells.Item($r, 29).Value2 = 50
  $ws.Cells.Item($r, 27).Value2 = $cs.Cells.Item($ctot - 2, 2).Text; $ws.Cells.Item($r, 28).Value2 = 7; $xl.CalculateFull()   # last conduit type + 7 m
  "test AC$r=50 -> AI=" + $ws.Cells.Item($r, 35).Text + "  total=" + $cs.Cells.Item($tot,4).Text + "  check=" + $cs.Cells.Item($chk,4).Text + "  diff=" + $cs.Cells.Item($dif,4).Text + " (must be 0)"
  "test AB$r=7 (" + $cs.Cells.Item($ctot - 2, 2).Text + ") -> conduit check=" + $cs.Cells.Item($ctot,4).Text + "  diff=" + $cs.Cells.Item($cdif,4).Text + " (must be 0)"
  $wb.Close($false)
} finally { $xl.Quit(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) }
