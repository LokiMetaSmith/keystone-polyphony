import asyncio
import os
import sys
import argparse
from pathlib import Path

# Ensure we can import local modules
sys.path.append(os.path.abspath("src"))

try:
    from liminal_bridge.mesh import LiminalMesh
except ImportError:
    print("Error: Could not import LiminalMesh. Ensure you are in the project root.")
    sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(
        description="Exchange SSH public keys via the swarm."
    )
    parser.add_argument(
        "--duration", type=int, default=30, help="Wait duration in seconds."
    )
    args = parser.parse_args()

    swarm_key = os.environ.get("SWARM_KEY")
    if not swarm_key:
        print("Error: SWARM_KEY environment variable is not set.")
        sys.exit(1)

    pubkey_path = Path.home() / ".ssh" / "id_ed25519.pub"
    if not pubkey_path.exists():
        print(f"Error: SSH public key not found at {pubkey_path}")
        sys.exit(1)

    with open(pubkey_path, "r") as f:
        my_pubkey = f.read().strip()

    print(f">>> Connecting to swarm with key: {swarm_key[:4]}...")

    # Initialize mesh
    mesh = LiminalMesh(
        secret_key=swarm_key,
        db_path="ssh_exchange.db",
        identity_path="ssh_identity.pem"
    )
    await mesh.start()

    try:
        # Give some time for discovery
        await asyncio.sleep(5)

        print(">>> Sharing my public key...")
        await mesh.update_set("ssh_peer_keys", my_pubkey)

        print(f">>> Monitoring for peer keys (Duration: {args.duration}s)...")

        auth_keys_path = Path.home() / ".ssh" / "authorized_keys"

        # Poll for changes
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < args.duration:
            peer_keys = mesh.get_kv("ssh_peer_keys") or []

            if peer_keys:
                current_auth_keys = set()
                if auth_keys_path.exists():
                    with open(auth_keys_path, "r") as f:
                        current_auth_keys = {
                            line.strip() for line in f if line.strip()
                        }

                added_count = 0
                for key in peer_keys:
                    if key != my_pubkey and key not in current_auth_keys:
                        print(">>> Discovered new peer key. Adding to auth...")
                        with open(auth_keys_path, "a") as f:
                            f.write(f"\n{key}\n")
                        current_auth_keys.add(key)
                        added_count += 1

                if added_count > 0:
                    print(f">>> Added {added_count} new keys.")

            await asyncio.sleep(5)

    finally:
        await mesh.stop()
        if os.path.exists("ssh_exchange.db"):
            os.remove("ssh_exchange.db")
        if os.path.exists("ssh_identity.pem"):
            os.remove("ssh_identity.pem")

    print(">>> Key exchange finished.")


if __name__ == "__main__":
    asyncio.run(main())
