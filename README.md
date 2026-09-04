# AmiyaBot MCP Server

[![GitHub Release](https://img.shields.io/github/v/release/AmiyaBot/Amiya-Bot-mcp-server)](https://github.com/AmiyaBot/Amiya-Bot-mcp-server/releases)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)

AmiyaBot MCP Server 是面向《明日方舟》数据查询的 MCP 服务。它基于本地游戏资源提供结构化数据和图片卡片，并附带命令行工具 `amiyabot-cli`。

1.0.5 版本支持查询干员、技能、精英化与技能升级材料、模组、召唤物、皮肤、材料、关卡、敌人、集成战略藏品和游戏术语。

## 功能

- 通过统一搜索查找干员、召唤物、皮肤、材料、关卡、敌人和集成战略藏品
- 返回结构化数据，并为适合展示的内容生成图片卡片
- 通过 Streamable HTTP 提供 MCP 服务，可接入支持远程 MCP 的客户端
- 提供 CLI、Docker 和 Helm 三种使用方式
- 支持资源首次初始化、后台更新和版本查询

当前提供 12 个 MCP 工具：

| 工具 | 用途 |
| --- | --- |
| `search` | 统一搜索入口，支持每小时同步的干员、敌人和材料常用别名；返回资源 ID 和真实类型，多候选时附带按类型展示的选择卡 |
| `get_operator_basic_data` | 查询干员详情和干员卡片 |
| `get_operator_skill` | 查询干员完整技能列表及所有等级数据 |
| `get_operator_material` | 查询干员培养材料和材料卡片 |
| `get_operator_modules` | 查询干员模组和模组卡片 |
| `get_token_detail` | 查询召唤物详情和召唤物卡片 |
| `get_operator_skins` | 查询干员皮肤和指定皮肤卡片 |
| `get_material` | 查询材料详情、合成路线和关卡掉落 |
| `get_stage_data` | 查询关卡、地图、敌人和掉落信息 |
| `get_enemy_data` | 查询敌人能力、属性和关联单位 |
| `get_integrated_strategy_collectible_detail` | 按统一搜索返回的唯一 ID 查询集成战略藏品详情和卡片 |
| `get_glossary` | 查询游戏术语及计算公式 |

除术语查询外，建议先调用 `search`，再将返回的 ID 传给对应的详情工具。

服务启动后会立即尝试同步旧版 AmiyaBot 全局别名表，之后每小时刷新一次。
别名参与精确、包含和相似度搜索，但不会形成独立的“别名”类型；命中项仍是
对应的干员、敌人或材料，并额外返回 `from_alias` 表示实际命中的别名。
同步失败时继续使用上一次成功的内存快照，不影响正式名称搜索。

统一搜索存在多个候选时会按类型生成选择卡，图片中的序号与结构化
`items` 顺序一致。选择卡使用全部有序结果 ID 的 SHA-256 作为缓存键，
因此返回相同候选和顺序的别名查询可以复用卡片；缓存按条目数和字节数
双重限制执行 LRU 淘汰。

## 运行 MCP 服务

可以通过 Docker、Helm 或本地安装运行 AmiyaBot MCP Server。

### Docker（推荐）

准备一个持久化目录并启动 1.0.5：

```bash
mkdir -p ./amiyabot-resources

docker run -d \
  --name amiyabot-mcp \
  -p 9000:9000 \
  -v "$(pwd)/amiyabot-resources:/app/resources" \
  hsyhhssyy/amiyabot-mcp:v1.0.5
```

首次启动时，容器会自动把游戏资源下载到挂载目录；所需时间取决于网络和磁盘性能。建议为资源、缓存和日志预留至少 20 GiB 空间。

### Helm

准备 `values.yaml`：

```yaml
config:
  baseUrl: https://amiyabot.example.com/

persistence:
  storageClass: nfs-client
  size: 20Gi

ingress:
  enabled: true
  className: nginx
  annotations:
    nginx.ingress.kubernetes.io/proxy-buffering: "off"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
  tls:
    enabled: true
    secretName: amiyabot-example-tls
```

安装 1.0.5：

```bash
helm repo add amiyabot https://AmiyaBot.github.io/Amiya-Bot-mcp-server
helm repo update
helm upgrade --install amiyabot-mcp amiyabot/amiyabot-mcp \
  --version 1.0.5 \
  -f values.yaml
```

Chart 默认创建 PVC 并将其挂载到 `/app/resources`。已有 PVC 可以通过 `persistence.existingClaim` 指定；不需要 Ingress 时，将 `ingress.enabled` 设置为 `false`。Streamable HTTP 包含长连接响应，使用 NGINX Ingress 时建议关闭响应缓冲并调大读写超时，如上例所示。

如果 `config.baseUrl` 包含路径前缀，请同时确认 Ingress Controller 能正确转发该路径。Chart 默认关闭 MCP DNS rebinding protection，以兼容不同的反向代理地址；如需开启，可设置 `config.mcpDnsRebindingProtectionEnabled: true`，并确保 `baseUrl` 与实际访问域名一致。

### 本地安装

需要 Python 3.11 或更高版本、Git，以及用于图片渲染的 Playwright Chromium。

#### 一键安装

下面的命令会将 1.0.5 安装到 `~/.local/share/amiyabot-cli/venv`，并在 `~/.local/bin` 创建 `amiyabot-cli`：

```bash
curl -fsSL https://raw.githubusercontent.com/AmiyaBot/Amiya-Bot-mcp-server/v1.0.5/install.sh \
  | AMIYABOT_PIP_SOURCE="git+https://github.com/AmiyaBot/Amiya-Bot-mcp-server.git@v1.0.5" sh
```

如果 `~/.local/bin` 不在 `PATH` 中，安装脚本会显示需要加入 shell 配置的内容。

不需要图片渲染时，可以跳过 Chromium 安装：

```bash
curl -fsSL https://raw.githubusercontent.com/AmiyaBot/Amiya-Bot-mcp-server/v1.0.5/install.sh \
  | AMIYABOT_PIP_SOURCE="git+https://github.com/AmiyaBot/Amiya-Bot-mcp-server.git@v1.0.5" sh -s -- --no-playwright
```

#### 从源码安装

```bash
git clone --branch v1.0.5 --depth 1 https://github.com/AmiyaBot/Amiya-Bot-mcp-server.git
cd Amiya-Bot-mcp-server

python3 -m venv .venv
./.venv/bin/pip install -e .
./.venv/bin/playwright install chromium
```

验证安装：

```bash
./.venv/bin/amiyabot-cli --help
```

### 启动与健康检查

通过一键安装或源码安装时，使用以下命令启动 Web/MCP 服务：

```bash
amiyabot-cli web
```

Docker 和 Helm 部署会自动启动服务。服务就绪后，可以在服务所在机器上执行健康检查：

```bash
curl http://127.0.0.1:9000/rest/status
```

### 服务端配置

程序会按从低到高的优先级合并以下 JSON 配置：

1. 安装包内置的 `data/config.json`
2. 全局配置文件
3. `resources/config.json`
4. 项目根目录的 `config.json`

Linux 全局配置默认位于 `~/.config/amiyabot-cli/config.json`；设置了 `XDG_CONFIG_HOME` 时，则位于 `$XDG_CONFIG_HOME/amiyabot-cli/config.json`。文件不存在时，程序会尝试自动创建 `{}`。

可用配置项：

| 配置项 | 用途 |
| --- | --- |
| `BaseUrl` | Web 服务的最终访问地址，用于生成卡片和静态资源 URL |
| `CommandServiceUrl` | CLI 执行单次命令时连接的服务地址 |
| `ResourcePath` | 游戏资源、缓存和日志所在目录 |
| `GameDataRepo` | 资源仓库地址 |
| `McpDnsRebindingProtectionEnabled` | 是否启用 MCP DNS rebinding protection |
| `RemoteAssetDownloadConcurrency` | PRTS 等远程素材下载任务共享的最大并发数，默认 `3` |
| `SearchCardCacheMaxEntries` | 统一搜索选择卡最多缓存的结果集合数，默认 `128` |
| `SearchCardCacheMaxBytes` | 统一搜索选择卡缓存的总字节上限，默认 `268435456`（256 MiB） |
| `SearchCardCacheMaxEntryBytes` | 单个统一搜索选择卡缓存目录的字节上限，默认 `16777216`（16 MiB） |

需要下载远程素材的任务应复用应用上下文中的下载管理器；单个请求可以独立设置超时、响应大小、允许主机和内容类型，所有请求共同受上述并发数限制：

```python
from src.app.remote_download_manager import (
    RemoteDownloadRequest,
    get_context_download_manager,
)

result = await get_context_download_manager(context).download(
    RemoteDownloadRequest(
        url="https://media.prts.wiki/path/to/asset.png",
        allowed_hosts=frozenset({"media.prts.wiki"}),
        allowed_content_types=frozenset({"image/png"}),
    )
)
```

批量任务可以调用同一管理器的 `download_many`；无需再自行创建并发信号量。

只覆盖本机 CLI 的服务地址时，可以使用：

```json
{
  "BaseUrl": "http://127.0.0.1:9000/",
  "CommandServiceUrl": "http://127.0.0.1:9000/"
}
```

服务通过域名或反向代理对外提供时，需要把 `BaseUrl` 设置为最终访问地址。`BaseUrl` 用于生成图片和静态资源链接，应包含协议、域名以及必要的路径前缀，并建议以 `/` 结尾。例如：

```json
{
  "BaseUrl": "https://amiyabot.example.com/"
}
```

使用 Docker 时，可以将该配置保存为 `config.json` 并挂载到容器中：

```bash
docker run -d \
  --name amiyabot-mcp \
  -p 9000:9000 \
  -v "$(pwd)/amiyabot-resources:/app/resources" \
  -v "$(pwd)/config.json:/app/config.json:ro" \
  hsyhhssyy/amiyabot-mcp:v1.0.5
```

## 接入 MCP 服务

新客户端建议通过 Streamable HTTP 连接单一 `/mcp` 端点。本机默认地址为：

```text
http://127.0.0.1:9000/mcp
```

如果 MCP 客户端与服务端不在同一台主机或同一个容器网络中，需要将 `127.0.0.1` 替换为客户端能够访问的最终域名或地址。迁移期内仍保留了旧 SSE 入口 `/mcp/sse`，新配置建议使用 Streamable HTTP。

### 通用客户端配置

常见的 MCP 客户端配置如下；不同客户端使用的字段名可能略有不同：

```json
{
  "mcpServers": {
    "amiya-mcp": {
      "transport": "streamable-http",
      "url": "http://127.0.0.1:9000/mcp"
    }
  }
}
```

部分客户端将 `transport` 的值命名为 `http` 或 `streamable_http`，请以该客户端的配置格式为准；服务端的端点路径均为 `/mcp`。

### AstrBot

AstrBot 将 Streamable HTTP 传输类型命名为 `streamable_http`（下划线），配置示例如下：

```json
{
  "transport": "streamable_http",
  "url": "http://127.0.0.1:9000/mcp"
}
```

不要在 AstrBot 中将 `transport` 写成 `streamable-http`（连字符）。当 AstrBot 不能识别该传输类型时，连接测试可能会向 `/mcp` 误发 GET 请求，并收到 `400 Bad Request: Missing session ID`。此错误通常表示客户端传输配置不匹配，不是 MCP 端点不可用。

### DeepSeek Harness

DeepSeek Harness 官方的 `@deepseek-ai/dsh-mcp-client` 已随 `dsh` CLI 提供，但默认 profile 不会启用任何 MCP 服务器。需要在 profile 的 `cordis.patch.yml` 中插入一个 MCP client 实例；这一行配置会同时启用官方 MCP 插件并连接 AmiyaBot MCP Server。

先运行一次 Harness 以初始化 `web` profile：

```bash
dsh web
```

默认配置文件位于 `~/.dsh/profiles/web/cordis.patch.yml`。如果设置了 `DSH_HOME`，则位于 `$DSH_HOME/profiles/web/cordis.patch.yml`；使用其他 profile 时，将路径中的 `web` 换成对应名称。

如果文件不存在，创建并写入以下内容；如果已有其他配置，将下面的 `insert` 项追加到现有顶层 YAML 数组中，不要覆盖原配置：

```yaml
- insert:
    - id: mcp-amiyabot
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: amiyabot
        transport: streamable-http
        url: http://127.0.0.1:9000/mcp
        toolCallTimeoutMs: 120000
```

保存后重启 Harness：

```bash
dsh web
```

Harness 会将 MCP 工具注册为带服务器命名空间的原生工具，例如 `search` 会显示为 `mcp__amiyabot__search`。可以用以下命令检查最终合并后的 profile 配置：

```bash
dsh --profile web --dump-config
```

如果 Harness 与 MCP 服务器不在同一台主机或同一个容器网络中，需要将 `url` 替换为 Harness 能够访问的最终地址，不能使用 MCP 服务器自己的 `127.0.0.1`。更多配置项参见 [DeepSeek Harness 官方 MCP client 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md)。

## CLI 使用

```bash
# 进入交互模式
amiyabot-cli

# 执行单次查询
amiyabot-cli op 阿米娅
amiyabot-cli material 银灰
amiyabot-cli glossary 攻击力

# 查看详细的命令服务连接过程
amiyabot-cli --verbose op 阿米娅

# 连接另一台 AmiyaBot MCP Server
amiyabot-cli --url https://amiyabot.example.com/ op 阿米娅
```

常用管理命令：

| 命令 | 用途 |
| --- | --- |
| `config-path` | 查看所有参与合并的配置文件路径 |
| `resource-version` | 查看当前资源版本 |
| `resource-update` | 在后台触发资源更新 |
| `resource-update-status` | 查看最近一次资源更新的状态和结果 |

如果本地没有资源数据，先执行：

```bash
amiyabot-cli resource-update
amiyabot-cli resource-update-status
```

Web 服务每 60 秒执行一次轻量资源可读性检查，每 15 分钟检查一次远端更新。资源异常时会立即进入自动恢复；所有更新和恢复都在 `resources/runtime/resource-updates/` 的独立事务目录中完成。只有 Git 拉取、解压、权限归一、必需 JSON 校验和候选 Bundle 构建全部成功后，服务才会通过 `resources/runtime/active-resource-release.json` 原子切换到 `resources/releases/<release-id>/`。在线版本不会被原地覆盖，清单同时保留上一有效版本用于回退。

`/health/ready` 表示当前 Bundle 与其磁盘资源均可用；异常时 Pod 会先退出 Service 流量。`/health/live` 只会在连续 3 次自动恢复失败且内存中没有有效 Bundle 后返回失败，让 Kubernetes 重启容器。Git、解压或发布事务持锁期间 liveness 不会失败。Helm 的 PreStop 最多等待 840 秒让资源事务结束，Pod 总终止宽限期默认是 900 秒。

旧版 `resources/assets/` 与 `resources/gamedata/` 会继续作为首次启动的只读来源；第一次成功更新后自动迁移到版本化发布目录。执行单次 CLI 查询时，如果本地命令服务尚未运行，CLI 会尝试自动在后台启动它。

## 升级

- Docker：拉取目标版本镜像后，用相同的端口、配置和资源目录重新创建容器。`/app/resources` 已正确挂载时，资源和缓存会保留。
- Helm：更新仓库后执行 `helm upgrade`，并通过 `--version` 固定目标 Chart 版本。
- 一键安装：将命令中的版本号替换为目标版本后重新执行，安装脚本会升级现有虚拟环境。

建议始终使用明确的版本号，不要依赖可变镜像标签。

## 常见问题

### 图片链接无法访问

检查 `BaseUrl` 是否为 MCP 客户端可访问的地址。远程客户端不能使用服务端自己的 `127.0.0.1`。

### 返回 `421 Invalid Host header`

启用了 `McpDnsRebindingProtectionEnabled` 时，访问域名需要与 `BaseUrl` 一致。也可以在可信的反向代理环境中关闭该选项。

### 没有生成图片卡片

检查 `/rest/status` 返回的 `playwright.ready`。本地安装还可以重新执行：

```bash
playwright install chromium
```

结构化数据不依赖卡片生成，Playwright 不可用时仍可查询。

### 可以直接暴露到公网吗

服务本身不提供访问认证。公网部署时，请通过反向代理、访问控制或防火墙限制访问，并启用 HTTPS。

## 项目地址

<https://github.com/AmiyaBot/Amiya-Bot-mcp-server>
