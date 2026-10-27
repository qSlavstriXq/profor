# Единственное место в проекте, где вызывается языковая модель.
# Чтобы сменить модель или провайдера, достаточно поменять настройки QWEN_* в .env,
# а если у нового провайдера другой формат API, то только этот файл.

import json
import logging

from django.conf import settings
from pydantic import ValidationError

logger = logging.getLogger("llm")


class LLMError(Exception):
    """Модель не ответила или ответила не по схеме."""


class LLMNotConfigured(LLMError):
    """Не задан QWEN_API_KEY в .env."""


def is_configured():
    return bool(settings.QWEN_API_KEY)


def _make_client():
    # Импорт внутри функции: библиотека нужна, только когда реально зовём модель
    from openai import OpenAI

    return OpenAI(
        api_key=settings.QWEN_API_KEY,
        base_url=settings.QWEN_BASE_URL,
        timeout=settings.QWEN_TIMEOUT,
        max_retries=1,
    )


def ask_json(system_prompt, data, schema, client=None):
    """Отправляет модели инструкцию и данные, возвращает ответ, проверенный схемой.

    system_prompt: инструкция для модели (текст)
    data: словарь с данными для модели, уйдёт как JSON
    schema: класс Pydantic, которому должен соответствовать ответ
    client: подменяется в тестах, чтобы не ходить в интернет

    Если ответ не прошёл проверку, просим модель исправиться ещё один раз.
    """
    if client is None:
        if not is_configured():
            raise LLMNotConfigured("Не задан QWEN_API_KEY")
        client = _make_client()

    # ensure_ascii=False: русские буквы идут как есть, а не А...,
    # так запрос короче и тратит меньше токенов
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False, separators=(",", ":"))},
    ]

    for attempt in (1, 2):
        content = _call(client, messages)
        try:
            return schema.model_validate_json(content)
        except ValidationError as error:
            logger.warning("Ответ модели не прошёл проверку (попытка %s): %s", attempt, error)
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    "Ответ не соответствует схеме. Исправь и верни только JSON. Ошибки: "
                    + str(error)
                )},
            ]
    raise LLMError("Модель дважды вернула ответ не по схеме")


def _call(client, messages):
    try:
        response = client.chat.completions.create(
            model=settings.QWEN_MODEL,
            messages=messages,
            response_format={"type": "json_object"},  # просим строго JSON
            max_tokens=settings.QWEN_MAX_TOKENS,
            temperature=0.3,  # меньше фантазии, ответы стабильнее
        )
    except Exception as error:  # сеть, неверный ключ, превышен лимит и т. п.
        raise LLMError(f"Ошибка обращения к модели: {error}") from error

    usage = getattr(response, "usage", None)
    if usage is not None:
        # Расход токенов в журнал: по нему будем сравнивать модели по цене
        logger.info(
            "Модель %s: токенов в запросе %s, в ответе %s",
            settings.QWEN_MODEL, usage.prompt_tokens, usage.completion_tokens,
        )
    return response.choices[0].message.content or ""
