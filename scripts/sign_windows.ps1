param(
    [Parameter(Mandatory = $true)]
    [string[]]$Files,
    [Parameter(Mandatory = $true)]
    [string]$CertificatePath,
    [Parameter(Mandatory = $true)]
    [string]$CertificatePassword
)

$signTool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if (-not $signTool) {
    throw "signtool.exe was not found"
}

foreach ($file in $Files) {
    & $signTool.FullName sign /fd SHA256 /td SHA256 /tr https://timestamp.digicert.com `
        /f $CertificatePath /p $CertificatePassword $file
    if ($LASTEXITCODE -ne 0) {
        throw "Signing failed: $file"
    }
    & $signTool.FullName verify /pa $file
    if ($LASTEXITCODE -ne 0) {
        throw "Signature verification failed: $file"
    }
}
