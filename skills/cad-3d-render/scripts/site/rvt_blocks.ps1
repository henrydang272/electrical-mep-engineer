param([string]$Path, [string]$Out)
$app = [Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application')
$doc = $app.Documents.Open($Path, $true)
$o = New-Object Collections.Generic.List[string]
foreach ($e in @($doc.ModelSpace)) {
  if ($e.EntityName -eq 'BlockInsert' -and $e.Name -match 'rvt' -and $e.Name -match '(04B|M01|M02|UD1|06B|17B|057)') {
    $p = $e.InsertionPoint; $o.Add("INS|$($e.Name)|$($p.X)|$($p.Y)|$($e.Rotation)|$($e.XScaleFactor)")
    foreach ($b in $doc.Blocks.Item($e.Name)) {
      if ($b.EntityName -eq 'Line') { $a = $b.StartPoint; $c = $b.EndPoint; $o.Add("L|$($e.Name)|$($b.Layer)|$($a.X)|$($a.Y)|$($c.X)|$($c.Y)") }

    }
  }
}
$o | Set-Content -Encoding utf8 $Out
$doc.Close($false); "done $($o.Count)"
