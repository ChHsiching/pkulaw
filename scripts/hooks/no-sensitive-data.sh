#!/usr/bin/env bash
# Check that staged files don't contain sensitive data (real tokens/keys)
for file in "$@"; do
    # Skip hook scripts themselves
    case "$file" in
        scripts/hooks/*) continue ;;
    esac
    if grep -qE 'eyJ[A-Za-z0-9_-]{40,}|secret_key|api_key.*=|password\s*=' "$file" 2>/dev/null; then
        echo "ERROR: possible sensitive data in $file"
        exit 1
    fi
done
exit 0
