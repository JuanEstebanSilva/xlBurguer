# Script de sincronización Git para XL Burguer (PowerShell)
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Verificando repositorio Git en: $projectRoot" -ForegroundColor Cyan

if (-not (Test-Path -Path ".git")) {
    git init
}

git branch -M main

$remoteExists = git remote
if ($remoteExists -contains "origin") {
    git remote set-url origin https://github.com/JuanEstebanSilva/xlBurguer.git
} else {
    git remote add origin https://github.com/JuanEstebanSilva/xlBurguer.git
}

git add .
$status = git status --porcelain
if ($status) {
    git commit -m "feat: transformacion integral a XL Burguer POS"
} else {
    Write-Host "No hay cambios pendientes para commit." -ForegroundColor Gray
}

Write-Host "Sincronizando con repositorio remoto https://github.com/JuanEstebanSilva/xlBurguer.git..." -ForegroundColor Yellow
git push -u origin main

Write-Host "Repositorio sincronizado exitosamente con GitHub." -ForegroundColor Green
