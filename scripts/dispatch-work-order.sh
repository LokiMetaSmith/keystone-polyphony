#!/bin/bash
# scripts/dispatch-work-order.sh
# Dispatch a work order to multiple agents in parallel.
# Usage: ./scripts/dispatch-work-order.sh <file> <number_of_agents>

set -e

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <path_to_work_order.md> <number_of_agents>"
    echo "Example: $0 .gemini/antigravity/brain/4f3708c9-333c-4cda-8ca9-01b1c9b57135/liminal_space_boot_story.md 5"
    exit 1
fi

WORK_ORDER_FILE="$1"
AGENT_COUNT="$2"

if [ ! -f "$WORK_ORDER_FILE" ]; then
    echo "Error: Work order file not found at $WORK_ORDER_FILE"
    exit 1
fi

# Extract the title from the first heading of the work order
TITLE=$(head -n 1 "$WORK_ORDER_FILE" | sed 's/^# //')
if [ -z "$TITLE" ]; then
    TITLE="Automated Work Order"
fi

echo "Dispatching '$TITLE' to $AGENT_COUNT agents..."

# Create the issues in the background to ensure they trigger in parallel
for i in $(seq 1 "$AGENT_COUNT"); do
    gh issue create \
        --title "$TITLE (Agent $i)" \
        --body-file "$WORK_ORDER_FILE" \
        --label "ready for work" \
        > /dev/null &

    # Slight sleep to space out API requests and avoid rate limits
    sleep 1
done

wait
echo "✅ All $AGENT_COUNT work orders dispatched to the agents!"
