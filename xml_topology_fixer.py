

from enum import Enum
import os
import shutil
from datetime import datetime
from lxml import etree
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import Qgis
from qgis.utils import iface


class XmlTopologyFixer:
    """
    A class to detect and fix topology issues in Ukrainian Cadastral XML files.

    This class provides functionality to:
    1. Identify unused points and polylines.
    2. Prompt the user for confirmation to fix the issues.
    3. Create a backup of the original file.
    4. Remove unused elements and sort points/polylines.
    5. Overwrite the original file with the corrected version.
    """

    class FixResult(Enum):
        """Represents the user's choice or the outcome of the check."""
        FILE_FIXED_AND_SAVED = 1
        OPEN_AS_IS = 2
        NO_ISSUES_FOUND = 3
        OPERATION_CANCELLED = 4

    def __init__(self, file_path, parent_widget=None):
        """
        Initializes the XmlTopologyFixer.

        :param file_path: The absolute path to the XML file.
        :param parent_widget: The parent widget for displaying message boxes.
        """
        self.file_path = file_path
        self.parent_widget = parent_widget
        self.tree = None
        self.root = None

    def check_and_fix_topology(self):
        """
        Main method to run the topology check and fix process.

        :return: A FixResult enum value indicating the outcome.
        """
        if not os.path.exists(self.file_path):
            return self.FixResult.OPERATION_CANCELLED

        try:
            parser = etree.XMLParser(remove_blank_text=True)
            self.tree = etree.parse(self.file_path, parser)
            self.root = self.tree.getroot()
        except etree.XMLSyntaxError:

            return self.FixResult.NO_ISSUES_FOUND

        metric_info = self.root.find('.//MetricInfo')
        if metric_info is None:
            return self.FixResult.NO_ISSUES_FOUND

        point_info = metric_info.find('PointInfo')
        polyline_info = metric_info.find('Polyline')

        if point_info is None or polyline_info is None:
            return self.FixResult.NO_ISSUES_FOUND

        used_point_ids = self._get_used_point_ids(metric_info)
        used_polyline_ids = self._get_used_polyline_ids()

        all_points = point_info.findall('Point')
        all_polylines = polyline_info.findall('PL')

        unused_points = [p for p in all_points if p.findtext(
            'UIDP') not in used_point_ids]
        unused_polylines = [pl for pl in all_polylines if pl.findtext(
            'ULID') not in used_polyline_ids]

        if not unused_points and not unused_polylines:
            return self.FixResult.NO_ISSUES_FOUND

        msg_box, clicked_button = self._confirm_fix(
            len(unused_points), len(unused_polylines))
        user_choice_role = msg_box.buttonRole(clicked_button)

        if user_choice_role == QMessageBox.YesRole:  # "Виправити та зберегти"

            self._backup_original_file()

            for point in unused_points:
                point_info.remove(point)
            for polyline in unused_polylines:
                polyline_info.remove(polyline)

            point_info[:] = sorted(
                point_info, key=lambda p: int(p.findtext('UIDP')))
            polyline_info[:] = sorted(
                polyline_info, key=lambda pl: int(pl.findtext('ULID')))

            self.tree.write(self.file_path, pretty_print=True,
                            xml_declaration=True, encoding='UTF-8')
            iface.messageBar().pushMessage(
                "Успіх", "Топологію було виправлено. Файл буде перезавантажено.",
                level=Qgis.Success, duration=5)
            return self.FixResult.FILE_FIXED_AND_SAVED

        elif user_choice_role == QMessageBox.NoRole:  # "Відкрити як є"
            return self.FixResult.OPEN_AS_IS
        else:  # RejectRole ("Скасувати") or closed dialog
            return self.FixResult.OPERATION_CANCELLED

    def _get_used_point_ids(self, metric_info):
        """Collects all referenced point IDs (UIDP)."""
        used_ids = set()

        for p_id in metric_info.xpath('.//Polyline/PL/Points/P/text()'):
            used_ids.add(p_id)

        for p_id in metric_info.xpath('.//ControlPoint/P/text()'):
            used_ids.add(p_id)

        for p_id in self.root.xpath('.//Boundary/Lines/Line/FP/text() | .//Boundary/Lines/Line/TP/text()'):
            used_ids.add(p_id)

        for p_id in self.root.xpath('.//AdjacentRests/Points/P/text()'):
            used_ids.add(p_id)

        for p_id in self.root.xpath('.//ParcelInfo/LandParcelInfo/MetricInfo/Externals/Boundary/Lines/Line/FP/text() | .//ParcelInfo/LandParcelInfo/MetricInfo/Externals/Boundary/Lines/Line/TP/text()'):
            used_ids.add(p_id)
        return used_ids

    def _get_used_polyline_ids(self):
        """Collects all referenced polyline IDs (ULID)."""
        used_ids = set()

        for ulid in self.root.xpath('.//Boundary/Lines/Line/ULID/text()'):
            used_ids.add(ulid)
        return used_ids

    def _confirm_fix(self, unused_points_count, unused_polylines_count):
        """Shows a confirmation dialog to the user."""
        message = "У файлі виявлено невикористовувані елементи:\n\n"
        if unused_points_count > 0:
            message += f"- Невикористовуваних точок: {unused_points_count}\n"
        if unused_polylines_count > 0:
            message += f"- Невикористовуваних поліліній: {unused_polylines_count}\n"

        message += "\nБажаєте виправити топологію перед відкриттям?"

        msg_box = QMessageBox(self.parent_widget)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle('Виправлення топології')
        msg_box.setText(message)
        msg_box.setInformativeText(
            "Буде створено резервну копію оригінального (неправильного) файлу.")

        fix_button = msg_box.addButton(
            "Виправити та зберегти", QMessageBox.YesRole)
        open_as_is_button = msg_box.addButton(
            "Відкрити як є", QMessageBox.NoRole)
        cancel_button = msg_box.addButton("Скасувати", QMessageBox.RejectRole)

        msg_box.setDefaultButton(fix_button)
        msg_box.exec_()

        return msg_box, msg_box.clickedButton()

    def _backup_original_file(self):
        """Creates a timestamped backup of the original XML file."""
        try:
            base, ext = os.path.splitext(self.file_path)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa
            backup_path = f"{base}_invalid_{timestamp}{ext}"
            shutil.copy2(self.file_path, backup_path)

            info_msg = f"Створено резервну копію:\n{os.path.basename(backup_path)}"
            QMessageBox.information(
                self.parent_widget, "Резервне копіювання", info_msg)

        except Exception as e:
            error_msg = f"Не вдалося створити резервну копію.\nПомилка: {e}"
            QMessageBox.warning(self.parent_widget,
                                "Помилка копіювання", error_msg)
