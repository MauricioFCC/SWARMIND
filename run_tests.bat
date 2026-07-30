@echo off
title Swarmind - Quick Test Runner
cd /d "%~dp0"
uv run python scripts/launcher.py test
pause
