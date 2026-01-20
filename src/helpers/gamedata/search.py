
from typing import Any, Literal
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, List, Optional, Sequence, Union

from src.domain.models.operator import Operator
from src.data.models.bundle import DataBundle
from src.app.context import AppContext

MatchKind = Literal["exact", "contains", "similar"]
QueryInput = Union[str, Sequence[str]] 

@dataclass(frozen=True)
class MatchResult:
    key: str              # name / skin / group ...
    matched_text: str     # 匹配到的关键词（比如 “史尔特尔”）
    value: Any            # 关联对象（比如 Operator / skin_id / group_id）
    kind: MatchKind       # "exact" | "contains" | "similar"
    score: float          # 可选：相似度得分（如果你的 find_most_similar 能返回）
    source_order: int     # SourceSpec 的顺序，用来稳定排序
    query_order: int      # query 在传入数组中的顺序，用来稳定同级排序

@dataclass
class SearchResults:
    matches: List[MatchResult]

    @property
    def first(self) -> Optional[MatchResult]:
        return self.matches[0] if self.matches else None

    def by_key(self, key: str) -> List[MatchResult]:
        return [m for m in self.matches if m.key == key]
    
    def __bool__(self) -> bool:
        return bool(self.matches)

@dataclass(frozen=True)
class SourceSpec:
    key: str
    candidates: Callable[[], Sequence[str]]
    resolve: Callable[[str], Any]

    # 命中 exact 后是否继续往下做 contains/similar
    continue_after_exact: bool = False

    # 这个 SourceSpec 自己是否允许 fuzzy（global exact_only 会覆盖它）
    allow_fuzzy: bool = True

def _sim(a: str, b: str) -> float:
    # 0~1
    return SequenceMatcher(None, a, b).ratio()

def _normalize_queries(query: QueryInput) -> List[str]:
    """
    把 query 统一成 list[str]：
    - 支持 str / Sequence[str]
    - strip
    - 去空
    - 去重但保留顺序
    """
    if isinstance(query, str):
        items = [query]
    else:
        items = list(query)

    seen = set()
    out: List[str] = []
    for q in items:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if not q:
            continue
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
    return out

def _search_one_query(
    query: str,
    *,
    query_order: int,            # ✅ 新增
    sources: List[SourceSpec],
    exact_only: bool,
    min_sim: float,
) -> List[MatchResult]:
    """
    对单个 query 执行搜索。
    逻辑完全等同于你原来的 search_source_spec 内部实现。
    """
    all_results: List[MatchResult] = []

    for si, spec in enumerate(sources):
        cand = list(spec.candidates())
        if not cand:
            continue

        # 1) exact
        exact_hits = [c for c in cand if c == query]
        has_exact = len(exact_hits) > 0

        # exact 全部加入（通常只有一个，但不强假设）
        for c in exact_hits:
            all_results.append(MatchResult(
                key=spec.key,
                matched_text=c,
                value=spec.resolve(c),
                kind="exact",
                score=1.0,
                source_order=si,
                query_order=query_order,   # ✅
            ))

        # 如果全局禁止模糊，直接跳过后续
        if exact_only:
            continue

        # 如果这个 source 不允许 fuzzy，也跳过
        if not spec.allow_fuzzy:
            continue

        # 如果命中 exact 且不允许继续 fuzzy，则结束这个 spec
        if has_exact and not spec.continue_after_exact:
            continue

        # 2) contains（候选包含 query）
        contains_hits = [c for c in cand if query in c and c != query]
        if contains_hits:
            # 更短/更接近的排前一点，但是更看重长度差
            # score 作为辅助：query 越长越好、candidate 越短越好
            def contains_score(c: str) -> float:
                pos = c.find(query)
                return 1.0 / (1 + pos) + 1.0 / (1 + abs(len(c) - len(query)))

            contains_hits_sorted = sorted(contains_hits, key=contains_score, reverse=True)
            for c in contains_hits_sorted:
                all_results.append(MatchResult(
                    key=spec.key,
                    matched_text=c,
                    value=spec.resolve(c),
                    kind="contains",
                    score=contains_score(c),
                    source_order=si,
                    query_order=query_order,  # ✅
                ))
            # 规则：如果有 contains，就不做逐字相似度
            continue

        # 3) similar（没有 contains 时）
        scored = []
        for c in cand:
            if c == query:
                continue
            s = _sim(query, c)
            if s >= min_sim:
                scored.append((s, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        for s, c in scored:
            all_results.append(MatchResult(
                key=spec.key,
                matched_text=c,
                value=spec.resolve(c),
                kind="similar",
                score=s,
                source_order=si,
                query_order=query_order,  # ✅
            ))

    return all_results

def search_source_spec(
    query: QueryInput,    # ✅ 支持字符串或字符串数组
    *,
    sources: List[SourceSpec],
    n: int = 10,
    exact_only: bool = False,   # 全局：打开后禁止模糊（覆盖 SourceSpec）
    min_sim: float = 0.2,       # 相似度阈值（可选）
) -> SearchResults:
    """
    在多个 SourceSpec 定义的搜索源中，对查询文本进行统一搜索并返回合并后的匹配结果。

    本函数支持“精确匹配 / 包含匹配 / 相似度匹配”三种策略，并按照固定优先级
    在所有搜索源（SourceSpec）之间合并、排序后返回前 n 个结果。

    --------------------
    匹配策略与优先级
    --------------------
    对每一个 SourceSpec，按以下顺序进行匹配：

    1. 精确匹配（exact）
       - 候选字符串与 query 完全相等
       - 一旦命中，必定加入结果列表
       - 是否继续进行模糊匹配由 SourceSpec.continue_after_exact 控制

    2. 包含匹配（contains）
       - 候选字符串包含 query（如 "凛御银灰" 包含 "银灰"）
       - 若存在包含匹配，则返回所有包含匹配结果
       - 一旦存在包含匹配，将不会再进行相似度匹配

    3. 相似度匹配（similar）
       - 仅在不存在包含匹配时才会进行
       - 基于文本相似度（0~1），按相似度从高到低返回
       - 可通过 min_sim 控制最低相似度阈值

    --------------------
    多 SourceSpec 合并规则
    --------------------
    - 所有 SourceSpec 的结果会被合并到同一个结果列表中
    - 全局排序规则为：
        1) 所有 exact 匹配
        2) 所有 contains 匹配
        3) 所有 similar 匹配
    - 同一匹配类型内：
        - 按 SourceSpec 在 sources 中的顺序排序
        - 再按 score 从高到低排序
    - 最终最多返回前 n 个结果

    --------------------
    全局与局部控制开关
    --------------------
    exact_only:
        - 若为 True，则禁止所有模糊匹配（contains / similar）
        - 仅允许 exact 匹配
        - 该设置会覆盖所有 SourceSpec 的 allow_fuzzy / continue_after_exact

    SourceSpec.continue_after_exact:
        - 控制在命中 exact 后，是否继续进行 contains / similar 匹配
        - 仅在 exact_only=False 时生效

    SourceSpec.allow_fuzzy:
        - 控制该 SourceSpec 是否允许模糊匹配
        - continue_after_exact 仅在 allow_fuzzy=True 时有效
        - exact_only=True 时该设置会被忽略
        - fuzzy 包括 contains / similar 两种匹配方式

    --------------------
    参数说明
    --------------------
    query : str
        用户的查询文本。

    sources : List[SourceSpec]
        搜索源定义列表，顺序即搜索与结果排序的优先顺序。

    n : int, default=10
        最多返回的匹配结果数量。

    exact_only : bool, default=False
        是否仅允许精确匹配（禁止所有模糊匹配）。

    min_sim : float, default=0.0
        相似度匹配的最小阈值（范围 0~1）。

    --------------------
    返回值
    --------------------
    SearchResults
        包含匹配结果的对象，属性包括：
        
        matches: List[MatchResult]
            匹配结果列表，每个 MatchResult 包含：
            - key: 来源标识（如 "name" / "skin" / "group"）
            - matched_text: 命中的候选字符串
            - value: 通过 SourceSpec.resolve 得到的对象
            - kind: 匹配类型（"exact" / "contains" / "similar"）
            - score: 匹配分数（exact 为 1.0）
            - source_order: SourceSpec 在 sources 中的顺序索引

    --------------------
    使用示例
    --------------------
    results = search_source_spec(
        "银灰",
        sources=sources,
        n=5
    )

    if not results.matches:
        handle_no_result()
    elif len(results.matches) == 1:
        show(results.matches[0].value)
    else:
        show_candidates(results.matches)
    """
        
    queries = _normalize_queries(query)
    if not queries or n <= 0:
        return SearchResults(matches=[])

    all_results: List[MatchResult] = []

    # 对每个 query 分别搜索
    for qi, q in enumerate(queries):
        all_results.extend(_search_one_query(
            q,
            query_order=qi,   # ✅
            sources=sources,
            exact_only=exact_only,
            min_sim=min_sim,
        ))

    # ---- 全局合并排序：exact 最前，然后 contains，然后 similar
    kind_rank = {"exact": 0, "contains": 1, "similar": 2}

    # 同一匹配类型内：
    #   1) 按 query_order（传入 query 的顺序）
    #   2) 按 SourceSpec 顺序
    #   3) 按 score
    #   4) 再按 matched_text 稳定
    all_results.sort(
        key=lambda r: (
            kind_rank.get(r.kind, 99),
            r.query_order,      # ✅ 核心：保证同级别按 query 顺序
            r.source_order,
            -r.score,
            r.matched_text
        )
    )

    # 去重策略（同 key + matched_text）
    seen = set()
    deduped: List[MatchResult] = []
    for r in all_results:
        k = (r.key, r.matched_text)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
        if len(deduped) >= n:
            break

    return SearchResults(matches=deduped)

def build_sources(bundle: DataBundle, source_key: Optional[List[str]] = None) -> List[SourceSpec]:

    all_source = [
        SourceSpec(
            key="name",
            candidates=lambda: list(bundle.operator_name_to_id.keys()),
            resolve=lambda k: bundle.operators[bundle.operator_name_to_id[k]],
            continue_after_exact=False,   # 对于干员搜索，找到精确名就不会继续（除了阿米娅，目前暂不考虑）
            allow_fuzzy=True,
        ),
        # skin/group/voice/story 继续按同样方式加
    ]

    if source_key:
        filtered = [s for s in all_source if s.key in source_key]
        return filtered
    else:
        return all_source
