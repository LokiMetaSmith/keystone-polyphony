#!/usr/bin/env bash
set -e

# Build script to pull down llama-cpp-wasm and compile it for Pollen

echo ">>> Setting up WASM LLM Engine build environment..."

WORK_DIR=$(mktemp -d)
DEST_DIR="$(pwd)/dist/wasm_llm"

echo ">>> Working directory: $WORK_DIR"
cd "$WORK_DIR"

# Step 1: Install Emscripten SDK if not present in path
if ! command -v emcc &> /dev/null; then
    echo ">>> Emscripten (emcc) not found in PATH. Installing emsdk..."
    git clone https://github.com/emscripten-core/emsdk.git
    cd emsdk
    ./emsdk install latest
    ./emsdk activate latest
    source ./emsdk_env.sh
    cd ..
else
    echo ">>> Emscripten found."
fi

# Step 2: Clone llama-cpp-wasm
echo ">>> Cloning tangledgroup/llama-cpp-wasm..."
git clone https://github.com/tangledgroup/llama-cpp-wasm.git
cd llama-cpp-wasm

# Step 3: Build Single-Threaded (safest baseline for generic Pollen WASM)
echo ">>> Building single-threaded WASM inference engine..."
# Ensure execution permissions
chmod +x build-single-thread.sh
./build-single-thread.sh

# Step 4: Extract the goods
echo ">>> Copying compiled WASM artifacts to destination..."
mkdir -p "$DEST_DIR"
cp -r dist/llama-st/* "$DEST_DIR/"

echo ">>> Cleaning up..."
rm -rf "$WORK_DIR"

echo ">>> Done! The WASM inference payload is ready at $DEST_DIR"
echo ">>> To deploy to Pollen, run: pln seed $DEST_DIR/llama.js llama-inference"
