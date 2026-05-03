#!/usr/bin/env bash
set -e

# Build script to pull down llama-cpp-wasm and compile it for Pollen

echo ">>> Setting up WASM LLM Engine build environment..."

# Get the absolute path to the repository root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_DIR="${REPO_ROOT}/dist/wasm_llm"

cd "$REPO_ROOT"

echo ">>> Initializing and updating git submodules..."
git submodule update --init --recursive

# Step 1: Install Emscripten SDK if not present in path
if ! command -v emcc &> /dev/null; then
    echo ">>> Emscripten (emcc) not found in PATH. Setting up emsdk from submodule..."
    cd third_party/emsdk
    ./emsdk install latest
    ./emsdk activate latest
    source ./emsdk_env.sh
    cd "$REPO_ROOT"
else
    echo ">>> Emscripten found."
fi

# Step 2: Build Single-Threaded (safest baseline for generic Pollen WASM)
echo ">>> Building single-threaded WASM inference engine from submodule..."
cd third_party/llama-cpp-wasm

# Ensure execution permissions
chmod +x build-single-thread.sh
./build-single-thread.sh

# Step 3: Extract the goods
echo ">>> Copying compiled WASM artifacts to destination..."
cd "$REPO_ROOT"
mkdir -p "$DEST_DIR"
cp -r third_party/llama-cpp-wasm/dist/llama-st/* "$DEST_DIR/"

echo ">>> Done! The WASM inference payload is ready at $DEST_DIR"
echo ">>> To deploy to Pollen, run: pln seed $DEST_DIR/llama.js llama-inference"
