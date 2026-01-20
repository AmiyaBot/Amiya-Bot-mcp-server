from __future__ import annotations

from src.app.renderers.types import Renderer,RenderOutput
from src.app.renderers.jinja_template_loader import JinjaTemplateLoader
from src.domain.types import QueryResult
import logging

logger = logging.getLogger(__name__)

class JinjaHtmlRenderer(Renderer):
    def __init__(self, loader: JinjaTemplateLoader):
        self.loader = loader
        self.kind = "html"

    def render(self, template_name: str, result: QueryResult) -> RenderOutput:
        ctx = dict(result.data or {})
        ctx["r"] = result
        text = self.loader.render_by_kind(
            kind="html", template_name=template_name, ext="html", ctx=ctx
        )
        return RenderOutput(mime="text/html; charset=utf-8", payload=text)

