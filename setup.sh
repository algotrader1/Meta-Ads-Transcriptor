#!/bin/bash
# Script d'installation des dépendances

echo "🔧 Installation des dépendances pour Facebook Ads Transcript Tool"
echo "=================================================================="

# Vérifier si Homebrew est installé (macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew non installé. Installation..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    # Installer ffmpeg
    echo "📦 Installation de ffmpeg..."
    brew install ffmpeg

fi

# Créer un environnement virtuel Python
echo "🐍 Création de l'environnement virtuel..."
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances Python
echo "📦 Installation des packages Python..."
pip install --upgrade pip
pip install yt-dlp openai-whisper

echo ""
echo "✅ Installation terminée!"
echo ""
echo "Pour utiliser le script:"
echo "  1. Activer l'environnement: source venv/bin/activate"
echo "  2. Lancer le script: python transcript_ads.py"
echo ""
