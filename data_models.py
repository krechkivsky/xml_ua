

class ShapeInfo:
    """Клас для зберігання опису геометричного об'єкта та його зв'язку з картою."""

    def __init__(self, layer_id, object_id, object_shape):
        self.layer_id = layer_id          # ID шару QGIS, на якому знаходиться об'єкт
        self.object_id = object_id        # Технічний ID об'єкта в межах одного шару (починається з 1 у кожному шарі)
        self.object_shape = object_shape
        self.delete = False  # Прапорець для позначення видалення


class xml_data:
    """Клас для зберігання даних, пов'язаних з одним відкритим XML-файлом."""

    def __init__(self, path: str = "", tree: object = None, group_name: str = "", backup_path: str = ""):
        self.original_path = ""
        self.path = path
        self.tree = tree
        self.group_name = group_name
        self.backup_path = backup_path
        self.temp_tree_state = None
        self.changed = False
        self.was_ever_changed = False
        self.shapes = []  # Список об'єктів ShapeInfo для відстеження геометрії
        self._object_id_counter = 0
