# -*- coding: utf-8 -*-
# validators.py
import re

from .common import log_msg, logFile

def validate_element(element, path):
    """
    Перевіряє валідність конкретного елемента.
    Повертає True, якщо валідний, інакше False.
    """
    if element is None:
        return True # Нема чого валідувати

    # --- Тестовий випадок для CompanyName ---
    if path.endswith("/InfoLandWork/Executor/CompanyName"):
        text = element.text
        if not text or not text.strip():
            return False  # Поле не повинно бути порожнім
        
        first_char = text.strip()[0]
        # Перевірка, чи перший символ є великою літерою (кирилиця або латиниця)
        if not first_char.isupper():
            return False

    # --- Новий випадок для ReceiverName ---
    elif path.endswith("/ServiceInfo/ReceiverName"):
        text = element.text
        if not text or not text.strip():
            return False  # Поле не повинно бути порожнім

        # Перевірка, чи перший символ є великою літерою кириличного алфавіту
        first_char = text.strip()[0]
        if not re.match(r'[А-ЯҐЄІЇ]', first_char):
            return False

    # Додайте інші правила валідації тут...

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
        log_msg(logFile, "Помилка: дерево XML не передано для обчислення площі.")
        return 0.0

    try:
        # Ця функція потребує реалізації _get_ordered_boundary_points
        # points = _get_ordered_boundary_points(tree)
        # ... логіка обчислення ...
        return 0.0 # Повертаємо заглушку

    except Exception as e:
        log_msg(logFile, f"Помилка під час обчислення площі з геометрії: {e}")
        return 0.0