#!/usr/bin/env bash
# Enforce Git Flow branch rules:
#   main    — no local commits at all (changes via PR from develop only)
#   develop — merge commits only (no direct commits; use feature/* branches)
#   other   — anything goes

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
git_dir=$(git rev-parse --git-dir 2>/dev/null)

if [ "$branch" = "main" ]; then
    echo "ERROR: commits to main are forbidden. Use PRs from develop."
    exit 1
fi

if [ "$branch" = "develop" ]; then
    if [ ! -f "${git_dir}/MERGE_HEAD" ]; then
        echo "ERROR: direct commits to develop are forbidden. Use feature/* branches."
        exit 1
    fi
fi

exit 0
