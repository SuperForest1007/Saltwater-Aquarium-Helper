@echo off
chcp 65001 >nul
echo ================================
echo  海水缸助手 - 功能测试
echo ================================
cd /d "%~dp0"

echo [1/2] 检查依赖...
python -c "import pytest" 2>nul || (echo 安装测试依赖... && python -m pip install pytest httpx)

echo [2/2] 运行测试...
python -m pytest
pause
