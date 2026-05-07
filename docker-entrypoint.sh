#!/bin/sh
set -eu

RESOURCE_MARKER="${AMIYA_RESOURCE_MARKER:-/app/resources/gamedata/excel/character_table.json}"

if [ "${AMIYA_SKIP_RESOURCE_INIT:-0}" != "1" ] && [ ! -f "${RESOURCE_MARKER}" ]; then
  echo "[entrypoint] 本地资源未初始化，开始执行首次资源更新..."
  python -m src.entrypoints.resource_update_worker
fi

exec "$@"