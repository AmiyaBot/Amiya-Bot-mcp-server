# AmiyaBot MCP Server

该项目提供可安装的命令 amiyabot-cli。

## 安装

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

## 使用

常用方式：

- 启动 Web 服务：amiyabot-cli web
- 进入交互式 CLI：amiyabot-cli
- 执行单次 CLI 指令：amiyabot-cli glossary 攻击力
- 指定命令服务地址：amiyabot-cli --url http://127.0.0.1:9000 glossary 攻击力

安装当前仓库后，amiyabot-cli 会进入环境的 PATH，可直接调用。

https://github.com/hsyhhssyy/Amiya-Bot-mcp-server