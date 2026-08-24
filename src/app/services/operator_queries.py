from __future__ import annotations

import base64
from dataclasses import dataclass
import logging
from pathlib import Path

from src.app.context import AppContext
from src.app.services.operator_material_output import build_operator_material_payload, render_operator_material_markdown
from src.app.services.operator_module_output import build_operator_module_payload, render_operator_module_markdown
from src.app.services.operator_output import (
    build_operator_payload,
    build_skin_payload,
    build_token_entries,
    render_operator_markdown,
    token_first_range,
    token_max_attr_data,
)
from src.app.services.operator_skin_assets import (
    SKIN_CACHE_PATH,
    resolve_operator_skin_artifact,
    resolve_skin_artifact_by_id,
)
from src.domain.models.operator import Operator
from src.domain.services.operator import (
    build_operator_query_result,
    build_operator_template_bg_data,
    build_operator_template_bg_url,
    build_operator_template_font_url,
)
from src.domain.services.operator_material import build_operator_material_query_result
from src.domain.services.operator_module import build_operator_module_query_result
from src.domain.types import QueryResult
from src.helpers.bundle import get_table
from src.helpers.card_urls import build_card_url
from src.helpers.gamedata.search import build_sources, search_source_spec

logger = logging.getLogger(__name__)
OPERATOR_INFO_CARD_REVISION = "card-v20"
OPERATOR_MATERIAL_CARD_REVISION = "mat-v1"
OPERATOR_MODULE_CARD_REVISION = "module-v2"
OPERATOR_TOKEN_CARD_REVISION = "token-v4"
OPERATOR_SKIN_CARD_REVISION = "skin-v1"
OPERATOR_SKIN_SELECTION_CARD_REVISION = "skin-selection-v2"


@dataclass(slots=True)
class QueryExecutionResult:
    data: str | dict | list[dict[str, str]] | None = None
    markdown: str | None = None
    image_url: str | None = None
    image_path: str | None = None
    message: str | None = None
    candidates: list[str] | None = None

    def to_response(self) -> dict:
        response = {}
        if self.data is not None:
            response["data"] = self.data
        # 2026-08-13: 输出契约统一——图片 URL 字段由 image_url 更名为 card_image_url，
        # CLI 与 MCP 共用本方法，均输出 card_image_url；内部字段名 image_url 保持不变。
        if self.image_url is not None:
            response["card_image_url"] = self.image_url
        if self.image_path is not None:
            response["image_path"] = self.image_path
        if self.message is not None:
            response["message"] = self.message
        if self.candidates:
            response["candidates"] = self.candidates
        return response


def _dedupe_names(matches) -> list[str]:
    return list(dict.fromkeys(match.matched_text for match in matches))


# 原函数名 _build_operator_search_items（2026-08-13 起重构为 _build_search_items，
# 统一构建干员与召唤物候选条目；干员条目与旧逻辑一致）。
# AI-CORRECTION 2026-08-13: 已支持皮肤条目（key=skin），返回 {"id", "name",
# "type": "皮肤", "operator_id", "operator_name"}，其中 operator_* 为皮肤归属干员。
def _build_search_items(
    matches,
    token_owner: dict[str, Operator],
) -> list[dict[str, str]]:
    """将搜索命中结果组装为统一候选条目。

    干员条目：{"id", "name", "type": "干员"}。
    召唤物条目：{"id", "name", "type": "召唤物", "operator_id", "operator_name"}，
    其中 operator_id/operator_name 为该召唤物所属干员（下游详情工具只接受干员 ID）。
    无主召唤物（未挂靠在任何干员下）不进入候选。
    皮肤条目：{"id", "name", "type": "皮肤", "operator_id", "operator_name"}，
    其中 operator_id/operator_name 为皮肤归属干员。
    """
    items: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for match in matches:
        value = match.value
        if match.key == "name":
            # 干员
            operator_id = str(getattr(value, "id", "") or "").strip()
            operator_name = str(getattr(value, "name", "") or match.matched_text).strip()
            if not operator_id or not operator_name or operator_id in seen_ids:
                continue

            seen_ids.add(operator_id)
            items.append({
                "id": operator_id,
                "name": operator_name,
                "type": "干员",
            })
        elif match.key == "token_name":
            # 召唤物：只返回有主的召唤物（"干员的召唤物"）
            token_id = str(getattr(value, "id", "") or "").strip()
            token_name = str(getattr(value, "name", "") or match.matched_text).strip()
            owner = token_owner.get(token_id)
            if not token_id or not token_name or token_id in seen_ids or owner is None:
                continue

            seen_ids.add(token_id)
            items.append({
                "id": token_id,
                "name": token_name,
                "type": "召唤物",
                "operator_id": owner.id,
                "operator_name": owner.name,
            })
        elif match.key == "skin":
            # 皮肤：附带归属干员信息（皮肤立绘可通过所属干员查询）
            skin_id = str(getattr(value, "skin_id", "") or "").strip()
            skin_name = str(getattr(value, "name", "") or match.matched_text).strip()
            operator_id = str(getattr(value, "operator_id", "") or "").strip()
            operator_name = str(getattr(value, "operator_name", "") or "").strip()
            if not skin_id or not skin_name or skin_id in seen_ids or not operator_id:
                continue

            seen_ids.add(skin_id)
            items.append({
                "id": skin_id,
                "name": skin_name,
                "type": "皮肤",
                "operator_id": operator_id,
                "operator_name": operator_name,
            })

    return items


def _resolve_safe_local_artifact_path(
    context: AppContext,
    artifact_path: Path,
    cache_root: Path,
) -> str | None:
    if not context.prefer_local_artifact_path:
        return None

    try:
        resolved_artifact = artifact_path.resolve()
        resolved_cache_root = cache_root.resolve()
        if not resolved_artifact.is_relative_to(resolved_cache_root):
            return None
        return str(resolved_artifact)
    except Exception:
        logger.warning("解析本地图片缓存路径失败", exc_info=True)
        return None


def _build_png_data_uri(path: Path) -> str | None:
    """读取 PNG 资源并转为 data uri；不存在返回 None（模板侧隐藏图片）"""
    if not path or not path.exists():
        return None
    try:
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{payload}"
    except Exception:
        logger.warning("读取图片资源失败: path=%s", path, exc_info=True)
        return None


def _build_token_avatar_data_uri(resource_root: Path, token_id: str) -> str | None:
    """读取召唤物头像并转为 data uri；头像缺失返回 None（模板侧隐藏图片）"""
    if not resource_root:
        return None
    return _build_png_data_uri(resource_root / "assets" / "avatar" / f"{token_id}#1.png")


def _build_skill_icon_data_uri(resource_root: Path, icon_id: str) -> str | None:
    """读取技能图标并转为 data uri；图标缺失返回 None（模板侧隐藏图片）"""
    if not resource_root or not icon_id:
        return None
    icon_path = resource_root / "assets" / "skill" / icon_id
    if not icon_path.suffix:
        icon_path = icon_path.with_suffix(".png")
    return _build_png_data_uri(icon_path)


async def _render_operator_token_card(
    context: AppContext,
    bundle,
    operator: Operator,
    token_entries: list[dict],
    *,
    bundle_version: str,
) -> str | None:
    """渲染干员召唤物卡片并返回图片 URL；任何失败由调用方降级处理"""
    tokens_map = getattr(bundle, "tokens", {}) or {}
    render_tokens: list[dict] = []
    for entry in token_entries:
        token = tokens_map.get(str(entry.get("id") or ""))
        if token is None:
            continue

        # 召唤物技能图标资源为 skchr_ 前缀（跟随所属干员），且召唤物技能通常与干员技能同名，
        # 因此按技能名复用干员技能图标；未命中时回退到召唤物技能自身 id（通常无对应资源）。
        operator_skill_icons = {
            str(getattr(skill, "name", "") or ""): str(getattr(skill, "icon", "") or "")
            for skill in operator.skills or []
        }

        render_skills: list[dict] = []
        for skill in token.skills or []:
            icon_id = operator_skill_icons.get(str(skill.get("name") or "")) or str(skill.get("icon") or "")
            render_skills.append(
                {
                    **skill,
                    "icon_data": _build_skill_icon_data_uri(
                        context.cfg.ResourcePath,
                        icon_id,
                    ),
                }
            )

        render_tokens.append(
            {
                "id": token.id,
                "name": token.name,
                "en_name": token.en_name,
                "classes": token.classes,
                "type": token.type,
                "description": token.description,
                "avatar_data": _build_token_avatar_data_uri(context.cfg.ResourcePath, token.id),
                "max_attr": token_max_attr_data(token),
                "range": token_first_range(token),
                "talents": token.talents or [],
                "skills": render_skills,
            }
        )

    if not render_tokens:
        return None

    payload_key = f"operator_token:{operator.id}:{bundle_version}:{OPERATOR_TOKEN_CARD_REVISION}"
    payload = QueryResult(
        type="operator_token",
        key=operator.name,
        title=f"{operator.name} 的召唤物",
        data={
            "op": operator,
            "tokens": render_tokens,
            "template_bg_data": build_operator_template_bg_data(context.cfg.ProjectRoot),
            "template_bg_url": build_operator_template_bg_url(context.cfg.ProjectRoot),
            "template_font_url": build_operator_template_font_url(context.cfg.ProjectRoot),
        },
    )

    await context.card_service.get(
        template="operator_token",
        payload_key=payload_key,
        payload=payload,
        format="png",
    )
    return build_card_url(
        cfg=context.cfg,
        template="operator_token",
        payload_key=payload_key,
        format="png",
    )


def _resolve_operator(
    context: AppContext,
    operator_name: str,
    operator_name_prefix: str = "",
) -> Operator | QueryExecutionResult:
    bundle = context.data_repository.get_bundle()
    operator_combine = f"{operator_name_prefix}{operator_name}"
    search_sources = build_sources(bundle, source_key=["name"])
    search_results = search_source_spec([operator_combine, operator_name], sources=search_sources)

    if not search_results:
        return QueryExecutionResult(message=f"未找到干员: {operator_combine or operator_name}")

    name_matches = search_results.by_key("name")
    if len(name_matches) != 1:
        exact_matches = [match for match in name_matches if match.matched_text == operator_combine]
        if not exact_matches:
            exact_matches = [match for match in name_matches if match.matched_text == operator_name]

        if len(exact_matches) == 1:
            name_matches = exact_matches
        else:
            return QueryExecutionResult(
                message="找到多个匹配的干员名称，需要用户做出选择",
                candidates=_dedupe_names(name_matches),
            )

    return name_matches[0].value


def _build_token_owner_map(bundle) -> dict[str, Operator]:
    """构建 召唤物 id -> 所属干员 的映射（被 search 与召唤物详情查询共用）"""
    token_owner: dict[str, Operator] = {}
    for op in (bundle.operators or {}).values():
        for token_id in op.token_ids or []:
            token_owner.setdefault(token_id, op)
    return token_owner


async def query_token_detail_by_id(
    context: AppContext,
    token_id: str,
) -> QueryExecutionResult:
    """根据召唤物 ID 获取召唤物详情（结构化数据 + 卡片图片）。

    复用 build_token_entries 组装语义化条目、_render_operator_token_card 渲染卡片；
    卡片渲染依赖所属干员（技能图标复用干员资源），无主召唤物仅返回结构化数据。
    """
    try:
        normalized_token_id = str(token_id or "").strip()
        if not normalized_token_id:
            return QueryExecutionResult(message="token_id 不能为空")

        bundle = context.data_repository.get_bundle()
        tokens_map = bundle.tokens or {}
        token = tokens_map.get(normalized_token_id)
        if token is None:
            return QueryExecutionResult(message=f"未找到召唤物ID: {normalized_token_id}")

        entries = build_token_entries(tokens_map, [normalized_token_id])
        if not entries:
            return QueryExecutionResult(message=f"召唤物数据为空: {normalized_token_id}")

        payload = dict(entries[0])
        owner = _build_token_owner_map(bundle).get(normalized_token_id)

        token_card_url = None
        if owner is not None:
            payload["所属干员"] = {"id": owner.id, "名称": owner.name}
            bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"
            try:
                token_card_url = await _render_operator_token_card(
                    context,
                    bundle,
                    owner,
                    entries,
                    bundle_version=bundle_version,
                )
            except Exception:
                logger.warning(
                    "准备召唤物卡片失败，已降级为无卡片: token_id=%s",
                    normalized_token_id,
                    exc_info=True,
                )

        result = QueryExecutionResult(data=payload)
        if token_card_url:
            result.image_url = token_card_url
        return result
    except Exception:
        logger.exception("查询召唤物详情失败: token_id=%s", token_id)
        return QueryExecutionResult(message="查询召唤物信息时发生错误.")


async def _render_operator_skin_card(
    context: AppContext,
    operator: Operator,
    skin,
    skin_artifact,
    bundle_version: str,
) -> str | None:
    """渲染单个皮肤的立绘卡片，返回卡片 URL；失败由调用方降级处理。"""
    payload_key = f"operator_skin:{skin.skin_id}:{bundle_version}:{OPERATOR_SKIN_CARD_REVISION}"
    payload = QueryResult(
        type="operator_skin",
        key=operator.name,
        title=f"{operator.name} - {skin.name}",
        data={
            "op": operator,
            "skin": skin,
            "skin_url": skin_artifact.to_data_uri(),
            "skin_public_url": skin_artifact.url or "",
            "template_bg_data": build_operator_template_bg_data(context.cfg.ProjectRoot),
            "template_bg_url": build_operator_template_bg_url(context.cfg.ProjectRoot),
            "template_font_url": build_operator_template_font_url(context.cfg.ProjectRoot),
        },
    )

    await context.card_service.get(
        template="operator_skin",
        payload_key=payload_key,
        payload=payload,
        format="png",
    )
    return build_card_url(
        cfg=context.cfg,
        template="operator_skin",
        payload_key=payload_key,
        format="png",
    )


def _build_skin_portrait_data_uri(resource_root: Path, skin_id: str) -> str | None:
    """读取 180×360 皮肤半身像作为选择卡预览；缺失时由调用方回退到立绘。"""
    if not resource_root or not skin_id:
        return None
    return _build_png_data_uri(resource_root / "assets" / "portrait" / f"{skin_id}.png")


async def _render_operator_skin_selection_card(
    context: AppContext,
    operator: Operator,
    selection_items: list[dict],
    bundle_version: str,
) -> str | None:
    """渲染一个干员的皮肤选择卡，并返回卡片 URL。"""
    if not selection_items:
        return None

    payload_key = (
        f"operator_skin_selection:{operator.id}:{bundle_version}:"
        f"{OPERATOR_SKIN_SELECTION_CARD_REVISION}"
    )
    payload = QueryResult(
        type="operator_skin_selection",
        key=operator.name,
        title=f"{operator.name} 的皮肤",
        data={
            "op": operator,
            "items": selection_items,
            "template_font_url": build_operator_template_font_url(context.cfg.ProjectRoot),
        },
    )

    await context.card_service.get(
        template="operator_skin_selection",
        payload_key=payload_key,
        payload=payload,
        format="png",
    )
    return build_card_url(
        cfg=context.cfg,
        template="operator_skin_selection",
        payload_key=payload_key,
        format="png",
    )


async def query_operator_skins(
    context: AppContext,
    operator_id: str,
) -> QueryExecutionResult:
    """根据干员 ID 获取皮肤选择卡、结构化列表与每个皮肤的图片 URL。

    条目结构复用 build_skin_payload；逐皮肤按 skin_id 精确取立绘并渲染
    operator_skin 卡片。选择卡渲染失败时仍返回各皮肤 URL；单个皮肤取图或
    渲染失败时，该条目降级为无 card_url/立绘URL。
    """
    try:
        resolved = _resolve_operator_by_id(context, operator_id)
        if isinstance(resolved, QueryExecutionResult):
            return resolved

        bundle = context.data_repository.get_bundle()
        bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"

        skins = resolved.skins()
        if not skins:
            return QueryExecutionResult(message=f"干员 {resolved.name} 没有皮肤数据")

        entries = build_skin_payload(resolved)
        selection_items: list[dict] = []
        for index, (entry, skin) in enumerate(zip(entries, skins), start=1):
            entry["序号"] = index
            entry["card_url"] = ""
            entry["立绘URL"] = ""
            skin_artifact = None
            try:
                skin_artifact = await resolve_skin_artifact_by_id(context, skin.skin_id)
                if skin_artifact is None:
                    logger.debug("皮肤立绘索引缺失，跳过卡片渲染: skin_id=%s", skin.skin_id)
                else:
                    entry["立绘URL"] = skin_artifact.url or ""
                    entry["card_url"] = await _render_operator_skin_card(
                        context,
                        resolved,
                        skin,
                        skin_artifact,
                        bundle_version=bundle_version,
                    )
            except Exception:
                logger.warning(
                    "准备皮肤卡片失败，已降级为无卡片: operator_id=%s skin_id=%s",
                    resolved.id,
                    skin.skin_id,
                    exc_info=True,
                )

            preview_data = _build_skin_portrait_data_uri(context.cfg.ResourcePath, skin.skin_id)
            preview_contain = False
            if preview_data is None and skin_artifact is not None:
                try:
                    preview_data = skin_artifact.to_data_uri()
                    preview_contain = True
                except Exception:
                    logger.warning(
                        "读取皮肤选择卡预览失败: operator_id=%s skin_id=%s",
                        resolved.id,
                        skin.skin_id,
                        exc_info=True,
                    )
            selection_items.append(
                {
                    "index": index,
                    "skin": skin,
                    "preview_data": preview_data or "",
                    "preview_contain": preview_contain,
                }
            )

        selection_card_url = None
        try:
            selection_card_url = await _render_operator_skin_selection_card(
                context,
                resolved,
                selection_items,
                bundle_version,
            )
        except Exception:
            logger.warning(
                "准备皮肤选择卡失败，已降级为皮肤 URL 列表: operator_id=%s",
                resolved.id,
                exc_info=True,
            )

        data = {
            "operator": {"id": resolved.id, "name": resolved.name},
            "skins": entries,
        }
        if selection_card_url:
            data["selection_card_url"] = selection_card_url
        return QueryExecutionResult(data=data, image_url=selection_card_url)
    except Exception:
        logger.exception("查询干员皮肤列表失败: operator_id=%s", operator_id)
        return QueryExecutionResult(message="查询干员皮肤信息时发生错误.")


def _resolve_operator_by_id(
    context: AppContext,
    operator_id: str,
) -> Operator | QueryExecutionResult:
    normalized_operator_id = str(operator_id or "").strip()
    if not normalized_operator_id:
        return QueryExecutionResult(message="operator_id 不能为空")

    bundle = context.data_repository.get_bundle()
    operator = bundle.operators.get(normalized_operator_id)
    if operator is None:
        return QueryExecutionResult(message=f"未找到干员ID: {normalized_operator_id}")

    return operator


# 原函数名 search_operator（2026-08-13 起重命名为 search，
# 升级为资源统一搜索：干员 + 干员的召唤物；未来扩展其他资源类型时在此收敛）。
def search(
    context: AppContext,
    query: str,
    limit: int = 10,
) -> QueryExecutionResult:
    from time import perf_counter
    t0 = perf_counter()

    normalized_query = str(query or "").strip()
    if not normalized_query:
        logger.debug("search: query 为空")
        return QueryExecutionResult(message="query 不能为空")

    logger.debug("search 开始: query=%s limit=%s", normalized_query, limit)

    bundle = context.data_repository.get_bundle()
    bundle_operators = len(bundle.operators) if bundle.operators else 0
    name_index_size = len(bundle.operator_name_to_id) if bundle.operator_name_to_id else 0
    token_name_index_size = len(bundle.token_name_to_id) if bundle.token_name_to_id else 0
    skin_name_index_size = len(bundle.skin_name_to_id) if bundle.skin_name_to_id else 0
    logger.debug(
        "search bundle 状态: operators=%s name_index=%s token_name_index=%s skin_name_index=%s",
        bundle_operators,
        name_index_size,
        token_name_index_size,
        skin_name_index_size,
    )
    if bundle_operators == 0 or name_index_size == 0:
        logger.warning(
            "search: 游戏数据为空！operators=%s name_index=%s",
            bundle_operators,
            name_index_size,
        )

    search_sources = build_sources(bundle, source_key=["name", "token_name", "skin"])
    logger.debug("search: build_sources 返回 %s 个 source", len(search_sources))

    search_results = search_source_spec(normalized_query, sources=search_sources, n=max(limit, 1))
    # 召唤物 -> 所属干员 反向映射：只允许"干员的召唤物"进入候选
    token_owner = _build_token_owner_map(bundle)

    items = _build_search_items(search_results.matches, token_owner)

    elapsed_ms = int((perf_counter() - t0) * 1000)
    logger.debug(
        "search 完成: query=%s matches=%s items=%s elapsed_ms=%s",
        normalized_query,
        len(search_results.matches),
        len(items),
        elapsed_ms,
    )

    if not items:
        logger.warning(
            "search: 未找到干员、召唤物或皮肤 query=%s bundle_operators=%s name_index=%s token_name_index=%s skin_name_index=%s",
            normalized_query,
            bundle_operators,
            name_index_size,
            token_name_index_size,
            skin_name_index_size,
        )
        return QueryExecutionResult(message=f"未找到匹配的干员、召唤物或皮肤: {normalized_query}")

    return QueryExecutionResult(data={"items": items})


async def query_operator_basic_by_id(
    context: AppContext,
    operator_id: str,
) -> QueryExecutionResult:
    try:
        resolved = _resolve_operator_by_id(context, operator_id)
        if isinstance(resolved, QueryExecutionResult):
            return resolved

        # 已通过 ID 拿到 Operator，直接构建 QueryResult，无需再做名称搜索
        result = build_operator_query_result(context, resolved)

        bundle = context.data_repository.get_bundle()
        bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"

        # 召唤物：组装语义化条目并渲染召唤物卡片（失败降级为无卡片 URL）
        token_entries = build_token_entries(bundle.tokens, resolved.token_ids or [])
        token_card_url = None
        if token_entries:
            try:
                token_card_url = await _render_operator_token_card(
                    context,
                    bundle,
                    resolved,
                    token_entries,
                    bundle_version=bundle_version,
                )
            except Exception:
                logger.warning(
                    "准备干员召唤物卡片失败，已降级为无召唤物卡片: operator_id=%s operator=%s",
                    resolved.id,
                    resolved.name,
                    exc_info=True,
                )

        structured_payload = build_operator_payload(
            result,
            token_entries=token_entries,
            token_card_url=token_card_url,
        )
        payload_key = f"operator:{resolved.id}:{bundle_version}:{OPERATOR_INFO_CARD_REVISION}"

        image_url = None
        image_path = None
        skin_artifact = None
        try:
            try:
                skin_artifact = await resolve_operator_skin_artifact(
                    context,
                    resolved,
                    bundle.tables,
                )
            except Exception:
                logger.warning(
                    "准备干员立绘素材失败，将继续尝试生成角色卡: operator_id=%s operator=%s",
                    resolved.id,
                    resolved.name,
                    exc_info=True,
                )

            if skin_artifact is not None:
                result.data["skin_url"] = skin_artifact.to_data_uri()
                result.data["skin_public_url"] = skin_artifact.url or ""

            card_artifact = await context.card_service.get(
                template="operator_info",
                payload_key=payload_key,
                payload=result,
                format="png",
                params=None,
            )

            image_url = build_card_url(
                cfg=context.cfg,
                template="operator_info",
                payload_key=payload_key,
                format="png",
            )
            image_path = _resolve_safe_local_artifact_path(
                context,
                card_artifact.path,
                context.card_service.cache_root,
            )
        except Exception:
            logger.warning(
                "准备干员角色卡失败，已降级为立绘直链或文本结果: operator_id=%s operator=%s payload_key=%s template=operator_info",
                resolved.id,
                resolved.name,
                payload_key,
                exc_info=True,
            )
            try:
                if skin_artifact is None:
                    skin_artifact = await resolve_operator_skin_artifact(
                        context,
                        resolved,
                        bundle.tables,
                    )
                if skin_artifact is not None:
                    image_url = skin_artifact.url
                    image_path = _resolve_safe_local_artifact_path(
                        context,
                        skin_artifact.path,
                        context.cfg.ResourcePath / SKIN_CACHE_PATH,
                    )
            except Exception:
                logger.info("准备干员立绘回退结果失败: operator_id=%s operator=%s", resolved.id, resolved.name, exc_info=True)

        return QueryExecutionResult(
            data=structured_payload,
            markdown=render_operator_markdown(
                structured_payload,
                image_url=image_url,
                image_path=image_path,
            ),
            image_url=image_url,
            image_path=image_path,
        )
    except Exception:
        logger.exception("按 ID 查询干员基础信息失败: operator_id=%s", operator_id)
        return QueryExecutionResult(message="查询干员信息时发生错误.")


async def query_operator_skill_by_id(
    context: AppContext,
    operator_id: str,
    index: int = 1,
    level: int = 10,
) -> QueryExecutionResult:
    if index < 1:
        return QueryExecutionResult(message=f"技能序号 index 必须 >= 1（当前：{index}）")
    if level < 1 or level > 10:
        return QueryExecutionResult(message=f"技能等级 level 必须在 1~10 之间（当前：{level}）")

    try:
        resolved = _resolve_operator_by_id(context, operator_id)
        if isinstance(resolved, QueryExecutionResult):
            return resolved

        bundle = context.data_repository.get_bundle()
        if not resolved.skills or len(resolved.skills) < index:
            return QueryExecutionResult(message=f"干员{resolved.name}没有第{index}个技能")

        skill = resolved.skills[index - 1]
        if not skill.levels:
            return QueryExecutionResult(message=f"干员{resolved.name}的技能“{skill.name}”没有等级数据")

        chosen = next((item for item in skill.levels if int(item.level) == int(level)), None)
        if not chosen:
            return QueryExecutionResult(message=f"干员{resolved.name}的技能“{skill.name}”无法升级到等级{level}")

        sp_type_table = get_table(bundle.tables, "sp_type", source="local", default={})
        skill_type_table = get_table(bundle.tables, "skill_type", source="local", default={})
        skill_level_table = get_table(bundle.tables, "skill_level", source="local", default={})

        sp_data = getattr(chosen, "sp", None)
        sp_type_raw = getattr(sp_data, "sp_type", "") if sp_data else ""
        sp_type_text = sp_type_table.get(sp_type_raw, sp_type_table.get(str(sp_type_raw), str(sp_type_raw)))

        skill_type_raw = getattr(chosen, "skill_type", "")
        skill_type_text = skill_type_table.get(
            skill_type_raw,
            skill_type_table.get(str(skill_type_raw), str(skill_type_raw)),
        )

        level_text = skill_level_table[str(level)] if level >= 8 else str(level)
        payload = {
            "op": resolved,
            "skill": {
                "index": index,
                "name": skill.name,
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

        bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"
        payload_key = f"operator_skill:{resolved.id}:{index}:{level}:{bundle_version}"

        text_artifact = await context.card_service.get(
            template="operator_skill",
            payload_key=payload_key,
            payload=payload,
            format="txt",
            params=None,
        )

        return QueryExecutionResult(data=text_artifact.read_text())
    except Exception:
        logger.exception("按 ID 查询干员技能信息失败: operator_id=%s", operator_id)
        return QueryExecutionResult(message="查询干员技能信息时发生错误.")


async def query_operator_basic(
    context: AppContext,
    operator_name: str,
    operator_name_prefix: str = "",
) -> QueryExecutionResult:
    resolved = _resolve_operator(context, operator_name, operator_name_prefix)
    if isinstance(resolved, QueryExecutionResult):
        return resolved
    return await query_operator_basic_by_id(context, resolved.id)


async def query_operator_skill(
    context: AppContext,
    operator_name: str,
    operator_name_prefix: str = "",
    index: int = 1,
    level: int = 10,
) -> QueryExecutionResult:
    resolved = _resolve_operator(context, operator_name, operator_name_prefix)
    if isinstance(resolved, QueryExecutionResult):
        return resolved
    return await query_operator_skill_by_id(context, resolved.id, index=index, level=level)


async def query_operator_material_by_id(
    context: AppContext,
    operator_id: str,
) -> QueryExecutionResult:
    try:
        resolved = _resolve_operator_by_id(context, operator_id)
        if isinstance(resolved, QueryExecutionResult):
            return resolved

        # 1–2 星干员不需要材料升级（对齐原插件）
        if int(getattr(resolved, "rarity", 0) or 0) <= 2:
            return QueryExecutionResult(
                message=f"博士，干员{getattr(resolved, 'name', '') or operator_id}不需要消耗材料进行升级哦~"
            )

        result = build_operator_material_query_result(context, resolved)
        structured_payload = build_operator_material_payload(result)

        bundle = context.data_repository.get_bundle()
        bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"
        payload_key = f"operator_material:{resolved.id}:{bundle_version}:{OPERATOR_MATERIAL_CARD_REVISION}"

        image_url = None
        image_path = None
        skin_artifact = None
        try:
            try:
                skin_artifact = await resolve_operator_skin_artifact(
                    context,
                    resolved,
                    bundle.tables,
                )
            except Exception:
                logger.warning(
                    "准备干员立绘素材失败，将继续尝试生成材料卡片: operator_id=%s operator=%s",
                    resolved.id,
                    resolved.name,
                    exc_info=True,
                )

            if skin_artifact is not None:
                result.data["skin_url"] = skin_artifact.to_data_uri()

            card_artifact = await context.card_service.get(
                template="operator_material",
                payload_key=payload_key,
                payload=result,
                format="png",
                params=None,
            )

            image_url = build_card_url(
                cfg=context.cfg,
                template="operator_material",
                payload_key=payload_key,
                format="png",
            )
            image_path = _resolve_safe_local_artifact_path(
                context,
                card_artifact.path,
                context.card_service.cache_root,
            )
        except Exception:
            logger.warning(
                "准备干员材料卡片失败，已降级为立绘直链或文本结果: operator_id=%s operator=%s payload_key=%s template=operator_material",
                resolved.id,
                resolved.name,
                payload_key,
                exc_info=True,
            )
            try:
                if skin_artifact is None:
                    skin_artifact = await resolve_operator_skin_artifact(
                        context,
                        resolved,
                        bundle.tables,
                    )
                if skin_artifact is not None:
                    image_url = skin_artifact.url
                    image_path = _resolve_safe_local_artifact_path(
                        context,
                        skin_artifact.path,
                        context.cfg.ResourcePath / SKIN_CACHE_PATH,
                    )
            except Exception:
                logger.info("准备干员立绘回退结果失败: operator_id=%s operator=%s", resolved.id, resolved.name, exc_info=True)

        return QueryExecutionResult(
            data=structured_payload,
            markdown=render_operator_material_markdown(
                structured_payload,
                image_url=image_url,
                image_path=image_path,
            ),
            image_url=image_url,
            image_path=image_path,
        )
    except Exception:
        logger.exception("按 ID 查询干员材料信息失败: operator_id=%s", operator_id)
        return QueryExecutionResult(message="查询干员材料信息时发生错误.")


async def query_operator_modules_by_id(
    context: AppContext,
    operator_id: str,
) -> QueryExecutionResult:
    try:
        resolved = _resolve_operator_by_id(context, operator_id)
        if isinstance(resolved, QueryExecutionResult):
            return resolved

        if not (getattr(resolved, "modules", None) or []):
            return QueryExecutionResult(message=f"干员 {resolved.name} 尚未拥有模组")

        result = build_operator_module_query_result(context, resolved)
        structured_payload = build_operator_module_payload(result)

        bundle = context.data_repository.get_bundle()
        bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"
        payload_key = f"operator_module:{resolved.id}:{bundle_version}:{OPERATOR_MODULE_CARD_REVISION}"

        image_url = None
        image_path = None
        try:
            card_artifact = await context.card_service.get(
                template="operator_module",
                payload_key=payload_key,
                payload=result,
                format="png",
                params=None,
            )
            image_path = _resolve_safe_local_artifact_path(
                context,
                card_artifact.path,
                context.card_service.cache_root,
            )
            try:
                image_url = build_card_url(
                    cfg=context.cfg,
                    template="operator_module",
                    payload_key=payload_key,
                    format="png",
                )
            except RuntimeError:
                logger.info(
                    "未配置 BaseUrl，模组卡片仅返回本地路径: operator_id=%s payload_key=%s",
                    resolved.id,
                    payload_key,
                )
        except Exception:
            logger.warning(
                "准备干员模组卡片失败，已降级为结构化数据: operator_id=%s operator=%s payload_key=%s",
                resolved.id,
                resolved.name,
                payload_key,
                exc_info=True,
            )

        return QueryExecutionResult(
            data=structured_payload,
            markdown=render_operator_module_markdown(
                structured_payload,
                image_url=image_url,
                image_path=image_path,
            ),
            image_url=image_url,
            image_path=image_path,
        )
    except Exception:
        logger.exception("按 ID 查询干员模组信息失败: operator_id=%s", operator_id)
        return QueryExecutionResult(message="查询干员模组信息时发生错误.")


async def query_operator_material(
    context: AppContext,
    operator_name: str,
    operator_name_prefix: str = "",
) -> QueryExecutionResult:
    resolved = _resolve_operator(context, operator_name, operator_name_prefix)
    if isinstance(resolved, QueryExecutionResult):
        return resolved
    return await query_operator_material_by_id(context, resolved.id)
