
![index.md](images/icon.png)


### Інсталяція QGIS

#### Встановити останню довгртермінову версію QGIS 3.40 з офіційного сайту www.qgis.org. 

Дана версія 0.9 плагіна створена на базі QT5, тому доцільно вибрати офлайн інсталятор довготермінової (Long Term) версії QGIS 3.40 для Вашої операційної системи. Станом на березень 2025 року версія з QT6 є експериментальною.

#### Налаштування системних змінних для QGIS 3.4X.X 

#### Ручне налаштування системних змінних 

- У каталозі, де встановлена QGIS (C:\Program Files\QGIS 3.4X.X\) повинні бути папки 

    - apps\qgis-ltr\bin
    
    - apps\Python312
    
    - apps\Python312\Scripts

- Алгоритм створення/редагування системних змінних:
    - По правому кліку на значку «Цей ПК» («Мій комп'ютер»)
    - Вибрати пункт «Властивості» з контекстного меню 
    - Використовуючи прокрутку у правій частині вікна «Налаштування», у розділі «Пов'язані налаштування», вибрати пункт «Додаткові налаштування системи»  
    - У вікні «Властивості системи», на вкладці «Додатково» натиснути кнопку «Змінні оточення»  
    - У таблиці «Системні змінні» з допомогою кнопок «Створити...» і/або «Редагувати...» наступні системні змінні:

<table>
    <tr>
        <th>Змінна</th>
        <th>Значення (залежить від шляху установки і версії QGIS)</th>
    </tr>
    <tr>
        <td>PATH</td>
        <td>D:\Program Files\QGIS 3.40.4\apps\qgis-ltr\bin;D:\Program Files\QGIS 3.40.4\apps\Python312\Scripts;D:\Program Files\QGIS 3.40.4\apps\Python312</td>
    </tr>
    <tr>
        <td>PYTHONPATH</td>
        <td>D:\Program Files\QGIS 3.40.4\apps\qgis-ltr\python;D:\Program Files\QGIS 3.40.4\apps\Python312;C:\Program Files\QGIS 3.40.4\apps\Python312\Lib\site-packages</td>
    </tr>
    <tr>
        <td>QGIS_PREFIX_PATH</td>
        <td>D:\Program Files\QGIS 3.40.4\apps\qgis-ltr</td>
    </tr>
    <tr>
        <td>GDAL_DATA</td>
        <td>D:\Program Files\QGIS 3.40.4\apps\qgis-ltr\share\gdal</td>
    </tr>
    <tr>
        <td>QT_PLUGIN_PATH</td>
        <td>D:\Program Files\QGIS 3.40.4\apps\qgis-ltr\qtplugins</td>
    </tr>
</table>
    



#### Налаштування системних змінних з допомогою скрипта

З [папки плагіна](install_plugin.md) скопіювати файл set_system_vars.bat у папку де встановлений QGIS і запустити його на виконання з правами адміністратора.

