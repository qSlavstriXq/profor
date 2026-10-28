import json

from django.core.management.base import BaseCommand, CommandError

from admissions.courses import COURSES_FILE, CourseDataError, load_courses


class Command(BaseCommand):
    help = "Загружает каталог курсов из admissions/data/courses/courses.json"

    def handle(self, *args, **options):
        with open(COURSES_FILE, encoding="utf-8") as file:
            data = json.load(file)
        try:
            count = load_courses(data)
        except CourseDataError as error:
            raise CommandError(f"{COURSES_FILE.name}: {error}")
        self.stdout.write(self.style.SUCCESS(f"Курсов в каталоге: {count}"))
