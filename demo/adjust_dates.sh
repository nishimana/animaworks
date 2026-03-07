#!/usr/bin/env bash
set -euo pipefail

# Adjust timestamps in demo example data so that the 3-day logs appear
# as "2 days ago → yesterday → today" relative to the current date.
#
# Usage: ./adjust_dates.sh <examples_dir>
#   examples_dir: path containing character dirs + channels/
#                 e.g. /demo/examples/ja

EXAMPLES_DIR="${1:?Usage: adjust_dates.sh <examples_dir>}"

if [ ! -d "$EXAMPLES_DIR" ]; then
    echo "ERROR: Directory not found: $EXAMPLES_DIR"
    exit 1
fi

# Original dates baked into the example files
ORIG_D1="2026-03-01"   # 2 days ago
ORIG_D2="2026-03-02"   # yesterday
ORIG_D3="2026-03-03"   # today
ORIG_D4="2026-03-04"   # tomorrow (knowledge timestamps)
ORIG_D5="2026-03-05"   # +2 days (knowledge timestamps)
ORIG_D10="2026-03-10"  # +7 days (task deadlines)

# Target dates relative to today
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "$TODAY - 1 day" +%Y-%m-%d 2>/dev/null \
         || date -v-1d +%Y-%m-%d)
DAY_BEFORE=$(date -d "$TODAY - 2 days" +%Y-%m-%d 2>/dev/null \
          || date -v-2d +%Y-%m-%d)
TOMORROW=$(date -d "$TODAY + 1 day" +%Y-%m-%d 2>/dev/null \
        || date -v+1d +%Y-%m-%d)
DAY_AFTER=$(date -d "$TODAY + 2 days" +%Y-%m-%d 2>/dev/null \
         || date -v+2d +%Y-%m-%d)
WEEK_LATER=$(date -d "$TODAY + 7 days" +%Y-%m-%d 2>/dev/null \
          || date -v+7d +%Y-%m-%d)

if [ "$ORIG_D1" = "$DAY_BEFORE" ] && [ "$ORIG_D2" = "$YESTERDAY" ] && [ "$ORIG_D3" = "$TODAY" ] \
   && [ "$ORIG_D4" = "$TOMORROW" ] && [ "$ORIG_D5" = "$DAY_AFTER" ] && [ "$ORIG_D10" = "$WEEK_LATER" ]; then
    echo "Dates already match today — no adjustment needed."
    exit 0
fi

echo "Adjusting dates: $ORIG_D1→$DAY_BEFORE  $ORIG_D2→$YESTERDAY  $ORIG_D3→$TODAY  $ORIG_D4→$TOMORROW  $ORIG_D5→$DAY_AFTER  $ORIG_D10→$WEEK_LATER"

adjust_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        return
    fi
    # Two-pass replacement to avoid cascade (e.g. D3→TODAY then TODAY→YESTERDAY)
    sed -i \
        -e "s/${ORIG_D10}/__PLACEHOLDER_D10__/g" \
        -e "s/${ORIG_D5}/__PLACEHOLDER_D5__/g" \
        -e "s/${ORIG_D4}/__PLACEHOLDER_D4__/g" \
        -e "s/${ORIG_D3}/__PLACEHOLDER_D3__/g" \
        -e "s/${ORIG_D2}/__PLACEHOLDER_D2__/g" \
        -e "s/${ORIG_D1}/__PLACEHOLDER_D1__/g" \
        "$file"
    sed -i \
        -e "s/__PLACEHOLDER_D10__/${WEEK_LATER}/g" \
        -e "s/__PLACEHOLDER_D5__/${DAY_AFTER}/g" \
        -e "s/__PLACEHOLDER_D4__/${TOMORROW}/g" \
        -e "s/__PLACEHOLDER_D3__/${TODAY}/g" \
        -e "s/__PLACEHOLDER_D2__/${YESTERDAY}/g" \
        -e "s/__PLACEHOLDER_D1__/${DAY_BEFORE}/g" \
        "$file"
}

rename_and_adjust() {
    local dir="$1"
    local ext="${2:-jsonl}"
    [ -d "$dir" ] || return
    for f in "$dir"/*."$ext"; do
        [ -f "$f" ] || continue
        local base
        base=$(basename "$f")
        local new_name="$base"
        new_name="${new_name//$ORIG_D10/$WEEK_LATER}"
        new_name="${new_name//$ORIG_D5/$DAY_AFTER}"
        new_name="${new_name//$ORIG_D4/$TOMORROW}"
        new_name="${new_name//$ORIG_D3/$TODAY}"
        new_name="${new_name//$ORIG_D2/$YESTERDAY}"
        new_name="${new_name//$ORIG_D1/$DAY_BEFORE}"
        if [ "$base" != "$new_name" ]; then
            mv "$dir/$base" "$dir/$new_name"
        fi
        adjust_file "$dir/$new_name"
    done
}

rename_jsonl() {
    rename_and_adjust "$1" "jsonl"
}

# Process character directories
for char_dir in "$EXAMPLES_DIR"/*/; do
    char_name="$(basename "$char_dir")"
    [ "$char_name" = "channels" ] && continue
    [ "$char_name" = "users" ] && continue

    rename_jsonl "$char_dir/activity_log"
    rename_and_adjust "$char_dir/episodes" "md"
    rename_and_adjust "$char_dir/knowledge" "md"

    adjust_file "$char_dir/state/current_task.md"
    adjust_file "$char_dir/state/conversation.json"
    adjust_file "$char_dir/state/task_queue.jsonl"
done

# Process shared channel files
rename_jsonl "$EXAMPLES_DIR/channels"

echo "Date adjustment complete."
