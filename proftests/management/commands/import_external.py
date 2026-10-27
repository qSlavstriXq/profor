from django.core.management.base import BaseCommand, CommandError

from proftests.external import EXTERNAL_DIR, ExternalDataError, import_rows, read_mapping, read_table


class Command(BaseCommand):
    help = "Загружает результаты тестов из таблицы центра профориентации (CSV или XLSX)"

    def add_arguments(self, parser):
        parser.add_argument("mapping", help="файл соответствия столбцов: имя в proftests/data/external без .json")
        parser.add_argument("table", help="путь к таблице центра (.csv или .xlsx)")
        parser.add_argument(
            "--save", action="store_true",
            help="записать в базу. Без этого флага только проверка и отчёт",
        )

    def handle(self, *args, **options):
        mapping_path = EXTERNAL_DIR / f"{options['mapping']}.json"
        if not mapping_path.exists():
            raise CommandError(f"Нет файла {mapping_path}")
        try:
            mapping = read_mapping(mapping_path)
            report = import_rows(mapping, read_table(options["table"]), dry_run=not options["save"])
        except ExternalDataError as error:
            raise CommandError(str(error))

        for error in report["errors"]:
            self.stdout.write(self.style.ERROR(error))
        if report["unknown_codes"]:
            rows = ", ".join(map(str, report["unknown_codes"]))
            self.stdout.write(self.style.WARNING(f"Код участника не найден на сайте, строки: {rows}"))
        if report["errors"]:
            raise CommandError("Есть ошибки, ничего не записано")
        verb = "Записано" if options["save"] else "Будет записано (запустите с --save)"
        self.stdout.write(self.style.SUCCESS(f"{verb} результатов: {report['saved']}"))
