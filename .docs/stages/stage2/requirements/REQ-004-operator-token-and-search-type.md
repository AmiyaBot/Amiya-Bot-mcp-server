# STAGE2-RQ-004 干员查询召唤物输出与 search_operator 类型字段

> 用途：干员查询（MCP / CLI JSON）附带召唤物数据与卡片 URL，并让 search_operator 输出带上实体类型标识，为后续多类型搜索扩展预留。

## 需求卡片

- 需求编号：`STAGE2-RQ-004`
- 名称：干员查询召唤物输出与 search_operator 类型字段
- 优先级：`P1`
- 状态：`done`
- 所属里程碑：`M2`
- 关联总表：[requirements-index.md](../requirements-index.md)

## 背景与目标

- 原版插件（`.temp/Amiya-Bot-plugins`）在查询干员详情时，若该干员拥有召唤物/装置（`displayTokenDict` 与技能 `overrideTokenKey`），会附带一张召唤物卡片；用户要求本项目在 MCP 与 CLI 的 JSON 输出中同样包含召唤物结构化数据与卡片 URL。
- 用户要求 `search_operator` 输出带上实体类型（当前固定为「干员」），为后续多类型搜索（如召唤物、敌人）预留扩展位，但本版本不进一步扩展搜索范围。

## 当前口径

1. 召唤物数据与卡片 URL 放入干员结构化 payload 的 `召唤物` 分区（`data.召唤物`），不放在顶层。
   - `data.召唤物.列表`：语义化召唤物条目（id、名称、英文名、职业、位置、描述、属性、攻击范围）。
   - `data.召唤物.卡片`：召唤物卡片图片 URL；卡片生成失败（如本地无 `BaseUrl`）时该字段缺省，但列表数据始终返回。
2. 干员无召唤物时不包含 `召唤物` 分区。
3. MCP `get_operator_basic_data` 保持无顶层 `image_url`；召唤物卡片 URL 位于 `data` 内部，不受影响。
4. `search_operator` 候选条目增加 `type` 字段（当前固定 `"干员"`），`id` 保持原值不变，下游工具无需适配。
5. 召唤物卡片使用新模板 `operator_token`（`data/templates/operator_token/`），复用干员卡背景与字体资源。

## 实施拆解

1. 数据层：`Operator` 增加 `token_ids` 字段；`OperatorImpl` 从 `displayTokenDict` 与技能 `overrideTokenKey` 收集召唤物 id。
2. 组装层：`operator_output.build_token_entries` 将 `bundle.tokens` 组装为语义化条目；`build_operator_payload` 附加 `召唤物` 分区。
3. 卡片层：`operator_queries._render_operator_token_card` 渲染召唤物卡片并返回 URL，失败降级；新模板 `operator_token.html.j2` / `operator_token.json.j2`。
4. 搜索层：`_build_operator_search_items` 输出增加 `type` 字段。
5. 契约文档：`.docs/common/MCP工具说明.md` 同步更新。

## 验收标准

1. MCP `get_operator_basic_data` 与 CLI `--json op` 对有召唤物的干员返回 `召唤物` 分区（数据 + 卡片 URL）。
2. 无召唤物干员不包含 `召唤物` 分区。
3. `search_operator` 候选条目包含 `type: "干员"`，`id` 保持原值。
4. 召唤物卡片图片可生成并通过 `/cards/operator_token/...` 访问。

## 测试记录

- 时间：2026-08-13
- 场景：凯尔希（召唤物 Mon3tr）CLI JSON 输出
- 操作步骤：本地服务 `main.py --json op 凯尔希`
- 预期结果：`data.召唤物.列表` 含 Mon3tr 完整数据（位置「近战位」），`data.召唤物.卡片` 为可访问的卡片 URL。
- 实际结果：符合预期。卡片 URL 返回 HTTP 200，卡片渲染正常（标题、头像、徽章、描述、属性表、攻击范围）。
- 证据：`resources/cache/cards/operator_token/operator_token:char_003_kalts:cbd0b01:token-v2/artifact.png`

- 时间：2026-08-13
- 场景：银灰（无召唤物）CLI JSON 输出
- 操作步骤：本地服务 `main.py --json op 银灰`
- 预期结果：不包含 `召唤物` 分区。
- 实际结果：符合预期。

- 时间：2026-08-13
- 场景：MCP 工具契约验证
- 操作步骤：通过 MCP SSE 调用 `search_operator`（凯尔希 / 银灰）与 `get_operator_basic_data`。
- 预期结果：`search_operator` 返回 `{"id", "name", "type": "干员"}`；`get_operator_basic_data` 无顶层 `image_url`，凯尔希含 `召唤物` 分区，银灰不含。
- 实际结果：全部断言通过。

### 测试记录模板

- 时间：
- 场景：
- 操作步骤：
- 预期结果：
- 实际结果：
- 证据：

## bug / 修复记录

- 编号：`STAGE2-RQ-004-BUG-001`
- 标题：召唤物「位置」显示「未知」
- 影响范围：`bundle_builder._build_token` 读取位置类型表方式错误（`tables.get("types")` 应为 local 表）。
- 复现路径：查询任意有召唤物干员，召唤物条目「位置」为「未知」。
- 根因：`types` 表位于 `tables["local"]["types"]`，原代码直接取顶层 key。
- 修复方案：改用 `get_table(tables, "types", source="local", default={})`。
- 回归结果：Mon3tr 位置正确显示「近战位」。
- 状态：`done`

## 待确认问题

1. `search_operator` 是否将 `type` 从独立字段改为拼接进 `id`（如 `char_002_amiya-干员`）：已与用户确认，采用独立 `type` 字段，`id` 保持原值。

## 状态更新

- 2026-08-13：建立 REQ-004，完成实现与本地端到端验证，状态 `done`。
- 2026-08-13：按用户确认补齐召唤物天赋与技能：`Token` 模型新增 `talents`/`skills`，`_build_token` 解析 character_table 天赋与技能（含 blackboard 模板），输出层与卡片模板同步展示；卡片 revision 升级为 `token-v3`。鸿雪「打字机」样例验证通过（天赋「弱点速记」+ 3 技能）。
- 2026-08-13：按用户要求增加召唤物技能图标与技能范围：技能条目增加 `icon`/`range` 解析（范围优先技能自身 rangeId，否则回退召唤物基础范围），卡片技能区块复用干员技能图标资源并渲染范围方块图，JSON 技能条目增加「攻击范围」；卡片 revision 升级为 `token-v4`。鸿雪样例验证通过。
