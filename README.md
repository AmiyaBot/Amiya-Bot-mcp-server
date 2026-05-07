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

### Docker 运行

项目 release 发布后，会由 GitHub Actions 自动构建 Docker 镜像并推送到 Docker Hub。
同时会自动更新 `latest` 标签。

```bash
mkdir -p ./amiyabot-resources

docker run -d \
	--name amiyabot-mcp \
	-p 9000:9000 \
	-v "$(pwd)/amiyabot-resources:/app/resources" \
	hsyhhssyy/amiyabot-mcp:latest
```

说明：

- `./amiyabot-resources:/app/resources` 会把资源目录映射到宿主机，资源更新、缓存和日志都会持久化到这里
- 如果挂载的是一个空目录，容器首次启动时会先自动拉取资源，再启动 Web 服务
- 资源仓库默认使用程序内置配置：`https://gitee.com/amiya-bot/amiya-bot-assets.git`
- 日常使用直接拉 `latest` 即可

如果你需要把对外访问地址改成自己的域名或反向代理地址，再额外挂载一个只覆盖 `BaseUrl` 的配置文件：

```json
{
	"BaseUrl": "https://amiyabot.example.com/"
}
```

```bash
docker run -d \
	--name amiyabot-mcp \
	-p 9000:9000 \
	-v "$(pwd)/amiyabot-resources:/app/resources" \
	-v "$(pwd)/config.json:/app/config.json:ro" \
	hsyhhssyy/amiyabot-mcp:latest
```

启动后可通过以下地址验证：

- 健康检查：`http://127.0.0.1:9000/rest/status`
- MCP SSE：`http://127.0.0.1:9000/mcp/sse`

### Helm 部署

仓库内置了 Helm chart：`charts/amiyabot-mcp`。

这个 chart 支持：

- 在 `values.yaml` 里配置对外 `BaseUrl`
- 根据 `BaseUrl` 自动生成 Ingress 的 host 和 path
- 通过 `persistence.storageClass` 选择 PVC 使用的 StorageClass
- 只创建 PVC，不创建 PV
- 默认镜像标签使用 `latest`
- 默认资源仓库使用程序内置配置，无需额外填写

最小化的 values 示例：

```yaml
config:
  baseUrl: https://amiyabot.example.com/

persistence:
  storageClass: nfs-client
  size: 20Gi

ingress:
  enabled: true
  className: nginx
```

安装方式：

```bash
helm upgrade --install amiyabot-mcp ./charts/amiyabot-mcp -f your-values.yaml
```

说明：

- chart 会把资源目录挂载到 `/app/resources`
- chart 默认创建 PVC；如果你已经有现成的 claim，可以设置 `persistence.existingClaim`
- `config.baseUrl` 建议直接写最终对外访问地址，例如 `https://amiyabot.example.com/`
- 如果 `config.baseUrl` 包含路径前缀，chart 会按该路径生成 Ingress，但具体是否需要重写路径，取决于你的 Ingress Controller 配置
- 如果你需要固定某个版本，再显式设置 `image.tag`

## 全局配置

现在支持读取全局 JSON 配置。

- Linux 下默认位置遵循 XDG 规范：`$XDG_CONFIG_HOME/amiyabot-cli/config.json`
- 如果没有设置 `XDG_CONFIG_HOME`，默认位置就是 `~/.config/amiyabot-cli/config.json`
- 程序首次读取配置时，如果这个文件不存在，会自动创建一个空内容的 `{}`

配置优先级从低到高依次是：

- 安装包内置的 `data/config.json`
- 全局配置文件
- 项目内的 `resources/config.json`
- 项目根目录的 `config.json`

其中 `BaseUrl` 会作为 MCP 服务器生成图片和静态资源链接的地址前缀。
请确保 MCP 的使用方能够通过这个地址访问到当前服务；如果 MCP 客户端不在同一台机器上，就不要使用 `127.0.0.1`。

如果你只想给全局安装的 CLI 指定需要覆盖的 URL，可以在全局配置里只写相关字段，例如：

```json
{
	"BaseUrl": "http://127.0.0.1:9000/",
	"CommandServiceUrl": "http://127.0.0.1:9000/"
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