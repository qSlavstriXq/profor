from django.db import models


class Profession(models.Model):
    """Профессия, понятная школьнику. Связывает результаты профтестов
    с направлениями вузов и школьными предметами. Загружается командой load_professions."""

    code = models.SlugField("Код", max_length=100, unique=True)
    title = models.CharField("Название", max_length=255)
    description = models.TextField("Описание для школьника")
    # Каким шкалам тестов подходит: {"klimov-ddo": ["tech"], "holland": ["r", "i"]}
    test_scales = models.JSONField("Шкалы тестов", default=dict, blank=True)
    # Школьные предметы (ОГЭ и ЕГЭ), коды как у Subject: ["math", "physics"]
    subjects = models.JSONField("Предметы", default=list, blank=True)
    # Направления вузов: группа ("09") или код направления ("09.03.04")
    directions = models.JSONField("Направления", default=list, blank=True)
    # Ссылки только на официальные страницы: [{"title": "...", "url": "https://..."}]
    links = models.JSONField("Ссылки", default=list, blank=True)
    verified = models.BooleanField("Проверено вручную", default=False)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Профессия"
        verbose_name_plural = "Профессии"
        ordering = ["title"]

    def __str__(self):
        return self.title

    def fits_direction(self, direction_code):
        """Подходит ли профессия к направлению 09.03.04: по группе 09 или по полному коду."""
        return any(direction_code.startswith(d) for d in self.directions)


class Video(models.Model):
    """Ролик о профессии с официального канала организации на RuTube или VK Видео.

    Файл у себя не храним: на странице профессии встраиваем плеер площадки.
    Загружается командой load_videos.
    """

    class Platform(models.TextChoices):
        RUTUBE = "rutube", "RuTube"
        VK = "vk", "VK Видео"

    platform = models.CharField("Площадка", max_length=10, choices=Platform.choices)
    video_id = models.CharField("Номер ролика на площадке", max_length=100)
    title = models.CharField("Название", max_length=255)
    channel = models.CharField("Канал (кто снял)", max_length=255)
    page_url = models.URLField("Страница ролика", max_length=500)
    # Адрес плеера для встраивания: RuTube — https://rutube.ru/play/embed/<номер>,
    # VK — из кнопки «Поделиться → Экспортировать» (с параметром hash)
    embed_url = models.URLField("Адрес плеера", max_length=500)
    duration = models.PositiveIntegerField("Длительность, секунд", null=True, blank=True)
    # Коды профессий из каталога: ["programmist"]
    professions = models.JSONField("Профессии", default=list, blank=True)
    verified = models.BooleanField("Проверено вручную", default=False)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Видео"
        verbose_name_plural = "Видео"
        ordering = ["duration", "title"]
        constraints = [
            models.UniqueConstraint(fields=["platform", "video_id"], name="unique_video_on_platform"),
        ]

    def __str__(self):
        return f"{self.title} ({self.channel})"

    @property
    def duration_display(self):
        """Длительность для показа: «3:21»."""
        if not self.duration:
            return ""
        return f"{self.duration // 60}:{self.duration % 60:02d}"
