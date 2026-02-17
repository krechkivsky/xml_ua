

import re

from .common import log_msg, logFile


def validate_element(element, path):
    """
    Перевіряє валідність конкретного елемента.
    Повертає True, якщо валідний, інакше False.
    """
    if element is None:
        return True  # Нема чого валідувати

    if path.endswith("/InfoLandWork/Executor/CompanyName"):
        text = element.text
        if not text or not text.strip():
            return False  # Поле не повинно бути порожнім

        first_char = text.strip()[0]

        if not first_char.isupper():
            return False

    elif path.endswith("/ServiceInfo/ReceiverName"):
        text = element.text
        if not text or not text.strip():
            return False  # Поле не повинно бути порожнім

        first_char = text.strip()[0]
        if not re.match(r'[А-ЯҐЄІЇ]', first_char):
            return False

    return True


def compute_parcel_area(tree):
    """
    Обчислює площу ділянки на основі координат її вузлів.

    Args:
        tree: Об'єкт lxml.etree._ElementTree.

    Returns:
        float: Обчислена площа в квадратних метрах, або 0.0 у разі помилки.
    """
    if tree is None:

        return 0.0

    try:

        return 0.0  # Повертаємо заглушку

    except Exception as e:

        return 0.0
