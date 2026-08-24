from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from src.app.context import AppContext

# 直接把你原来的实现挪过来（这里假设函数体不变）
def mark_glossary_used_terms(context: AppContext, text: str) -> List[str]:
    """
    在给定文本中，查找并标记所有出现的 glossary 术语，并且返回这些术语列表。
    """

    if not context.data_repository:
        return []

    bundle = context.data_repository.get_bundle()

    if bundle.tables.get("local_glossary") is None:
        return []

    glossary = bundle.tables["local_glossary"]

    used_terms = set()
    all_glossary_terms = list(glossary.keys())
    normalized_text = text.casefold()

    for g in all_glossary_terms:
        if g.casefold() in normalized_text:
            used_terms.add(g)

    return list(used_terms)
