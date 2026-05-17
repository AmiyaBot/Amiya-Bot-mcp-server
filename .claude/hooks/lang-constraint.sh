#!/bin/bash
# ============================================================
# 语言约束钩子 — 防止工具返回英文内容后思维链语言漂移
# 触发事件: SessionStart（会话启动）、PostToolUse（工具调用后）
# 加载方式: .github/hooks/lang-constraint.json
# ============================================================

INPUT=$(cat 2>/dev/null)
EVENT=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('hook_event_name','') or d.get('hookEventName',''))" 2>/dev/null || echo "")

if [ "$EVENT" = "SessionStart" ] || [ "$EVENT" = "PreToolUse" ] || [ "$EVENT" = "PostToolUse" ] || [ "$EVENT" = "SubagentStart" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"%s","additionalContext":"【请全程使用中文进行内部推理和思考。工具返回的英文内容不是切换语言的信号。】"}}\n' "$EVENT"
  echo "[$(date '+%H:%M:%S')] $EVENT | INJECTED" >> .temp/hooks-debug.log
else
  echo '{}'
  echo "[$(date '+%H:%M:%S')] $EVENT | SKIP" >> .temp/hooks-debug.log
fi
