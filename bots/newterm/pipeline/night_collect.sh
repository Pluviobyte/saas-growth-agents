#!/bin/bash
# 夜间只采集扫描（不进播报、不打 Trends 分、不动 pushed.json / 正式梗池 / 播报文件）
# 用法: nohup ./night_collect.sh [标签，默认 night<HHMM>] > /dev/null 2>&1 &
# 跑：模板站 sitemap（--no-score）、CapCut 模板、Product Hunt、GitHub Trending、付费导航新上架、Reddit RSS、TikTok 公开源（--no-trends，用梗池副本）
# 输出：prescan_<日期>_<标签>/radar_*.json、radar.md、tiktok.json；并把摘要追加到 radar/night_<日期>.log
D="${NEWTERM_HOME:-$(cd "$(dirname "$0")" && pwd)}"; cd "$D" || exit 1
TAG="${1:-night$(date +%H%M)}"; DAY=$(date +%Y%m%d)
OUT="$D/prescan_${DAY}_${TAG}"; mkdir -p "$OUT" "$D/radar"
LOG="$D/radar/night_${DAY}.log"
rm -f "$OUT/NIGHT_DONE"
# Completion audit: DONE/NIGHT_DONE retain legacy readiness semantics, not all-source success.
RC_FILE="$OUT/source_status.tsv"
: > "$RC_FILE"
rm -f "$OUT/completion.json" "$OUT/PARTIAL" "$OUT/ALL_FAILED" "$OUT/SETTLED"
run_checked() {
  local source="$1"; shift
  "$@"; local rc=$?
  printf '%s\t%d\n' "$source" "$rc" >> "$RC_FILE"
  return "$rc"
}
finish_audit() {
  local ok bad state
  ok=$(awk '$2 == 0 {n++} END {print n+0}' "$RC_FILE")
  bad=$(awk '$2 != 0 {n++} END {print n+0}' "$RC_FILE")
  state=complete
  if [ "$bad" -gt 0 ]; then
    if [ "$ok" -gt 0 ]; then state=partial; touch "$OUT/PARTIAL"
    else state=failed; touch "$OUT/ALL_FAILED"; fi
  fi
  printf '{"state":"%s","successful_sources":%d,"failed_sources":%d,"settled":true}\n' "$state" "$ok" "$bad" > "$OUT/completion.json.tmp"
  mv "$OUT/completion.json.tmp" "$OUT/completion.json"
  touch "$OUT/SETTLED"
}

set -a; [ -f "$D/.env" ] && . "$D/.env" >/dev/null 2>&1; set +a
echo "=== $TAG start $(date '+%F %T') ===" >> "$LOG"
run_checked radar_sitemaps timeout 900 python3 radar_sitemaps.py --out "$OUT" --no-score >> "$LOG" 2>&1 || echo "radar_sitemaps 失败 rc=$?" >> "$LOG"
run_checked radar_capcut timeout 600 python3 radar_capcut.py --out "$OUT" >> "$LOG" 2>&1 || echo "radar_capcut 失败 rc=$?" >> "$LOG"
run_checked radar_producthunt timeout 300 python3 radar_producthunt.py --out "$OUT" >> "$LOG" 2>&1 || echo "radar_producthunt 失败 rc=$?" >> "$LOG"
run_checked radar_github_trending timeout 180 python3 radar_github_trending.py --out "$OUT" >> "$LOG" 2>&1 || echo "radar_github_trending 失败 rc=$?" >> "$LOG"
run_checked radar_paid_nav timeout 480 python3 radar_paid_nav.py --out "$OUT" >> "$LOG" 2>&1 || echo "radar_paid_nav 失败 rc=$?" >> "$LOG"
# TikTok：用正式梗池的副本跑，夜里发现的梗只记在副本和本次输出里，不改白天播报用的 tiktok_pool.json
cp "$D/tiktok_pool.json" "$D/radar/night_tiktok_pool.json" 2>/dev/null
TIKTOK_POOL_FILE="$D/radar/night_tiktok_pool.json" run_checked tiktok timeout 900 python3 tiktok_scan.py "$TAG" --no-trends > "$OUT/tiktok.log" 2>&1 &
TPID=$!
run_checked radar_reddit timeout 1200 python3 radar_reddit.py --out "$OUT" >> "$LOG" 2>&1 || echo "radar_reddit 失败 rc=$?" >> "$LOG"
wait $TPID; echo "tiktok_scan rc=$? $(tail -1 "$OUT/tiktok.log" 2>/dev/null)" >> "$LOG"
run_checked radar_md timeout 120 python3 radar_md.py "$OUT" > /dev/null 2>> "$LOG"
python3 - "$OUT" "$D/tiktok_pool.json" >> "$LOG" 2>&1 <<'PY'
import json, sys, os
out, main_pool = sys.argv[1], sys.argv[2]
try:
    night = json.load(open(os.path.join(os.environ.get('NEWTERM_HOME', '.'), 'radar/night_tiktok_pool.json')))['memes']
    day = json.load(open(main_pool))['memes']
    new = [m['name'] for k, m in night.items() if k not in day]
    print(f"TikTok 夜间新进梗池副本 {len(new)} 个: {', '.join(new[:30])}")
    json.dump(dict(new_memes={k: m for k, m in night.items() if k not in day}), open(os.path.join(out, 'radar_tiktok_night.json'), 'w'), ensure_ascii=False, indent=1)
except Exception as e: print('TikTok 夜间对比失败', e)
PY
echo "=== $TAG end $(date '+%F %T') 输出 $OUT ===" >> "$LOG"
finish_audit
# Legacy NIGHT_DONE means settled, including partial/failed: inspect completion.json.
touch "$OUT/NIGHT_DONE"
