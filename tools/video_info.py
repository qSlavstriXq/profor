"""Помощник для каталога видео (careers/data/videos.json).

Поиск роликов на RuTube (короткие, до 5 минут), чтобы выбрать с официальных каналов:

    python tools/video_info.py --search "профессия агроном"

Добавить ролик RuTube в каталог: название, канал и длительность подставятся сами:

    python tools/video_info.py https://rutube.ru/video/<номер>/ --add agronom,biolog

После добавления: python manage.py load_videos

Официальный ли канал (вуз, компания, ведомство) и правда ли ролик о профессии, решает человек:
случайные каналы часто перезаливают чужие ролики. Перезаливы не добавляем.

VK Видео: открытого интерфейса нет. Откройте ролик, «Поделиться» → «Экспортировать»,
скопируйте адрес из src="..." (https://vkvideo.ru/video_ext.php?oid=...&id=...&hash=...)
и впишите запись в videos.json вручную, platform = "vk".
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

VIDEOS_FILE = Path(__file__).resolve().parent.parent / "careers" / "data" / "videos.json"
API = "https://rutube.ru/api"
UA = {"User-Agent": "Mozilla/5.0 (profor video helper)"}
RUTUBE_ID = re.compile(r"rutube\.ru/(?:video|play/embed)/([0-9a-f]{32})")


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def minutes(seconds):
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds else "?"


def search(query, max_seconds):
    data = get(f"{API}/search/video/?query={urllib.parse.quote(query)}")
    for video in data.get("results", []):
        if video.get("duration") and video["duration"] <= max_seconds:
            print(f"{minutes(video['duration']):>5}  {video['title'][:70]}")
            print(f"       канал: {video['author']['name']} | {video['video_url']}")


def rutube_entry(url, professions):
    match = RUTUBE_ID.search(url)
    if not match:
        sys.exit(f"Не похоже на ссылку RuTube: {url}")
    video = get(f"{API}/video/{match.group(1)}/")
    return {
        "platform": "rutube",
        "video_id": video["id"],
        "title": video["title"].strip(),
        "channel": video["author"]["name"].strip(),
        "page_url": f"https://rutube.ru/video/{video['id']}/",
        "embed_url": f"https://rutube.ru/play/embed/{video['id']}",
        "duration": video["duration"],
        "professions": professions,
        "verified": False,
    }


def add(entry):
    with open(VIDEOS_FILE, encoding="utf-8") as file:
        data = json.load(file)
    if any(v["platform"] == entry["platform"] and v["video_id"] == entry["video_id"] for v in data["videos"]):
        sys.exit("Этот ролик уже есть в каталоге.")
    data["videos"].append(entry)
    with open(VIDEOS_FILE, "w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"Добавлено в {VIDEOS_FILE.name}. Загрузите: python manage.py load_videos")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", nargs="?", help="ссылка на ролик RuTube")
    parser.add_argument("--search", help="поисковый запрос на RuTube")
    parser.add_argument("--max", type=int, default=300, help="максимальная длительность в секундах (по умолчанию 300)")
    parser.add_argument("--add", help="коды профессий через запятую: добавить ролик в каталог")
    args = parser.parse_args()

    if args.search:
        search(args.search, args.max)
    elif args.url:
        entry = rutube_entry(args.url, [c.strip() for c in (args.add or "").split(",") if c.strip()])
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        if args.add:
            add(entry)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
