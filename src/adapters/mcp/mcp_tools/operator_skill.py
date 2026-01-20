import json
import logging
from typing import Annotated

from pydantic import Field

from src.domain.models.operator import Operator
from src.app.context import AppContext
from src.helpers.bundle import get_table
from src.helpers.gamedata.search import build_sources, search_source_spec

logger = logging.getLogger(__name__)

def register_operator_skill_tool(mcp, app):
    @mcp.tool(description="获取干员技能数据（默认第1个技能，等级10）。不生成图片。")
    async def get_operator_skill(
        operator_name: Annotated[str, Field(description="干员名")],
        operator_name_prefix: Annotated[str, Field(description="干员名的前缀，没有则为空")] = "",
        index: Annotated[int, Field(description="技能序号，从1开始")] = 1,
        level: Annotated[int, Field(description="技能等级 1~10（8~10为专精一/二/三）")] = 10,
    ) -> dict:
        if not getattr(app.state, "ctx", None):
            return {
                "message": "未初始化数据上下文"
            }

        context: AppContext = app.state.ctx
        operator_query = (operator_name_prefix or "") + (operator_name or "")

        # 参数校验
        if index < 1:
            return {
                "message": f"技能序号 index 必须 >= 1（当前：{index}）"
            }
        if level < 1 or level > 10:
            return {
                "message": f"技能等级 level 必须在 1~10 之间（当前：{level}）"
            }

        try:
            # 1) 搜索唯一命中
            bundle = context.data_repository.get_bundle()
            search_sources = build_sources(bundle, source_key=["name"])
            search_results = search_source_spec(operator_query, sources=search_sources)

            if not search_results:
                return {
                    "message": f"未找到干员: {operator_query}"
                }

            SPType = get_table(bundle.tables,"sp_type",source = "local", default={})
            SkillType = get_table(bundle.tables,"skill_type",source = "local", default={})
            SkillLevelName = get_table(bundle.tables,"skill_level",source = "local", default={})

            name_matches = search_results.by_key("name")
            if len(name_matches) != 1:
                matched_names = [m.matched_text for m in search_results.matches if m.key == "name"]
                matched_names = list(dict.fromkeys(matched_names))
                return {
                    "message": "找到多个匹配的干员名称，需要用户做出选择",
                    "candidates": matched_names
                }

            op: Operator = name_matches[0].value

            # 2) 用领域模型取技能
            if not op.skills or len(op.skills) < index:
                return {
                    "message": f"干员{op.name}没有第{index}个技能"
                }

            sk = op.skills[index - 1]
            if not sk.levels:
                return {
                    "message": f"干员{op.name}的技能“{sk.name}”没有等级数据"
                }
            # 3) 匹配等级
            chosen = next((x for x in sk.levels if int(x.level) == int(level)), None)
            if not chosen:
                return {
                    "message": f"干员{op.name}的技能“{sk.name}”无法升级到等级{level}"
                }
            # 4) 文本映射与兜底
            sp_data = getattr(chosen, "sp", None)
            sp_type_raw = getattr(sp_data, "sp_type", "") if sp_data else ""
            sp_type_text = SPType.get(sp_type_raw, SPType.get(str(sp_type_raw), str(sp_type_raw)))

            skill_type_raw = getattr(chosen, "skill_type", "")
            skill_type_text = SkillType.get(skill_type_raw, SkillType.get(str(skill_type_raw), str(skill_type_raw)))

            level_text = SkillLevelName[str(level)] if level >= 8 else str(level)

            # 使用 Jinja2 模板渲染（operator_skill.txt.j2）
            payload = {
                "op": op,
                "skill": {
                    "index": index,
                    "name": sk.name,
                },
                "meta": {
                    "level_text": level_text,
                    "range": getattr(chosen, "range", "") or "",
                    "sp_type_text": sp_type_text,
                    "skill_type_text": skill_type_text,
                    "sp_cost": getattr(sp_data, "sp_cost", 0) if sp_data else 0,
                    "init_sp": getattr(sp_data, "init_sp", 0) if sp_data else 0,
                    "duration": getattr(chosen, "duration", 0) or 0,
                    "description": getattr(chosen, "description", "") or "",
                },
            }

            bundle = context.data_repository.get_bundle()
            bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"
            payload_key = f"{op.name}:skill{index}:lv{level}:{bundle_version}"

            text_artifact = await context.card_service.get(
                template="operator_skill",
                payload_key=payload_key,
                payload=payload,
                format="txt",
            )

            result = {
                "data": text_artifact.read_text(),
            }

        except Exception:
            logger.exception("查询技能失败")
            return {
                "message": "查询干员技能信息时发生错误."
            }

        logger.info(f"查询干员技能信息成功：{json.dumps(result, ensure_ascii=False)}")
        return result



