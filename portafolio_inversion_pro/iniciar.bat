@echo off
chcp 65001 > nul
title Inversión Pro — Sistema de Portafolios

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║     INVERSIÓN PRO — Iniciando...         ║
echo  ╚══════════════════════════════════════════╝
echo.

cd /d "C:\Users\Grupo QAB\Desktop\Andrea\Portafolio"

:: Verificar Python
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+
    pause
    exit /b 1
)

:: Instalar dependencias si no están
echo [INFO] Verificando dependencias...
pip install -r requirements.txt -q --disable-pip-version-check

:: Crear directorios necesarios
if not exist instance mkdir instance
if not exist logs mkdir logs

echo [INFO] Iniciando servidor en http://localhost:5000
echo [INFO] Admin por defecto: admin@portafolio.com / admin123
echo [INFO] Presiona Ctrl+C para detener
echo.

python app.py

pause
