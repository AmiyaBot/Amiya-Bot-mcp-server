
import logging

from src.app.context import AppContext
from src.app.services.glossary_queries import query_glossary
from src.app.services.operator_queries import query_operator_basic, query_operator_skill
from src.adapters.cmd.registery import register_command

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

    logger.info(f"查询干员: {operator_name}")
    result = await query_operator_basic(
        ctx,
        operator_name=operator_name,
        operator_name_prefix=operator_name_prefix,
    )
    if result.candidates:
        return f"❌ {result.message}: {', '.join(result.candidates)}，请提供更精确的名称。"
    if result.message:
        return f"❌ {result.message}"
    return f"✅ 查询成功！\n\n{result.data}\n\n图片链接: {result.image_url}"

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

    logger.info(f"查询干员技能: {operator_name}, index={index}, level={level}")
    result = await query_operator_skill(
        ctx,
        operator_name=operator_name,
        index=index,
        level=level,
    )
    if result.candidates:
        return f"❌ {result.message}: {', '.join(result.candidates)}，请提供更精确的名称。"
    if result.message:
        return f"❌ {result.message}"
    return f"✅ 查询成功！\n\n{result.data}"

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

        query_term = args.strip()

        matched_terms = query_glossary(ctx, query_term)
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