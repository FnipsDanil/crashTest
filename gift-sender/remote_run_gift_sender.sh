#!/bin/bash

# Remote Gift Sender Runner
# This script connects to remote server, runs gift sender, and shows logs

# Load configuration from remote_config.sh if it exists
if [ -f "remote_config.sh" ]; then
    echo "📋 Loading configuration from remote_config.sh..."
    source remote_config.sh
else
    echo "⚠️ No remote_config.sh found. Please create it based on remote_config.example.sh"
    echo "Using default configuration (you should modify this script):"
    
    # Default configuration - modify these variables for your setup
    REMOTE_HOST="your_server_ip"
    REMOTE_USER="your_username"
    REMOTE_PATH="/path/to/crash-stars-game/gift-sender"
    SSH_KEY_PATH="~/.ssh/id_rsa"  # Optional: specify SSH key path
fi

echo "🌐 Connecting to remote server..."
echo "Host: $REMOTE_USER@$REMOTE_HOST"
echo "Path: $REMOTE_PATH"
echo "=================================="

# Build SSH command based on configuration
SSH_CMD_ARGS=""
if [ -n "$SSH_KEY_PATH" ]; then
    SSH_CMD_ARGS="-i $SSH_KEY_PATH"
fi

if [ -n "$REMOTE_USER" ]; then
    SSH_TARGET="$REMOTE_USER@$REMOTE_HOST"
else
    SSH_TARGET="$REMOTE_HOST"
fi

# SSH command to run gift sender remotely
ssh $SSH_CMD_ARGS "$SSH_TARGET" << EOF
    echo "📂 Navigating to gift sender directory..."
    cd "$REMOTE_PATH" || { echo "❌ Failed to navigate to $REMOTE_PATH"; exit 1; }
    
    echo "🚀 Starting Gift Sender on remote server..."
    echo "Current directory: \$(pwd)"
    echo "=================================="
    
    # Run the gift sender
    ./run_gift_sender.sh
    
    echo ""
    echo "📋 Recent logs from gift sender:"
    echo "=================================="
    
    # Show recent logs if they exist
    if [ -f "logs/gift_sender.log" ]; then
        echo "📄 Showing last 50 lines of gift_sender.log:"
        tail -n 50 logs/gift_sender.log
    else
        echo "⚠️ No logs found in logs/gift_sender.log"
    fi
    
    echo ""
    echo "🐳 Docker container logs:"
    echo "=================================="
    docker logs gift-sender --tail 20 2>/dev/null || echo "⚠️ No docker logs available"
    
    echo ""
    echo "✅ Remote gift sender execution completed!"
EOF

echo ""
echo "🏁 Remote execution finished. Check output above for results."