param([int]$Rate = 1)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$taskSpec=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'narration.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$taskSpeech=[System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $taskSpeech.SelectVoice($taskSpec.voice)
    $taskSpeech.Rate=$Rate
    $taskSpeech.Volume=100
    foreach($taskScene in $taskSpec.scenes){
        $taskSpeech.SetOutputToWaveFile((Join-Path $PSScriptRoot ($taskScene.id+'.wav')))
        $taskSpeech.Speak($taskScene.text)
        $taskSpeech.SetOutputToNull()
    }
} finally {$taskSpeech.Dispose()}
Write-Output '分段旁白已生成。'
