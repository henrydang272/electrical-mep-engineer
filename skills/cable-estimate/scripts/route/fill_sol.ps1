# fill_sol.ps1 -Sol <SOL.xlsx> -Plan <fill_plan.json>
# Writes AA (conduit type), AB (conduit m, formula), AC (Hor., number), AD (Ver., formula) and appends AL remark.
# TQ rows: AA..AD cleared, remark "TQ: ...". Backup <SOL>.bak_<time>.xlsx first. Works on the open workbook if Excel has it.
param([Parameter(Mandatory)][string]$Sol, [Parameter(Mandatory)][string]$Plan)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path $Sol).Path
Copy-Item $root ($root -replace '\.xlsx$', ".bak_$(Get-Date -Format yyyyMMdd_HHmm).xlsx")
$plan = Get-Content $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
$xl = $null; try { $xl = [Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application') } catch {}
$wb = $null; $own = $false
if ($xl) { foreach ($w in $xl.Workbooks) { if ($w.FullName -eq $root) { $wb = $w } } }
if (-not $wb) { $xl = New-Object -ComObject Excel.Application; $xl.Visible = $false; $xl.DisplayAlerts = $false; $wb = $xl.Workbooks.Open($root); $own = $true }
try {
  $ws = $wb.Worksheets.Item('SOL'); $n = 0
  foreach ($p in $plan.PSObject.Properties) {
    $r = [int]$p.Name; $v = $p.Value
    $al = [string]$ws.Range("AL$r").Value2
    if ($v.TQ) {
      $note = $v.TQ
      $ws.Range("AA${r}:AD${r}").ClearContents() | Out-Null   # TQ rows stay blank (no estimates)
      $al = (($al -split ' \| ') | Where-Object { $_ -and $_ -notmatch ('^' + [char]0x01AF) }) -join ' | '   # drop old "UOC TINH" remark
      $ws.Range("AL$r").Value2 = $al
    }
    else {
      if (-not $v.force -and [string]$ws.Range("AC$r").Formula -ne '') { continue }   # overwrite only rows this tool filled
      $ws.Range("AA$r").Value2 = $v.AA
      $ws.Range("AB$r").Formula = $v.AB
      $ws.Range("AC$r").Value2 = [double]$v.AC
      $ws.Range("AD$r").Formula = $v.AD
      $note = $v.note
    }
    if ($al -notlike "*$note*") { $ws.Range("AL$r").Value2 = $(if ($al) { "$al | $note" } else { $note }) }
    $n++
  }
  $xl.Calculate(); $wb.Save()
  "rows written: $n"
} finally { if ($own) { $wb.Close($false); $xl.Quit() } }
