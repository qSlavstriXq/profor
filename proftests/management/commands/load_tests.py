from django.core.management.base import BaseCommand, CommandError

from proftests.loader import DATA_DIR, TestDataError, load_test, read_test_file


class Command(BaseCommand):
    help = "Загружает профтесты из JSON-файлов в папке proftests/data"

    def handle(self, *args, **options):
        files = sorted(DATA_DIR.glob("*.json"))
        if not files:
            raise CommandError(f"В {DATA_DIR} нет JSON-файлов")

        for path in files:
            try:
                test = load_test(read_test_file(path))
            except TestDataError as error:
                raise CommandError(f"{path.name}: {error}")
            self.stdout.write(self.style.SUCCESS(
                f"{path.name}: «{test.title}», вопросов {test.questions.count()}"
            ))
