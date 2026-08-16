@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================
echo   ReefPal 海水缸助手 - 启动
echo ================================
echo.
echo  本机访问:  http://localhost:8000
echo  手机访问:  手机连同一WiFi后打开 http://本机IP:8000
echo  查本机IP:  ipconfig   (IPv4 地址那一行)
echo.
echo  按 Ctrl+C 停止服务
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
