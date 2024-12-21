# -*- coding: utf-8 -*-
import os
import sys
import inspect
import configparser
from qgis.PyQt.QtCore import Qt


logFile = open(os.path.dirname(__file__) + "/xml_ua.log", "w")
ini_path = os.path.dirname(__file__) + "/xml_ua.ini"
xsd_path = os.path.dirname(__file__) + "/templates/UAXML.xsd"



def get_xml_file_path():
    
    common.log_var(common.logFile)
    options = QFileDialog.Options()
    options |= QFileDialog.ReadOnly  # Опція лише для читання (необов’язкова)
    
    file_path, _ = QFileDialog.getOpenFileName(None,"Вибір файлу","","Файли XML (*.xml)",options=options)
    
    return file_path


def save_tree_view_to_xml(tree_view, xmlPath):

    common.log_var(common.logFile)
    doc = QDomDocument()
    
    model = tree_view.model()
    root_item = model.item(0)
    
    def add_elements_to_dom(parent_dom_element, item):
        common.log_var(common.logFile)
        for row in range(item.rowCount()):
            child_item = item.child(row, 0)
            value_item = item.child(row, 1)

            element = doc.createElement(child_item.text())
            if value_item and value_item.text():
                element.appendChild(doc.createTextNode(value_item.text()))

            parent_dom_element.appendChild(element)

            add_elements_to_dom(element, child_item)

    # Створюємо кореневий елемент та додаємо до документа
    root_element = doc.createElement(root_item.text())
    doc.appendChild(root_element)
    add_elements_to_dom(root_element, root_item)

    # Збереження документа у файл
    with open(xmlPath, 'w', encoding='utf-8') as file:
        file.write('<?xml version="1.0" encoding="utf-8"?>\n  ' + doc.toString(2))  # 4 — це відступ для читабельності

    common.log_var(common.logFile, f"Зміни збережено у {xmlPath}")


def layer_in_project(layer_name):


    common.log_var(common.logFile)
    layers = QgsProject.instance().mapLayers().values()
    
    for layer in layers:
        if layer.name() == layer_name:
            return layer
    return None


def get_points_xml(xmlPath):
    
    global pointsData
    global XYs
    
    common.log_var(common.logFile)
    tree = ET.parse(xmlPath)
    root = tree.getroot()
    pointsData = []
    XYs = []
    
    for point in root.findall(".//PointInfo/Point"):
        uid = point.find("UIDP").text if point.find("UIDP") is not None else None
        pn = point.find("PN").text if point.find("PN") is not None else None
        x = point.find("X").text if point.find("X") is not None else None
        y = point.find("Y").text if point.find("Y") is not None else None
        h = point.find("H").text if point.find("H") is not None else None
        mx = point.find("MX").text if point.find("MX") is not None else None
        my = point.find("MY").text if point.find("MY") is not None else None
        mh = point.find("MH").text if point.find("MH") is not None else None
        description = point.find("Description").text if point.find("Description") is not None else None

        pointsData.append({
            "uid": uid,
            "pn": pn,
            "x": x,
            "y": y,
            "h": h,
            "mx": mx,
            "my": my,
            "mh": mh,
            "description": description
        })
        
        XYs.append({
            "uid": uid,
            "x": x,
            "y": y,
        })
    
    
    return


def add_points_to_qgis(xmlPath):
    
    global pointsData
    global treeViewKadNum
    
    common.log_var(common.logFile, " treeViewKadNum = " + treeViewKadNum)
    layer_name = treeViewKadNum + "_точки"
    common.log_var(logFile, " layer_name = " + layer_name)
    layer = common.layer_in_project(layer_name)
    common.log_var(logFile, "crs=" + crsEpsg)
   
    if not layer: layer = QgsVectorLayer("Point?crs=" + crsEpsg, layer_name, "memory")
    
    provider = layer.dataProvider()
    
    provider.addAttributes([
    QgsField("UIDP", QVariant.String),
    QgsField("PN", QVariant.String),
    #QgsField("X", QVariant.String),
    #QgsField("Y", QVariant.String),
    QgsField("H", QVariant.String),
    QgsField("MX", QVariant.String),
    QgsField("MY", QVariant.String),
    QgsField("MH", QVariant.String),
    QgsField("Description", QVariant.String)])
    layer.updateFields()
    
    for point_data in pointsData:
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(point_data["y"]), float(point_data["x"]))))
        #common.log_var(logFile, " point_data['y'] = " + point_data["y"])
            
        feature.setAttributes([
            point_data["uid"],
            point_data["pn"],
            #point_data["x"],
            #point_data["y"],
            point_data["h"],
            point_data["mx"],
            point_data["my"],
            point_data["mh"],
            point_data["description"]])
        provider.addFeature(feature)

    #common.log_var(logFile, " pointsData = " + str(pointsData))

    # Додавання шару до проекту QGIS
    QgsProject.instance().addMapLayer(layer)
    
    return


def get_object_name(obj):
    
    """Повертає ім'я об'єкта або None, якщо не знайдено."""
    for name, value in globals().items():
        if value is obj:
            return name
    for name, value in locals().items():
        if value is obj:
            return name
    return None


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
    
    filename = os.path.basename(inspect.stack()[1].frame.f_code.co_filename)
    lineno = sys._getframe().f_back.f_lineno
    spaces1 = " " * (4 - len(str(lineno)))
    spaces2 = " " * (20 - len(filename))
    # logFile.write(f"/.{filename}:{sys._getframe().f_back.f_lineno} {caller(2)}(): {msg}\n")
    logFile.write(f"/.{filename}{spaces2}{spaces1}{lineno}  {caller(2)}(): {msg}\n")
    logFile.flush()


def get_call_stack(i:int):
    
    """Отримує стек викликів у вигляді рядка у зворотному порядку."""
    stack = inspect.stack()
    result = ""
    # Ітеруємо по стеку у зворотному порядку, пропускаючи перші два фрейми
    for frame_info in reversed(stack[2:]):
        frame = frame_info.frame
        filename = os.path.basename(frame.f_code.co_filename)
        lineno = frame.f_lineno
        spaces = ' ' * (30 - len(filename) - len(str(lineno)))
        func_name = frame.f_code.co_name
        result += f"\n    ./{filename}:{lineno}{spaces}{func_name}()"
        
    return result


def log_stack(logFile, msg=""):
    
    """Записує повідомлення в лог-файл з інформацією про стек викликів."""
    filename = os.path.basename(__file__)
    lineno = sys._getframe().f_back.f_lineno
    caller_func_name = sys._getframe().f_back.f_code.co_name
    stack_info = get_call_stack(2)
    log_message = f"Log stack:{stack_info}:\n\t\t{msg}\n"
    logFile.write(log_message)
    logFile.flush()


def log_var(logFile, msg=""):
    
    """Записує повідомлення в лог-файл з інформацією про стек викликів."""
    filename = os.path.basename(__file__)
    lineno = sys._getframe().f_back.f_lineno
    caller_func_name = sys._getframe().f_back.f_code.co_name
    stack_info = get_call_stack(2)
    log_message = f"Debug variable:{stack_info}:\n\t\t{msg}\n"
    logFile.write(log_message)
    logFile.flush()


def log_dict(logFile, dictionary, msg=""):
    """Записує словник в лог-файл з інформацією про стек викликів."""
    filename = os.path.basename(__file__)
    lineno = sys._getframe().f_back.f_lineno
    caller_func_name = sys._getframe().f_back.f_code.co_name
    stack_info = get_call_stack(2)
    dict_str = ""
    for key, value in dictionary.items():
        dict_str += f"\t\t{key}: {value}\n"
    log_message = f"Debug dict:{stack_info}\n\t{msg}\n{dict_str}"
    logFile.write(log_message)
    logFile.flush()


def log_object(logFile, obj, frame, search = ""):
    
    """ 
        Записує об'єкт в лог-файл з інформацією про стек викликів.
        Особливості виклику:
        1. В модулі повинен імпортуватись inspect.
        2. Перед викликом необхідно встановити контекст об'єкта:
            frame = inspect.currentframe()        
            common.log_object(common.logFile, object, frame, 'property')

    
    """
    filename = os.path.basename(__file__)
    lineno = sys._getframe().f_back.f_lineno
    caller_func_name = sys._getframe().f_back.f_code.co_name
    stack_info = get_call_stack(2)
    obj_str = ""
    for attr_name in dir(obj):
        if not attr_name.startswith("__"):  # Ігноруємо магічні атрибути
            try:
                attr_value = getattr(obj, attr_name)
                if search:
                    if search == str(attr_name):
                        obj_str += f"\t\t{attr_name}: {attr_value}\n"
                else:
                    obj_str += f"\t\t{attr_name}: {attr_value}\n"
            except Exception as e:  # Обробка можливих помилок при доступі до атрибутів
                obj_str += f"\t\t{attr_name}: <Помилка отримання значення: {e}>\n"
    # log_message = f"Debug object: <{filename}:{lineno}> {caller_func_name}():\n{stack_info}{msg}\n{obj_str}"
    log_message = f"Debug object:{stack_info} {get_object_name_from_frame(obj, frame)}:\n{obj_str}"
    logFile.write(log_message)
    logFile.flush()


def log_model(logFile, model):

    if model is None:
        
        filename = os.path.basename(__file__)
        lineno = sys._getframe().f_back.f_lineno
        caller_func_name = sys._getframe().f_back.f_code.co_name
        stack_info = get_call_stack(2)
        # log_message = f"Debug : {caller_func_name}():\n{stack_info}\t\t{msg}\n"
        log_message = f"Debug model:{stack_info}:\n\t\t{table_view}: Модель не встановлена\n"
        logFile.write(log_message)
        logFile.flush()
        return
        
    stack_info = get_call_stack(2)

    logFile.write(f"Debug model:{stack_info}:\n\tІнформація про модель:\n")
    logFile.write(f"\t\tТип моделі: {type(model)}\n")
    logFile.write(f"\t\tКількість рядків: {model.rowCount()}\n")
    logFile.write(f"\t\tКількість стовпців: {model.columnCount()}\n")

    # Отримання заголовків (якщо модель їх підтримує)
    try:
        for col in range(model.columnCount()):
            header_data = model.headerData(col, Qt.Orientation.Horizontal)
            logFile.write(f"\tЗаголовок стовпця {col}: {header_data}\n")
    except AttributeError:
        logFile.write("Модель не підтримує заголовки")

    # Отримання даних з кількох комірок для прикладу
    try:
        for row in range(min(3, model.rowCount())): # Виводимо дані максимум з 3 рядків
            for col in range(min(3, model.columnCount())): # Виводимо дані максимум з 3 стовпців
                index = model.index(row, col)
                data = model.data(index)
                logFile.write(f"\t\tДані в комірці ({row}, {col}): {data}\n")
    except IndexError:
        logFile.write("Вихід за межі індексу моделі\n")


def log_object_model(logFile, table_view):

    model = table_view.model()
    if model is None:
        
        filename = os.path.basename(__file__)
        lineno = sys._getframe().f_back.f_lineno
        caller_func_name = sys._getframe().f_back.f_code.co_name
        stack_info = get_call_stack()
        # log_message = f"Debug : {caller_func_name}():\n{stack_info}\t\t{msg}\n"
        log_message = f"Debug model:{stack_info}:\n\t\t{table_view}: Модель не встановлена\n"
        logFile.write(log_message)
        logFile.flush()
        return
        
    stack_info = get_call_stack()

    logFile.write(f"Debug model:{stack_info}:\n\tІнформація про модель:\n")
    logFile.write(f"\t\tТип моделі: {type(model)}\n")
    logFile.write(f"\t\tКількість рядків: {model.rowCount()}\n")
    logFile.write(f"\t\tКількість стовпців: {model.columnCount()}\n")

    # Отримання заголовків (якщо модель їх підтримує)
    try:
        for col in range(model.columnCount()):
            header_data = model.headerData(col, Qt.Orientation.Horizontal)
            logFile.write(f"\tЗаголовок стовпця {col}: {header_data}\n")
    except AttributeError:
        logFile.write("Модель не підтримує заголовки")

    # Отримання даних з кількох комірок для прикладу
    try:
        for row in range(min(3, model.rowCount())): # Виводимо дані максимум з 3 рядків
            for col in range(min(3, model.columnCount())): # Виводимо дані максимум з 3 стовпців
                index = model.index(row, col)
                data = model.data(index)
                logFile.write(f"\t\tДані в комірці ({row}, {col}): {data}\n")
    except IndexError:
        logFile.write("Вихід за межі індексу моделі\n")


def log_xml(logFile, element, filter_tag, level=0):
    # Перевіряємо, чи потрібно обробляти цей вузол
    if filter_tag and element.tag != filter_tag:
        logFile.write("\n")
        return

    # Друк тегу
    logFile.write("\n")
    indent = '  ' * level
    logFile.write(f"{indent}{element.tag}")

    # Друк атрибутів
    for attribute, value in element.attrib.items():
        logFile.write(f" {attribute}->{value}")

    # Обробка дочірніх елементів
    for child in element:
        log_xml(logFile, child, filter_tag, level + 1)


class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr):
        return optionstr

config = CaseSensitiveConfigParser()
config.read(ini_path, encoding="utf-8")

elements_to_expand = [
    "UkrainianCadastralExchangeFile",
    "InfoPart",
    "CadastralZoneInfo",
    "CadastralQuarters",
    "CadastralQuarterInfo",
    "Parcels",
    "ParcelInfo",
    "ParcelMetricInfo",
    "LandsParcel",
    "AdjacentUnits"]


metadata_elements = [
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileDate",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileGUID",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FormatVersion",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverName",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverIdentifier",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/Software",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/SoftwareVersion"]

