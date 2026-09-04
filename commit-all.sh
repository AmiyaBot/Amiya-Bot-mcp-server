#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "当前目录不是 Git 仓库。" >&2
  exit 1
fi

push_after_commit=1
if [[ "${1:-}" == "--no-push" ]]; then
  push_after_commit=0
  shift
fi

if [[ $# -eq 0 ]]; then
  echo "用法: ./commit-all.sh [--no-push] <提交信息>" >&2
  exit 1
fi

commit_message="$*"
if [[ -z "${commit_message//[[:space:]]/}" ]]; then
  echo "提交信息不能为空。" >&2
  exit 1
fi

if [[ -z "$(git status --porcelain)" ]]; then
  echo "没有可提交的变更。"
  exit 0
fi

git add -A

if git diff --cached --quiet; then
  echo "没有可提交的变更。"
  exit 0
fi

git commit -m "$commit_message"
echo "已提交本地改动。"

if [[ $push_after_commit -eq 0 ]]; then
  echo "未推送（--no-push）。"
  exit 0
fi

if ! git rev-parse --abbrev-ref '@{u}' >/dev/null 2>&1; then
  echo "当前分支没有 upstream；本地提交已保留，未执行推送。" >&2
  exit 2
fi

if ! git push; then
  echo "推送失败；本地提交已保留，请检查远端状态后手动处理。" >&2
  exit 1
fi

echo "已推送当前分支。"
