import inspect
import re


if not hasattr(inspect, 'getargspec'):  # noqa
    def getargspec_replacement(func):
        full_arg_spec = inspect.getfullargspec(func)
        return (full_arg_spec.args, full_arg_spec.varargs, full_arg_spec.varkw, full_arg_spec.defaults)
    inspect.getargspec = getargspec_replacement


try:
    import pymorphy2

    morph = pymorphy2.MorphAnalyzer(lang='uk')
    PYMORPHY2_AVAILABLE = True
except ImportError:
    PYMORPHY2_AVAILABLE = False

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

        p = morph.parse(part.lower())[0]

        gender = None
        if len(parts) > 1 and i == 0:  # Якщо це прізвище
            if 'Patr' in morph.parse(parts[-1])[0].tag:  # По-батькові
                gender = morph.parse(parts[-1])[0].tag.gender
            elif 'Name' in morph.parse(parts[1])[0].tag:  # Ім'я
                gender = morph.parse(parts[1])[0].tag.gender

        inflected_word = p.inflect({'gent', gender} if gender else {'gent'})

        if inflected_word:

            genitive_parts.append(inflected_word.word.capitalize())
        else:

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
    genitive_parts = [p.inflect({'gent'}).word if p.inflect(
        {'gent'}) else p for p in parts]

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
    if not phrase:
        return phrase

    def _fix_iv(word: str) -> str:
        """
        Fix genitive singular for Ukrainian place names ending with '-ів'/'-їв'.
        Examples: Турів->Турова, Яворів->Яворова, Миколаїв->Миколаєва, Харків->Харкова, Жидачів->Жидачева.
        """
        if not word or not re.fullmatch(r"[A-Za-zА-Яа-яІіЇїЄєҐґ'-]+", word):
            return word
        w = word.strip()
        low = w.lower()

        if low.endswith("аїв"):
            base = w[:-3]
            suff = "аєва"
        elif low.endswith("їв"):
            base = w[:-2]
            suff = "єва"
        elif low.endswith("чів"):
            base = w[:-2]
            suff = "ева"
        elif low.endswith("ів"):
            base = w[:-2]
            suff = "ова"
        else:
            return word

        out = f"{base}{suff}"
        if w[:1].isupper():
            return out[:1].upper() + out[1:]
        return out


    if not PYMORPHY2_AVAILABLE:
        return " ".join(_fix_iv(w) for w in phrase.split())

    words = phrase.split()
    genitive_words = []
    for word in words:

        if word.lower().endswith(("ів", "їв")):
            genitive_words.append(_fix_iv(word))
            continue

        parsed_word = morph.parse(word)[0]
        inflected = parsed_word.inflect({'gent'})
        if inflected:
            gen = inflected.word.capitalize() if word.istitle() else inflected.word
            genitive_words.append(_fix_iv(gen))
        else:
            genitive_words.append(_fix_iv(word))

    return " ".join(genitive_words)
