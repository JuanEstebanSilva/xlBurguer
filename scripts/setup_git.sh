#!/usr/bin/env bash
# Script de sincronización Git para XL Burguer (Bash)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "Verificando repositorio Git en: $PROJECT_ROOT"
if [ ! -d ".git" ]; then
    git init
fi

git branch -M main

if git remote | grep -q "origin"; then
    git remote set-url origin https://github.com/JuanEstebanSilva/xlBurguer.git
else
    git remote add origin https://github.com/JuanEstebanSilva/xlBurguer.git
fi

git add .
if ! git diff-index --quiet HEAD --; then
    git commit -m "feat: transformacion integral a XL Burguer POS"
else
    echo "No hay cambios pendientes para commit."
fi

echo "Sincronizando con repositorio remoto https://github.com/JuanEstebanSilva/xlBurguer.git..."
git push -u origin main

echo "Repositorio sincronizado exitosamente con GitHub."
