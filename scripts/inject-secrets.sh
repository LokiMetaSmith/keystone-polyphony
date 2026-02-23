#!/bin/bash
# scripts/inject-secrets.sh

set -e

# Load .env if it exists
if [ -f .env ]; then
  echo "Loading variables from .env..."
  source .env
elif [ -f ../.env ]; then
  echo "Loading variables from ../.env..."
  source ../.env
fi

# Check for gh
if ! command -v gh &> /dev/null; then
    echo "Error: gh could not be found. Please install GitHub CLI."
    exit 1
fi

# Check login
if ! gh auth status &> /dev/null; then
    echo "Error: You must be logged in to gh. Run 'gh auth login'."
    exit 1
fi

# Detect Repo
REPO=""
if [ -n "$1" ]; then
    REPO=$1
else
    # Try to detect
    echo "Detecting repository..."
    REPO=$(gh repo view --json owner,name -q ".owner.login + \"/\" + .name" 2>/dev/null || true)

    if [ -z "$REPO" ]; then
        # Fallback to git config if gh fails to detect (e.g. not in a git dir, though script assumes so)
        REMOTE_URL=$(git config --get remote.origin.url 2>/dev/null || true)
        if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+/[^.]+)(\.git)?$ ]]; then
            REPO="${BASH_REMATCH[1]}"
        fi
    fi

    if [ -z "$REPO" ]; then
        echo "Could not detect repository. Please provide it as an argument: ./inject-secrets.sh owner/repo"
        exit 1
    fi
fi

echo ">>> Injecting Swarm Secrets for repo: $REPO"

set_secret() {
    local key=$1
    local val=$2

    if [ -z "$val" ]; then
        read -s -p "Enter value for $key (hidden): " val
        echo ""
    fi

    if [ -n "$val" ]; then
        echo "Setting secret $key..."
        gh secret set "$key" --body "$val" --repo "$REPO"
    else
        echo "Skipping $key (no value provided)."
    fi
}

set_variable() {
    local key=$1
    local val=$2

    if [ -z "$val" ]; then
        # Default values if not provided
        local default=""
        if [ "$key" == "JULES_DAILY_TASKS" ]; then default="10"; fi
        if [ "$key" == "AGENT_DAILY_TASKS" ]; then default="5"; fi

        read -p "Enter value for $key [$default]: " input
        val=${input:-$default}
    fi

    if [ -n "$val" ]; then
        echo "Setting variable $key to $val..."
        gh variable set "$key" --body "$val" --repo "$REPO"
    else
         echo "Skipping variable $key (no value provided)."
    fi
}

# Secrets
# User can set these env vars before running, or be prompted
set_secret "SWARM_KEY" "$SWARM_KEY"
set_secret "DUCKY_API_KEY" "$DUCKY_API_KEY"
set_secret "AGENT_API_KEY" "$AGENT_API_KEY"

# Variables
set_variable "JULES_DAILY_TASKS" "$JULES_DAILY_TASKS"
set_variable "AGENT_DAILY_TASKS" "$AGENT_DAILY_TASKS"

echo ">>> Swarm secrets and quotas initialized."
