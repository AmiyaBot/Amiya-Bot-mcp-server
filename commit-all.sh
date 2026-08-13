#!/usr/bin/env bash
# commit-all.sh — 提交当前全部改动并推送到远端
# 用法: ./commit-all.sh <提交信息>
#
# 行为：
#   1. 暂存全部改动（含未跟踪文件）
#   2. 使用传入的提交信息提交
#   3. 推送当前分支与全部标签到远端
set -euo pipefail

# 切换到仓库根目录（脚本所在目录）
cd "$(dirname "$0")"

COMMIT_MSG="${1:-}"

if [[ -z "$COMMIT_MSG" ]]; then
  echo "❌ 用法: ./commit-all.sh <提交信息>"
  exit 1
fi

# 暂存全部改动
git add -A

# 无改动时直接退出
if git diff --cached --quiet; then
  echo "✅ 没有需要提交的改动"
  exit 0
fi

echo "📦 即将提交的改动："
git status --short

git commit -m "$COMMIT_MSG"

if ! git push; then
  echo "❌ 推送分支失败：远端可能有新提交，请先 git pull --rebase 后再试"
  exit 1
fi

if ! git push --tags; then
  echo "❌ 推送标签失败"
  exit 1
fi

echo "✅ 提交并推送完成"
