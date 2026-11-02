# Script de sincronización Git para Carnicería San Diego (PowerShell)
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

Write-Host "Verificando repositorio Git en: $projectRoot" -ForegroundColor Cyan

if (-not (Test-Path -Path ".git")) {
    git init
}

git branch -M main

$remoteExists = git remote
if ($remoteExists -contains "origin") {
    git remote set-url origin https://github.com/juanSilvaE/sanDiego.git
} else {
    git remote add origin https://github.com/juanSilvaE/sanDiego.git
}

git add .
$status = git status --porcelain
if ($status) {
    git commit -m "feat: core pos, inventory, hardware layer and excel reporting for Carniceria San Diego"
} else {
    Write-Host "No hay cambios pendientes para commit." -ForegroundColor Gray
}

Write-Host "Sincronizando con repositorio remoto https://github.com/juanSilvaE/sanDiego.git..." -ForegroundColor Yellow
git push -u origin main

Write-Host "Repositorio sincronizado exitosamente con GitHub." -ForegroundColor Green
