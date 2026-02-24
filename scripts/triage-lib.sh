#!/usr/bin/env bash

# Library of functions for issue triage

get_triage_agents() {
    echo "${TRIAGE_AGENTS:-}" | tr ',' ' '
}

get_agent_config() {
    local agent_name="$1"
    if [ ! -f ".github/reviewers.yml" ]; then
        return 1
    fi

    # Try to use yq to parse yaml to json (assuming mikefarah/yq syntax as in workflows)
    local json
    if ! json=$(yq -o json . .github/reviewers.yml 2>/dev/null); then
        # If yq is missing or fails, log warning
        echo "Warning: yq failed or not found. Cannot parse reviewers.yml." >&2
        return 1
    fi

    # Find matching reviewer by name or label (case-insensitive)
    echo "$json" | jq -c ".reviewers[] | select((.name | ascii_downcase) == (\"$agent_name\" | ascii_downcase) or (.label | ascii_downcase) == (\"$agent_name\" | ascii_downcase))" | head -n 1
}

check_agent_quota() {
    local agent="$1"
    local repo="$2"

    local limit=0

    # Helper to get limit from VARS_JSON or env var
    get_limit_from_var() {
        local var_name="$1"
        local lim=0
        if [ -n "${VARS_JSON:-}" ]; then
            lim=$(echo "$VARS_JSON" | jq -r ".${var_name} // 0")
        fi
        if [ "$lim" -eq 0 ]; then
            lim="${!var_name:-0}"
        fi
        echo "$lim"
    }

    # Try to get limit from config
    local config
    config=$(get_agent_config "$agent" || echo "")

    if [ -n "$config" ]; then
        local quota_var
        quota_var=$(echo "$config" | jq -r '.quota_var // empty')

        if [ -n "$quota_var" ]; then
            limit=$(get_limit_from_var "$quota_var")
        fi
    fi

    if [ "$limit" -eq 0 ]; then
        # Fallback: Handle uppercase for env var lookup based on agent name
        local agent_upper=$(echo "$agent" | tr '[:lower:]' '[:upper:]' | tr '-' '_')
        local limit_var="${agent_upper}_DAILY_TASKS"

        limit=$(get_limit_from_var "$limit_var")

        if [ "$limit" -eq 0 ]; then
            limit=$(get_limit_from_var "AGENT_DAILY_TASKS")
        fi
    fi

    if [ "$limit" -eq 0 ]; then
        # No limit set, assume unlimited
        return 0
    fi

    local since=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-24H +%Y-%m-%dT%H:%M:%SZ)

    # Label to look for: from config if available, else standard fallback
    local label="$agent"
    if [ -n "$config" ]; then
        label=$(echo "$config" | jq -r '.label // empty')
    fi

    if [ -z "$label" ] || [ "$label" = "null" ]; then
        # Fallback label logic
        if [ "$agent" != "jules" ]; then
            label="triage-agent:$agent"
        else
            label="jules"
        fi
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
