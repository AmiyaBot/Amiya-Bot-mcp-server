from jinja2 import Environment, FileSystemLoader, TemplateNotFound
import logging

logger = logging.getLogger(__name__)

class JinjaTemplateLoader:
    def __init__(self, template_root: str):
        self.env = Environment(
            loader=FileSystemLoader(template_root),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_by_kind(self, *, kind: str, template_name: str, ext: str, ctx: dict) -> str:
        relpath = self.resolve_template(kind=kind, template_name=template_name, ext=ext)
        return self.env.get_template(relpath).render(**ctx)


    def resolve_template(self, *, kind: str, template_name: str, ext: str) -> str:
        """
        返回第一个存在的模板路径；都不存在则抛 TemplateNotFound(列出所有候选)。
        """
        candidates = [
            f"{kind}/{template_name}.{ext}.j2",
            f"{template_name}.{ext}.j2",
            f"{template_name}/{template_name}.{ext}.j2",
        ]

        for relpath in candidates:
            try:
                self.env.get_template(relpath)
                return relpath
            except TemplateNotFound:
                continue
            
        raise TemplateNotFound(f"None of templates found: {candidates}")