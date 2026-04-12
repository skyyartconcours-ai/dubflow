#!/bin/bash
echo "================================================"
echo "  DubFlow — YouTube Dubbing Pipeline"
echo "================================================"
echo ""
echo "Installation des dépendances..."
pip install -r requirements.txt --quiet
echo ""
echo "Lancement du serveur..."
python app.py
