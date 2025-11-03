# -*- coding: utf-8 -*-
# common.py
import os
import sys
import inspect
import configparser
from datetime import datetime

from qgis.core import QgsPointXY
from qgis.core import QgsGeometry
from qgis.core import QgsWkbTypes

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtXml import QDomDocument

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtWidgets import QDockWidget

from types import ModuleType, FunctionType
from gc import get_referents

from xmlschema import XMLSchema

# region Спільні змінні
logFile = open(os.path.dirname(__file__) + "/log.md", "w", encoding="utf-8")
logFile.write(f"## Plugin reloaded at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
logFile.flush()

# --- Початок змін: Приховування "фантомних" віджетів при перезавантаженні ---
try:
    from qgis.utils import iface # Імпортуємо iface

    if iface: # Перевіряємо, чи iface доступний
        
        main_window = iface.mainWindow()
        # logFile.write(f"main_window: {str(main_window)}\n\n")
        # logFile.flush()

        if main_window:
            # Шукаємо всі док-віджети, які є екземплярами нашого класу
            for widget in main_window.findChildren(QDockWidget):
                # logFile.write(f"INFO: Перевірка віджета: Title='{widget.windowTitle()}', Visible={widget.isVisible()}\n")
                if widget.windowTitle() == "xml_ua" and widget.isVisible():
                    widget.hide()
                    logFile.write(f"INFO: Приховано старий видимий віджет під час перезавантаження плагіна.\n")
except Exception as e:
    logFile.write(f"WARNING: Не вдалося приховати старий віджет під час перезавантаження: {e}\n")
# --- Кінець змін ---

ini_path = os.path.dirname(__file__) + "/templates/xml_ua.ini"
docs_path = os.path.dirname(__file__) + "/templates/docs_list.ini"
fields_path = os.path.dirname(__file__) + "/templates/field_dicts.ini"
xsd_path = os.path.dirname(__file__) + "/templates/UAXML.xsd"
xml_template = os.path.dirname(__file__) + "/templates/template.xml"
xml_file_name = ""
# endregion

# Custom objects know their class.
# Function objects seem to know way too much, including modules.
# Exclude modules as well.
BLACKLIST = type, ModuleType, FunctionType
def size(obj):
    """sum size of object & members."""
    if isinstance(obj, BLACKLIST):
        raise TypeError('getsize() does not take argument of type: '+ str(type(obj)))
    seen_ids = set()
    size = 0
    objects = [obj]
    while objects:
        need_referents = []
        for obj in objects:
            if not isinstance(obj, BLACKLIST) and id(obj) not in seen_ids:
                seen_ids.add(id(obj))
                size += sys.getsizeof(obj)
                need_referents.append(obj)
        objects = get_referents(*need_referents)
    return size

# region З'єднання
class Connections(QObject):
    """
    Клас для централізованого управління з'єднаннями сигналів і слотів.
    """
    connectionRemoved = pyqtSignal()

    def __init__(self):
        super().__init__()
        # Зберігаємо кортежі (sender, signal_name, slot)
        self.connections = []  

    def connect(self, sender, signal_name, slot):
        """
        Встановлює з'єднання між сигналом та слотом, якщо воно ще не існує.

        Цей метод є централізованим способом керування з'єднаннями в плагіні.
        Він перевіряє, чи з'єднання вже було встановлено раніше, щоб уникнути
        дублювання, яке може призвести до багаторазового виклику слотів.

        Аргументи:
            sender (QObject): Об'єкт, який випромінює сигнал.
            signal_name (str): Назва сигналу у вигляді рядка (наприклад, "clicked").
            slot (function): Метод (слот), який має бути викликаний.

        Викликається:
        - З різних частин плагіна (`__init__.py`, `dockwidget.py`, `tree_view.py` тощо)
          для налаштування взаємодії між компонентами інтерфейсу та логікою.
        """

        # #log_msg(logFile, f"Запит на встановлення з'єднання:\n\tвід {type(sender).__name__}, \n\tна '{signal_name}', \n\tдо {slot.__name__}")

        # Перевіряємо, чи з'єднання вже існує
        if self.connection_established(sender, signal_name, slot):
            #log_msg(logFile, f"З'єднання вже існує: {type(sender).__name__}, '{signal_name}', {slot.__name__}")
            QMessageBox.warning(None, "xml_ua", f"З'єднання вже існує: {type(sender).__name__}, '{signal_name}', {slot.__name__}")
            # Виходимо, якщо з'єднання вже є
            return  

        try:
            # Отримуємо сигнал за назвою від об'єкта sender
            signal = getattr(sender, signal_name)
            # #log_msg(logFile, f"Отримано сигнал: {signal}")

            # Перевіряємо чи signal є сигналом або функцією
            if not isinstance(signal, pyqtSignal) and not callable(signal):
                 raise AttributeError(f"'{signal_name}' is not a signal or callable on '{type(sender).__name__}'")

            signal.connect(slot)
            self.connections.append((sender, signal_name, slot))
            # #log_msg(logFile, f"Встановлено з'єднання: {type(sender).__name__}, '{signal_name}', {slot.__name__}")
        except AttributeError as e:
            log_msg(logFile, f"Помилка встановлення з'єднання: {e}")

    def disconnect(self, sender, signal_name, slot):
        """
        Розриває конкретне з'єднання, яке було раніше встановлено через цей менеджер.
        """
        connection_to_remove = (sender, signal_name, slot)
        
        if connection_to_remove in self.connections:
            try:
                # Отримуємо сигнал за назвою від об'єкта sender
                signal = getattr(sender, signal_name)
                # Розриваємо з'єднання
                signal.disconnect(slot)
                # Видаляємо з'єднання зі списку
                self.connections.remove(connection_to_remove)
                #log_msg(logFile, f"Від'єднано з'єднання: {type(sender).__name__}, '{signal_name}', {slot.__name__}")
            except (TypeError, AttributeError) as e:
                # Логуємо помилку, якщо від'єднання не вдалося
                log_msg(logFile, f"Помилка від'єднання з'єднання: {e}, signal: {signal_name}, slot: {slot}")
        else:
            # Логуємо, якщо з'єднання не було знайдено в нашому списку
            log_msg(logFile, f"З'єднання для від'єднання не знайдено: {type(sender).__name__}, '{signal_name}', {slot.__name__}")



    def disconnect_all(self):
        """
        Від'єднує всі з'єднання, зареєстровані в менеджері.
        """
        for sender, signal_name, slot in self.connections:
            try:
                signal = getattr(sender, signal_name)
                signal.disconnect(slot)
                #log_msg(logFile, f"Від'єднано з'єднання: {type(sender).__name__}, '{signal_name}', {slot.__name__}")
            except TypeError as e:
                log_msg(logFile, f"Помилка від'єднання з'єднання: {e}, signal: {signal_name}, slot: {slot}")
            except AttributeError as e:
                log_msg(logFile, f"Помилка від'єднання з'єднання: {e}, signal: {signal_name}, slot: {slot}")
        self.connections.clear()
        self.connectionRemoved.emit()
        #log_msg(logFile, "Всі з'єднання видалено.")


    def connection_established(self, sender, signal_name, slot) -> bool:
        """
        Перевіряє, чи встановлено з'єднання між вказаним сигналом та слотом.

        :param sender: Об'єкт-відправник сигналу.
        :param signal_name: Ім'я сигналу.
        :param slot: Слот.
        :return: True, якщо з'єднання встановлено, False в іншому випадку.
        """
        for s, sn, sl in self.connections:
            if s is sender and sn == signal_name and sl == slot:
                return True
        return False


    def list_all(self):
        """
        Формує і повертає нумерований список встановлених з'єднань.

        Returns:
            str: Нумерований список встановлених з'єднань у форматі:
                 1. sender, signal_name, slot
                 2. ...
        """
        result = "Список встановлених з'єднань:\n"
        for i, (sender, signal_name, slot) in enumerate(self.connections):
            sender_name = type(sender).__name__
            slot_name = slot.__name__
            result += f"{i + 1}. {sender_name}, '{signal_name}', {slot_name}\n"
        return result


# Створюємо глобальний екземпляр з'єднань
connector = Connections()
# endregion

# region Логи
def get_object_name_from_frame(obj, frame):
    """
        Пошук імені об'єкта у вказаному фреймі стеку.
        frame = inspect.currentframe()

    """
    for name, value in frame.f_locals.items():
        if value is obj:
            return name
    return None


def caller(i: int):
    return inspect.stack()[i].function


def log_msg(logFile, msg=""):
    """ """
    filename = os.path.basename(inspect.stack()[1].frame.f_code.co_filename)
    lineno = sys._getframe().f_back.f_lineno
    #logFile.write(f"\n### [{caller(2)}(): {msg}]({filename}#L{lineno})" )
    logFile.write(f"\n##### [{caller(2)}():]({filename}#L{lineno}) {msg}" )
    logFile.flush()


def get_call_stack(i: int):
    """Отримує стек викликів у вигляді рядка у зворотному порядку."""
    stack = inspect.stack()
    result = ""
    # Ітеруємо по стеку у зворотному порядку, пропускаючи перші два фрейми
    i = 0
    for frame_info in reversed(stack[2:]):
        i += 1
        frame = frame_info.frame
        filename = os.path.basename(frame.f_code.co_filename)
        lineno = frame.f_lineno
        spaces = ' ' * (24 - len(filename))
        func_name = frame.f_code.co_name
        if filename != "<string>":
            result += f"\n [{i}. {filename} {spaces} {func_name}]({filename}#L{lineno})"
        #result += f"[{i}. {filename} {spaces} {func_name}]({filename}#L{lineno})\n"

    return result


def log_calls(logFile: str, msg: str = "") -> None:
    """ Записує повідомлення в лог-файл з інформацією про стек викликів.
    """
    stack_info = get_call_stack(2)
    #log_message = f"\n#### Стек викликів:{stack_info} {msg}"
    log_message = f"{stack_info}→\n{msg} \n"
    #log_message = f"\n## {stack_info}→\n{msg}"
    logFile.write(log_message)
    logFile.flush()




# endregion

def geometry_to_string(geometry):
    """
    Formats coordinates from a QgsGeometry object into a multi-line string.

    Args:
        geometry: A QgsGeometry object.

    Returns:
        A multi-line string representing the coordinates of the geometry,
        formatted as described in the prompt.
        Returns an empty string if the input geometry is empty or invalid.
        Returns an error message if the geometry type is not supported.
    """
    if not isinstance(geometry, QgsGeometry):
        return "Error: Input must be a QgsGeometry object."
        # raise TypeError("Input must be a QgsGeometry object.")

    # if not geometry.isValid():
    #     return "Error: Invalid geometry."

    if geometry.isEmpty():
        return ""

    geometry_type = geometry.wkbType()
    result_string = ""

    if geometry_type == QgsWkbTypes.Point:
        result_string += "point:\n"
        point = geometry.asPoint()
        result_string += f"1. {point.x():.2f}, {point.y():.2f}\n"

    elif geometry_type == QgsWkbTypes.MultiPoint:
        result_string += "multipoint:\n"
        for i, point in enumerate(geometry.asMultiPoint()):
            result_string += f"\t{i + 1}. {point.x():.2f}, {point.y():.2f}\n"

    elif geometry_type == QgsWkbTypes.LineString:
        result_string += "linestring:\n"
        for i, point in enumerate(geometry.asPolyline()):
            result_string += f"{i + 1}. {point.x():.2f}, {point.y():.2f}\n"

    elif geometry_type == QgsWkbTypes.MultiLineString:
        result_string += "multilinestring:\n"
        for j, polyline in enumerate(geometry.asMultiPolyline()):
            result_string += f"linestring {j + 1}:\n"
            for i, point in enumerate(polyline):
                result_string += f"\t{i + 1}. {point.x():.2f}, {point.y():.2f}\n"

    elif geometry_type == QgsWkbTypes.Polygon:
        result_string += "polygon:\n"
        for i, point in enumerate(geometry.asPolygon()[0]):
            result_string += f"{i + 1}. {point.x():.2f}, {point.y():.2f}\n"

    elif geometry_type == QgsWkbTypes.MultiPolygon:
        result_string += "multipolygon:\n"
        for j, polygon in enumerate(geometry.asMultiPolygon()):
            result_string += f"polygon {j + 1}:\n"
            for i, point in enumerate(polygon[0]):
                result_string += f"\t{i + 1}. {point.x():.2f}, {point.y():.2f}\n"
            for k, internal_ring in enumerate(polygon[1:]):
                result_string += f"\tinternal ring {k + 1}:\n"
                for i, point in enumerate(internal_ring):
                    result_string += f"\t\t{i + 1}. {point.x():.2f}, {point.y():.2f}\n"

    else:
        return "Error: Unsupported geometry type."

    return result_string.strip() + "\n"

# region INI
class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr):
        return optionstr

config = CaseSensitiveConfigParser(strict=False)
config.read(ini_path, encoding="utf-8")
config_docs = CaseSensitiveConfigParser(strict=False)
config_docs.read(docs_path, encoding="utf-8")
# endregion
metadata_elements = [
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileDate",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileGUID",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FormatVersion",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverName",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverIdentifier",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/Software",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/SoftwareVersion"]

# region Категорія земель
category_raw = {
    "100" : "Землі сільськогосподарського призначення",
    "200" : "Землі житлової та громадської забудови",
    "300" : "Землі природно-заповідного та іншого природоохоронного призначення",
    "400" : "Землі оздоровчого призначення",
    "500" : "Землі рекреаційного призначення",
    "600" : "Землі історико-культурного призначення",
    "700" : "Землі лісогосподарського призначення",
    "800" : "Землі водного фонду",
    "900" : "Землі промисловості, транспорту, електронних комунікацій, енергетики,оборони та іншого призначення"
}

# Автоматичне формування ValueMap: текст (випадає) → код (записується)
category_map = {
    #f"{label} {code}": code for code, label in category_raw.items()
    f"{code} {label}": code for code, label in category_raw.items()
}
# endregion

# region Цільове призначення (використання) земельної ділянки
purpose_raw = {
    "01.00" : "Категорія: землі сільськогосподарського призначення",
    "01.01" : "Для ведення товарного сільськогосподарського виробництва",
    "01.02" : "Для ведення фермерського господарства",
    "01.03" : "Для ведення особистого селянського господарства",
    "01.04" : "Для ведення підсобного сільського господарства",
    "01.05" : "Для індивідуального садівництва",
    "01.06" : "Для колективного садівництва",
    "01.07" : "Для городництва",
    "01.08" : "Для сінокосіння і випасання худоби",
    "01.09" : "Для дослідних і навчальних цілей",
    "01.10" : "Для пропаганди передового досвіду ведення сільського господарства",
    "01.11" : "Для надання послуг у сільському господарстві",
    "01.12" : "Для розміщення інфраструктури оптових ринків с/г продукції",
    "01.13" : "Для іншого сільськогосподарського призначення",
    "01.14" : "Для 01.01-01.13, 01.15-01.19 та для природно-заповідного фонду",
    "01.15" : "Земельні ділянки запасу під сільськогосподарськими будівлями і дворами",
    "01.16" : "Земельні ділянки під полезахисними лісовими смугами",
    "01.17" : "Земельні ділянки запасу (не надані у власність або користування)",
    "01.18" : "Земельні ділянки загального користування (польові дороги, прогони)",
    "01.19" : "Земельні ділянки під громадськими сіножатями та громадськими пасовищами",
    "02.00" : "Категорія: земельні ділянки житлової і громадської забудови",
    "02.01" : "Для будівництва і обслуговування житлового будинку, госп. будівель і споруд",
    "02.02" : "Для колективного житлового будівництва",
    "02.03" : "Для будівництва і обслуговування багатоквартирного житлового будинку",
    "02.04" : "Для будівництва і обслуговування будівель тимчасового проживання",
    "02.05" : "Для будівництва індивідуальних гаражів",
    "02.06" : "Для колективного гаражного будівництва",
    "02.07" : "Для іншої житлової забудови",
    "02.08" : "Для 02.01-02.07, 02.09-02.12 та природно-заповідного фонду",
    "02.09" : "Паркінги та автостоянки у житловій та громадській забудові",
    "02.10" : "Для багатоквартирного житлового будинку з об’єктами",
    "02.11" : "Земельні ділянки запасу",
    "02.12" : "Внутрішньоквартальні проїзди, пішохідні зони",
    "03.00" : "Категорія: земельні ділянки громадської забудови",
    "03.01" : "Будівлі органів державної влади та органів місцевого самоврядування",
    "03.02" : "Для будівництва та обслуговування будівель закладів освіти",
    "03.03" : "Для будівництва та обслуговування будівель закладів охорони здоров’я",
    "03.04" : "Будівлі громадських та релігійних організацій",
    "03.05" : "Заклади культурно-просвітницького обслуговування",
    "03.06" : "Будівлі екстериторіальних організацій та органів",
    "03.07" : "Для будівництва та обслуговування будівель торгівлі",
    "03.08" : "Об’єкти туристичної інфраструктури та закладів громадського харчування",
    "03.09" : "Для будівництва та обслуговування будівель кредитно-фінансових установ",
    "03.10" : "Адміністративні будинки, офіси",
    "03.11" : "Для будівництва та обслуговування будівель і споруд закладів науки",
    "03.12" : "Будівлі закладів комунального обслуговування",
    "03.13" : "Будівель закладів побутового обслуговування",
    "03.14" : "Для розміщення та постійної діяльності органів і підрозділів ДСНС",
    "03.15" : "Для будівництва та обслуговування інших будівель громадської забудови",
    "03.16" : "Для 03.01-03.15, 03.17-03.20 та природно-заповідного фонду",
    "03.17" : "Заклади з обслуговування відвідувачів об’єктів рекреаційного призначення",
    "03.18" : "Для розміщення та експлуатації установ/місць виконання покарань",
    "03.19" : "Земельні ділянки запасу н/п",
    "03.20" : "Внутрішньоквартальні проїзди, пішохідні зони",
    "04.00" : "Категорія: землі природно-заповідного фонду",
    "04.01" : "Для збереження та використання біосферних заповідників",
    "04.02" : "Для збереження та використання природних заповідників",
    "04.03" : "Для збереження та використання національних природних парків",
    "04.04" : "Для збереження та використання ботанічних садів",
    "04.05" : "Для збереження та використання зоологічних парків",
    "04.06" : "Для збереження та використання дендрологічних парків",
    "04.07" : "Для збереження та використання парків-пам’яток садово-паркового мистецтва",
    "04.08" : "Для збереження та використання заказників",
    "04.09" : "Для збереження та використання заповідних урочищ",
    "04.10" : "Для збереження та використання пам’яток природи",
    "04.11" : "Для збереження та використання регіональних ландшафтних парків",
    "05.00" : "Категорія: Землі іншого природоохоронного призначенняя",
    "05.01" : "Земельні ділянки іншого природоохоронного призначенняя",
    "06.00" : "Категорія: землі оздоровчого призначення",
    "06.01" : "Для будівництва і обслуговування санаторно-оздоровчих закладів",
    "06.02" : "Для розробки родовищ природних лікувальних ресурсів",
    "06.03" : "Для інших оздоровчих цілей",
    "06.04" : "Для цілей підрозділів 06.01-06.03, 06.05 та природно-заповідного фонду",
    "06.05" : "Земельні ділянки запасу",
    "07.00" : "Категорія: землі рекреаційного призначення",
    "07.01" : "Для будівництва та обслуговування об’єктів рекреаційного призначення",
    "07.02" : "Для будівництва та обслуговування об’єктів фізичної культури і спорту",
    "07.03" : "Для індивідуального дачного будівництва",
    "07.04" : "Для колективного дачного будівництва",
    "07.05" : "Для 07.01-07.04, 07.06-07.09 та природно-заповідного фонду",
    "07.06" : "Для збереження, використання та відтворення зелених зон і насаджень",
    "07.07" : "Земельні ділянки запасу",
    "07.08" : "Земельні ділянки загального користування - зелені насадження",
    "07.09" : "Земельні ділянки загального користування відведені під місця поховання",
    "08.00" : "Категорія: землі історико-культурного призначення",
    "08.01" : "Для забезпечення охорони об’єктів культурної спадщини",
    "08.02" : "Для розміщення та обслуговування музейних закладів",
    "08.03" : "Для іншого історико-культурного призначення",
    "08.04" : "Для 08.01-08.03, 08.05 та природно-заповідного фонду",
    "08.05" : "Земельні ділянки запасу",
    "09.00" : "Категорія: землі лісогосподарського призначення",
    "09.01" : "Для ведення лісового господарства і пов’язаних з ним послуг",
    "09.02" : "Для іншого лісогосподарського призначення",
    "09.03" : "Для 09.01-09.02, 09.04-09.05 та природно-заповідного фонду",
    "09.04" : "Для лісогосподарських підприємств, установ, організацій",
    "09.05" : "Земельні ділянки запасу",
    "10.00" : "Категорія: землі водного фонду",
    "10.01" : "Для експлуатації та догляду за водними об’єктами",
    "10.02" : "Для облаштування та догляду за прибережними захисними смугами",
    "10.03" : "Для експлуатації та догляду за смугами відведення",
    "10.04" : "Для гідротехнічних, інших водогосподарських споруд і каналів",
    "10.05" : "Для догляду за береговими смугами водних шляхів",
    "10.06" : "Для сінокосіння",
    "10.07" : "Для рибогосподарських потреб",
    "10.08" : "Для культурно-оздоровчих потреб",
    "10.09" : "Для проведення науково-дослідних робіт",
    "10.10" : "Для гідротехнічних, гідрометричних та лінійних споруд",
    "10.11" : "Для санаторіїв у межах прибережних захисних смуг",
    "10.12" : "Для 10.01-10.11, 10.13-10.16 природно-заповідного фонду",
    "10.13" : "Земельні ділянки запасу",
    "10.14" : "Водні об’єкти загального користування",
    "10.15" : "Земельні ділянки під пляжами",
    "10.16" : "Земельні ділянки під громадськими сіножатями",
    "11.00" : "Категорія: землі промисловості, транспорту, оборони та ін.",
    "11.01" : "Будівелі та споруди підприємствам, що пов’язані з користуванням надрами",
    "11.02" : "Будівелі та споруди підприємств промисловості",
    "11.03" : "Будівелі та споруди будівельних організацій та підприємств",
    "11.04" : "Будівелі та споруди технічної інфраструктури",
    "11.05" : "Для 11.01-11.04, 11.06-11.08 та  природно-заповідного фонду",
    "11.06" : "Земельні ділянки запасу",
    "11.07" : "Зелені насадження спеціального призначення",
    "11.08" : "Для цілей поводження з відходами",
    "12.00" : "Категорія: земельні ділянки транспорту",
    "12.01" : "Будівлі і споруди залізничного транспорту",
    "12.02" : "Будівлі і споруди морського транспорту",
    "12.03" : "Будівлі і споруди річкового транспорту",
    "12.04" : "Будівлі і споруди автомобільного транспорту та дорожнього господарства",
    "12.05" : "Будівлі і споруди авіаційного транспорту",
    "12.06" : "Об’єкти трубопроивідного транспорту",
    "12.07" : "Будівлі і споруди міського електротранспорту",
    "12.08" : "Будівлі і споруди додаткових транспортних послуг",
    "12.09" : "Будівлі і споруди іншого наземного транспорту",
    "12.10" : "Для 12.01-12.09, 12.11-12.13 та природно-заповідного фонду",
    "12.11" : "Для розміщення та експлуатації об’єктів дорожнього сервісу",
    "12.12" : "Земельні ділянки запасу",
    "12.13" : "Земельні ділянки загального користування (вулиці, майдани, проїзди...)",
    "13.00" : "Категорія: землі пошти і електронних комунікацій",
    "13.01" : "Для розміщення та експлуатації об’єктів і споруд електронних комунікацій",
    "13.02" : "Для розміщення та експлуатації будівель та споруд поштового зв’язку",
    "13.03" : "Для розміщення та експлуатації інших технічних засобів",
    "13.04" : "Для 13.01-13.03, 13.05-13.06 та природно-заповідного фонду",
    "13.05" : "ДС спеціального зв’язку та захисту інформації України",
    "13.06" : "Земельні ділянки запасу",
    "14.00" : "Категорія: землі енергетики",
    "14.01" : "Для об’єктів енергогенеруючих підприємств, установ і організацій",
    "14.02" : "Для об’єктів передачі електричної та теплової енергії",
    "14.03" : "Для 14.01-14.02, 14.04-14.06 таприродно-заповідного фонду",
    "14.04" : "Земельні ділянки запасу",
    "14.05" : "Земельні ділянки загального користування зелених насаджень",
    "14.06" : "Земельні ділянки загального користування, для поводження з відходами",
    "15.00" : "Категорія: землі оборони",
    "15.01" : "Для розміщення та постійної діяльності Збройних Сил",
    "15.02" : "Для розміщення та постійної діяльності Національної гвардії",
    "15.03" : "Для Державної прикордонної служби",
    "15.04" : "Для розміщення та постійної діяльності Служби безпеки",
    "15.05" : "Для Державної спеціальної служби транспорту",
    "15.06" : "Для Служби зовнішньої розвідки України",
    "15.07" : "Для інших військових формувань",
    "15.08" : "Для 15.01-15.07, 15.09-15.11 таприродно-заповідного фонду",
    "15.09" : "Для об'єктів МВС",
    "15.10" : "Для об'єктів Національної поліції",
    "15.11" : "Для об'єктів Міноборони",
    "16.00" : "Категорія: Землі запасу",
    "17.00" : "Категорія: Землі резервного фонду",
    "18.00" : "Категорія: Землі загального користування",
    "19.00" : "Категорія: Для 16.00-18.00 та природно-заповідного фонду",
}

# Автоматичне формування ValueMap: код + текст (випадає) → код (записується)
purpose_map = {
    f"{code} {label}": code for code, label in purpose_raw.items()
}

# endregion

# region Код форми власності
code_raw = {
    "100": "Приватна власність",
    "200": "Державна власність",
    "300": "Комунальна власність",
}

code_map = {
    f"{code} {label}": code for code, label in code_raw.items()
}
# endregion

# region Словник форма<->xml для Ділянки
# встановлює відповідність між іменем поля форми
# і шляхом елемента у дереві xml
parcel_field2path_dict = {
    "ParcelID": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/ParcelID",
    "Description": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/Description",
    "AreaSize": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/Area/Size",
    "AreaUnit": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/Area/MeasurementUnit",
    "DeterminationMethod": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelMetricInfo/Area/DeterminationMethod",
    "Region": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/Region",
    "Settlement": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/Settlement",
    "District": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/District",
    # ParcelLocation Складний тип: <Urban></Urban> або <Rural></Rural>
    # а одне поле: В межах/За межами
    # можна реалізувати словником з 2-х значень:
    # "<Urban></Urban>": "У межах населеного пункту"
    # "<Rural></Rural>": "За межами населеного пункту"
    "ParcelLocation": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/District",
    "StreetType": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/ParcelAddress/StreetType",
    "StreetName": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/ParcelAddress/StreetName",
    "Building": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/ParcelAddress/Building",
    "Block": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/ParcelAddress/Block",
    "AdditionalInfo": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/ParcelLocationInfo/AdditionalInfoBlock/AdditionalInfo",
    "Category": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/CategoryPurposeInfo/Category",
    "Purpose": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/CategoryPurposeInfo/Purpose",
    "Use": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/CategoryPurposeInfo/Use",
    "Code": "/InfoPart/CadastralZoneInfo/CadastralQuarters/CadastralQuarterInfo/Parcels/ParcelInfo/OwnershipInfo/Code"
}
# endregion

# region Словник елемент xml->поле форми для DeterminationMethod Ділянки
area_determination_map = {
    "<ExhangeFileCoordinates/>": "За координатами обмінного файлу",
    "<DocExch/>": "Згідно із правовстановлювальним документом",
    "<Calculation><CoordinateSystem><SC42/></CoordinateSystem></Calculation>": "Переобчислення з СК-42 (6 град зона)",
    "<Calculation><CoordinateSystem><SC42_3/></CoordinateSystem></Calculation>": "Переобчислення з СК-42 (3 град зона)",
    "<Calculation><CoordinateSystem><USC2000/></CoordinateSystem></Calculation>": "Переобчислення з УСК2000",
    "<Calculation><CoordinateSystem><WGS84/></CoordinateSystem></Calculation>": "Переобчислення з WGS84",
    "<Calculation><CoordinateSystem><SC63><X/></SC63></CoordinateSystem></Calculation>": "Переобчислення з SC63-X",
    "<Calculation><CoordinateSystem><SC63><C/></SC63></CoordinateSystem></Calculation>": "Переобчислення з SC63-C",
    "<Calculation><CoordinateSystem><SC63><P/></SC63></CoordinateSystem></Calculation>": "Переобчислення з SC63-P",
    "<Calculation><CoordinateSystem><SC63><T/></SC63></CoordinateSystem></Calculation>": "Переобчислення з SC63-T",
    # "Local" — обробляється окремо
}
# endregion

def insert_element_in_order(parent_element, new_element):
    """
    Вставляє new_element в parent_element у правильному порядку,
    визначеному схемою для ParcelInfo.
    """
    # Визначений порядок елементів у ParcelInfo
    order = [
        "ParcelLocationInfo", "CategoryPurposeInfo", "OwnershipInfo",
        "ParcelMetricInfo", "Proprietors", "Leases", "Subleases", "Restrictions",
        "LandsParcel", "AdjacentUnits", "TechnicalDocumentationInfo", "AdditionalInfoBlock"
    ]

    new_tag = new_element.tag
    if new_tag not in order:
        parent_element.append(new_element) # Додаємо в кінець, якщо тег невідомий
        return

    new_element_order_index = order.index(new_tag)

    # Знаходимо позицію для вставки
    insert_before_element = None
    for child in parent_element:
        if child.tag in order and order.index(child.tag) > new_element_order_index:
            insert_before_element = child
            break

    if insert_before_element is not None:
        insert_before_element.addprevious(new_element)
    else:
        parent_element.append(new_element)

def insert_element_in_order(parent_element, new_element):
    """
    Вставляє new_element в parent_element у правильному порядку,
    визначеному схемою.
    """
    # Порядок елементів для ParcelInfo
    order_map = {
        "ParcelInfo": [
            "ParcelLocationInfo", "CategoryPurposeInfo", "OwnershipInfo",
            "ParcelMetricInfo", "Proprietors", "Leases", "Subleases", "Restrictions",
            "LandsParcel", "AdjacentUnits", "TechnicalDocumentationInfo", "AdditionalInfoBlock"
        ]
    }
    order = order_map.get(parent_element.tag)

    if not order or new_element.tag not in order:
        parent_element.append(new_element)  # Додаємо в кінець, якщо порядок не визначено
        return

    new_element_order_index = order.index(new_element.tag)
    for child in reversed(parent_element):
        if child.tag in order and order.index(child.tag) <= new_element_order_index:
            child.addnext(new_element)
            return
    parent_element.insert(0, new_element)
