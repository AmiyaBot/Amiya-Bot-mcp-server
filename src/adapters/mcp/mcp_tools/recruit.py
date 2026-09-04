import logging
from typing import Annotated, Literal

from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end, log_tool_exception, log_tool_not_ready, log_tool_start
from src.app.context import AppContext
from src.app.services.recruit_queries import query_recruit

logger = logging.getLogger(__name__)

RecruitTag = Literal[
    "近卫干员",
    "狙击干员",
    "重装干员",
    "医疗干员",
    "辅助干员",
    "术师干员",
    "特种干员",
    "先锋干员",
    "近战位",
    "远程位",
    "高级资深干员",
    "控场",
    "爆发",
    "资深干员",
    "治疗",
    "支援",
    "新手",
    "费用回复",
    "输出",
    "生存",
    "群攻",
    "防护",
    "减速",
    "削弱",
    "快速复活",
    "位移",
    "召唤",
    "支援机械",
    "元素",
    "男性干员",
    "女性干员",
]

_RECRUIT_TOOL_DESC = """根据明日方舟公开招募标签返回稀有组合与候选干员。
若图片标签区显示 tags 枚举中的 5 个词条，则按公招截图处理：必须识别并一次性传入全部 5 个词条。禁止自行组合、筛选或多次调用，工具会完成组合计算。
返回的 card_image_url 图片已汇总全部有效组合与候选干员；有该字段时直接向用户展示图片，不要自行计算、筛选或复述结果。"""


def register_recruit_with_tag_tool(mcp, app):
    @mcp.tool(description=_RECRUIT_TOOL_DESC)
    async def recruit_with_tag(
        tags: Annotated[
            list[RecruitTag],
            Field(
                description="公招标签；截图必须传入标签区显示的全部 5 项",
                min_length=1,
                max_length=5,
            ),
        ],
    ) -> dict:
        tool_name = "recruit_with_tag"
        started_at = log_tool_start(logger, tool_name, tags=tags)
        try:
            if not getattr(app.state, "ctx", None):
                log_tool_not_ready(logger, tool_name)
                payload = {"message": "未初始化数据上下文"}
                log_tool_end(logger, tool_name, started_at, payload)
                return payload
            context: AppContext = app.state.ctx
            payload = await query_recruit(context, tags)
            log_tool_end(logger, tool_name, started_at, payload)
            return payload
        except Exception:
            log_tool_exception(logger, tool_name, started_at, tags=tags)
            raise
