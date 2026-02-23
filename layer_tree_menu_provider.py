from qgis.gui import QgsLayerTreeViewMenuProvider
from qgis.core import QgsLayerTreeLayer
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.utils import iface as qgis_iface


class XmlUaLayerTreeMenuProvider(QgsLayerTreeViewMenuProvider):
    """
    Custom menu provider for the QGIS Layer Tree View.
    Adds custom actions for deleting XML sections corresponding to layers.
    """

    def __init__(self, dockwidget):
        super().__init__()
        self.dockwidget = dockwidget

    def createContextMenu(self, *args, **kwargs):
        """
        Creates custom context menu actions for the clicked node in the layer tree.
        """

        menu = None
        clicked_node = None

        if len(args) >= 2:
            menu, clicked_node = args[0], args[1]
        elif len(args) == 1:
            clicked_node = args[0]

        menu = kwargs.get("menu", menu)
        clicked_node = kwargs.get("clicked_node", kwargs.get("clickedNode", clicked_node))

        if not isinstance(menu, QMenu):
            menu = QMenu()

        if clicked_node is None:
            try:
                view = qgis_iface.layerTreeView() if qgis_iface else None
                if view:
                    if hasattr(view, "currentNode"):
                        clicked_node = view.currentNode()
                    elif hasattr(view, "layerTreeModel") and hasattr(view, "currentIndex"):
                        model = view.layerTreeModel()
                        index = view.currentIndex()
                        if model and index and hasattr(model, "index2node"):
                            clicked_node = model.index2node(index)
            except Exception:
                clicked_node = None

        if clicked_node is None:
            return menu

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

        return menu
