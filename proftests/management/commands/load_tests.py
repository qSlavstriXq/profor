from django.core.management.base import BaseCommand, CommandError

from proftests.loader import DATA_DIR, TestDataError, load_test, read_test_file
from proftests.models import Test

EXAMPLES_DIR = DATA_DIR / "examples"


class Command(BaseCommand):
    help = "Загружает профтесты из JSON-файлов в папке proftests/data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--examples", action="store_true",
            help="загрузить образцы формата из data/examples и показать их на сайте",
        )
        parser.add_argument(
            "--hide-examples", action="store_true",
            help="скрыть образцы формата на сайте (перед конференцией)",
        )

    def handle(self, *args, **options):
        if options["hide_examples"]:
            self.hide_examples()
            return

        folder = EXAMPLES_DIR if options["examples"] else DATA_DIR
        files = sorted(folder.glob("*.json"))
        if not files:
            raise CommandError(f"В {folder} нет JSON-файлов")

        for path in files:
            data = read_test_file(path)
            if options["examples"]:
                # В файлах образцов стоит is_active: false, чтобы они не попали
                # на сайт случайно. Здесь мы показываем их сознательно, для просмотра.
                data["is_active"] = True
            try:
                test = load_test(data)
            except TestDataError as error:
                raise CommandError(f"{path.name}: {error}")
            self.stdout.write(self.style.SUCCESS(
                f"{path.name}: «{test.title}», вопросов {test.questions.count()}"
            ))

    def hide_examples(self):
        codes = [read_test_file(path)["code"] for path in sorted(EXAMPLES_DIR.glob("*.json"))]
        hidden = Test.objects.filter(code__in=codes, is_active=True).update(is_active=False)
        self.stdout.write(self.style.SUCCESS(f"Скрыто образцов: {hidden}"))
