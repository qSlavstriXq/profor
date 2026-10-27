# Данные о вузах

Один файл = один вуз, имя файла совпадает с `code` (например, `hse.json`).

Загрузка в базу:

```
python manage.py load_universities          # все файлы
python manage.py load_universities hse mipt # только эти
```

Повторная загрузка обновляет данные. Программы, которых нет в файле, удаляются.
Если в файле ошибка, база не меняется.

## Формат

```json
{
  "code": "hse",
  "name": "Национальный исследовательский университет «Высшая школа экономики»",
  "short_name": "ВШЭ",
  "website": "https://www.hse.ru",
  "has_dormitory": true,
  "source_url": "https://ba.hse.ru/...",
  "verified": false,
  "programs": [
    {
      "faculty": "Факультет компьютерных наук",
      "name": "Программная инженерия",
      "direction_code": "09.03.04",
      "study_form": "full_time",
      "tuition_per_year": 750000,
      "source_url": "https://...",
      "verified": false,
      "exams": [
        {"subject": "math", "min_score": 75},
        {"subject": "russian", "min_score": 60},
        {"one_of": [
          {"subject": "informatics", "min_score": 70},
          {"subject": "physics", "min_score": 70}
        ]}
      ],
      "stats": [
        {"year": 2024, "passing_score_budget": 285, "budget_places": 150, "source_url": "https://..."}
      ]
    }
  ]
}
```

- `study_form`: `full_time` (очная), `part_time` (очно-заочная), `distance` (заочная).
- Предметы: `math`, `russian`, `informatics`, `physics`, `chemistry`, `biology`,
  `social`, `history`, `literature`, `english`.
- `one_of`: один предмет на выбор. Засчитывается тот, что выгоднее школьнику.
- `passing_score_budget`: проходной балл на бюджет по общему конкурсу,
  сумма ЕГЭ **без** индивидуальных достижений, если вуз публикует её отдельно.
  У агрегаторов балл иногда включает достижения (до +10), поэтому оценка шансов получается
  чуть осторожнее. Год, где балл больше 100 × число предметов + 10, не берём: тогда экзаменов
  было больше (например, у ВШЭ в 2022–2023 годах было 4 экзамена).
- `min_score`: минимальный балл, установленный вузом (не минимальный порог Рособрнадзора).
- `source_url` у программы и у каждого года: откуда взяты цифры. Если не указан
  у программы, берётся ссылка вуза.
- `verified`: `true` ставит только человек, сверивший цифры с источником.
- Неизвестное значение не выдумываем: поле пропускаем.
