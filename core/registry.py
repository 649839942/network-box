"""
工具注册表：从 config/tools.yaml 加载工具箱导航与工具面板。
"""
import importlib
from pathlib import Path

import yaml

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "config" / "tools.yaml"


def load_tool_registry(path=None) -> dict:
    """读取工具注册表 YAML。"""
    registry_path = Path(path) if path else DEFAULT_REGISTRY_PATH
    if not registry_path.exists():
        raise FileNotFoundError(f"工具注册表不存在: {registry_path}")

    with open(registry_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError("工具注册表格式错误，应为 YAML 字典")
    return data


def import_panel_class(panel_ref: str):
    """按 module:ClassName 字符串导入工具面板类。"""
    module_name, _, class_name = panel_ref.partition(":")
    if not module_name or not class_name:
        raise ValueError(f"无效的面板引用: {panel_ref}")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def build_panels(registry: dict) -> dict:
    """根据注册表实例化所有工具面板，返回 {tool_id: panel}。"""
    panels = {}
    for category in registry.get("categories", []):
        for tool in category.get("tools", []):
            tool_id = tool.get("id")
            if not tool_id:
                continue
            panel_class = import_panel_class(tool["panel"])
            panels[tool_id] = panel_class()
    return panels
