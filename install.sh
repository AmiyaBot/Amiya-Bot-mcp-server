#!/usr/bin/env sh
set -eu

APP_NAME="amiyabot-cli"
INSTALL_DIR="${AMIYABOT_INSTALL_DIR:-$HOME/.local/share/amiyabot-cli}"
BIN_DIR="${AMIYABOT_BIN_DIR:-$HOME/.local/bin}"
PIP_SOURCE="${AMIYABOT_PIP_SOURCE:-git+https://github.com/AmiyaBot/Amiya-Bot-mcp-server.git@master}"
INSTALL_PLAYWRIGHT="${AMIYABOT_INSTALL_PLAYWRIGHT:-0}"

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "缺少命令: $1" >&2
        exit 1
    fi
}

ensure_venv() {
    if [ -x "$INSTALL_DIR/venv/bin/python" ]; then
        return
    fi

    python3 -m venv "$INSTALL_DIR/venv" || {
        echo "创建虚拟环境失败，请确认已安装 python3-venv 或等效组件。" >&2
        exit 1
    }
}

write_wrapper() {
    mkdir -p "$BIN_DIR"
    cat > "$BIN_DIR/$APP_NAME" <<EOF
#!/usr/bin/env sh
exec "$INSTALL_DIR/venv/bin/$APP_NAME" "\$@"
EOF
    chmod +x "$BIN_DIR/$APP_NAME"
}

print_path_hint() {
    case ":$PATH:" in
        *":$BIN_DIR:"*)
            echo "$BIN_DIR 已在 PATH 中。"
            ;;
        *)
            echo "请将以下内容加入你的 shell 配置文件，例如 ~/.bashrc："
            echo "export PATH=\"$BIN_DIR:\$PATH\""
            ;;
    esac
}

need_cmd python3

case "$PIP_SOURCE" in
    git+*)
        need_cmd git
        ;;
esac

mkdir -p "$INSTALL_DIR"
ensure_venv

"$INSTALL_DIR/venv/bin/pip" install --upgrade pip setuptools wheel >/dev/null
"$INSTALL_DIR/venv/bin/pip" install --upgrade "$PIP_SOURCE"

if [ "$INSTALL_PLAYWRIGHT" = "1" ]; then
    "$INSTALL_DIR/venv/bin/playwright" install chromium || {
        echo "Playwright 浏览器安装失败，请稍后手动执行: $INSTALL_DIR/venv/bin/playwright install chromium" >&2
    }
fi

write_wrapper

if "$BIN_DIR/$APP_NAME" --help >/dev/null 2>&1; then
    echo "$APP_NAME 安装完成。"
else
    echo "$APP_NAME 已安装，但运行验证失败，请检查 Python 环境和依赖。" >&2
    exit 1
fi

echo "包装命令位置: $BIN_DIR/$APP_NAME"
echo "虚拟环境位置: $INSTALL_DIR/venv"
if [ "$INSTALL_PLAYWRIGHT" != "1" ]; then
    echo "如需完整图片渲染能力，可额外执行: $INSTALL_DIR/venv/bin/playwright install chromium"
fi
print_path_hint