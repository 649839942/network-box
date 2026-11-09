# core/config_loader.py
import shutil
import sys
from pathlib import Path

import yaml


COMMAND_CONFIG_FILES = {
    "huawei": "HW-command.yaml",
    "h3c": "H3C-command.yaml",
    "cisco": "Cisco-command.yaml",
}


def ensure_external_config_files():
    """首次运行时将内置 YAML 复制到 EXE 同目录，已有文件不覆盖。"""
    if not getattr(sys, "frozen", False):
        return

    external_dir = Path(sys.executable).parent / "config"
    bundled_dir = Path(sys._MEIPASS) / "config"
    external_dir.mkdir(parents=True, exist_ok=True)

    for source in bundled_dir.glob("*.yaml"):
        target = external_dir / source.name
        if not target.exists():
            shutil.copy2(source, target)


def get_command_config_path(vendor: str) -> Path:
    """返回指定厂商的外部或内置巡检命令配置路径。"""
    filename = COMMAND_CONFIG_FILES.get(vendor)
    if filename is None:
        raise ValueError(f"不支持的巡检模板: {vendor}")

    if getattr(sys, "frozen", False):
        ensure_external_config_files()
        exe_dir = Path(sys.executable).parent
        external_config = exe_dir / "config" / filename
        if external_config.exists():
            return external_config
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent

    return base / "config" / filename


def get_default_config_path() -> Path:
    """返回默认的华为巡检命令配置路径。"""
    return get_command_config_path("huawei")


def load_commands_yaml(yaml_path):
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"命令配置文件不存在: {yaml_path}")
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data
    except yaml.YAMLError as e:
        line = getattr(e, 'problem_mark', None)
        line_info = f" (大约第 {line.line + 1} 行)" if line else ""
        raise ValueError(f"YAML 解析失败{line_info}: {e}")

def get_commands_by_group(config, group_names=None):
    if not isinstance(config, dict):
        return []
    commands = []
    if group_names is None:
        group_names = list(config.keys())
    for group_name in group_names:
        if group_name not in config:
            continue
        group_data = config[group_name]
        for cmd_entry in group_data.get("commands", []):
            cmd_text = cmd_entry.get("command", "").strip()
            if not cmd_text:
                continue
            commands.append({
                "group": group_name,
                "command": cmd_text,
                "note": cmd_entry.get("note", "")
            })
    return commands
