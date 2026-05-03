# Hybrid WASM LLM Engine: Usage Guide

This guide explains how to deploy a fully decentralized, peer-to-peer AI inference pipeline by combining **Keystone Polyphony**'s agent orchestration with **Pollen**'s WASM compute fabric.

By following these steps, you can compile an LLM to WebAssembly, chunk and distribute its weights across a P2P mesh, and instruct Keystone agents to route inference tasks dynamically based on hardware topology.

## 1. Build the WASM Inference Engine

First, you need to compile the C++ LLM inference engine (`llama.cpp`) into a generic `.wasm` payload that Pollen can execute.

We provide an automated script that downloads the Emscripten SDK and builds the `tangledgroup/llama-cpp-wasm` repository:

```bash
./scripts/build_wasm_llm.sh
```

This will output the required WebAssembly files into the `dist/wasm_llm/` directory.

## 2. Distribute the Model Weights (GGUF)

Large Language Models (like Llama 3 `8B.gguf`) are too massive to transfer directly over standard WebSockets. Instead, we chunk them and distribute them over Pollen's content-addressed blob storage.

You can use the `ModelDistributor` utility to slice your `.gguf` file into 50MB chunks and generate a deployment script:

```python
from src.liminal_bridge.gguf_distributor import ModelDistributor

distributor = ModelDistributor(chunk_size_mb=50)
chunks = distributor.chunk_file("my_model.gguf", output_dir="./model_chunks")
manifest = distributor.generate_distribution_manifest("my_model.gguf", chunks, "./model_chunks/manifest.json")

# This creates a bash script full of `pln seed` commands
script_path = distributor.generate_pollen_seed_script("./model_chunks", chunks, "./model_chunks/manifest.json")
print(f"Run {script_path} to seed the model to the Pollen mesh!")
```

## 3. Plan Pipeline Parallelism (Model Sharding)

If your model is too large for a single node, you can split it horizontally across multiple nodes (Pipeline Parallelism).

The Keystone `Architect` can autonomously analyze a GGUF file and generate the exact mesh topology required:

```python
from src.liminal_bridge.architect import Architect
import asyncio

async def plan():
    architect = Architect()
    # Split the model across 4 nodes
    plan = await architect.plan_pipeline_parallelism("my_model.gguf", num_nodes=4)
    print(plan)

asyncio.run(plan())
```

This will output the specific `--prop pipeline_stage=X` tags you need to assign to your mesh nodes.

## 4. Launch Nodes with Topology Tags

When starting your Liminal Bridge nodes, use the `--prop` flag to advertise their hardware capabilities or their specific pipeline stage routing tags.

```bash
# Node 1: Fast GPU for heavy lifting
./polyphony start --mode daemon --prop role=gpu

# Node 2: Pipeline Stage 0
./polyphony start --mode daemon --prop pipeline_stage=0

# Node 3: Pipeline Stage 1
./polyphony start --mode daemon --prop pipeline_stage=1
```

## 5. Configure the Architect to Use Pollen

To tell Keystone to use your decentralized mesh instead of OpenAI or Anthropic, set the `DUCKY_MODEL` environment variable to use the `pollen:` prefix.

You can also explicitly define where the local Pollen gateway is running (it defaults to `http://localhost:3000`).

```bash
export DUCKY_MODEL="pollen:my_distributed_model"
export POLLEN_GATEWAY_URL="http://127.0.0.1:3000"

./polyphony start
```

## 6. Autonomous Agent Task Handoff

Once configured, your local agents (like Jules) don't need to do anything special. When the `LiminalMesh` decides a cognitive task is too heavy, it will broadcast a `run_inference` command targeting nodes with `pollen_compute` capabilities.

1. The target nodes intercept the command.
2. They execute the prompt against the WASM engine.
3. If they are engaged in Sequence Parallelism, they sync their context via the `DistributedKVCache` CRDT metadata.
4. They stream the final generated text back into the mesh as a "Thought", closing the loop for the initiating agent.

You now have a fully sovereign, decentralized AI pipeline!
