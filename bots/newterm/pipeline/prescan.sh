#!/bin/bash
# 播报前预跑：拉哥飞批次 + 跑 newterm.py（只读不写 pushed.json）+ TikTok 扫描，按时段存结果
# 用法: nohup ./prescan.sh morning|noon|evening &
# TikTok：routine 先把 X/标签页结果写到 prescan_<日期>_<时段>/tiktok_x_input.json，再启动本脚本；
#         tiktok_scan.py 与 newterm.py 并行，完成后写 TIKTOK_DONE（失败写 TIKTOK_FAILED）。
SLOT="$1"; D="${NEWTERM_HOME:-$(cd "$(dirname "$0")" && pwd)}"; cd "$D" || exit 1
DAY=$(date +%Y%m%d)
OUT="$D/prescan_${DAY}_${SLOT}"
mkdir -p "$OUT"; rm -f "$OUT/DONE" "$OUT/FAILED" "$OUT/RADAR_DONE"
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

echo "start $(date '+%F %T')" > "$OUT/status.txt"
set -a; [ -f "$D/.env" ] && . "$D/.env"; set +a
# TikTok Trends 只在 morning 打；noon/evening 复用梗池与缓存，省 AIsa
TT_EXTRA=""
case "$SLOT" in noon|evening) TT_EXTRA="--no-trends" ;; esac
run_checked tiktok timeout 900 python3 tiktok_scan.py "$SLOT" $TT_EXTRA > "$OUT/tiktok.log" 2>&1 &
TPID=$!
# 雷达（失败不影响主流程）：sitemap + CapCut + Product Hunt + GitHub Trending + 付费导航新上架 + Reddit 依次跑，汇总 radar.md
# 一手源（Reddit/CapCut/PH/GitHub Trending/付费导航新上架/大站内页）抓到即可进播报候选，不看 Trends 门槛
# AIsa 省钱：sitemap 日间 --no-score；tiktok 仅 morning 打 Trends（noon/evening --no-trends）
( run_checked radar_sitemaps timeout 900 python3 radar_sitemaps.py --out "$OUT" --no-score > "$OUT/radar_sitemaps.log" 2>&1 || echo "radar_sitemaps rc=$? $(date '+%F %T')" >> "$OUT/radar_errors.log"
  run_checked radar_capcut timeout 600 python3 radar_capcut.py --out "$OUT" > "$OUT/radar_capcut.log" 2>&1 || echo "radar_capcut rc=$? $(date '+%F %T')" >> "$OUT/radar_errors.log"
  run_checked radar_producthunt timeout 300 python3 radar_producthunt.py --out "$OUT" > "$OUT/radar_producthunt.log" 2>&1 || echo "radar_producthunt rc=$? $(date '+%F %T')" >> "$OUT/radar_errors.log"
  run_checked radar_github_trending timeout 180 python3 radar_github_trending.py --out "$OUT" > "$OUT/radar_github_trending.log" 2>&1 || echo "radar_github_trending rc=$? $(date '+%F %T')" >> "$OUT/radar_errors.log"
  run_checked radar_paid_nav timeout 480 python3 radar_paid_nav.py --out "$OUT" > "$OUT/radar_paid_nav.log" 2>&1 || echo "radar_paid_nav rc=$? $(date '+%F %T')" >> "$OUT/radar_errors.log"
  run_checked radar_reddit timeout 1200 python3 radar_reddit.py --out "$OUT" > "$OUT/radar_reddit.log" 2>&1 || echo "radar_reddit rc=$? $(date '+%F %T')" >> "$OUT/radar_errors.log"
  run_checked radar_md timeout 120 python3 radar_md.py "$OUT" > /dev/null 2>> "$OUT/radar_errors.log"
  echo "radar end $(date '+%F %T')" >> "$OUT/status.txt"; touch "$OUT/RADAR_DONE" ) &
RPID=$!
# 哥飞新词服务（seo.web.cafe）是可选的付费数据源：没配 GEFEI_API_KEY 就跳过
if [ -n "${GEFEI_API_KEY:-}" ]; then
  run_checked gefei timeout 600 python3 gefei_api.py --days 1 --min 0.2 > "$OUT/gefei.log" 2>&1
fi
run_checked newterm timeout 1800 python3 newterm.py --dry > "$OUT/newterm.log" 2>&1
RC=$?
[ -f "report_${DAY}.md" ] && cp "report_${DAY}.md" "$OUT/report.md"
echo "end $(date '+%F %T') rc=$RC" >> "$OUT/status.txt"
wait $TPID; echo "tiktok end $(date '+%F %T') rc=$?" >> "$OUT/status.txt"
wait $RPID 2>/dev/null || true
finish_audit
# Main report failure retains the legacy FAILED signal; auxiliary failure is degradable.
if [ "$RC" -eq 0 ]; then touch "$OUT/DONE"; else touch "$OUT/FAILED"; fi
