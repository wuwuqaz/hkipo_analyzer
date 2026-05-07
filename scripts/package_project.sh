#!/bin/bash
# 打包 hkipo_analyzer.zip — 排除临时文件、缓存、备份
# 用法: bash scripts/package_project.sh

set -e
cd "$(dirname "$0")/.."

OUT="hkipo_analyzer.zip"
rm -f "$OUT"

zip -r "$OUT" . \
  -x "*/__pycache__/*" \
  -x "__pycache__/*" \
  -x "*.pyc" \
  -x ".DS_Store" \
  -x "__MACOSX/*" \
  -x ".git/*" \
  -x "temp/*.pdf" \
  -x "temp/results_cache.json" \
  -x "temp/ipo_history.json" \
  -x "data/backups/*" \
  -x ".env" \
  -x ".gitignore" \
  -x "$OUT"

echo "✓ 打包完成: $OUT ($(du -h "$OUT" | cut -f1))"
