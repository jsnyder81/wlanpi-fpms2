#!/bin/bash
#
# Remote build wrapper for wlanpi-fpms2
#
set -e

REMOTE_HOST="jakesnyder@192.168.5.14"
REMOTE_DIR="/tmp/wlanpi-fpms2-build"
DISTROS=("${@:-bullseye}")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "Starting Remote Build for ${DISTROS[*]}"
echo "Target: $REMOTE_HOST"
echo "========================================="

# Create remote directory first just in case
ssh -o StrictHostKeyChecking=no "$REMOTE_HOST" "mkdir -p $REMOTE_DIR"

echo "Step 1: Syncing files to remote host..."
# Exclude git, build artifacts, and existing debs to save bandwidth
rsync -avz --exclude '.git' --exclude '*.deb' --exclude 'build' --exclude 'dist' --exclude '.pybuild' \
    ./ "$REMOTE_HOST:$REMOTE_DIR/"

echo ""
echo "Step 2: Executing build on remote host..."
# Run the native build script on the remote ARM machine
ssh -o StrictHostKeyChecking=no "$REMOTE_HOST" "cd $REMOTE_DIR && ./build-package-native.sh ${DISTROS[*]}"

echo ""
echo "Step 3: Pulling built packages back to local machine..."
# Fetch the compiled .deb files
rsync -avz "$REMOTE_HOST:$REMOTE_DIR/*.deb" ./

echo ""
echo "========================================="
echo "Remote Build Complete!"
echo "Packages are now available in the current directory:"
ls -lh *.deb 2>/dev/null || echo "No .deb files found"
echo "========================================="
