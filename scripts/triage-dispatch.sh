#!/usr/bin/env bash

# Dispatch triage for a single file
# Usage: ./scripts/triage-dispatch.sh <file> <repo>

set -euo pipefail

SCRIPT_DIR=$(dirname "$0")
source "$SCRIPT_DIR/triage-lib.sh"

FILE="$1"
REPO="$2"

if [ ! -f "$FILE" ]; then
    echo "Error: File $FILE not found" >&2
    exit 1
fi

AGENTS=$(get_triage_agents)
if [ -z "$AGENTS" ]; then
    # No agents configured, consider it refined
    echo "ALL_REFINED"
    exit 0
fi

for agent in $AGENTS; do
    if is_refined_by "$FILE" "$agent"; then
        continue
    fi

    # This is the next required agent
    echo "Next required agent for $FILE: $agent" >&2

    if check_agent_quota "$agent" "$REPO"; then
        # Check if it's a CLI agent
        agent_upper=$(echo "$agent" | tr '[:lower:]' '[:upper:]' | tr '-' '_')

        local cmd=""
        if [ -n "${VARS_JSON:-}" ]; then
            cmd=$(echo "$VARS_JSON" | jq -r ".${agent_upper}_COMMAND // empty")
        fi
        if [ -z "$cmd" ]; then
            cmd_var="${agent_upper}_COMMAND"
            cmd="${!cmd_var:-}"
        fi

        # Default for architect
        if [ -z "$cmd" ] && [ "$agent" == "architect" ]; then
             cmd="python3 scripts/refine_issue.py"
        fi

        # Check if it is an async agent defined in reviewers.yml
        local config=""
        if [ -z "$cmd" ]; then
             config=$(get_agent_config "$agent" || echo "")
        fi

        if [ -n "$cmd" ]; then
            echo "Running CLI agent: $agent" >&2
            # CLI agents are expected to update the file and return 0
            if $cmd "$FILE"; then
                mark_refined_by "$FILE" "$agent"
                echo "Agent $agent refined $FILE (sync)" >&2
                # Continue to next agent for the same file
                continue
            else
                echo "Error: CLI agent $agent failed on $FILE" >&2
                exit 1
            fi
        elif [ -n "$config" ]; then
            # Async agent (configured in reviewers.yml)

            NAME=$(echo "$config" | jq -r '.name')
            LABEL=$(echo "$config" | jq -r '.label')
            HANDLE=$(echo "$config" | jq -r '.handle')

            # Check for existing triage issue for this file
            # We look for open issues with labels '$LABEL' and 'triage' that mention the file path
            EXISTS=$(gh api "/repos/$REPO/issues?labels=$LABEL,triage&state=open" --jq ".[] | select(.body | contains(\"Triaging file: \`$FILE\`\")) | .number" | head -n 1 || echo "")
            if [ -n "$EXISTS" ]; then
                echo "Triage issue #$EXISTS already exists for $FILE" >&2
                echo "DISPATCHED_ASYNC"
                exit 0
            fi

            echo "Dispatching to $NAME (async)" >&2
            TITLE=$(get_issue_title "$FILE")
            BODY=$(cat "$FILE")

            COMMENT_BODY="<!-- triage-instructions -->
## 🤖 $NAME Triage Requested

Please refine this issue according to the following requirements:

1. **Human Interaction Story** — Clear narrative of how a contributor interacts with the feature.
2. **BDD Feature File** — Complete Cucumber \`.feature\` file included.
3. **Self-Contained** — Prerequisites listed and marked as blocking.
4. **Surgical Scope** — One concern per issue.

When your review is complete, please:
- Update the source file \`$FILE\` with the refined content.
- Include the marker \`<!-- triage-refined: $agent -->\` at the end of the file.
- Commit and push the changes.
- Close this issue."

            # Create local issue
            ISSUE_URL=$(gh issue create \
                --repo "$REPO" \
                --title "[TRIAGE] $TITLE" \
                --body "Triaging file: \`$FILE\`

---
$BODY" \
                --label "$LABEL" \
                --label "pre-review" \
                --label "triage")

            # Post instructions as a comment
            gh issue comment "$ISSUE_URL" --repo "$REPO" --body "$COMMENT_BODY"

            echo "DISPATCHED_ASYNC"
            exit 0
        else
            echo "Warning: Unknown agent type or missing configuration for $agent" >&2
            # For now, we treat unknown agents as "not available"
            echo "QUOTA_EXHAUSTED"
            exit 0
        fi
    else
        echo "Quota exhausted for required agent: $agent" >&2
        echo "QUOTA_EXHAUSTED"
        exit 0
    fi
done

echo "ALL_REFINED"
