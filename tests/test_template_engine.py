import asyncio

import pytest

from action_executor.templating import TemplateEngine


class StubLogger:
    def __init__(self) -> None:
        self.records = []

    def warning(self, *args, **kwargs) -> None:
        self.records.append(("warning", args, kwargs))

    def error(self, *args, **kwargs) -> None:
        self.records.append(("error", args, kwargs))

    def info(self, *args, **kwargs) -> None:
        self.records.append(("info", args, kwargs))


@pytest.fixture
def template_engine() -> TemplateEngine:
    return TemplateEngine(logger=StubLogger())


def test_render_structure_supports_nested_dict_and_list(template_engine: TemplateEngine) -> None:
    context = {"greeting": "Hello", "user": {"name": "AstrBot"}}
    structure = {
        "message": "{{ greeting }} {{ user.name }}!",
        "items": ["{{ user.name|lower }}", 42, {"nested": "{{ greeting|lower }}"}],
    }

    rendered = asyncio.run(template_engine.render_structure(structure, context))

    assert rendered == {
        "message": "Hello AstrBot!",
        "items": ["astrbot", 42, {"nested": "hello"}],
    }


def test_render_button_overrides_renders_templates(template_engine: TemplateEngine) -> None:
    overrides_cfg = [
        {
            "target": "self",
            "temporary": False,
            "text_template": "Hi {{ username }}",
            "layout": {"row": "2", "col": "1"},
        }
    ]
    context = {"username": "Neo"}

    overrides = asyncio.run(
        template_engine.render_button_overrides(overrides_cfg, context)
    )

    assert overrides == [
        {
            "target": "self",
            "temporary": False,
            "text": "Hi Neo",
            "layout": {"row": 2, "col": 1},
        }
    ]
