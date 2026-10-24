param(
  [Parameter(Mandatory=$true)][string]$PptxPath,
  [Parameter(Mandatory=$true)][string]$WorkDir,
  [ValidateSet('Render','ExportPdf','Editability')][string]$Mode = 'Render',
  [string]$PdfPath
)
$ErrorActionPreference = 'Stop'
$pptApplication = $null
$deckPresentation = $null
$originalPresentationCount = 0
$renderDir = Join-Path $WorkDir 'rendered'
New-Item -ItemType Directory -Path $renderDir -Force | Out-Null
if ($Mode -eq 'ExportPdf') {
  if (-not $PdfPath) { throw 'PdfPath is required.' }
  $proofPath=Join-Path $WorkDir 'proof.html'
  if (-not (Test-Path -LiteralPath $proofPath)) { throw 'Generate and inspect the HTML proof before PDF export.' }
  $edgePath=Join-Path ${env:ProgramFiles(x86)} 'Microsoft/Edge/Application/msedge.exe'
  if (-not (Test-Path -LiteralPath $edgePath)) { throw 'Microsoft Edge was not found.' }
  $pdfAbsolutePath=[System.IO.Path]::GetFullPath($PdfPath)
  $proofUri=[System.Uri]::new([System.IO.Path]::GetFullPath($proofPath)).AbsoluteUri
  $profilePath=Join-Path $WorkDir 'edge-pdf-profile'
  $edgeArguments=@('--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--no-pdf-header-footer','--allow-file-access-from-files','--disable-features=AutofillAiWalletPrivatePasses',"--user-data-dir=`"$profilePath`"","--print-to-pdf=`"$pdfAbsolutePath`"",$proofUri)
  $edgeProcess=Start-Process -FilePath $edgePath -ArgumentList $edgeArguments -WindowStyle Hidden -PassThru
  $exported=$false
  for ($attempt=0;$attempt -lt 60;$attempt++) {
    Start-Sleep -Milliseconds 500
    if ((Test-Path -LiteralPath $pdfAbsolutePath) -and (Get-Item -LiteralPath $pdfAbsolutePath).Length -gt 0) { $exported=$true; break }
  }
  if (-not $exported) { throw 'HTML PDF export did not produce a file within 30 seconds.' }
  Write-Output "Exported HTML proof to $pdfAbsolutePath"
  return
}
try {
  $pptApplication = New-Object -ComObject PowerPoint.Application
  $originalPresentationCount = $pptApplication.Presentations.Count
  if ($Mode -eq 'Editability') {
    $copyPath = Join-Path $WorkDir 'build/editability-check.pptx'
    Copy-Item -LiteralPath $PptxPath -Destination $copyPath -Force
    $deckPresentation = $pptApplication.Presentations.Open($copyPath,0,0,0)
    $tableShape = $null
    foreach ($shape in $deckPresentation.Slides.Item(4).Shapes) {
      if ($shape.HasTable -eq -1) { $tableShape=$shape; break }
    }
    if ($null -eq $tableShape) { throw 'Slide 4 has no native table.' }
    $tableShape.Table.Cell(2,1).Shape.TextFrame.TextRange.Text = 'Editable table check'
    $chartChanges = @()
    foreach ($slideNumber in @(7,8)) {
      $chartShape = $null
      foreach ($shape in $deckPresentation.Slides.Item($slideNumber).Shapes) {
        if ($shape.HasChart -eq -1) { $chartShape=$shape; break }
      }
      if ($null -eq $chartShape) { throw "Slide $slideNumber has no native chart." }
      $width = $chartShape.Width
      $chartShape.Width = $width + 6
      $chartShape.Chart.HasTitle = -1
      $chartShape.Chart.ChartTitle.Text = "Editable chart check $slideNumber"
      $chartChanges += @{slide=$slideNumber;width=($width+6);title="Editable chart check $slideNumber"}
    }
    $deckPresentation.Save()
    $deckPresentation.Close()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($deckPresentation)
    $deckPresentation = $pptApplication.Presentations.Open($copyPath,-1,0,0)
    $tableVerified = $false
    foreach ($shape in $deckPresentation.Slides.Item(4).Shapes) {
      if ($shape.HasTable -eq -1) { $tableVerified=$shape.Table.Cell(2,1).Shape.TextFrame.TextRange.Text -eq 'Editable table check'; break }
    }
    $verified = @()
    foreach ($change in $chartChanges) {
      foreach ($shape in $deckPresentation.Slides.Item($change.slide).Shapes) {
        if ($shape.HasChart -eq -1) {
          $verified += @{slide=$change.slide;title_saved_reopened=($shape.Chart.ChartTitle.Text -eq $change.title);resize_saved_reopened=([Math]::Abs($shape.Width-$change.width) -lt 0.1)}
          break
        }
      }
    }
    $passed=$tableVerified -and @($verified | Where-Object {-not ($_.title_saved_reopened -and $_.resize_saved_reopened)}).Count -eq 0
    @{engine='Microsoft PowerPoint COM';version=$pptApplication.Version;table_slide_4_edit_saved_reopened=$tableVerified;charts=$verified;passed=$passed;test_copy=$copyPath;final_file_unchanged=$true} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $WorkDir 'editability.json') -Encoding utf8
    if (-not $passed) { throw 'Native editability verification failed.' }
    Write-Output 'Native table and both native charts saved and reopened after test edits.'
  } else {
    $deckPresentation = $pptApplication.Presentations.Open($PptxPath,-1,0,0)
    & {
      $slides=@()
      $overflow=@()
      for ($number=1;$number -le $deckPresentation.Slides.Count;$number++) {
        $slide=$deckPresentation.Slides.Item($number)
        $fileName='slide-{0:d2}.png' -f $number
        $slide.Export((Join-Path $renderDir $fileName),'PNG',1920,1080)
        $texts=@()
        $charts=0
        $tables=0
        foreach ($shape in $slide.Shapes) {
          if ($shape.HasTable -eq -1) { $tables++ }
          if ($shape.HasChart -eq -1) { $charts++ }
          if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
            $text=$shape.TextFrame.TextRange.Text
            $texts += $text
            $boundHeight=$shape.TextFrame2.TextRange.BoundHeight
            $boundWidth=$shape.TextFrame2.TextRange.BoundWidth
            if ($boundHeight -gt ($shape.Height+1) -or $boundWidth -gt ($shape.Width+1)) {
              $overflow += @{slide=$number;name=$shape.Name;text=$text;shape_width=$shape.Width;shape_height=$shape.Height;bound_width=$boundWidth;bound_height=$boundHeight}
            }
          }
        }
        $slides += @{slide=$number;image="rendered/$fileName";native_charts=$charts;native_tables=$tables;text=$texts}
        Write-Output "Rendered slide $number"
      }
      $fonts=@()
      for ($number=1;$number -le $deckPresentation.Fonts.Count;$number++) { $fonts += $deckPresentation.Fonts.Item($number).Name }
      @{engine='Microsoft PowerPoint COM';version=$pptApplication.Version;source=$PptxPath;slide_count=$deckPresentation.Slides.Count;fonts=$fonts;slides=$slides;text_bounds_findings=$overflow} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $WorkDir 'powerpoint-render.json') -Encoding utf8
      $sections=($slides | ForEach-Object { '<section><img src="{0}" alt="Slide {1}"></section>' -f $_.image,$_.slide }) -join "`n"
      $html=@"
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Meiyu Prepare pitch proof</title>
<style>html,body{margin:0;background:#dfe5db}section{width:1280px;height:720px;margin:24px auto;background:#f3f2e9;break-after:page}img{display:block;width:1280px;height:720px}@page{size:13.333333in 7.5in;margin:0}@media print{html,body{background:white}section{margin:0}}</style>
</head><body>
$sections
</body></html>
"@
      Set-Content -LiteralPath (Join-Path $WorkDir 'proof.html') -Value $html -Encoding utf8
      Write-Output 'Created proof.html. Inspect every slide and its formulas before exporting PDF.'
    }
  }
}
finally {
  if ($null -ne $deckPresentation) { $deckPresentation.Close(); [void][Runtime.InteropServices.Marshal]::ReleaseComObject($deckPresentation) }
  if ($null -ne $pptApplication) {
    if ($originalPresentationCount -eq 0) { $pptApplication.Quit() }
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($pptApplication)
  }
}
