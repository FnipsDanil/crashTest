#!/bin/bash

# Example configuration for remote_run_gift_sender.sh
# Copy this file to remote_config.sh and modify the values

# Remote server configuration
export REMOTE_HOST="your_server_ip_or_domain"
export REMOTE_USER="your_username"
export REMOTE_PATH="/home/your_username/crash-stars-game/gift-sender"

# SSH configuration (optional)
export SSH_KEY_PATH="~/.ssh/id_rsa"  # Path to your SSH private key

# Alternative: use SSH config instead
# Make sure you have an entry in ~/.ssh/config like:
# Host crash-server
#     HostName your_server_ip
#     User your_username
#     IdentityFile ~/.ssh/your_key
#     Port 22
# 
# Then you can set:
# export REMOTE_HOST="crash-server"
# export REMOTE_USER=""  # Leave empty when using SSH config