# .docs — 项目文档

## 项目背景

本仓库是 QQ 机器人 AmiyaBot 官方插件库 [AmiyaBot/Amiya-Bot-plugins](https://github.com/AmiyaBot/Amiya-Bot-plugins) 中**明日方舟数据展示**相关能力的 MCP 重做版。

- **原版代码本地副本**：原插件仓库代码已克隆至 `.temp/Amiya-Bot-plugins`,复刻功能时可在此对照原实现。
- **复刻范围**：原插件库功能很多(签到、抽卡、游戏等),本仓库只关注其中**明日方舟数据展示**相关内容,其余功能不关心。
- **重做方式**：不是代码一比一复刻,而是在保证功能一致的基础上**全新重做**,包括数据结构层面的调整。
- **交付形态**：独立 MCP Server,对外暴露 MCP 工具(SSE 协议 `/mcp/sse`)与 REST 端点(`/rest/status` 等),提供可安装命令 `amiyabot-cli`。

## 本仓库技术特点

- 分层架构:`adapters`(cmd/mcp)→ `app`(bootstrap/渲染器/服务/转换器)→ `domain`(领域模型与服务)。
- 数据结构重做:调整了 `TableData` 的 PythonObject 结构,把其中因历史遗留产生的一系列字段修正为更合适的组织形式,并优化了加载速度。
- 卡片渲染:Jinja2 模板 + Playwright 服务端渲染,支持 html/json/txt 三种输出。
- 游戏数据:位于 `resources/gamedata/`,是解包工具解出的游戏 JSON(如 `excel/character_table.json` 等),本项目据此进行数据分析和展示。
- 静态资源:头像、立绘等展示资源同样位于 `resources/`(来自 `https://gitee.com/amiya-bot/amiya-bot-assets.git`),通过 `BaseUrl` 配置对外提供,支持 Docker / Helm 部署。

## 目录结构

```
.docs/
├── README.md              # 本文件:项目背景与目录说明
├── common/                # 跨 stage 稳定复用的共享资料
│   ├── MCP工具说明.md      # 对外 MCP 工具契约
│   └── stage-template/    # stage 文档模板
└── stages/                # 各阶段规划文档
    ├── stage1/
    └── stage2/
```

## 相关地址

- 原始插件仓库:<https://github.com/AmiyaBot/Amiya-Bot-plugins>
- 资源仓库:<https://gitee.com/amiya-bot/amiya-bot-assets.git>
