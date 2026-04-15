# feifei-tts.ps1 - 菲菲语音合成 PowerShell 包装脚本
# 用法: .\feifei-tts.ps1 -Text "你好呀，我是菲菲~" [-Voice gentle] [-NoPlay]

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Text,

    [Parameter(Position=1)]
    [ValidateSet("default", "gentle", "mature", "night")]
    [string]$Voice = "default",

    [switch]$NoPlay
)

$ErrorActionPreference = "Stop"

# 菲菲语音配置
$VoiceConfigs = @{
    "default" = @{ Voice="zh-CN-XiaoxiaoNeural"; Rate="-10%"; Pitch="+5Hz"; Desc="晓晓-活泼温柔少女音" }
    "gentle"  = @{ Voice="zh-CN-XiaoyiNeural";  Rate="-15%"; Pitch="+3Hz"; Desc="晓伊-温暖柔和少女音" }
    "mature"  = @{ Voice="zh-CN-XiaobeiNeural"; Rate="-10%"; Pitch="0Hz";  Desc="晓北-知性温柔姐姐音" }
    "night"   = @{ Voice="zh-CN-XiaoxiaoNeural"; Rate="-25%"; Pitch="-8Hz"; Desc="晓晓-低沉夜话音" }
}

$cfg = $VoiceConfigs[$Voice]

$tmpDir = $env:TEMP
$tmpFile = Join-Path $tmpDir "feifei_$(Get-Random).mp3"

Write-Host "菲菲 TTS" -ForegroundColor Cyan
Write-Host "  文本: $($Text.Substring(0, [Math]::Min(50, $Text.Length)))${if($Text.Length -gt 50){'...'}}" -ForegroundColor Gray
Write-Host "  语音: $($cfg.Desc)" -ForegroundColor Gray
Write-Host "  语速: $($cfg.Rate)  音调: $($cfg.Pitch)" -ForegroundColor Gray

try {
    $pythonCmd = "python"
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        $pythonCmd = "python3"
    }

    $scriptPath = Join-Path $PSScriptRoot "feifei-tts.py"
    if (-not (Test-Path $scriptPath)) {
        $scriptPath = Join-Path $PSScriptRoot "soul-companion\scripts\feifei-tts.py"
    }
    if (-not (Test-Path $scriptPath)) {
        $scriptPath = Join-Path $env:USERPROFILE ".claude\skills\soul-companion\scripts\feifei-tts.py"
    }

    $args = @(
        "--voice-name", $Voice,
        "--no-play",
        $Text
    )

    if ($NoPlay) {
        $args = @("--no-play") + $args
    }

    $env:PYTHONIOENCODING = "utf-8"

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $pythonCmd
    $psi.Arguments = "`"$scriptPath`" $Text --voice-name `"$Voice`" --no-play"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.SetEnvironmentVariable("PYTHONIOENCODING", "utf-8")

    $proc = Start-Process -FilePath $pythonCmd -ArgumentList "`"$scriptPath`"", $Text, "--voice-name", $Voice, "--no-play" -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$tmpDir\feifei_out.txt" -RedirectStandardError "$tmpDir\feifei_err.txt"

    $out = Get-Content "$tmpDir\feifei_out.txt" -Raw -ErrorAction SilentlyContinue
    $err = Get-Content "$tmpDir\feifei_err.txt" -Raw -ErrorAction SilentlyContinue

    if ($out) { Write-Host $out }
    if ($err -and $err -notmatch "^$") { Write-Host $err -ForegroundColor Yellow }

    Write-Host "OK: $tmpFile" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    exit 1
}
