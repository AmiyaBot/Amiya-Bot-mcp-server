from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from src.app.context import AppContext
from src.app.services.operator_output import build_operator_payload, render_operator_markdown
from src.app.services.operator_skin_assets import SKIN_CACHE_PATH, resolve_operator_skin_artifact
from src.domain.models.operator import Operator
from src.domain.services.operator import search_operator_by_name
from src.helpers.bundle import get_table
from src.helpers.card_urls import build_card_url
from src.helpers.gamedata.search import build_sources, search_source_spec

logger = logging.getLogger(__name__)
OPERATOR_INFO_CARD_REVISION = "card-v19"


@dataclass(slots=True)
class QueryExecutionResult:
    data: str | dict | None = None
    markdown: str | None = None
    image_url: str | None = None
    image_path: str | None = None
    message: str | None = None
    candidates: list[str] | None = None

    def to_response(self) -> dict:
        response = {}
        if self.data is not None:
            response["data"] = self.data
        if self.image_url is not None:
            response["image_url"] = self.image_url
        if self.image_path is not None:
            response["image_path"] = self.image_path
        if self.message is not None:
            response["message"] = self.message
        if self.candidates:
            response["candidates"] = self.candidates
        return response


def _dedupe_names(matches) -> list[str]:
    return list(dict.fromkeys(match.matched_text for match in matches))


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


async def query_operator_basic(
    context: AppContext,
    operator_name: str,
    operator_name_prefix: str = "",
) -> QueryExecutionResult:
    try:
        resolved = _resolve_operator(context, operator_name, operator_name_prefix)
        if isinstance(resolved, QueryExecutionResult):
            return resolved

        result = search_operator_by_name(context, resolved.name)
        structured_payload = build_operator_payload(result)

        bundle = context.data_repository.get_bundle()
        bundle_version = getattr(bundle, "version", None) or getattr(bundle, "hash", None) or "v0"
        payload_key = f"operator:{resolved.name}:{bundle_version}:{OPERATOR_INFO_CARD_REVISION}"

        image_url = None
        image_path = None
        try:
            skin_artifact = await resolve_operator_skin_artifact(
                context,
                resolved,
                bundle.tables,
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
        except Exception as exc:
            logger.info("准备干员角色卡失败，已降级为立绘直链或文本结果: %s", exc)
            try:
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
                logger.info("准备干员立绘回退结果失败", exc_info=True)

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
        logger.exception("查询干员基础信息失败")
        return QueryExecutionResult(message="查询干员信息时发生错误.")


async def query_operator_skill(
    context: AppContext,
    operator_name: str,
    operator_name_prefix: str = "",
    index: int = 1,
    level: int = 10,
) -> QueryExecutionResult:
    if index < 1:
        return QueryExecutionResult(message=f"技能序号 index 必须 >= 1（当前：{index}）")
    if level < 1 or level > 10:
        return QueryExecutionResult(message=f"技能等级 level 必须在 1~10 之间（当前：{level}）")

    try:
        resolved = _resolve_operator(context, operator_name, operator_name_prefix)
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
        payload_key = f"operator_skill:{resolved.name}:{index}:{level}:{bundle_version}"

        text_artifact = await context.card_service.get(
            template="operator_skill",
            payload_key=payload_key,
            payload=payload,
            format="txt",
            params=None,
        )

        return QueryExecutionResult(data=text_artifact.read_text())
    except Exception:
        logger.exception("查询干员技能信息失败")
        return QueryExecutionResult(message="查询干员技能信息时发生错误.")