#!/bin/bash
set -e

echo "=== Removing old Docker versions (if any) ==="
sudo apt-get remove -y docker docker-engine docker.io containerd runc || true

echo "=== Updating package index and installing prerequisites ==="
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common

echo "=== Adding Docker GPG key ==="
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo "=== Adding Docker repository ==="
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
$(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "=== Updating package index again ==="
sudo apt-get update

echo "=== Installing Docker packages ==="
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "=== Adding current user to docker group (optional) ==="
sudo usermod -aG docker $USER
echo "You may need to log out and back in for group changes to take effect."

echo "=== Verifying Docker installation ==="
sudo docker run --rm hello-world

echo "=== Docker installation complete! ==="
