#!/usr/bin/env bash
# 每日一键更新：抓数据 → 算模型 → 刷新工作台
#   ./run_daily.sh           正常抓取（约 2 分钟）
#   ./run_daily.sh --rebuild 不联网，用上次的原始数据重建（改样式/改模型时用，几秒）
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "找不到 python3，请先安装 Python 3.9+ 后重试"
  exit 1
fi

"$PY" run.py "$@"

echo
echo "工作台：$(pwd)/output/dashboard.html"
echo "当日简报：$(pwd)/output/daily_$(date +%F).md"
