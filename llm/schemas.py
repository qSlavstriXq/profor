# Схема ответа модели. Pydantic проверяет, что модель вернула все поля
# нужных типов. Если нет, ответ не принимается.

from typing import Literal

from pydantic import BaseModel, Field


class TestAnalysis(BaseModel):
    """Разбор одного пройденного теста."""

    test_code: str
    summary: str = Field(min_length=1)


class Direction(BaseModel):
    """Возможное направление поступления."""

    title: str = Field(min_length=1)
    why: str = Field(min_length=1)
    professions: list[str] = []
    # Только id из списка программ, который мы передали модели. Сверяется в strategy.py
    program_ids: list[int] = []


class NextStep(BaseModel):
    """Что ещё пройти: курс или тест."""

    kind: Literal["course", "test"]
    title: str = Field(min_length=1)
    why: str = Field(min_length=1)
    for_profession: str = ""
    # Если это тест с нашего сайта, его код. Сверяется в strategy.py
    test_code: str | None = None


class Strategy(BaseModel):
    summary: str = Field(min_length=1)
    test_analysis: list[TestAnalysis]
    directions: list[Direction] = Field(min_length=1, max_length=5)
    next_steps: list[NextStep] = Field(max_length=6)
