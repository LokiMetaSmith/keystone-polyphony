#!/usr/bin/env python3
import os
import sys
import argparse

# Add the src directory to the python path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.liminal_bridge.gguf_sharder import GGUFSharder
from src.liminal_bridge.gguf_distributor import ModelDistributor


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a GGUF model for distribution across the Pollen Mesh."
    )
    parser.add_argument("model", type=str, help="Path to the .gguf model file")
    parser.add_argument(
        "--nodes",
        type=int,
        default=4,
        help="Number of nodes/stages for Pipeline Parallelism",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=50,
        help="Size in MB for each distributed blob chunk",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="./mesh_deployment",
        help="Output directory for chunks and scripts",
    )

    args = parser.parse_args()

    print(f"\n🧠 Preparing Model: {args.model}")
    print("============================================================")

    # 1. Model Sharding (Pipeline Parallelism)
    print(f"\n1. Calculating Pipeline Parallelism Topology ({args.nodes} nodes)...")
    try:
        sharder = GGUFSharder(args.model)
        stages = sharder.calculate_pipeline_stages(args.nodes)
        sharding_plan = sharder.generate_pollen_seed_plan(stages)

        plan_path = os.path.join(args.out_dir, "pipeline_topology_plan.txt")
        if not os.path.exists(args.out_dir):
            os.makedirs(args.out_dir)

        with open(plan_path, "w") as f:
            f.write(sharding_plan)
        print(f"✅ Topology plan saved to: {plan_path}")
    except Exception as e:
        print(f"❌ Failed to calculate sharding topology: {e}")
        return

    # 2. Model Weight Distribution (Blob Chunking)
    print(f"\n2. Chunking Model Weights ({args.chunk_size}MB per blob)...")
    try:
        distributor = ModelDistributor(chunk_size_mb=args.chunk_size)
        chunks = distributor.chunk_file(args.model, args.out_dir)

        manifest_path = os.path.join(args.out_dir, "manifest.json")
        distributor.generate_distribution_manifest(
            os.path.basename(args.model), chunks, manifest_path
        )

        script_path = distributor.generate_pollen_seed_script(
            args.out_dir, chunks, manifest_path
        )
        print(f"✅ Generated {len(chunks)} chunks.")
        print(f"✅ Assembly manifest saved to: {manifest_path}")
        print(f"✅ Pollen seeding script saved to: {script_path}")
    except Exception as e:
        print(f"❌ Failed to distribute model weights: {e}")
        return

    print("\n🚀 Preparation Complete!")
    print("Next steps:")
    print(f"  1. Run '{script_path}' to push the blobs to the P2P mesh.")
    print(
        f"  2. Review '{plan_path}' to launch your Keystone nodes with the correct --prop tags."
    )
    print("\n")


if __name__ == "__main__":
    main()
