from __future__ import annotations

from typing import List, Union

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

    matched = set()
    all_glossary_terms = list(glossary.keys())

    for query_term in terms:
        for glossary_term in all_glossary_terms:
            if glossary_term in query_term or query_term in glossary_term:
                matched.add(glossary_term)

    changed = True
    while changed:
        changed = False
        for term in list(matched):
            explain = glossary.get(term, "") or ""
            for glossary_term in all_glossary_terms:
                if glossary_term in explain and glossary_term not in matched:
                    matched.add(glossary_term)
                    changed = True

    return {term: glossary[term] for term in all_glossary_terms if term in matched}