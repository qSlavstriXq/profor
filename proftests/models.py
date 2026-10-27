import secrets

from django.db import models

from admissions.models import Subject

# Буквы и цифры для кода участника. Убраны похожие символы (0/O, 1/I/L),
# чтобы код было легко переписать с экрана.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6


def generate_participant_code():
    """Случайный код вида P-7F3K9Q. secrets даёт непредсказуемые значения."""
    return "P-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


class Test(models.Model):
    """Профтест. Содержание загружается из JSON командой load_tests."""

    class Kind(models.TextChoices):
        CAREER = "career", "Профориентационный"
        PERSONALITY = "personality", "Личностные качества"
        KNOWLEDGE = "knowledge", "Знание предмета"

    code = models.SlugField("Код теста", unique=True)
    kind = models.CharField("Вид теста", max_length=20, choices=Kind.choices, default=Kind.CAREER)
    title = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)
    instruction = models.TextField("Инструкция для школьника", blank=True)
    source = models.CharField("Источник методики", max_length=255, blank=True)
    is_active = models.BooleanField("Показывать на сайте", default=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Профтест"
        verbose_name_plural = "Профтесты"

    def __str__(self):
        return self.title


class Scale(models.Model):
    """Шкала результата, например «Человек — техника»."""

    test = models.ForeignKey(
        Test, on_delete=models.CASCADE,
        related_name="scales", verbose_name="Тест",
    )
    code = models.SlugField("Код шкалы")
    name = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    # Для тестов на знания: к какому предмету ЕГЭ относится шкала (тема)
    subject = models.CharField("Предмет ЕГЭ", max_length=20, choices=Subject.choices, blank=True)

    class Meta:
        verbose_name = "Шкала"
        verbose_name_plural = "Шкалы"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["test", "code"], name="unique_scale_code"),
        ]

    def __str__(self):
        return self.name


class Interpretation(models.Model):
    """Что значит результат по шкале в диапазоне от min_points до max_points."""

    scale = models.ForeignKey(
        Scale, on_delete=models.CASCADE,
        related_name="interpretations", verbose_name="Шкала",
    )
    min_points = models.PositiveSmallIntegerField("От (баллов)")
    max_points = models.PositiveSmallIntegerField("До (баллов)")
    level = models.CharField("Уровень", max_length=50)
    text = models.TextField("Пояснение")

    class Meta:
        verbose_name = "Расшифровка"
        verbose_name_plural = "Расшифровки"
        ordering = ["min_points"]

    def __str__(self):
        return f"{self.scale}: {self.min_points}–{self.max_points} ({self.level})"


class Question(models.Model):
    test = models.ForeignKey(
        Test, on_delete=models.CASCADE,
        related_name="questions", verbose_name="Тест",
    )
    order = models.PositiveSmallIntegerField("Номер")
    # В ДДО Климова у вопроса нет текста, только два варианта на выбор
    text = models.TextField("Текст вопроса", blank=True)

    class Meta:
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["test", "order"], name="unique_question_order"),
        ]

    def __str__(self):
        return f"{self.test.code} №{self.order}"


class Option(models.Model):
    """Вариант ответа. Если его выбрали, шкала scale получает points баллов."""

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE,
        related_name="options", verbose_name="Вопрос",
    )
    order = models.PositiveSmallIntegerField("Порядок", default=0)
    text = models.TextField("Текст")
    scale = models.ForeignKey(
        Scale, on_delete=models.CASCADE,
        related_name="options", verbose_name="Шкала",
    )
    points = models.PositiveSmallIntegerField("Баллы", default=1)

    class Meta:
        verbose_name = "Вариант ответа"
        verbose_name_plural = "Варианты ответа"
        ordering = ["order"]

    def __str__(self):
        return self.text


class Participant(models.Model):
    """Участник. Только код, никаких персональных данных."""

    code = models.CharField(
        "Код", max_length=20, unique=True, default=generate_participant_code,
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Участник"
        verbose_name_plural = "Участники"

    def __str__(self):
        return self.code


class Attempt(models.Model):
    """Одно прохождение теста участником."""

    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE,
        related_name="attempts", verbose_name="Участник",
    )
    # PROTECT: тест с прохождениями нельзя случайно удалить вместе с результатами
    test = models.ForeignKey(
        Test, on_delete=models.PROTECT,
        related_name="attempts", verbose_name="Тест",
    )
    started_at = models.DateTimeField("Начато", auto_now_add=True)
    finished_at = models.DateTimeField("Завершено", null=True, blank=True)
    # Итог по шкалам, например {"nature": 5, "tech": 2}. Считается в scoring.py
    scores = models.JSONField("Баллы по шкалам", null=True, blank=True)

    class Meta:
        verbose_name = "Прохождение"
        verbose_name_plural = "Прохождения"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.participant} — {self.test}"


class Answer(models.Model):
    attempt = models.ForeignKey(
        Attempt, on_delete=models.CASCADE,
        related_name="answers", verbose_name="Прохождение",
    )
    question = models.ForeignKey(Question, on_delete=models.PROTECT, verbose_name="Вопрос")
    option = models.ForeignKey(Option, on_delete=models.PROTECT, verbose_name="Ответ")

    class Meta:
        verbose_name = "Ответ"
        verbose_name_plural = "Ответы"
        constraints = [
            models.UniqueConstraint(fields=["attempt", "question"], name="unique_answer"),
        ]


class StrategyReport(models.Model):
    """Сохранённый ответ модели со стратегией, чтобы не тратить токены
    при каждом открытии страницы. Заглушки сюда не сохраняются."""

    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE,
        related_name="strategy_reports", verbose_name="Участник",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    model_name = models.CharField("Модель", max_length=100)
    # На каких данных построено: id прохождений и баллы ЕГЭ.
    # Если данные поменялись, стратегию нужно составить заново.
    basis = models.JSONField("Исходные данные")
    content = models.JSONField("Стратегия")

    class Meta:
        verbose_name = "Стратегия"
        verbose_name_plural = "Стратегии"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.participant} — {self.created_at:%d.%m.%Y %H:%M}"


class ExternalResult(models.Model):
    """Результат теста, пройденного вне сайта, например в центре профориентации.

    Загружается из таблицы центра командой import_external. Храним только код участника,
    название теста и баллы по шкалам: имена и контакты из таблицы центра не сохраняются.
    """

    participant = models.ForeignKey(
        Participant, on_delete=models.CASCADE,
        related_name="external_results", verbose_name="Участник",
    )
    source = models.SlugField("Код источника")
    source_name = models.CharField("Источник", max_length=255)
    test_name = models.CharField("Тест", max_length=255)
    taken_at = models.DateField("Дата прохождения", null=True, blank=True)
    # [{"name": "Человек — техника", "value": 7, "max": 10, "level": "высокий"}, ...]
    scales = models.JSONField("Баллы по шкалам")
    imported_at = models.DateTimeField("Загружено", auto_now=True)

    class Meta:
        verbose_name = "Внешний результат"
        verbose_name_plural = "Внешние результаты"
        ordering = ["-taken_at", "-imported_at"]
        constraints = [
            # Повторная загрузка той же таблицы обновляет запись, а не создаёт копию
            models.UniqueConstraint(
                fields=["participant", "source", "test_name", "taken_at"], name="unique_external_result",
            ),
        ]

    def __str__(self):
        return f"{self.participant} — {self.test_name} ({self.source_name})"
