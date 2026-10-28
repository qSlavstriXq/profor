"""Проверка движка шансов на реальных проходных баллах из базы.

    python tools/backtest_chances.py

Для каждой программы, где известны баллы хотя бы за 3 года, берём все годы, кроме
последнего, считаем по ним ожидаемый проходной балл (как в admissions/chances.py)
и сравниваем с настоящим баллом последнего года. Ошибка = настоящий − ожидаемый:
плюс значит, что проходной оказался выше, чем мы ждали (школьник мог не пройти).

По ошибкам видно, насколько широкими должны быть категории шансов: например,
если в 9 случаях из 10 ошибка не больше +10, то запас в 10 баллов («страховка»)
действительно почти гарантирует поступление.
"""
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django  # noqa: E402

django.setup()

from admissions import chances  # noqa: E402
from admissions.models import Program  # noqa: E402

# Какие значения TREND_WEIGHT сравниваем
WEIGHTS = [0.0, 0.5, 1.0]


def collect_cases():
    cases = []
    for program in Program.objects.prefetch_related("stats"):
        scores = [s.passing_score_budget for s in program.stats.all() if s.passing_score_budget]
        if len(scores) >= 3:
            cases.append((str(program), scores[:-1], scores[-1]))
    return cases


def percentile(values, share):
    values = sorted(values)
    return values[min(len(values) - 1, int(share * len(values)))]


def main():
    cases = collect_cases()
    print(f"Программ, где известны баллы хотя бы за 3 года: {len(cases)}")
    if not cases:
        return
    for weight in WEIGHTS:
        chances.TREND_WEIGHT = weight
        errors = [actual - chances.expected_score(history) for _name, history, actual in cases]
        above_10 = sum(e > 10 for e in errors) / len(errors)
        above_5 = sum(e > 5 for e in errors) / len(errors)
        print(
            f"TREND_WEIGHT={weight}: средняя ошибка {statistics.mean(errors):+.1f}, "
            f"средняя по модулю {statistics.mean(abs(e) for e in errors):.1f}, "
            f"90% ошибок не больше {percentile(errors, 0.9):+.1f}; "
            f"проходной выше ожидаемого больше чем на 5 баллов: {above_5:.0%}, на 10: {above_10:.0%}"
        )


if __name__ == "__main__":
    main()
