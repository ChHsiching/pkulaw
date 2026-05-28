#!/usr/bin/env bash
# Check that commit message does not contain co-authored-by
if grep -qiE "co-authored-by" "$1" 2>/dev/null; then
    echo "ERROR: co-author not allowed in commits"
    exit 1
fi
exit 0
