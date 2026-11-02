#!/usr/bin/env bash
# Script de sincronización Git para Carnicería San Diego (Bash)

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
    git remote set-url origin https://github.com/juanSilvaE/sanDiego.git
else
    git remote add origin https://github.com/juanSilvaE/sanDiego.git
fi

git add .
if ! git diff-index --quiet HEAD --; then
    git commit -m "feat: core pos, inventory, hardware layer and excel reporting for Carnicería San Diego"
else
    echo "No hay cambios pendientes para commit."
fi

echo "Sincronizando con repositorio remoto https://github.com/juanSilvaE/sanDiego.git..."
git push -u origin main

echo "Repositorio sincronizado exitosamente con GitHub."
