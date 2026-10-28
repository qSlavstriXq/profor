import json

from django.core.management.base import BaseCommand, CommandError

from careers.videos import VIDEOS_FILE, VideoDataError, load_videos


class Command(BaseCommand):
    help = "Загружает каталог видео из careers/data/videos.json"

    def handle(self, *args, **options):
        with open(VIDEOS_FILE, encoding="utf-8") as file:
            data = json.load(file)
        try:
            count = load_videos(data)
        except VideoDataError as error:
            raise CommandError(f"{VIDEOS_FILE.name}: {error}")
        self.stdout.write(self.style.SUCCESS(f"Видео в каталоге: {count}"))
