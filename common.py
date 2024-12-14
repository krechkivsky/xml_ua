import os, sys, inspect

logFile = open(os.path.dirname(__file__) + "/xml_ua.log", "w")
xsd_path = os.path.dirname(__file__) + "/templates/UAXML.xsd"

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
    "AdjacentUnits"
]

metadata_elements = [
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileDate",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FileID/FileGUID",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/FormatVersion",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverName",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/ReceiverIdentifier",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/Software",
    "UkrainianCadastralExchangeFile/AdditionalPart/ServiceInfo/SoftwareVersion",
]


'''
# Для того, щоб лог-функції правильно відображали назву модуля, їх
# потрібно визначати у кожному модулі

def caller():
    return inspect.stack()[2].function

def logging(logFile, msg=""):
    logFile.write(f"{sys._getframe().f_back.f_lineno}: {caller()} {msg}\n")
    logFile.flush()

def log_dict(logFile, dict, name: str = ""):
    msg = f"{name}:"
    for key, value in dict.items():
        msg += '\n\t' + f"{key}: {value}"
    logFile.write(f"{sys._getframe().f_back.f_lineno}: {caller()}: {msg}\n")
    logFile.flush()
    
def log_attributes(object):
    for attr, value in vars(object).items():
        logging(logFile, f"{attr}: {value}")
        
'''

# import sys, inspect
    # for frame_info in inspect.stack(): common.logFile.write("\t" + f" stack: {os.path.basename(frame_info.filename)}: {frame_info.lineno}: {frame_info.function}" + "\n")

def get_xml_file_path():
    
    logging(common.logFile)
    options = QFileDialog.Options()
    options |= QFileDialog.ReadOnly  # Опція лише для читання (необов’язкова)
    
    file_path, _ = QFileDialog.getOpenFileName(None,"Вибір файлу","","Файли XML (*.xml)",options=options)
    
    return file_path
