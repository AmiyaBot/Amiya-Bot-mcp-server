from __future__ import annotations

import json

from src.app.renderers.types import RenderOutput
from src.app.renderers.jinja_template_loader import JinjaTemplateLoader
from src.app.renderers.types import Renderer
from src.domain.types import QueryResult


class JinjaJsonRenderer(Renderer):
    def __init__(self, loader: JinjaTemplateLoader):
        self.loader = loader
        self.kind = "json"

    def render(self, template_name: str, result: QueryResult) -> RenderOutput:
        ctx = dict(result.data or {})
        ctx["r"] = result
        rendered = self.loader.render_by_kind(
            kind="json", template_name=template_name, ext="json", ctx=ctx
        ).strip()

        payload = json.loads(rendered)
        return RenderOutput(
            mime="application/json; charset=utf-8",
            payload=payload,
        )

