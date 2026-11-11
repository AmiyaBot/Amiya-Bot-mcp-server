# AI-REMOVED 2026-11-10:
# Reason: 用户仅授权结构化数据，撤回未经授权的卫戍协议查询和卡片接入。
# Trigger: 用户要求先去掉本次新增接口，后续按指导梳理添加。
# Evidence: 本次工作区 diff 中新增的卫戍协议工具、搜索和卡片代码。
# Replacement: None；仅保留 src/data/repository/bundle/autochess.py 数据结构化。
# Risk: Low；既有查询入口保持原行为。
# Human Review: Required
# Original code:
# from __future__ import annotations
#
# import logging
# from typing import Annotated
#
# from pydantic import Field
#
# from src.adapters.mcp.tool_logging import log_tool_start, log_tool_end, log_tool_exception
# from src.app.services.autochess_queries import query_autochess_detail
#
# logger = logging.getLogger(__name__)
#
# 
# def register_autochess_tool(mcp, app):
#     @mcp.tool(description="查询卫戍协议盟约、棋子或策略的资料与卡片。先调用 search，按活动、version_id 和 ruleset 区分档期与教程，再将候选 id 传入。棋子详情包含普通/精锐状态、基础价格、所属盟约和特质原文；策略含主动/被动技能。展示数值与说明彼此独立，不推算特质实际结算效果。")
#     async def get_autochess_detail(
#         entry_id: Annotated[str, Field(description="search 返回的卫戍协议资料唯一 ID，不接受名称")],
#     ) -> dict:
#         started = log_tool_start(logger, "get_autochess_detail", entry_id=entry_id)
#         try:
#             context = getattr(app.state, "ctx", None)
#             response = ({"message": "未初始化数据上下文"} if context is None else
#                         (await query_autochess_detail(context, entry_id)).to_response())
#             log_tool_end(logger, "get_autochess_detail", started, response)
#             return response
#         except Exception:
#             log_tool_exception(logger, "get_autochess_detail", started, entry_id=entry_id)
#             return {"message": "查询卫戍协议资料时发生错误."}
