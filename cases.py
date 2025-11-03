# -*- coding: utf-8 -*-
# cases.py

import inspect

# --- Початок виправлення: Monkey-patch для сумісності з Python 3.11+ ---
# У нових версіях Python функцію `inspect.getargspec` було видалено,
# що призводить до помилки у старих версіях бібліотеки pymorphy2.
# Цей код додає застарілу функцію назад, перенаправляючи її на нову.
# --- Початок виправлення: ValueError: too many values to unpack ---
# Стара функція getargspec повертала 4 значення, а нова getfullargspec - 7.
# Створюємо обгортку, яка повертає лише перші 4 значення, як очікує pymorphy2.
if not hasattr(inspect, 'getargspec'): # noqa
    def getargspec_replacement(func):
        full_arg_spec = inspect.getfullargspec(func)
        return (full_arg_spec.args, full_arg_spec.varargs, full_arg_spec.varkw, full_arg_spec.defaults)
    inspect.getargspec = getargspec_replacement
# --- Кінець виправлення ---

try:
    import pymorphy2
    # Ініціалізація аналізатора для української мови
    morph = pymorphy2.MorphAnalyzer(lang='uk')
    PYMORPHY2_AVAILABLE = True
except ImportError:
    PYMORPHY2_AVAILABLE = False
    # Функція-заглушка, якщо бібліотека не встановлена
    def log_pymorphy_error():
        from .common import log_msg, logFile
        log_msg(logFile, "ПОМИЛКА: Бібліотека 'pymorphy2' або словники 'pymorphy2-dicts-uk' не встановлені. Функції відмінювання не працюватимуть.")
        log_msg(logFile, "Виконайте 'pip install pymorphy2 pymorphy2-dicts-uk' у вашому середовищі Python для QGIS.")
    log_pymorphy_error()


def bornPIB(full_name_str: str) -> str:
    """
    Конвертує ПІБ (прізвище, ім'я, по-батькові) з називного відмінка у родовий.
    Наприклад: "Іванов Іван Іванович" -> "Іванова Івана Івановича"

    Args:
        full_name_str (str): Рядок, що містить ПІБ у називному відмінку.

    Returns:
        str: Рядок з ПІБ у родовому відмінку.
    """
    if not PYMORPHY2_AVAILABLE or not full_name_str:
        return full_name_str

    parts = full_name_str.split()
    genitive_parts = []

    for i, part in enumerate(parts):
        # pymorphy2 краще працює з малими літерами
        p = morph.parse(part.lower())[0]
        
        # Визначаємо стать за іменем або по-батькові для кращого відмінювання прізвища
        gender = None
        if len(parts) > 1 and i == 0: # Якщо це прізвище
            if 'Patr' in morph.parse(parts[-1])[0].tag: # По-батькові
                gender = morph.parse(parts[-1])[0].tag.gender
            elif 'Name' in morph.parse(parts[1])[0].tag: # Ім'я
                gender = morph.parse(parts[1])[0].tag.gender

        # Відмінюємо у родовий відмінок ('gent')
        inflected_word = p.inflect({'gent', gender} if gender else {'gent'})
        
        if inflected_word:
            # Зберігаємо велику літеру
            genitive_parts.append(inflected_word.word.capitalize())
        else:
            # Якщо відмінювання не вдалося, повертаємо оригінальне слово
            genitive_parts.append(part)

    return " ".join(genitive_parts)

def bornRada(rada_name_str: str) -> str:
    """
    Конвертує назву сільської ради або територіальної громади з називного відмінка у родовий.
    Наприклад: "Іванівська сільська рада" -> "Іванівської сільської ради"

    Args:
        rada_name_str (str): Рядок з назвою у називному відмінку.

    Returns:
        str: Рядок з назвою у родовому відмінку.
    """
    if not PYMORPHY2_AVAILABLE or not rada_name_str:
        return rada_name_str

    parts = rada_name_str.split()
    genitive_parts = [p.inflect({'gent'}).word if p.inflect({'gent'}) else p for p in parts]
    
    # Зберігаємо велику літеру для першого слова
    if genitive_parts:
        genitive_parts[0] = genitive_parts[0].capitalize()

    return " ".join(genitive_parts)

def to_genitive(phrase: str) -> str:
    """
    Конвертує фразу з називного відмінка у родовий.
    Наприклад: "Іванівська сільська рада" -> "Іванівської сільської ради"

    Args:
        phrase (str): Рядок з фразою у називному відмінку.

    Returns:
        str: Рядок з фразою у родовому відмінку.
    """
    if not PYMORPHY2_AVAILABLE or not phrase:
        return phrase

    words = phrase.split()
    genitive_words = []
    for word in words:
        parsed_word = morph.parse(word)[0]
        inflected = parsed_word.inflect({'gent'})
        genitive_words.append(inflected.word.capitalize() if word.istitle() else inflected.word if inflected else word)

    return " ".join(genitive_words)