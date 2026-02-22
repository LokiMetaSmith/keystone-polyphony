#!/usr/bin/env bash

# Library of functions for issue triage

get_triage_agents() {
    echo "${TRIAGE_AGENTS:-}" | tr ',' ' '
}

check_agent_quota() {
    local agent="$1"
    local repo="$2"

    # Handle uppercase for env var lookup
    local agent_upper=$(echo "$agent" | tr '[:lower:]' '[:upper:]' | tr '-' '_')

    local limit=0
    if [ -n "${VARS_JSON:-}" ]; then
        limit=$(echo "$VARS_JSON" | jq -r ".${agent_upper}_DAILY_TASKS // 0")
        if [ "$limit" -eq 0 ]; then
            limit=$(echo "$VARS_JSON" | jq -r ".AGENT_DAILY_TASKS // 0")
        fi
    fi

    if [ "$limit" -eq 0 ]; then
        # Check env vars as fallback
        local limit_var="${agent_upper}_DAILY_TASKS"
        limit="${!limit_var:-0}"
        if [ "$limit" -eq 0 ]; then
            limit="${AGENT_DAILY_TASKS:-0}"
        fi
    fi

    if [ "$limit" -eq 0 ]; then
        # No limit set, assume unlimited
        return 0
    fi

    local since=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-24H +%Y-%m-%dT%H:%M:%SZ)

    # Label to look for: 'jules' if agent is jules, else 'triage-agent:<agent>'
    local label="$agent"
    if [ "$agent" != "jules" ]; then
        label="triage-agent:$agent"
    fi

    # Query issues with the label
    # We use state=all to include issues that were assigned and then closed today
    local issues=$(gh api "/repos/$repo/issues?labels=$label&state=all&per_page=100" --jq '.[].number' 2>/dev/null || echo "")
    local assigned_today=0

    for jnum in $issues; do
        local labeled_at=$(gh api "/repos/$repo/issues/$jnum/timeline" \
            --jq "[.[] | select(.event == 'labeled' and .label.name == '$label')] | last | .created_at // empty" 2>/dev/null || echo "")
        if [ -n "$labeled_at" ] && [[ "$labeled_at" > "$since" ]]; then
            assigned_today=$((assigned_today + 1))
        fi
    done

    echo "Agent $agent usage: $assigned_today / $limit" >&2

    if [ "$assigned_today" -ge "$limit" ]; then
        return 1 # Quota reached
    fi
    return 0 # Quota available
}

is_refined_by() {
    local file="$1"
    local agent="$2"
    # Match agent name in the triage-refined marker
    grep -qE "<!-- triage-refined:.*(^|[[:space:],])$agent([[:space:],]|$).*-->" "$file"
}

get_issue_title() {
    local file="$1"
    # Skip frontmatter if present and find the first # header
    awk '
        BEGIN { in_fm=0; found=0 }
        /^---$/ {
            if (NR==1) { in_fm=1; next }
            else if (in_fm) { in_fm=0; next }
        }
        !in_fm && /^# / {
            title=$0;
            sub(/^# /, "", title);
            print title;
            found=1;
            exit
        }
        END { if (!found) exit 1 }
    ' "$file" 2>/dev/null || basename "$file" .md
}

mark_refined_by() {
    local file="$1"
    local agent="$2"
    if is_refined_by "$file" "$agent"; then
        return 0
    fi

    if grep -q "<!-- triage-refined: " "$file"; then
        # Append to existing list
        sed -i "s/<!-- triage-refined: \(.*\) -->/<!-- triage-refined: \1, ${agent} -->/" "$file"
    else
        # Add new marker
        echo "" >> "$file"
        echo "<!-- triage-refined: ${agent} -->" >> "$file"
    fi
}
