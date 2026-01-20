from __future__ import annotations
import logging

from src.helpers.bundle import get_table

from src.app.context import AppContext
from src.domain.models.operator import Operator
from src.domain.types import QueryResult
from src.helpers.glossary import mark_glossary_used_terms

logger = logging.getLogger(__name__)

class OperatorNotFoundError(ValueError):
    pass


def get_operator_basic_core(
    context: AppContext,
    operator_name: str,
    operator_name_prefix: str = "",
) -> QueryResult:
    """
    Core 函数：只做查询与结构化输出，不做 mcp/bot，不拼最终字符串。
    """
    if not context or not context.data_repository:
        raise RuntimeError("数据仓库未初始化")

    bundle = context.data_repository.get_bundle()
    tables = getattr(bundle, "tables", None) or {}

    query_name = f"{operator_name_prefix}{operator_name}"
    operator_id = bundle.operator_name_to_id.get(query_name)

    if not operator_id:
        raise OperatorNotFoundError(f"未找到干员{operator_name}的资料")

    opt = bundle.operators.get(operator_id)
    if not opt or not isinstance(opt, Operator):
        raise OperatorNotFoundError(f"未找到干员{operator_name}的资料")

    opt_detail = opt.detail()

    char_name = opt.name
    char_desc = opt_detail.get("trait", "无描述")
    classes = opt.classes
    classes_sub = opt.classes_sub
    group = opt.group

    # 属性名表与单位表
    attrs_map: dict[str, str] = get_table(tables, "attrs", source="local", default={})
    attrs_unit: dict[str, str] = get_table(tables, "attrs_unit", source="local", default={})

    # 组装属性列表（给模板渲染）
    attrs_list = []
    for k, display_name in attrs_map.items():
        if k in opt_detail:
            unit = attrs_unit.get(k, "")
            attrs_list.append(
                {
                    "key": k,
                    "name": display_name,
                    "value": opt_detail.get(k),
                    "unit": unit,
                }
            )

    # 天赋
    talents_list = []
    for idx, item in enumerate(opt.talents()):
        if item.get("talents_name"):
            talents_list.append(
                {
                    "index": idx + 1,
                    "name": item.get("talents_name", ""),
                    "desc": item.get("talents_desc", ""),
                }
            )

    # 术语
    glossary_used = []
    glossary_used += mark_glossary_used_terms(context, classes)
    glossary_used += mark_glossary_used_terms(context, classes_sub)
    glossary_used = sorted(set(glossary_used))

    return QueryResult(
        type="operator.basic",
        key=operator_id,
        title=char_name,
        data={
            "operator_id": operator_id,
            "query_name": query_name,
            "name": char_name,
            "profession": classes,
            "sub_profession": classes_sub,
            "desc": char_desc,
            "group": group,
            "attrs": attrs_list,
            "talents": talents_list,
            "glossary_used": glossary_used,
        },
        meta={},
    )
