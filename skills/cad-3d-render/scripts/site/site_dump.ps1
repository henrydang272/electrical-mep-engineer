$app=[Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application')
foreach($d in $app.Documents){ if($d.Name -like '*000-XX-DR-A-2001*'){ $doc=$d } }
$o=New-Object System.Collections.Generic.List[string]
$R={ param($v) [math]::Round([double]$v,2) }
function Dump($ents,$tag){
 foreach($e in $ents){
  switch($e.EntityName){
   'LightWeightPolyline' { $s=@(); foreach($q in $e.Coordinates){ $s+="$(& $R $q.X),$(& $R $q.Y)" }; $o.Add("$tag|P|$($e.Layer)|$($e.Closed)|$($s -join ' ')") }
   'Line' { $a=$e.StartPoint;$b=$e.EndPoint; $o.Add("$tag|L|$($e.Layer)|$(& $R $a.X),$(& $R $a.Y) $(& $R $b.X),$(& $R $b.Y)") }
   'Arc' { $c=$e.Center; $o.Add("$tag|A|$($e.Layer)|$(& $R $c.X),$(& $R $c.Y)|$(& $R $e.Radius)|$(& $R $e.StartAngle)|$(& $R $e.EndAngle)") }
   'Circle' { $c=$e.Center; $o.Add("$tag|C|$($e.Layer)|$(& $R $c.X),$(& $R $c.Y)|$(& $R $e.Radius)") }
   { $_ -in 'Mtext','Text' } { $p=$e.InsertionPoint; $t=($e.TextString -replace '\[A-Za-z][^;]*;','' -replace '[{}]','' -replace '\s+',' '); $o.Add("$tag|T|$($e.Layer)|$(& $R $p.X),$(& $R $p.Y)|$t") }
   'Hatch' { try { $o.Add("$tag|H|$($e.Layer)|$($e.PatternName)|$($e.NumberOfLoops)") } catch {} }
   'BlockInsert' { $p=$e.InsertionPoint; $o.Add("$tag|B|$($e.Layer)|$(& $R $p.X),$(& $R $p.Y)|$($e.Name)") }
  }
 }
}
Dump $doc.Blocks.Item('PRJ-MASTER PLAN_dwg-5045969-site plan') 'MP'
Dump $doc.ModelSpace 'MS'
foreach($bn in @('Family - ___-V4-site plan','Family - ___-V5-site plan')){ Dump $doc.Blocks.Item($bn) 'SB' }
[IO.File]::WriteAllLines($args[0],$o); "wrote $($o.Count)"
