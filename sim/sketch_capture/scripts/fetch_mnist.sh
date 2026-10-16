#!/usr/bin/env bash
# One-time download of the MNIST test split (IDX format) into ~/datasets/mnist.
# Usage: scripts/fetch_mnist.sh [target_dir]
set -euo pipefail

BASE_URL="https://ossci-datasets.s3.amazonaws.com/mnist"
TARGET="${1:-$HOME/datasets/mnist}"
FILES=(t10k-images-idx3-ubyte t10k-labels-idx1-ubyte)

mkdir -p "$TARGET"

for name in "${FILES[@]}"; do
    if [ -f "$TARGET/$name" ]; then
        echo "have $name"
        continue
    fi
    echo "fetching $name.gz"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 -o "$TARGET/$name.gz" "$BASE_URL/$name.gz"
    else
        wget -O "$TARGET/$name.gz" "$BASE_URL/$name.gz"
    fi
    gunzip -f "$TARGET/$name.gz"
done

echo "MNIST test files are in $TARGET"
