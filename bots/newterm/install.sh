#!/bin/bash
# 把新词监控流水线装到一个工作目录（脚本按平铺目录写的，AIsa 客户端要放在同一层）。
# 用法: bash bots/newterm/install.sh [工作目录，默认 /workspace/newterm]
# 已有的状态文件（pushed.json、radar/、.env、prescan_*）不会被覆盖。
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-/workspace/newterm}"
mkdir -p "$DEST/radar"
cp "$REPO"/bots/newterm/pipeline/*.py "$REPO"/bots/newterm/pipeline/*.sh "$REPO"/bots/newterm/pipeline/BROADCAST_FORMAT.md "$REPO"/bots/newterm/pipeline/watchlist.example.json "$DEST/"
cp "$REPO"/lib/aisa/aisa_keyring.py "$REPO"/lib/aisa/aisa_trends.py "$DEST/"
chmod +x "$DEST"/*.sh
# 有自己维护的名单（不进公开仓库）就一起装上，已有的不覆盖
[ -f "$REPO/bots/newterm/pipeline/watchlist.json" ] && [ ! -f "$DEST/watchlist.json" ] && cp "$REPO/bots/newterm/pipeline/watchlist.json" "$DEST/"
[ -f "$DEST/pushed.json" ] || echo '{}' > "$DEST/pushed.json"
[ -f "$DEST/tiktok_pool.json" ] || echo '{"memes": {}}' > "$DEST/tiktok_pool.json"
[ -f "$DEST/.env" ] || cp "$REPO/.env.example" "$DEST/.env"
chmod 600 "$DEST/.env"
[ -n "${SKIP_PIP:-}" ] || python3 -m pip install -q -r "$REPO/bots/newterm/requirements.txt" || echo "依赖没装全，请手动执行: pip install -r $REPO/bots/newterm/requirements.txt"
echo "装好了: $DEST"
echo "下一步: 把 AISA_API_KEY 等 Key 从保险库写进 $DEST/.env（不要贴在聊天里），然后跑一次: bash $DEST/prescan.sh morning"
