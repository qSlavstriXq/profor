# Связь результатов профтеста с направлениями обучения.
# Таблицы лежат в proftests/data/directions/<код теста>.json, по одной на тест.

import json
import re
from functools import lru_cache
from pathlib import Path

from .loader import DATA_DIR

DIRECTIONS_DIR = DATA_DIR / "directions"

GROUP_RE = re.compile(r"^\d{2}$")             # 09
CODE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")  # 09.03.04


def validate_mapping(data, scale_codes):
    """Возвращает список ошибок. scale_codes: какие шкалы есть у теста."""
    errors = []
    for scale, rule in data.get("scales", {}).items():
        if scale not in scale_codes:
            errors.append(f"шкалы {scale!r} нет в тесте")
        for group in rule.get("groups", []):
            if not GROUP_RE.match(group):
                errors.append(f"{scale}: группа {group!r} должна быть из двух цифр")
        for code in rule.get("codes", []):
            if not CODE_RE.match(code):
                errors.append(f"{scale}: код {code!r} должен быть вида 09.03.04")
    return errors


@lru_cache
def load_mapping(test_code):
    """Таблица для теста или None, если её нет.

    lru_cache: файл читается один раз, дальше берётся из памяти.
    После правки файла перезапустите сервер.
    """
    path = DIRECTIONS_DIR / f"{test_code}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def fits(direction_code, rule):
    """Подходит ли направление под правило одной шкалы."""
    return direction_code in rule.get("codes", []) or direction_code[:2] in rule.get("groups", [])


def matching_scales(test_code, direction_code, scales):
    """Какие из шкал scales подходят направлению (в том же порядке)."""
    mapping = load_mapping(test_code)
    if mapping is None or not direction_code:
        return []
    rules = mapping["scales"]
    return [scale for scale in scales if scale in rules and fits(direction_code, rules[scale])]
