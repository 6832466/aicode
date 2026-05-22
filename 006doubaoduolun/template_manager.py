import json
import os
from dataclasses import dataclass, field, asdict
from typing import List

_DEFAULT_TEMPLATES = [
    {"name": "专业写作助手", "content": "你是一位专业的写作助手，擅长各类文体的写作和润色。"},
    {"name": "代码审查专家", "content": "你是一位资深软件工程师，专注于代码质量审查和优化建议。"},
    {"name": "数据分析师",   "content": "你是一位数据分析专家，擅长从数据中提取洞察并给出建议。"},
    {"name": "翻译专家",     "content": "你是一位专业翻译，精通中英文互译，注重语境和文化差异。"},
]

_SAVE_PATH = os.path.join(os.path.dirname(__file__), "templates.json")


@dataclass
class PromptTemplate:
    name: str
    content: str


class TemplateManager:
    def __init__(self):
        self._templates: List[PromptTemplate] = []
        self._load()

    def _load(self):
        if os.path.exists(_SAVE_PATH):
            try:
                with open(_SAVE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._templates = [PromptTemplate(**d) for d in data]
                return
            except Exception:
                pass
        self._templates = [PromptTemplate(**d) for d in _DEFAULT_TEMPLATES]
        self._save()

    def _save(self):
        with open(_SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump([asdict(t) for t in self._templates], f, ensure_ascii=False, indent=2)

    def all(self) -> List[PromptTemplate]:
        return list(self._templates)

    def add(self, name: str, content: str):
        self._templates.append(PromptTemplate(name=name, content=content))
        self._save()

    def update(self, index: int, name: str, content: str):
        self._templates[index] = PromptTemplate(name=name, content=content)
        self._save()

    def delete(self, index: int):
        self._templates.pop(index)
        self._save()

    def move_up(self, index: int):
        if index > 0:
            self._templates[index], self._templates[index - 1] = \
                self._templates[index - 1], self._templates[index]
            self._save()

    def move_down(self, index: int):
        if index < len(self._templates) - 1:
            self._templates[index], self._templates[index + 1] = \
                self._templates[index + 1], self._templates[index]
            self._save()


# singleton
_manager: TemplateManager = None


def get_manager() -> TemplateManager:
    global _manager
    if _manager is None:
        _manager = TemplateManager()
    return _manager
