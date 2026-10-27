# Загрузка результатов, полученных вне сайта (например, в центре профориентации).
#
# Таблица центра (CSV или Excel) + файл соответствия столбцов из proftests/data/external/.
# Из таблицы читаются только столбцы, перечисленные в файле соответствия: код участника,
# дата и баллы. Имена, контакты и названия школ, даже если они есть в таблице, не читаются.

import csv
import json
from datetime import datetime
from pathlib import Path

from django.db import transaction

from .loader import DATA_DIR
from .models import ExternalResult, Participant

EXTERNAL_DIR = DATA_DIR / "external"


class ExternalDataError(Exception):
    """Файл соответствия или таблица содержат ошибки."""


def read_mapping(path):
    with open(path, encoding="utf-8") as file:
        mapping = json.load(file)
    errors = validate_mapping(mapping)
    if errors:
        raise ExternalDataError("; ".join(errors))
    return mapping


def validate_mapping(mapping):
    """Возвращает список ошибок файла соответствия. Пустой список: всё в порядке."""
    errors = []
    for field in ("source", "source_name", "participant_code_column", "tests"):
        if not mapping.get(field):
            errors.append(f"нет поля {field}")
    for number, test in enumerate(mapping.get("tests", []), start=1):
        if not test.get("test_name"):
            errors.append(f"тест {number}: нет test_name")
        if not test.get("scales"):
            errors.append(f"тест {number}: нет шкал")
        for scale in test.get("scales", []):
            if not scale.get("column") or not scale.get("name"):
                errors.append(f"тест {number}: у шкалы нужны column и name")
    return errors


def mapped_columns(mapping):
    """Все столбцы таблицы, которые мы читаем."""
    columns = [mapping["participant_code_column"]]
    if mapping.get("date_column"):
        columns.append(mapping["date_column"])
    for test in mapping["tests"]:
        for scale in test["scales"]:
            columns.append(scale["column"])
            if scale.get("level_column"):
                columns.append(scale["level_column"])
    return columns


def read_table(path):
    """Строки таблицы как словари {столбец: значение}. Поддерживаются CSV и XLSX."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as file:
            sample = file.read(4096)
            file.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")  # Excel в России сохраняет через «;»
            return list(csv.DictReader(file, dialect=dialect))
    if path.suffix.lower() == ".xlsx":
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise ExternalDataError("для Excel установите openpyxl или сохраните таблицу как CSV")
        sheet = load_workbook(path, read_only=True, data_only=True).active
        rows = list(sheet.iter_rows(values_only=True))
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        return [{h: ("" if v is None else str(v)) for h, v in zip(header, row)} for row in rows[1:]]
    raise ExternalDataError(f"неизвестный формат {path.suffix}: нужен .csv или .xlsx")


def _number(text):
    text = str(text or "").strip().replace(",", ".")
    if not text:
        return None
    value = float(text)
    return int(value) if value.is_integer() else value


def _level(value, scale):
    """Уровень по таблице уровней из файла соответствия, если она есть."""
    for item in scale.get("levels", []):
        if item["min"] <= value <= item["max"]:
            return item["level"]
    return ""


@transaction.atomic
def import_rows(mapping, rows, dry_run=False):
    """Загружает строки таблицы. Возвращает отчёт.

    Участника ищем по коду, который выдал наш сайт. Новых участников не создаём:
    код ученик получает на сайте и сообщает центру.
    """
    if rows:
        missing = [c for c in mapped_columns(mapping) if c not in rows[0]]
        if missing:
            raise ExternalDataError(f"в таблице нет столбцов: {', '.join(missing)}")

    report = {"saved": 0, "unknown_codes": [], "errors": []}
    for number, row in enumerate(rows, start=2):  # строка 1 — заголовок
        code = row[mapping["participant_code_column"]].strip().upper()
        participant = Participant.objects.filter(code=code).first()
        if participant is None:
            report["unknown_codes"].append(number)
            continue
        try:
            taken_at = None
            if mapping.get("date_column") and row[mapping["date_column"]].strip():
                taken_at = datetime.strptime(
                    row[mapping["date_column"]].strip(), mapping.get("date_format", "%d.%m.%Y"),
                ).date()
            for test in mapping["tests"]:
                scales = []
                for scale in test["scales"]:
                    value = _number(row[scale["column"]])
                    if value is None:
                        continue
                    level = row[scale["level_column"]].strip() if scale.get("level_column") else ""
                    scales.append({
                        "name": scale["name"], "value": value, "max": scale.get("max"),
                        "level": level or _level(value, scale),
                    })
                if not scales:
                    continue  # этот тест ученик не проходил
                if not dry_run:
                    ExternalResult.objects.update_or_create(
                        participant=participant, source=mapping["source"],
                        test_name=test["test_name"], taken_at=taken_at,
                        defaults={"source_name": mapping["source_name"], "scales": scales},
                    )
                report["saved"] += 1
        except ValueError as error:
            report["errors"].append(f"строка {number}: {error}")
    if report["errors"]:
        # Ошибка в данных: не загружаем ничего, чтобы не было половины таблицы
        transaction.set_rollback(True)
        report["saved"] = 0
    return report
