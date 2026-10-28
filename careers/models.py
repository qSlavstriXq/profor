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
