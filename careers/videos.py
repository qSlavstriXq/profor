# Каталог видео о профессиях: загрузка из careers/data/videos.json.
# Формат описан в careers/data/README.md

import json

from django.db import transaction

from .loader import DATA_DIR, PROFESSIONS_FILE
from .models import Video

VIDEOS_FILE = DATA_DIR / "videos.json"

# Плеер встраиваем только с этих адресов: так в страницу не попадёт чужой сайт
EMBED_PREFIXES = {
    Video.Platform.RUTUBE: ("https://rutube.ru/play/embed/",),
    Video.Platform.VK: ("https://vk.com/video_ext.php?", "https://vkvideo.ru/video_ext.php?"),
}


class VideoDataError(Exception):
    """Файл видео содержит ошибки."""


def profession_codes():
    """Коды профессий из файла каталога профессий."""
    with open(PROFESSIONS_FILE, encoding="utf-8") as file:
        return {item["code"] for item in json.load(file)["professions"]}


def validate_videos(data, professions=None):
    """Возвращает список ошибок. Пустой список: файл в порядке.

    professions: коды профессий; в тестах подставляем свои.
    """
    if professions is None:
        professions = profession_codes()
    errors = []
    seen = set()
    for number, item in enumerate(data.get("videos", []), start=1):
        where = f"видео {number} ({item.get('title', 'без названия')})"
        for field in ("platform", "video_id", "title", "channel", "page_url", "embed_url"):
            if not item.get(field):
                errors.append(f"{where}: не заполнено поле {field}")
        key = (item.get("platform"), item.get("video_id"))
        if key in seen:
            errors.append(f"{where}: ролик повторяется")
        seen.add(key)
        prefixes = EMBED_PREFIXES.get(item.get("platform"))
        if prefixes is None:
            errors.append(f"{where}: площадка должна быть rutube или vk")
        elif not str(item.get("embed_url", "")).startswith(prefixes):
            errors.append(f"{where}: адрес плеера должен начинаться с {' или '.join(prefixes)}")
        if not str(item.get("page_url", "")).startswith("https://"):
            errors.append(f"{where}: page_url должен начинаться с https://")
        duration = item.get("duration")
        if duration is not None and (not isinstance(duration, int) or duration <= 0):
            errors.append(f"{where}: длительность — целое число секунд")
        if not item.get("professions"):
            errors.append(f"{where}: не указаны профессии")
        for code in item.get("professions", []):
            if code not in professions:
                errors.append(f"{where}: профессии {code!r} нет в каталоге")
    return errors


@transaction.atomic
def load_videos(data, professions=None):
    """Создаёт или обновляет ролики. Ролики, которых нет в файле, удаляются."""
    errors = validate_videos(data, professions)
    if errors:
        raise VideoDataError("; ".join(errors))
    keep = []
    for item in data.get("videos", []):
        video, _created = Video.objects.update_or_create(
            platform=item["platform"],
            video_id=item["video_id"],
            defaults={
                "title": item["title"],
                "channel": item["channel"],
                "page_url": item["page_url"],
                "embed_url": item["embed_url"],
                "duration": item.get("duration"),
                "professions": item["professions"],
                "verified": item.get("verified", False),
            },
        )
        keep.append(video.pk)
    Video.objects.exclude(pk__in=keep).delete()
    return len(keep)
