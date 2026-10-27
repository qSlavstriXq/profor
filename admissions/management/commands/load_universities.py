from django.core.management.base import BaseCommand, CommandError

from admissions.loader import DATA_DIR, UniversityDataError, load_university, read_university_file


class Command(BaseCommand):
    help = "Загружает вузы и программы из JSON-файлов в папке admissions/data"

    def add_arguments(self, parser):
        parser.add_argument(
            "codes", nargs="*",
            help="Имена файлов без .json (например, hse mipt). Без них загружаются все.",
        )

    def handle(self, *args, **options):
        if options["codes"]:
            files = [DATA_DIR / f"{code}.json" for code in options["codes"]]
            missing = [path.name for path in files if not path.exists()]
            if missing:
                raise CommandError(f"Нет файлов: {', '.join(missing)}")
        else:
            files = sorted(DATA_DIR.glob("*.json"))
        if not files:
            raise CommandError(f"В {DATA_DIR} нет JSON-файлов")

        for path in files:
            try:
                university = load_university(read_university_file(path))
            except UniversityDataError as error:
                raise CommandError(f"{path.name}: {error}")
            self.stdout.write(self.style.SUCCESS(
                f"{path.name}: «{university}», программ {university.programs.count()}"
            ))
