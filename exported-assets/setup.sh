#!/bin/bash
# Bomberman+ Complete Automated System Setup

echo "=========================================="
echo "BOMBERMAN+ AUTOMATED GAME SYSTEM"
echo "=========================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi

echo "✓ Python 3 found"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo "✓ Dependencies installed"

echo ""
echo "=========================================="
echo "SETUP COMPLETE"
echo "=========================================="
echo ""
echo "To start the automated game engine:"
echo "  python3 game_engine.py"
echo ""
echo "To start the web visualizer:"
echo "  python3 web_visualizer.py"
echo "  (Then open http://localhost:5000)"
echo ""
echo "=========================================="
