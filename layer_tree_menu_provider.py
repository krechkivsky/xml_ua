from qgis.gui import QgsLayerTreeViewMenuProvider
from qgis.core import QgsLayerTreeGroup, QgsLayerTreeLayer, QgsProject
from qgis.PyQt.QtWidgets import QAction, QMenu

from .common import log_msg, logFile


class XmlUaLayerTreeMenuProvider(QgsLayerTreeViewMenuProvider):
    """
    Custom menu provider for the QGIS Layer Tree View.
    Adds custom actions for deleting XML sections corresponding to layers.
    """

    def __init__(self, dockwidget):
        super().__init__()
        self.dockwidget = dockwidget

    def createContextMenu(self, menu: QMenu, clicked_node: 'QgsLayerTreeAbstractNode'):
        """
        Creates custom context menu actions for the clicked node in the layer tree.
        """

        deletable_layers_as_section = set(
            self.dockwidget.LAYER_NAME_TO_XML_CONTAINER_PATH.keys())
        protected_layers = set(self.dockwidget.PROTECTED_LAYERS)

        if isinstance(clicked_node, QgsLayerTreeLayer):
            layer = clicked_node.layer()

            if layer and layer.name() in deletable_layers_as_section and layer.name() not in protected_layers:

                xml_data = self.dockwidget.find_xml_data_for_layer(layer)
                if xml_data:
                    menu.addSeparator()
                    action = QAction(
                        f"Видалити розділ '{layer.name()}' з XML", menu)
                    action.triggered.connect(
                        lambda: self.dockwidget.delete_xml_section_from_layer_tree(clicked_node))
                    menu.addAction(action)

            elif layer and layer.name() in protected_layers:

                pass
