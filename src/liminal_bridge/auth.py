import os
import sys
import secrets


def get_or_create_swarm_key() -> str:
    # Step A: Check os.environ for SWARM_KEY. If it exists, return it.
    key = os.environ.get("SWARM_KEY")
    if key:
        return key

    # Determine project root
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    env_file = os.path.join(project_root, ".env")
    swarm_key_file = os.path.join(project_root, ".swarm_key")

    # Step B: Check for a local .env or .swarm_key file in the project root.
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.strip().startswith("SWARM_KEY="):
                    parts = line.strip().split("=", 1)
                    if len(parts) == 2 and parts[1].strip():
                        val = parts[1].strip()
                        # Strip optional quotes
                        if val.startswith('"') and val.endswith('"'):
                            val = val[1:-1]
                        elif val.startswith("'") and val.endswith("'"):
                            val = val[1:-1]
                        os.environ["SWARM_KEY"] = val
                        return val

    if os.path.exists(swarm_key_file):
        with open(swarm_key_file, "r") as f:
            val = f.read().strip()
            if val:
                os.environ["SWARM_KEY"] = val
                return val

    # Step C: If neither exists, generate a secure key.
    new_key = secrets.token_hex(32)

    try:
        with open(swarm_key_file, "w") as f:
            f.write(new_key + "\n")
        print(
            f">>> A new local swarm was initialized. Secure SWARM_KEY generated and saved to {swarm_key_file}."
        )
    except Exception as e:
        print(
            f"WARNING: Failed to save generated swarm key to file: {e}",
            file=sys.stderr,
        )

    os.environ["SWARM_KEY"] = new_key
    return new_key
