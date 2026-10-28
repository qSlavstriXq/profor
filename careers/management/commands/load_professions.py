import json

from django.core.management.base import BaseCommand, CommandError

from careers.loader import PROFESSIONS_FILE, ProfessionDataError, load_professions


class Command(BaseCommand):
    help = "Загружает каталог профессий из careers/data/professions.json"

    def handle(self, *args, **options):
        with open(PROFESSIONS_FILE, encoding="utf-8") as file:
            data = json.load(file)
        try:
            count = load_professions(data)
        except ProfessionDataError as error:
            raise CommandError(f"{PROFESSIONS_FILE.name}: {error}")
        self.stdout.write(self.style.SUCCESS(f"Профессий в каталоге: {count}"))
