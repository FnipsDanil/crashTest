#!/bin/bash
# Script to run the gift sender in interactive mode connected to main Docker network
echo "🚀 Starting Interactive Gift Sender..."
# Create logs directory if it doesn't exist
mkdir -p logs
# Docker compose will build the image automatically
# Get the main network name
NETWORK_NAME="crash-stars-game_crash-stars-network"
# Check if network exists
if ! docker network ls | grep -q "$NETWORK_NAME"; then
    echo "❌ Network $NETWORK_NAME not found!"
    echo "💡 Make sure the main application is running: docker compose up -d"
    exit 1
fi
echo "🌐 Connecting to network: $NETWORK_NAME"
echo "📦 Starting interactive gift sender container..."
echo "⚠️  Use Ctrl+C to exit when done"
echo ""
# Run the gift sender using docker-compose with interactive mode
docker compose run --rm gift-sender
echo "✅ Gift Sender session ended."