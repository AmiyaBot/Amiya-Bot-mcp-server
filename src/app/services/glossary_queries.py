from __future__ import annotations

from typing import TYPE_CHECKING, List, Union

if TYPE_CHECKING:
    from src.app.context import AppContext


def split_terms(raw_value: str) -> List[str]:
    if not isinstance(raw_value, str):
        return []

    normalized = raw_value
    for separator in ["，", ",", "、", ";", "；"]:
        normalized = normalized.replace(separator, " ")
    return [part.strip() for part in normalized.split() if part.strip()]


def query_glossary(context: AppContext, glossary_name: Union[List[str], str]) -> dict[str, str]:
    if not context.data_repository:
        return {}

    bundle = context.data_repository.get_bundle()
    glossary = bundle.tables.get("local_glossary")
    if glossary is None:
        return {}

    terms: List[str] = []
    if isinstance(glossary_name, list):
        for item in glossary_name:
            if isinstance(item, str) and item.strip():
                terms.extend(split_terms(item))
    elif isinstance(glossary_name, str):
        terms = split_terms(glossary_name)
    else:
        return {}

    matched: set[str] = set()
    all_glossary_terms = list(glossary.keys())
    normalized_explanations = {
        glossary_term: str(glossary.get(glossary_term, "") or "").casefold()
        for glossary_term in all_glossary_terms
    }

    for query_term in terms:
        normalized_query = query_term.casefold()

        # 名称匹配优先，避免常见关键词因出现在大量解释中而扩大初始结果集。
        name_matches = {
            glossary_term
            for glossary_term in all_glossary_terms
            if normalized_query in glossary_term.casefold()
            or glossary_term.casefold() in normalized_query
        }
        if name_matches:
            matched.update(name_matches)
            continue

        # 名称没有命中时再查解释，用于兼容“法抗”“魔法抗性”等别名。
        for glossary_term in all_glossary_terms:
            if normalized_query in normalized_explanations[glossary_term]:
                matched.add(glossary_term)

    changed = True
    while changed:
        changed = False
        for term in list(matched):
            normalized_explain = normalized_explanations[term]
            for glossary_term in all_glossary_terms:
                if (
                    glossary_term.casefold() in normalized_explain
                    and glossary_term not in matched
                ):
                    matched.add(glossary_term)
                    changed = True

    return {term: glossary[term] for term in all_glossary_terms if term in matched}
