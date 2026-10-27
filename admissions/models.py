from django.db import models


class Subject(models.TextChoices):
    MATH = "math", "Математика"
    RUSSIAN = "russian", "Русский язык"
    INFORMATICS = "informatics", "Информатика"
    PHYSICS = "physics", "Физика"
    CHEMISTRY = "chemistry", "Химия"
    BIOLOGY = "biology", "Биология"
    SOCIAL = "social", "Обществознание"
    HISTORY = "history", "История"
    LITERATURE = "literature", "Литература"
    ENGLISH = "english", "Английский язык"


class University(models.Model):
    name = models.CharField("Название", max_length=255)
    country = models.CharField("Страна", max_length=2, default="RU")
    city = models.CharField("Город", max_length=100, default="Москва")
    website = models.URLField("Сайт", blank=True)
    has_dormitory = models.BooleanField("Есть общежитие", default=False)
    source_url = models.URLField("Источник данных", blank=True)
    verified = models.BooleanField("Проверено вручную", default=False)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Вуз"
        verbose_name_plural = "Вузы"

    def __str__(self):
        return self.name


class Program(models.Model):
    class StudyForm(models.TextChoices):
        FULL_TIME = "full_time", "Очная"
        PART_TIME = "part_time", "Очно-заочная"
        DISTANCE = "distance", "Заочная"

    university = models.ForeignKey(
        University, on_delete=models.CASCADE,
        related_name="programs", verbose_name="Вуз",
    )
    name = models.CharField("Название программы", max_length=255)
    direction_code = models.CharField("Код направления", max_length=20, blank=True)
    study_form = models.CharField(
        "Форма обучения", max_length=20,
        choices=StudyForm.choices, default=StudyForm.FULL_TIME,
    )
    tuition_per_year = models.PositiveIntegerField("Стоимость в год, руб.", null=True, blank=True)
    source_url = models.URLField("Источник данных", blank=True)
    verified = models.BooleanField("Проверено вручную", default=False)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Программа"
        verbose_name_plural = "Программы"

    def __str__(self):
        return f"{self.university.name}: {self.name}"


class ProgramExam(models.Model):
    program = models.ForeignKey(
        Program, on_delete=models.CASCADE,
        related_name="exams", verbose_name="Программа",
    )
    subject = models.CharField("Предмет ЕГЭ", max_length=20, choices=Subject.choices)
    min_score = models.PositiveSmallIntegerField("Минимальный балл", default=0)

    class Meta:
        verbose_name = "Требуемый предмет"
        verbose_name_plural = "Требуемые предметы"

    def __str__(self):
        return f"{self.get_subject_display()} (от {self.min_score})"


class AdmissionStat(models.Model):
    program = models.ForeignKey(
        Program, on_delete=models.CASCADE,
        related_name="stats", verbose_name="Программа",
    )
    year = models.PositiveSmallIntegerField("Год")
    passing_score_budget = models.PositiveSmallIntegerField(
        "Проходной балл на бюджет (сумма ЕГЭ)", null=True, blank=True,
    )
    budget_places = models.PositiveSmallIntegerField("Бюджетных мест", null=True, blank=True)

    class Meta:
        verbose_name = "Статистика приёма"
        verbose_name_plural = "Статистика приёма"
        constraints = [
            models.UniqueConstraint(fields=["program", "year"], name="unique_program_year"),
        ]
        ordering = ["year"]

    def __str__(self):
        return f"{self.program} ({self.year})"