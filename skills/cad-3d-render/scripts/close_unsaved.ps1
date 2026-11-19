$app=[Runtime.InteropServices.Marshal]::GetActiveObject('Icad.Application')
$docs=@(); foreach($d in $app.Documents){ $docs+=$d }
foreach($d in $docs){ if(-not $d.FullName -or $d.FullName -eq '' -or $d.Name -match '^Drawing'){ "closing $($d.Name)"; $d.Close($false) } }
