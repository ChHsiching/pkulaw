#!/bin/bash
echo "=== $(date) ==="
tail -5 output/crawl_full.log
echo "---"
python3 -c "
import json
p=json.load(open('output/progress.json'))
d=json.load(open('output/pkulaw_cases.json'))
s=json.load(open('output/search_results.json'))
rem = len(s) - len(p['fetched_gids'])
print(f'Search: {len(s)} | Fetched: {len(p[\"fetched_gids\"])} | Data: {len(d)} | Remaining: {rem}')
"
ps aux | grep "python3 -u main.py" | grep -v grep | awk '{print "PID:", $2, "MEM:", $6/1024"MB"}' || echo "Process finished"
