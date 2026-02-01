#!/bin/bash
# =====================================================
# Local LLM Setup Script for Stock Analyzer
# =====================================================
#
# This script installs and configures Ollama for
# AI-powered stock analysis.
#
# Usage:
#   chmod +x setup_local_llm.sh
#   ./setup_local_llm.sh
#
# =====================================================

set -e

echo "========================================"
echo "🤖 Local LLM Setup for Stock Analyzer"
echo "========================================"
echo

# Check if Ollama is installed
if command -v ollama &> /dev/null; then
    echo "✅ Ollama is already installed"
    ollama --version
else
    echo "📦 Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "✅ Ollama installed"
fi

echo

# Check if Ollama is running
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama is running"
else
    echo "🚀 Starting Ollama server..."
    ollama serve &
    sleep 3
    echo "✅ Ollama server started"
fi

echo

# Pull recommended models
echo "📥 Pulling recommended models..."
echo

# Fast model for quick analysis
echo "1/3 Pulling llama3.2:1b (fast, ~1GB)..."
ollama pull llama3.2:1b

echo

# Balanced model
echo "2/3 Pulling llama3.2:3b (balanced, ~2GB)..."
ollama pull llama3.2:3b

echo

# Optional: Best model (larger)
read -p "Do you want to install the best model (mistral:7b, ~4GB)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "3/3 Pulling mistral:7b (best quality, ~4GB)..."
    ollama pull mistral:7b
else
    echo "Skipping mistral:7b"
fi

echo
echo "========================================"
echo "✅ Setup Complete!"
echo "========================================"
echo
echo "Available models:"
ollama list
echo
echo "To test the integration:"
echo "  python src/local_llm/ollama_client.py"
echo
echo "To use in stock analyzer:"
echo "  from local_llm import StockAnalyzerLLM"
echo "  analyzer = StockAnalyzerLLM()"
echo "  result = analyzer.analyze_stock('NVDA', price=140)"
echo
echo "========================================"
