@echo off
echo ================================================
echo   DubFlow - YouTube Dubbing Pipeline
echo ================================================
echo.
echo Installation des dependances...
pip install -r requirements.txt --quiet
echo.
echo Lancement du serveur...
python app.py
pause
