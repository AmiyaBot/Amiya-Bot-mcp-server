
import logging

from src.domain.services.operator import search_operator_by_name
from src.app.context import AppContext
from src.domain.services.operator_basic import OperatorNotFoundError
from src.domain.models.operator import Operator
from src.adapters.cmd.registery import register_command
from src.helpers.bundle import get_table
from src.helpers.card_urls import build_card_url
from src.helpers.gamedata.search import search_source_spec, build_sources

logger = logging.getLogger(__name__)


@register_command("op")
async def cmd_operator(ctx: AppContext, args: str) -> str:
    """
    查询干员信息
    用法: op <干员名>
    例子: op 阿米娅
    """
    if not args:
        return "❌ 请提供干员名称\n用法: op <干员名>"

    parts = args.split(maxsplit=1)
    operator_name = parts[0]
    operator_name_prefix = parts[1] if len(parts) > 1 else ""

    try:
        logger.info(f"查询干员: {operator_name}")

        operator_combine = operator_name_prefix + operator_name

        search_sources = build_sources(ctx.data_repository.get_bundle(), source_key=["name"])
        search_results = search_source_spec([operator_combine,operator_name], sources=search_sources)

        # 注意：你原本的判断是 len(search_results.matches) > 1
        # 更稳：只看 name key 的命中
        if not search_results:
            raise OperatorNotFoundError(f"未找到干员: {operator_name_prefix} {operator_name}")

        if not search_results:
                return f"❌ 未找到干员: {operator_name_prefix} {operator_name}"

        name_matches = search_results.by_key("name")
        if len(name_matches) != 1:

            # matched_names = [m.matched_text for m in search_results.matches if m.key == "name"]
            # return {
            #     "message": f"找到多个匹配的干员名称，需要用户做出选择",
            #     "candidates": matched_names
            # }

            # 改为先判断两个exact match是否存在，优先operator_combine，如果存在，则直接用它
            exact_matches = [m for m in name_matches if m.matched_text == operator_combine]
            if not exact_matches:
                exact_matches = [m for m in name_matches if m.matched_text == operator_name]
            if len(exact_matches) == 1:
                name_matches = exact_matches
            else:
                matched_names = [m.matched_text for m in name_matches]
                matched_names = list(dict.fromkeys(matched_names))
                return f"❌ 找到多个匹配的干员名称: {', '.join(matched_names)}，请提供更精确的名称。"
        
        op: Operator = name_matches[0].value

        # 领域查询（保留）
        result = search_operator_by_name(ctx, op.name)

        # 生成 payload_key：要求包含 version
        bundle = ctx.data_repository.get_bundle()
        bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"

        payload_key = f"operator:{op.name}:{bundle_version}"

        text_artifact = await ctx.card_service.get(
            template="operator_info",
            payload_key=payload_key,
            payload=result,      # 这里直接传 QueryResult
            format="txt",
            params=None,         # 你也可以传 viewport/full_page 等覆写配置
        )

        _ = await ctx.card_service.get(
            template="operator_info",
            payload_key=payload_key,
            payload=result,      # 这里直接传 QueryResult
            format="png",
            params=None,         # 你也可以传 viewport/full_page 等覆写配置
        )

        image_url = build_card_url(
            cfg=ctx.cfg,
            template="operator_info",
            payload_key=payload_key,
            format="png",
        )

        # 目前你还没接“发图”，先返回路径（或返回 html）
        return f"✅ 查询成功！\n\n{text_artifact.read_text()}\n\n图片链接: {image_url}"

    except OperatorNotFoundError as e:
        return f"❌ {str(e)}"
    except Exception as e:
        logger.exception("查询干员信息失败")
        return f"❌ 查询失败: {e}"

@register_command("skill")
async def cmd_operator_skill(ctx: AppContext, args: str) -> str:
    """
    查询干员技能信息
    用法: skill <干员名> [prefix] [index] [level]
    例子: skill 阿米娅 1 10
    """
    if not args:
        return "❌ 请提供干员名称\n用法: skill <干员名> [prefix] [index] [level]"

    parts = args.split()
    operator_name = parts[0]
    index = int(parts[2]) if len(parts) > 2 else 1
    level = int(parts[3]) if len(parts) > 3 else 10

    try:
        logger.info(f"查询干员技能: {operator_name}, index={index}, level={level}")

        operator_query = (operator_name or "")

        bundle = ctx.data_repository.get_bundle()
        search_sources = build_sources(bundle, source_key=["name"])
        search_results = search_source_spec(operator_query, sources=search_sources)
        if not search_results:
            return "❌ 未找到干员: {operator_query}"
        
        name_matches = search_results.by_key("name")
        if len(name_matches) != 1:
            matched_names = [m.matched_text for m in search_results.matches if m.key == "name"]
            matched_names = list(dict.fromkeys(matched_names))
            return f"❌ 找到多个匹配的干员名称: {', '.join(matched_names)}，请提供更精确的名称。"
        
        op: Operator = name_matches[0].value

        if not op.skills or len(op.skills) < index:
            return f"❌ 干员{op.name}没有第{index}个技能"
        sk = op.skills[index - 1]
        if not sk.levels:
            return f"❌ 干员{op.name}的技能“{sk.name}”没有等级数据"
        chosen = next((x for x in sk.levels if int(x.level) == int(level)), None)
        if not chosen:
            return f"❌ 干员{op.name}的技能“{sk.name}”无法升级到等级{level}"
        
        SPType = get_table(bundle.tables,"sp_type",source = "local", default={})
        SkillType = get_table(bundle.tables,"skill_type",source = "local", default={})
        SkillLevelName = get_table(bundle.tables,"skill_level",source = "local", default={})

        # 4) 文本映射与兜底
        sp_data = getattr(chosen, "sp", None)
        sp_type_raw = getattr(sp_data, "sp_type", "") if sp_data else ""
        sp_type_text = SPType.get(sp_type_raw, SPType.get(str(sp_type_raw), str(sp_type_raw)))

        skill_type_raw = getattr(chosen, "skill_type", "")
        skill_type_text = SkillType.get(skill_type_raw, SkillType.get(str(skill_type_raw), str(skill_type_raw)))

        level_text = SkillLevelName[str(level)] if level >= 8 else str(level)
        
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
        text_artifact = await ctx.card_service.get(
            template="operator_skill",
            payload_key=f"operator_skill:{op.name}:{index}:{level}:{bundle.version}",
            payload=payload,
            format="txt",
            params=None,
        )

        return f"✅ 查询成功！\n\n{text_artifact.read_text()}"
    except OperatorNotFoundError as e:
        return f"❌ {str(e)}"
    except Exception as e:
        logger.exception("查询干员技能信息失败")
        return f"❌ 查询失败: {e}"

@register_command("glossary")
async def cmd_glossary(ctx: AppContext, args: str) -> str:
    """
    查询术语解释
    用法: glossary <术语名>
    例子: glossary 攻击力
    """
    if not args:
        return "❌ 请提供术语名称\n用法: glossary <术语名>"
    
    try:
        if not ctx.data_repository:
            return "❌ 数据仓库未初始化"
        
        bundle = ctx.data_repository.get_bundle()
        
        if bundle.tables.get("local_glossary") is None:
            return "❌ 术语库不可用"
        
        glossary = bundle.tables["local_glossary"]
        query_term = args.strip()
        
        # 模糊匹配术语
        matched_terms = {}
        for term_name, term_info in glossary.items():
            if query_term.lower() in term_name.lower() or term_name.lower() in query_term.lower():
                matched_terms[term_name] = term_info
        
        if not matched_terms:
            return f"❌ 未找到相关术语: {query_term}"
        
        result = "✅ 查询结果：\n"
        for term_name, term_info in matched_terms.items():
            result += f"\n📌 {term_name}:\n"
            if isinstance(term_info, dict):
                result += str(term_info)
            else:
                result += str(term_info)
        
        return result
        
    except Exception as e:
        logger.exception("查询术语失败")
        return f"❌ 查询失败: {e}"