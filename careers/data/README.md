# Каталог профессий

Файл `professions.json`, загрузка: `python manage.py load_professions`.
Профессии, которых нет в файле, при загрузке удаляются из базы.

| Поле | Что это |
|---|---|
| `code` | Код латиницей, уникальный: `programmist` |
| `title` | Название: «Программист» |
| `description` | Описание для школьника, 2–3 предложения своими словами |
| `test_scales` | Каким шкалам тестов подходит: `{"klimov-ddo": ["tech"], "holland": ["r", "i"]}`. Тесты и шкалы проверяются по файлам в `proftests/data/` |
| `subjects` | Школьные предметы (ОГЭ и ЕГЭ): `math`, `russian`, `informatics`, `physics`, `chemistry`, `biology`, `social`, `history`, `literature`, `english`, `geography` |
| `directions` | Направления вузов: группа `09` или код `09.03.04` |
| `links` | Ссылки только на официальные страницы: `[{"title": "...", "url": "https://..."}]`. «Проекторию», «Билет в будущее» и агрегаторы не используем |
| `verified` | `true`, когда эксперт проверил описание и связи |

# Каталог видео

Файл `videos.json`, загрузка: `python manage.py load_videos` (после `load_professions`).
На странице профессии встраивается плеер RuTube или VK Видео: сами файлы мы не храним.
Ролики берём только с официальных каналов организаций (вузы, компании, ведомства, телеканалы).
Перезаливы со случайных каналов, «Проекторию», «Билет в будущее» и YouTube не используем.

Добавить ролик RuTube проще всего помощником: он сам подставит название, канал и длительность.

```
python tools/video_info.py --search "профессия агроном"        # найти ролики до 5 минут
python tools/video_info.py https://rutube.ru/video/<номер>/ --add agronom
python manage.py load_videos
```

| Поле | Что это |
|---|---|
| `platform` | `rutube` или `vk` |
| `video_id` | Номер ролика на площадке |
| `title`, `channel` | Название и канал, как на площадке |
| `page_url` | Страница ролика |
| `embed_url` | Адрес плеера. RuTube: `https://rutube.ru/play/embed/<номер>`. VK: «Поделиться» → «Экспортировать», адрес из `src="..."` (`https://vkvideo.ru/video_ext.php?oid=...&id=...&hash=...`) |
| `duration` | Длительность в секундах |
| `professions` | Коды профессий из `professions.json` |
| `verified` | `true`, когда человек посмотрел ролик и проверил канал |
