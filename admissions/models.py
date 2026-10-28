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
    GEOGRAPHY = "geography", "География"


class University(models.Model):
    # Постоянный код вуза (hse, mipt): по нему импорт находит вуз при повторной загрузке
    code = models.SlugField("Код", max_length=50, unique=True, null=True, blank=True)
    name = models.CharField("Название", max_length=255)
    short_name = models.CharField("Краткое название", max_length=50, blank=True)
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
        return self.short_name or self.name


class Program(models.Model):
    class StudyForm(models.TextChoices):
        FULL_TIME = "full_time", "Очная"
        PART_TIME = "part_time", "Очно-заочная"
        DISTANCE = "distance", "Заочная"

    university = models.ForeignKey(
        University, on_delete=models.CASCADE,
        related_name="programs", verbose_name="Вуз",
    )
    faculty = models.CharField("Факультет или институт", max_length=255, blank=True)
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
        return f"{self.university}: {self.name}"


class ProgramExam(models.Model):
    program = models.ForeignKey(
        Program, on_delete=models.CASCADE,
        related_name="exams", verbose_name="Программа",
    )
    subject = models.CharField("Предмет ЕГЭ", max_length=20, choices=Subject.choices)
    min_score = models.PositiveSmallIntegerField("Минимальный балл", default=0)
    # Предметы с одинаковым номером группы сдаются на выбор: «физика или информатика».
    # Пусто: предмет обязательный.
    choice_group = models.PositiveSmallIntegerField("Группа выбора", null=True, blank=True)

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
    passing_score_paid = models.PositiveSmallIntegerField(
        "Проходной балл на платное (сумма ЕГЭ)", null=True, blank=True,
    )
    paid_places = models.PositiveSmallIntegerField("Платных мест", null=True, blank=True)
    source_url = models.URLField("Источник данных", blank=True)

    class Meta:
        verbose_name = "Статистика приёма"
        verbose_name_plural = "Статистика приёма"
        constraints = [
            models.UniqueConstraint(fields=["program", "year"], name="unique_program_year"),
        ]
        ordering = ["year"]

    def __str__(self):
        return f"{self.program} ({self.year})"

class Course(models.Model):
    """Проверенный курс из нашего каталога. ИИ-помощник советует курсы только отсюда,
    чтобы не придумывать несуществующие. Каталог загружается командой load_courses."""

    class Kind(models.TextChoices):
        COURSE = "course", "Подготовка к экзаменам"
        SCHOOL = "school", "Профильная школа или кружок"
        ONLINE_SCHOOL = "online_school", "Онлайн-школа"
        EVENT = "event", "Лекции и встречи"
        EXCURSION = "excursion", "Экскурсия"
        PROFPROBA = "profproba", "Профпроба"

    code = models.SlugField("Код", max_length=100, unique=True)
    kind = models.CharField("Вид", max_length=20, choices=Kind.choices, default=Kind.COURSE)
    title = models.CharField("Название", max_length=255)
    provider = models.CharField("Кто проводит", max_length=255)
    url = models.URLField("Страница курса")
    description = models.TextField("Описание", blank=True)
    # Для каких направлений: группа ("09") или код направления ("09.03.04")
    directions = models.JSONField("Направления", default=list, blank=True)
    # Для каких классов: [9, 10, 11]. Пустой список: класс не важен
    grades = models.JSONField("Классы", default=list, blank=True)
    # Школьные предметы, коды как у Subject: ["math", "physics"]
    subjects = models.JSONField("Предметы", default=list, blank=True)
    professions = models.CharField("Для каких профессий", max_length=255, blank=True)
    is_free = models.BooleanField("Бесплатный", null=True, blank=True)
    verified = models.BooleanField("Проверено вручную", default=False)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"

    def __str__(self):
        return f"{self.title} ({self.provider})"

    def fits_direction(self, direction_code):
        """Подходит ли курс к направлению 09.03.04: по группе 09 или по полному коду."""
        return any(direction_code.startswith(d) for d in self.directions)

    def fits_grade(self, grade):
        """Подходит ли курс школьнику этого класса. Если класс неизвестен, подходит любой курс."""
        return grade is None or not self.grades or grade in self.grades

    def fits_profession(self, profession):
        """Подходит ли курс к профессии.

        Если у курса указаны направления (школа юного историка — 46), сверяем по ним.
        Если нет (подготовка к ЕГЭ по математике), сверяем по предметам. Русский язык
        нужен почти везде, поэтому по нему одному курс к профессии не привязываем.
        """
        if self.directions:
            return any(
                # Группа подходит к коду внутри неё и наоборот: 09 и 09.03.04
                mine.startswith(theirs) or theirs.startswith(mine)
                for mine in self.directions for theirs in profession.directions
            )
        return bool(set(self.subjects) & set(profession.subjects) - {"russian"})

    @property
    def grades_display(self):
        """Классы для показа: «9–11 класс», «10 класс»."""
        if not self.grades:
            return ""
        low, high = min(self.grades), max(self.grades)
        return f"{low} класс" if low == high else f"{low}–{high} класс"
