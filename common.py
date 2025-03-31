
import os
import sys
import inspect
import configparser

from qgis.core import QgsPointXY
from qgis.core import QgsGeometry
from qgis.core import QgsWkbTypes
from qgis.core import QgsApplication

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtXml import QDomDocument

from qgis.PyQt.QtWidgets import QMessageBox

from types import ModuleType, FunctionType
from gc import get_referents

from xmlschema import XMLSchema





logFile = open(os.path.dirname(__file__) + "/xml_ua.md", "w")
ini_path = os.path.dirname(__file__) + "/templates/xml_ua.ini"
docs_path = os.path.dirname(__file__) + "/templates/docs_list.ini"
xsd_path = os.path.dirname(__file__) + "/templates/UAXML.xsd"
xml_template = os.path.dirname(__file__) + "/templates/template.xml"
xml_file_name = ""






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


class Connections(QObject):
    """
    Клас для централізованого управління з'єднаннями сигналів і слотів.
    """
    connectionRemoved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.connections = []  # Зберігаємо кортежі (sender, signal_name, slot)

    def connect(self, sender, signal_name, slot):
        """
        Встановлює з'єднання між сигналом та слотом, якщо воно ще не встановлено.
        """

        if self.connection_established(sender, signal_name, slot):
            log_calls(logFile, f"З'єднання вже існує: {type(sender).__name__}, '{signal_name}', {slot.__name__}")
            QMessageBox.warning(None, "xml_ua", f"З'єднання вже існує: {type(sender).__name__}, '{signal_name}', {slot.__name__}")
            return  # Виходимо, якщо з'єднання вже є

        try:

            signal = getattr(sender, signal_name)


            if not isinstance(signal, pyqtSignal) and not callable(signal):
                 raise AttributeError(f"'{signal_name}' is not a signal or callable on '{type(sender).__name__}'")

            signal.connect(slot)
            self.connections.append((sender, signal_name, slot))

        except AttributeError as e:
            log_calls(logFile, f"Помилка встановлення з'єднання: {e}")


    def disconnect_all(self):
        """
        Від'єднує всі з'єднання, зареєстровані в менеджері.
        """
        for sender, signal_name, slot in self.connections:
            try:
                signal = getattr(sender, signal_name)
                signal.disconnect(slot)
                log_calls(logFile, f"Від'єднано з'єднання: {type(sender).__name__}, '{signal_name}', {slot.__name__}")
            except TypeError as e:
                log_calls(logFile, f"Помилка від'єднання з'єднання: {e}, signal: {signal_name}, slot: {slot}")
            except AttributeError as e:
                log_calls(logFile, f"Помилка від'єднання з'єднання: {e}, signal: {signal_name}, slot: {slot}")
        self.connections.clear()
        self.connectionRemoved.emit()
        log_msg(logFile, "Всі з'єднання видалено.")


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



connector = Connections()


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

    logFile.write(f"\n##### [{caller(2)}():]({filename}#L{lineno}) {msg}" )
    logFile.flush()


def get_call_stack(i: int):
    """Отримує стек викликів у вигляді рядка у зворотному порядку."""
    stack = inspect.stack()
    result = ""

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


    return result


def log_calls(logFile: str, msg: str = "") -> None:
    """ Записує повідомлення в лог-файл з інформацією про стек викликів.
    """
    stack_info = get_call_stack(2)

    log_message = f"{stack_info}→\n{msg} \n"

    logFile.write(log_message)
    logFile.flush()


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



class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr):
        return optionstr

config = CaseSensitiveConfigParser(strict=False)
config.read(ini_path, encoding="utf-8")
config_docs = CaseSensitiveConfigParser(strict=False)
config_docs.read(docs_path, encoding="utf-8")


metadata_elements = [
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileDate",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileGUID",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FormatVersion",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverName",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverIdentifier",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/Software",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/SoftwareVersion"]
