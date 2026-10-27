# Шаблонные фильтры для русского языка.
# Подключение в шаблоне: {% load russian %}

from django import template

register = template.Library()


def plural_form(number, forms):
    """Выбирает форму слова для числа: 1 балл, 2 балла, 5 баллов.

    forms: три формы через запятую, «один, два, пять»: "балл,балла,баллов".
    """
    one, few, many = forms.split(",")
    n = abs(int(round(number)))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


@register.filter
def plural(number, forms):
    """{{ 5|plural:"балл,балла,баллов" }} -> «5 баллов»."""
    return f"{abs(int(round(number)))} {plural_form(number, forms)}"
