# Pollen WASM Integration

This directory contains the wrapper logic required to bridge our LLM inference payloads with the Pollen execution environment.

## Extism WASM Wrapper (`wasm_wrapper.go`)

Pollen invokes WASM seeds using the [Extism](https://extism.org/) framework. Our wrapper (`wasm_wrapper.go`) acts as the entrypoint for the `llama-cpp-wasm` engine when running inside the Pollen mesh.

### How it works:
1. **Pollen Call:** An agent uses the mesh to trigger `pln call llm_engine run_inference '{"prompt": "Hello", "max_tokens": 50}'`.
2. **Input Processing:** The `run_inference` function uses the Extism PDK to read the JSON bytes from the Pollen host.
3. **Engine Execution:** The wrapper feeds the prompt into the compiled `llama.cpp` WASM bindings.
4. **Output Emission:** The generated tokens are buffered and sent back to the Pollen host via `pdk.Output()`, which streams the response back across the QUIC transport to the requesting Keystone agent.

### Compilation
To compile this wrapper for the Pollen mesh, use TinyGo:
```bash
tinygo build -o dist/wasm_llm/llm_wrapper.wasm -target wasi src/pollen_integration/wasm_wrapper.go
```
