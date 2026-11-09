"""Configuration vendor detection and line comparison helpers."""
import re
from difflib import SequenceMatcher


VENDOR_NAMES = {
    "huawei": "华为",
    "h3c": "新华三",
    "cisco": "思科",
}


def detect_config_vendor(config_text: str):
    """Return ``huawei``, ``h3c``, or ``cisco`` from strong vendor markers."""
    lowered = config_text.lower()
    padded = f"\n{lowered}"
    scores = {"huawei": 0, "h3c": 0, "cisco": 0}

    if "!software version vrp" in lowered:
        scores["huawei"] += 6
    if "\nsysname " in padded or lowered.startswith("sysname "):
        scores["huawei"] += 2
    if "\nreturn" in padded:
        scores["huawei"] += 2
    if "\nuser-interface vty " in padded:
        scores["huawei"] += 2
    if lowered.count("\n#") >= 2:
        scores["huawei"] += 1

    if "comware software" in lowered or "h3c comware" in lowered:
        scores["h3c"] += 8
    if re.search(r"(?m)^\s*version\s+\d+\.\d+(?:\.\d+)?,\s*release\b", lowered):
        scores["h3c"] += 7
    if re.search(r"(?m)^\s*line class\s+", lowered):
        scores["h3c"] += 5
    if re.search(r"(?m)^\s*irf\s+", lowered):
        scores["h3c"] += 3
    if re.search(r"(?m)^\s*local-user\s+\S+\s+class\s+manage\b", lowered):
        scores["h3c"] += 2

    if "building configuration..." in lowered:
        scores["cisco"] += 6
    if "current configuration :" in lowered:
        scores["cisco"] += 6
    if "boot-start-marker" in lowered:
        scores["cisco"] += 4
    if "\nservice timestamps " in padded:
        scores["cisco"] += 2
    if "\nline vty 0 4" in padded:
        scores["cisco"] += 2
    if "\nend" in padded:
        scores["cisco"] += 1
    if any(line.startswith("version ") for line in lowered.splitlines()):
        scores["cisco"] += 2

    vendor, score = max(scores.items(), key=lambda item: item[1])
    if score < 4:
        return None
    if list(scores.values()).count(score) > 1:
        return None
    return vendor


def compare_config_lines(old_text: str, new_text: str) -> dict:
    """Return highlighted line indexes and the number of changed blocks."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = SequenceMatcher(None, old_lines, new_lines, autojunk=False)

    old_indexes = set()
    new_indexes = set()
    changed_blocks = 0

    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_blocks += 1
        old_indexes.update(range(old_start, old_end))
        new_indexes.update(range(new_start, new_end))

    return {
        "old_indexes": sorted(old_indexes),
        "new_indexes": sorted(new_indexes),
        "changed_blocks": changed_blocks,
    }
