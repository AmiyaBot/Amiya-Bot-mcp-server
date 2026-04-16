# AmiyaBot MCP Server

该项目提供可安装的命令 amiyabot-cli。

## 安装

### 一键安装

可以直接使用 GitHub 上的安装脚本：

```bash
curl -fsSL https://raw.githubusercontent.com/AmiyaBot/Amiya-Bot-mcp-server/master/install.sh | sh
```

这个脚本默认会：

- 将程序安装到 `~/.local/share/amiyabot-cli/venv`
- 在 `~/.local/bin/amiyabot-cli` 生成包装命令
- 默认安装 Playwright 浏览器，以便直接具备完整图片渲染能力

如果 `~/.local/bin` 还没在 PATH 中，脚本会提示你把它加入 shell 配置。

如果你不希望安装 Playwright 浏览器，可以显式传入 `--no-playwright`：

```bash
curl -fsSL https://raw.githubusercontent.com/AmiyaBot/Amiya-Bot-mcp-server/master/install.sh | sh -s -- --no-playwright
```

### 手动安装

建议在项目根目录使用虚拟环境安装：

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .
```

安装完成后，可以先验证命令是否已经生成：

```bash
./.venv/bin/amiyabot-cli --help
```

如果希望在当前 shell 里直接调用 amiyabot-cli，有两种常用方式：

1. 激活虚拟环境

```bash
source .venv/bin/activate
amiyabot-cli --help
```

2. 将当前项目的虚拟环境加入 PATH

```bash
export PATH="$PWD/.venv/bin:$PATH"
amiyabot-cli --help
```

如果你想长期生效，可以把上面的 export 写入 shell 配置文件，例如 ~/.bashrc。

如果需要完整的图片渲染能力，还需要额外安装 Playwright 浏览器：

```bash
./.venv/bin/playwright install chromium
```

## 全局配置

CLI 现在支持读取全局 JSON 配置。

- Linux 下默认位置遵循 XDG 规范：`$XDG_CONFIG_HOME/amiyabot-cli/config.json`
- 如果没有设置 `XDG_CONFIG_HOME`，默认位置就是 `~/.config/amiyabot-cli/config.json`
- 程序首次读取配置时，如果这个文件不存在，会自动创建一个空内容的 `{}`

配置优先级从低到高依次是：

- 安装包内置的 `data/config.json`
- 全局配置文件
- 项目内的 `resources/config.json`
- 项目根目录的 `config.json`

如果你只想给全局安装的 CLI 指定远端 URL，可以在全局配置里只写需要覆盖的字段，例如：

```json
{
	"BaseUrl": "https://your-public-host.example.com/",
	"CommandServiceUrl": "https://your-command-service.example.com/"
}
```

## 使用

常用方式：

- 启动 Web 服务：amiyabot-cli web
- 进入交互式 CLI：amiyabot-cli
- 执行单次 CLI 指令：amiyabot-cli glossary 攻击力
- 查看执行流程：amiyabot-cli --verbose glossary 攻击力
- 查看所有参与合并的配置路径：amiyabot-cli config-path
- 查询当前资源版本：amiyabot-cli resource-version
- 查询最近一次资源更新时间和结果：amiyabot-cli resource-update-status
- 手动触发一次后台资源更新：amiyabot-cli resource-update
- 指定命令服务地址：amiyabot-cli --url http://127.0.0.1:9000 glossary 攻击力

如果本地还没有任何资源数据，`op`、`skill`、`glossary` 和 `resource-version` 会立即提示先执行 `resource-update`，不会再等待首次初始化完成。

安装当前仓库后，amiyabot-cli 会进入环境的 PATH，可直接调用。

https://github.com/hsyhhssyy/Amiya-Bot-mcp-server