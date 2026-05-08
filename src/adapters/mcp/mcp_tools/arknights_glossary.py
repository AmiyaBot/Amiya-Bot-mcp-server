import json
import logging

from typing import Annotated,List,Union
from pydantic import Field

from src.adapters.mcp.tool_logging import log_tool_end
from src.adapters.mcp.tool_logging import log_tool_exception
from src.adapters.mcp.tool_logging import log_tool_not_ready
from src.adapters.mcp.tool_logging import log_tool_start
from src.app.context import AppContext
from src.app.services.glossary_queries import query_glossary

logger = logging.getLogger("mcp_tool")

def register_glossary_tool(mcp,app):
    @mcp.tool(
        description='获取明日方舟游戏数据中指定术语的解释和计算公式。例如你可以查询特定术语如"攻击力"来获取关于如何计算具体伤害的公式。',
    )
    def get_glossary(
        glossary_name: Annotated[Union[List[str], str], Field(description='要查询的术语名列表，可以是术语字符串、逗号/顿号分隔的术语字符串、或字符串数组')],
    ) -> str:
        """
        输入:
            - glossary_name: 可以是术语字符串、逗号/顿号分隔的术语字符串、或字符串数组
        输出:
            - JSON 字符串: { "术语名": "术语解释", ... }
        规则:
            1) 只要用户查询的术语中“包含” glossary 的术语（或反向包含以增强召回），就算匹配
            2) 如果某个术语解释文本中包含了其它 glossary 术语名，则级联把这些术语也加入返回结果
        """
        tool_name = "get_glossary"
        started_at = log_tool_start(logger, tool_name, glossary_name=glossary_name)

        try:
            if not app.state.ctx:
                log_tool_not_ready(logger, tool_name)
                payload = {}
                log_tool_end(logger, tool_name, started_at, payload)
                return "{}"

            context: AppContext = app.state.ctx

            if not context.data_repository:
                log_tool_not_ready(logger, tool_name)
                payload = {}
                log_tool_end(logger, tool_name, started_at, payload)
                return "{}"

            result = query_glossary(context, glossary_name)
            ret_val = json.dumps(result, ensure_ascii=False)
            log_tool_end(
                logger,
                tool_name,
                started_at,
                {
                    "data": {
                        "term_count": len(result),
                        "terms": sorted(result.keys())[:10],
                    }
                },
            )
            return ret_val
        except Exception:
            log_tool_exception(logger, tool_name, started_at, glossary_name=glossary_name)
            raise