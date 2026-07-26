# Original plugin created for Skyrim by bluebuiy
#     https://www.nexusmods.com/skyrimspecialedition/mods/59598
# Modified for Fallout 4 by wxMichael
#     https://www.nexusmods.com/fallout4/mods/85067
#
# This version created by GoriRed
# Version: 1.2
# License: CC-BY-NC
# https://github.com/tkoopman/MO2-Batch-Plugin-Cleaner

import enum
import logging
import os
from pathlib import Path
import sys
import typing

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPoint,
    QSortFilterProxyModel,
    Qt,
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QDialog, QMenu, QMessageBox, QWidget
import mobase  # type: ignore

from . import ui_main_screen
from . import icons
from . import cleaning_data
from .cleaning_data import crc32, crc_cleaning_data, source


launchOptions = [
    "-IKnowWhatImDoing",
    "-QuickAutoClean",
    "-autoexit",
    "-autoload",
]


class keep_logs(enum.IntEnum):
    NONE = 0
    UNKNOWN = 1
    MANUAL = 3
    CLEANED = 4
    ALL = 5


class GameInfo(typing.TypedDict):
    xEditName: str
    xEditSwitch: str
    LootFolder: str | None


gameInfo: dict[str, GameInfo] = {
    "Oblivion": {
        "xEditName": "TES4Edit",
        "xEditSwitch": "-tes4",
        "LootFolder": "Oblivion",
    },
    "Nehrim": {
        "xEditName": "TES4Edit",
        "xEditSwitch": "-tes4",
        "LootFolder": "Nehrim",
    },
    "Fallout3": {
        "xEditName": "FO3Edit",
        "xEditSwitch": "-fo3",
        "LootFolder": "Fallout3",
    },
    "FalloutNV": {
        "xEditName": "FNVEdit",
        "xEditSwitch": "-fnv",
        "LootFolder": "FalloutNV",
    },
    "TTW": {
        "xEditName": "FNVEdit",
        "xEditSwitch": "-fnv",
        "LootFolder": None,
    },
    "Skyrim": {
        "xEditName": "TES5Edit",
        "xEditSwitch": "-tes5",
        "LootFolder": "Skyrim",
    },
    "SkyrimSE": {
        "xEditName": "SSEEdit",
        "xEditSwitch": "-sse",
        "LootFolder": "Skyrim Special Edition",
    },
    "SkyrimVR": {
        "xEditName": "TES5VREdit",
        "xEditSwitch": "-tes5vr",
        "LootFolder": "Skyrim VR",
    },
    "Enderal": {
        "xEditName": "EnderalEdit",
        "xEditSwitch": "-enderal",
        "LootFolder": "Enderal",
    },
    "EnderalSE": {
        "xEditName": "EnderalSEEdit",
        "xEditSwitch": "-enderalse",
        "LootFolder": "Enderal Special Edition",
    },
    "Fallout4": {
        "xEditName": "FO4Edit",
        "xEditSwitch": "-fo4",
        "LootFolder": "Fallout4",
    },
    "Fallout4VR": {
        "xEditName": "FO4VREdit",
        "xEditSwitch": "-fo4vr",
        "LootFolder": "Fallout4VR",
    },
    "Fallout76": {
        "xEditName": "FO76Edit",
        "xEditSwitch": "-fo76",
        "LootFolder": None,
    },
    "Starfield": {
        "xEditName": "SF1Edit",
        "xEditSwitch": "-sf1",
        "LootFolder": "Starfield",
    },
}


def to_int(value: typing.Any, default: int = 0) -> int:
    try:
        return int(value)
    except ValueError:
        return default


class plugin_clean_state(enum.Enum):
    UNKNOWN = enum.auto()
    CLEAN = enum.auto()
    DIRTY = enum.auto()
    REQUIRES_MANUAL = enum.auto()


class plugin_type(enum.Enum):
    PRIMARY = enum.auto()
    DLC = enum.auto()
    CC = enum.auto()
    OTHER = enum.auto()


class plugin(typing.TypedDict):
    name: str
    selected: bool
    priority: int
    type: plugin_type
    origin: str
    state: plugin_clean_state
    hasNoRecords: bool
    crc: crc32 | None
    cleaning_data: cleaning_data.cleaning_data | None
    processed: str | bool
    ignore: bool


class Plugins:
    def __init__(
        self,
        organizer: mobase.IOrganizer,
        crc_cleaning_data: crc_cleaning_data,
        plugins: list["plugin"],
        index: dict[str, int] | None,
        first_dynamic: int,
        first_dynamic_name: str | None,
        cleanPrimary: bool,
        cleanCC: bool,
        cleanElse: bool,
    ) -> None:
        self.organizer = organizer
        self.crc_cleaning_data = crc_cleaning_data
        self.__plugins = plugins
        if isinstance(index, dict):
            self.__plugins_index = index
        else:
            self.reindex()

        self.first_dynamic = first_dynamic
        self.first_dynamic_name = first_dynamic_name
        self.__cleanPrimary = cleanPrimary
        self.__cleanCC = cleanCC
        self.__cleanElse = cleanElse

    def reindex(self) -> None:
        self.__plugins_index = {
            plugin["name"].casefold(): i for i, plugin in enumerate(self.__plugins)
        }

    @staticmethod
    def All(organizer: mobase.IOrganizer) -> "Plugins":
        loot = gameInfo[organizer.managedGame().gameShortName()]["LootFolder"]
        crc_cleaning_data = (
            cleaning_data.LootData.load(
                str(
                    Path(os.environ["LOCALAPPDATA"])
                    / "LOOT"
                    / "games"
                    / loot
                    / "masterlist.yaml"
                )
            )
            if loot
            else None
        )
        user_data = cleaning_data.CsvData.load(
            Path(organizer.getPluginDataPath()) / "cleaning_data.csv"
        )
        if crc_cleaning_data:
            crc_cleaning_data.update_data(user_data)
        else:
            crc_cleaning_data = user_data

        plugin_list = organizer.pluginList()

        plugins = [
            (name, plugin_list.priority(name)) for name in plugin_list.pluginNames()
        ]
        plugins.sort(key=lambda x: x[1])
        plugins = [name for name, _ in plugins]

        plugins_data = list[plugin]()
        plugins_index = dict[str, int]()

        primaryPlugins = [
            name.casefold() for name in organizer.managedGame().primaryPlugins()
        ]
        DLCPlugins = [name.casefold() for name in organizer.managedGame().DLCPlugins()]
        CCPlugins = [name.casefold() for name in organizer.managedGame().CCPlugins()]

        cleanPrimary = bool(organizer.pluginSetting(CleanerPlugin.NAME(), "clean_beth"))
        cleanCC = bool(organizer.pluginSetting(CleanerPlugin.NAME(), "clean_cc"))
        cleanElse = bool(organizer.pluginSetting(CleanerPlugin.NAME(), "clean_else"))
        firstDynamic = str(
            organizer.pluginSetting(CleanerPlugin.NAME(), "first_dynamic")
        )
        firstDynamicFound = -1

        ignored = str(organizer.pluginSetting(CleanerPlugin.NAME(), "do_not_clean"))

        if ignored:
            ignored = [name.casefold().strip() for name in ignored.split(",")]
        else:
            ignored = list[str]()

        for plugin_name in plugins:
            if plugin_list.state(plugin_name) != mobase.PluginState.ACTIVE:
                # Can't clean inactive plugins
                continue

            plugin_name_cf = plugin_name.casefold()
            origin = organizer.pluginList().origin(plugin_name)
            mod = organizer.modList().getMod(origin)

            match origin:
                case "data":
                    directory = Path(
                        organizer.managedGame().dataDirectory().absolutePath()
                    )
                case "overwrite":
                    directory = Path(organizer.overwritePath())
                case _:
                    directory = Path(mod.absolutePath())
            filename = directory / plugin_name

            crc = crc32.from_file(filename) if Path(filename).is_file() else None
            hasNoRecords = plugin_list.hasNoRecords(plugin_name)
            cd = crc_cleaning_data.find(plugin_name, crc)

            pluginType = (
                plugin_type.CC
                if plugin_name_cf in CCPlugins
                else (
                    plugin_type.DLC
                    if plugin_name_cf in DLCPlugins
                    else (
                        plugin_type.PRIMARY
                        if plugin_name_cf in primaryPlugins
                        else plugin_type.OTHER
                    )
                )
            )

            state = (
                plugin_clean_state.CLEAN
                if hasNoRecords
                else (
                    plugin_clean_state.UNKNOWN
                    if cd is None
                    else (
                        plugin_clean_state.CLEAN
                        if cd.is_clean()
                        else (
                            plugin_clean_state.DIRTY
                            if cd.is_auto_cleanable()
                            else (
                                plugin_clean_state.REQUIRES_MANUAL
                                if cd.requires_manual_fix()
                                else plugin_clean_state.UNKNOWN
                            )
                        )
                    )
                )
            )

            if plugin_name == firstDynamic:
                firstDynamicFound = plugin_list.priority(plugin_name)

            ignore = plugin_name_cf in ignored
            priority = plugin_list.priority(plugin_name)
            selected = Plugins.__selected_default(
                ignore,
                state,
                priority,
                pluginType,
                firstDynamicFound,
                cleanPrimary,
                cleanCC,
                cleanElse,
            )

            data = plugin(
                {
                    "name": plugin_name,
                    "selected": selected,
                    "priority": priority,
                    "type": pluginType,
                    "origin": origin,
                    "state": state,
                    "hasNoRecords": hasNoRecords,
                    "crc": crc,
                    "cleaning_data": cd,
                    "processed": False,
                    "ignore": ignore,
                }
            )

            plugins_index[plugin_name_cf] = len(plugins_data)
            plugins_data.append(data)

        return Plugins(
            organizer,
            crc_cleaning_data,
            plugins_data,
            plugins_index,
            firstDynamicFound,
            firstDynamic if firstDynamicFound != -1 else None,
            cleanPrimary,
            cleanCC,
            cleanElse,
        )

    def get_ignored(self) -> list[str]:
        return sorted([plugin["name"] for plugin in self.__plugins if plugin["ignore"]])

    @staticmethod
    def __selected_default(
        ignore: bool,
        state: plugin_clean_state,
        priority: int,
        pluginType: plugin_type,
        first_dynamic: int,
        cleanPrimary: bool,
        cleanCC: bool,
        cleanElse: bool,
    ) -> bool:
        if ignore:
            return False

        if state not in [plugin_clean_state.DIRTY, plugin_clean_state.UNKNOWN]:
            return False

        if first_dynamic != -1 and priority >= first_dynamic:
            return False

        match pluginType:
            case plugin_type.PRIMARY:
                return cleanPrimary
            case plugin_type.DLC:
                return cleanPrimary
            case plugin_type.CC:
                return cleanCC
            case _:
                return cleanElse

    def selected_default(self, plugin: plugin) -> bool:
        return Plugins.__selected_default(
            plugin["ignore"],
            plugin["state"],
            plugin["priority"],
            plugin["type"],
            self.first_dynamic,
            self.__cleanPrimary,
            self.__cleanCC,
            self.__cleanElse,
        )

    @staticmethod
    def Selected(plugins: "Plugins") -> "Plugins":
        selected_plugins = [
            plugin for plugin in plugins.__plugins if plugin["selected"]
        ]

        selected_plugins.sort(key=lambda x: x["priority"])
        return Plugins(
            plugins.organizer,
            plugins.crc_cleaning_data,
            selected_plugins,
            None,
            plugins.first_dynamic,
            plugins.first_dynamic_name,
            plugins.__cleanPrimary,
            plugins.__cleanCC,
            plugins.__cleanElse,
        )

    def __getitem__(self, value: str | int) -> plugin | None:
        if isinstance(value, str):
            name = value.casefold()
            if name in self.__plugins_index:
                return self.__plugins[self.__plugins_index[name]]
        else:
            if 0 <= value < len(self.__plugins):
                return self.__plugins[value]

        return None

    def __len__(self) -> int:
        return len(self.__plugins)

    def __iter__(self) -> typing.Iterator[plugin]:
        return iter(self.__plugins)

    def indexOf(self, plugin: plugin) -> int:
        name = plugin["name"].casefold()
        if name in self.__plugins_index:
            return self.__plugins_index[name]
        return -1


class plugin_select_model(QAbstractTableModel):
    def __init__(self, plugins: Plugins, parent: QWidget | None = None) -> None:
        super().__init__()
        self.__plugins = plugins

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if index.isValid():
            p = self.__plugins[index.row()]
            if p and p["ignore"]:
                return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            return (
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
                if index.column() == 0
                else Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )

        return None  # type: ignore

    def index(
        self, row: int, column: int, parent: QModelIndex | None = None
    ) -> QModelIndex:
        plugin = self.__plugins[row]
        if plugin:
            return self.createIndex(row, column, plugin["name"])

        return QModelIndex()

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.__plugins)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 4

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = 0):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            match section:
                case 0:
                    return "Plugin"
                case 1:
                    return None
                case 2:
                    return "Pri"
                case 3:
                    return "CRC"
                case _:
                    return None

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.EditRole
    ) -> Qt.CheckState | QIcon | str | int | None:
        if not index.isValid():
            return None

        row = index.row()
        plugin = self.__plugins[row]
        if not plugin:
            return None

        match index.column():
            case 0:
                if role == Qt.ItemDataRole.CheckStateRole:
                    return (
                        Qt.CheckState.Checked
                        if plugin["selected"]
                        else Qt.CheckState.Unchecked
                    )

                if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
                    return plugin["name"]

                if role == Qt.ItemDataRole.ToolTipRole:
                    return (
                        "Primary Plugin"
                        if plugin["type"] == plugin_type.PRIMARY
                        else (
                            "DLC Plugin"
                            if plugin["type"] == plugin_type.DLC
                            else (
                                "Creation Club Plugin"
                                if plugin["type"] == plugin_type.CC
                                else f"Mod: {plugin["origin"]}"
                            )
                        )
                    )

            case 1:
                is_dynamic = (
                    self.__plugins.first_dynamic != -1
                    and plugin["priority"] >= self.__plugins.first_dynamic
                )
                if role == Qt.ItemDataRole.DecorationRole:
                    if plugin["ignore"]:
                        return icons.DO_NOT_CLEAN

                    if is_dynamic:
                        return icons.DO_NOT_CLEAN

                    match plugin["state"]:
                        case plugin_clean_state.UNKNOWN:
                            return icons.CLEAN_STATE_UNKNOWN
                        case plugin_clean_state.CLEAN:
                            return icons.CLEAN_STATE_CLEAN
                        case plugin_clean_state.DIRTY:
                            return icons.CLEAN_STATE_DIRTY
                        case plugin_clean_state.REQUIRES_MANUAL:
                            return icons.CLEAN_STATE_MANUAL
                if role == Qt.ItemDataRole.ToolTipRole:
                    if is_dynamic:
                        return f"Do not clean. Dynamic patches start at {self.__plugins.first_dynamic_name}"
                    match plugin["state"]:
                        case plugin_clean_state.UNKNOWN:
                            return "Unknown cleaning state"
                        case plugin_clean_state.CLEAN:
                            return (
                                "Clean [No Records]"
                                if plugin["hasNoRecords"]
                                else (
                                    "Clean [LOOT Masterlist]"
                                    if plugin["cleaning_data"]
                                    and plugin["cleaning_data"].source == source.LOOT
                                    else "Clean [User Data]"
                                )
                            )
                        case plugin_clean_state.DIRTY:
                            return (
                                "Dirty [LOOT Masterlist]"
                                if plugin["cleaning_data"]
                                and plugin["cleaning_data"].source == source.LOOT
                                else "Dirty [User Data]"
                            )
                        case plugin_clean_state.REQUIRES_MANUAL:
                            return "Plugin requires manual cleaning"
            case 2:
                if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
                    return plugin["priority"]
            case 3:
                if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
                    return str(plugin["crc"])
            case _:
                return None

    def setData(
        self,
        index: QModelIndex,
        value: typing.Any,
        role: int = Qt.ItemDataRole.CheckStateRole,
    ) -> bool:
        if (
            role == Qt.ItemDataRole.CheckStateRole
            and index.isValid()
            and index.column() == 0
        ):
            value = value == Qt.CheckState.Checked.value
            plugin = self.__plugins[index.data()]
            if plugin:
                plugin["selected"] = value

                self.dataChanged.emit(index, index, [role])

        return False


class PluginSelectWindow(QDialog):
    def __init__(self, plugins: Plugins, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.__main_screen = ui_main_screen.Ui_main_screen()
        self.__main_screen.setupUi(self)  # type: ignore
        self.__plugins = plugins
        self.__plugins_model = plugin_select_model(plugins)
        self.__proxyModel = QSortFilterProxyModel()
        self.__proxyModel.setSourceModel(self.__plugins_model)
        self.__proxyModel.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.__main_screen.filterEdit.textChanged.connect(self.filter)  # type: ignore
        self.__main_screen.pluginsView.setModel(self.__proxyModel)
        self.__previous_sort_column = 2
        self.__previous_sort_order = Qt.SortOrder.AscendingOrder
        self.__main_screen.pluginsView.sortByColumn(2, Qt.SortOrder.AscendingOrder)
        self.__main_screen.pluginsView.resizeColumnsToContents()
        self.__main_screen.pluginsView.horizontalHeader().sortIndicatorChanged.connect(self.sort_indicator_changed)  # type: ignore

        self.__main_screen.pluginsView.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.__main_screen.pluginsView.customContextMenuRequested.connect(self.show_context_menu)  # type: ignore

    def filter(self):
        filter_text = self.__main_screen.filterEdit.text()
        if filter_text:
            self.__proxyModel.setFilterFixedString(filter_text)
        else:
            self.__proxyModel.setFilterFixedString("")

    def show_context_menu(self, position: QPoint):
        context_menu = QMenu(self)
        context_menu.setToolTipsVisible(True)

        index = self.__main_screen.pluginsView.indexAt(position)
        if not index.isValid():
            return

        selected_rows = self.__main_screen.pluginsView.selectionModel().selectedRows(0)
        if not selected_rows:
            return

        # Gather the check states of selected plugins
        selected_plugins = [
            self.__plugins[row.data()]
            for row in selected_rows
            if self.__plugins[row.data()]
        ]
        all_ignored  = len(selected_plugins) > 0 and all(p["ignore"] for p in selected_plugins)
        selected_states = [p["selected"] for p in selected_plugins if not p["ignore"]]
        all_enabled  = bool(selected_states) and all(selected_states)
        all_disabled = bool(selected_states) and not any(selected_states)

        action = QAction("Enable selected", self)
        action.setToolTip("Check all selected plugins")
        action.setEnabled(not all_ignored and not all_enabled)
        action.triggered.connect(self.context_menu_enable_selected)  # type: ignore
        context_menu.addAction(action)  # type: ignore

        action = QAction("Disable selected", self)
        action.setToolTip("Uncheck all selected plugins")
        action.setEnabled(not all_ignored and not all_disabled)
        action.triggered.connect(self.context_menu_disable_selected)  # type: ignore
        context_menu.addAction(action)  # type: ignore
        if not all_ignored and not all_enabled and not all_disabled:
            action = QAction("Invert selected", self)
            action.setToolTip("Toggle the check state of all selected plugins")
            action.triggered.connect(self.context_menu_invert_selected)  # type: ignore
            context_menu.addAction(action)  # type: ignore

        context_menu.addSeparator()

        # Determine ignore label based on the right-clicked plugin
        clicked_index = index if index.column() == 0 else index.sibling(index.row(), 0)
        clicked_plugin_name = self.__main_screen.pluginsView.model().data(clicked_index, Qt.ItemDataRole.DisplayRole)  # type: ignore
        clicked_plugin = self.__plugins[clicked_plugin_name] if isinstance(clicked_plugin_name, str) else None
        if not clicked_plugin:
            return

        new_ignore = not clicked_plugin["ignore"]
        action = QAction("Do not clean" if new_ignore else "Allow cleaning", self)
        action.setToolTip("Toggle cleaning for all selected plugins")
        action.triggered.connect(lambda: self.context_menu_toggle_ignore(new_ignore))  # type: ignore
        context_menu.addAction(action)  # type: ignore

        is_current_dynamic = (
            self.__plugins.first_dynamic != -1
            and clicked_plugin["priority"] == self.__plugins.first_dynamic
        )

        if is_current_dynamic:
            action = QAction("Clear first dynamic patch", self)
            action.setToolTip("Remove the first dynamic patch setting and restore affected plugins to default state")
            action.setEnabled(len(selected_rows) == 1)
            action.triggered.connect(self.context_menu_clear_dynamic)  # type: ignore
        else:
            action = QAction("Set first dynamic patch", self)
            action.setToolTip("Will never auto select this mod or any with higher priority")
            action.setEnabled(len(selected_rows) == 1)
            action.triggered.connect(self.context_menu_set_dynamic)  # type: ignore
        context_menu.addAction(action)  # type: ignore

        context_menu.addSeparator()

        action = QAction("Reset All", self)
        action.setToolTip("Reset all plugins to their default state")
        action.triggered.connect(self.context_menu_reset_all)  # type: ignore
        context_menu.addAction(action)  # type: ignore

        context_menu.exec(self.__main_screen.pluginsView.mapToGlobal(position))  # type: ignore

    def context_menu_toggle_ignore(self, new_ignore: bool):
        model = self.__main_screen.pluginsView.model()
        if not model:
            return

        selected_rows = self.__main_screen.pluginsView.selectionModel().selectedRows(0)
        if not selected_rows:
            return

        for index in selected_rows:
            plugin = self.__plugins[index.data()]
            if plugin:
                plugin["ignore"] = new_ignore

                if plugin["ignore"]:
                    plugin["selected"] = False
                else:
                    plugin["selected"] = self.__plugins.selected_default(plugin)

                model.dataChanged.emit(
                    index,
                    index.siblingAtColumn(model.columnCount() - 1),
                    [
                        Qt.ItemDataRole.DisplayRole,
                        Qt.ItemDataRole.CheckStateRole,
                        Qt.ItemDataRole.DecorationRole,
                    ],
                )

        self.__plugins.organizer.setPluginSetting(
            CleanerPlugin.NAME(),
            "do_not_clean",
            ",".join(self.__plugins.get_ignored()),
        )

    def __reset_plugin_state_range(self, start: int, end: int):
        """Reset selected state for all plugins with priority in [start, end]."""
        model = self.__main_screen.pluginsView.model()
        if not model:
            return

        for x in range(model.rowCount()):
            col0_index = model.index(x, 0)
            p = to_int(model.data(model.index(x, 2), Qt.ItemDataRole.DisplayRole), -1)
            if start <= p <= end:
                plugin_name = model.data(col0_index, Qt.ItemDataRole.DisplayRole)  # type: ignore
                p_obj = self.__plugins[plugin_name] if isinstance(plugin_name, str) else None
                if p_obj is None:
                    continue
                p_obj["selected"] = self.__plugins.selected_default(p_obj)
                model.dataChanged.emit(col0_index, col0_index, [Qt.ItemDataRole.CheckStateRole])  # type: ignore

        row_count = self.__plugins_model.rowCount()
        if row_count > 0:
            self.__plugins_model.dataChanged.emit(
                self.__plugins_model.index(0, 1),
                self.__plugins_model.index(row_count - 1, 1),
                [Qt.ItemDataRole.DecorationRole, Qt.ItemDataRole.ToolTipRole],
            )

    def context_menu_clear_dynamic(self):
        if self.__plugins.first_dynamic == -1:
            return

        self.__plugins.organizer.setPluginSetting(
            CleanerPlugin.NAME(), "first_dynamic", ""
        )
        old_first_dynamic = self.__plugins.first_dynamic
        self.__plugins.first_dynamic = -1
        self.__plugins.first_dynamic_name = None
        self.__reset_plugin_state_range(old_first_dynamic, sys.maxsize)

    def context_menu_set_dynamic(self):
        index = self.__main_screen.pluginsView.currentIndex()
        if not index.isValid():
            return

        model = self.__main_screen.pluginsView.model()
        if not model:
            return

        if index.column() != 0:
            index = index.sibling(index.row(), 0)

        plugin = model.data(index, Qt.ItemDataRole.DisplayRole)  # type: ignore
        priority = to_int(model.data(index.sibling(index.row(), 2), Qt.ItemDataRole.DisplayRole), sys.maxsize)  # type: ignore
        if not plugin or not isinstance(plugin, str):
            return

        self.__plugins.organizer.setPluginSetting(
            CleanerPlugin.NAME(), "first_dynamic", plugin
        )
        old_first_dynamic = self.__plugins.first_dynamic
        self.__plugins.first_dynamic = priority
        self.__plugins.first_dynamic_name = plugin
        lower_bound = min(priority, old_first_dynamic) if old_first_dynamic >= 0 else priority
        self.__reset_plugin_state_range(lower_bound, sys.maxsize)

    def context_menu_reset_all(self):
        self.__reset_plugin_state_range(0, sys.maxsize)

    def __set_selected_check_state(self, state: bool | None):
        """Set or toggle selected for all selected rows. Pass None to invert."""
        model = self.__main_screen.pluginsView.model()
        if not model:
            return

        selected_rows = self.__main_screen.pluginsView.selectionModel().selectedRows(0)
        for index in selected_rows:
            plugin = self.__plugins[index.data()]
            if plugin and not plugin["ignore"]:
                plugin["selected"] = not plugin["selected"] if state is None else state
                model.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])

    def context_menu_enable_selected(self):
        self.__set_selected_check_state(True)

    def context_menu_disable_selected(self):
        self.__set_selected_check_state(False)

    def context_menu_invert_selected(self):
        self.__set_selected_check_state(None)

    def sort_indicator_changed(self, column: int, order: Qt.SortOrder):
        if column == 1:
            self.__main_screen.pluginsView.sortByColumn(
                self.__previous_sort_column, self.__previous_sort_order
            )
        else:
            self.__previous_sort_column = column
            self.__previous_sort_order = order


class plugin_progress_model(QAbstractTableModel):
    def __init__(self, plugins: Plugins, parent: QWidget | None = None) -> None:
        super().__init__()
        self.__plugins = plugins

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if index.isValid():
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

        return None  # type: ignore

    def index(
        self, row: int, column: int, parent: QModelIndex | None = None
    ) -> QModelIndex:
        plugin = self.__plugins[row]
        if plugin:
            return self.createIndex(row, column, plugin["name"])

        return QModelIndex()

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.__plugins)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 3

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = 0):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            match section:
                case 0:
                    return "Plugin"
                case 1:
                    return "Pri"
                case 2:
                    return "Status"
                case _:
                    return None

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.EditRole
    ) -> Qt.CheckState | QIcon | str | int | None:
        if not index.isValid():
            return None

        row = index.row()
        plugin = self.__plugins[row]
        if not plugin:
            return None

        match index.column():
            case 0:
                if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
                    return plugin["name"]

                if role == Qt.ItemDataRole.ToolTipRole:
                    return (
                        "Primary Plugin"
                        if plugin["type"] == plugin_type.PRIMARY
                        else (
                            "DLC Plugin"
                            if plugin["type"] == plugin_type.DLC
                            else (
                                "Creation Club Plugin"
                                if plugin["type"] == plugin_type.CC
                                else f"Mod: {plugin["origin"]}"
                            )
                        )
                    )
            case 1:
                if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
                    return plugin["priority"]
            case 2:
                if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
                    return (
                        str(plugin["processed"])
                        if plugin["processed"]
                        else "In queue..."
                    )
            case _:
                return None

    def update(self, plugin: plugin, processed: str | bool) -> None:
        index = self.__plugins.indexOf(plugin)
        if index >= 0:
            plugin["processed"] = processed

            self.dataChanged.emit(
                self.index(index, 0),
                self.index(index, self.columnCount() - 1),
                [Qt.ItemDataRole.DisplayRole],
            )


class PluginProgressWindow(QDialog):
    def __init__(self, plugins: Plugins, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.__canceled = False
        self.__stopped = False
        self.__plugins = plugins
        self.__organizer = plugins.organizer
        self.__main_screen = ui_main_screen.Ui_main_screen()
        self.__main_screen.setupUi(self)  # type: ignore
        self.__plugins_model = plugin_progress_model(plugins)
        self.__proxyModel = QSortFilterProxyModel()
        self.__proxyModel.setSourceModel(self.__plugins_model)
        self.__main_screen.pluginsView.setModel(self.__proxyModel)
        self.__main_screen.pluginsView.resizeColumnsToContents()

        self.__main_screen.filterEdit.setHidden(True)
        self.__main_screen.pluginsView.setSortingEnabled(False)
        self.__main_screen.okButton.setHidden(True)
        self.__main_screen.cancelButton.setText("Stop")

        # Set global launch args
        self.__outputPath = (
            Path(self.__organizer.pluginDataPath()) / CleanerPlugin.NAME()
        )
        os.makedirs(self.__outputPath, exist_ok=True)

        self.__xEditArgs = list(launchOptions)
        # TODO: Re-enable this if I find a way to force xEdit to perform backups if disabled in GUI, as this just tells it where to back up but won't force it to create backups
        # if self.__organizer.pluginSetting(CleanerPlugin.NAME(), "save_dirty_plugins"):
        #    self.__xEditArgs.append(f'-B:"{self.__outputPath}\\"')

        if self.__organizer.pluginSetting(CleanerPlugin.NAME(), "explicit_data_path"):
            self.__xEditArgs.append(
                f'-D:"{self.__organizer.managedGame().dataDirectory().absolutePath()}"'
            )

        if self.__organizer.pluginSetting(CleanerPlugin.NAME(), "explicit_ini_path"):
            self.__xEditArgs.append(
                f'-I:"{self.__organizer.managedGame().documentsDirectory().path()}/{self.__organizer.managedGame().iniFiles()[0]}"'
            )

        self.__xEditArgs.append(
            gameInfo[self.__organizer.managedGame().gameShortName()]["xEditSwitch"]
        )

        self.__xEditExecutableName = (
            "xEdit"
            if self.__organizer.pluginSetting(CleanerPlugin.NAME(), "exe_name_xedit")
            else gameInfo[self.__organizer.managedGame().gameShortName()]["xEditName"]
        )

        logging.debug(f"MO2 Application to launch: {self.__xEditExecutableName}")
        logging.debug(f"Args: {self.__xEditArgs}")

    def reject(self) -> None:
        if self.__stopped:
            super().reject()
        else:
            self.__canceled = True
            self.__main_screen.cancelButton.setText("Stopping...")

    def get_log_level(self) -> keep_logs:
        logLevel = self.__organizer.pluginSetting(CleanerPlugin.NAME(), "keep_logs")
        newLogLevel = to_int(logLevel, 4)
        if newLogLevel < 0:
            newLogLevel = 0
        elif newLogLevel > 5:
            newLogLevel = 5

        if newLogLevel != logLevel:
            self.__organizer.setPluginSetting(
                CleanerPlugin.NAME(), "keep_logs", newLogLevel
            )

        return keep_logs(newLogLevel)

    def clean_all(self):
        userFile = Path(self.__organizer.getPluginDataPath()) / "cleaning_data.csv"

        keep_log_level = self.get_log_level()
        for x in range(len(self.__plugins)):
            plugin = self.__plugins[x]
            if not plugin:
                self.__stopped = True
                raise ValueError("Plugin not found")

            if self.__canceled:
                self.__plugins_model.update(plugin, "Canceled")
                continue

            self.__plugins_model.update(plugin, "Processing...")

            self.__main_screen.pluginsView.selectRow(x)
            self.__main_screen.pluginsView.scrollTo(self.__proxyModel.index(x, 0))

            result = self.clean(plugin)
            if isinstance(result, crc_cleaning_data):
                match len(result):
                    case 0:
                        logging.error(
                            "No files detected in LOOT data from xEdit run. This should never happen."
                        )
                        self.reject()
                        continue
                    case 1:
                        pass
                    case _:
                        logging.error(
                            "Multiple different files detected in LOOT data from xEdit run. This should never happen."
                        )
                        self.reject()
                        continue

                name = plugin["name"].casefold()
                if name not in result:
                    logging.error(
                        "Plugin name not found in LOOT data from xEdit run. This should never happen."
                    )
                    self.reject()
                    continue

                updatedData = result[name]
                if plugin["crc"] not in updatedData:
                    logging.error(
                        "Plugin CRC not found in LOOT data from xEdit run. This should never happen."
                    )
                    self.reject()
                    continue

                crc_cleaning_data.update(self.__plugins.crc_cleaning_data, result)
                cleaning_data.CsvData.save(self.__plugins.crc_cleaning_data, userFile)

                crcData = updatedData[plugin["crc"]]

                log_level = keep_logs.UNKNOWN
                if crcData.is_clean():
                    self.__plugins_model.update(plugin, "Clean")
                    log_level = keep_logs.ALL
                else:
                    cleanedCrc = None
                    cleanedData = None

                    if crcData.is_auto_cleanable():
                        for crc, data in updatedData.items():
                            if crc == plugin["crc"]:
                                continue
                            cleanedCrc = crc
                            cleanedData = data
                            if not data.is_auto_cleanable():
                                break

                        if cleanedCrc and cleanedData:
                            if cleanedData.is_clean():
                                self.__plugins_model.update(
                                    plugin,
                                    f"Cleaned - ITM: {crcData.itm} UDR: {crcData.udr}",
                                )
                                log_level = keep_logs.CLEANED
                            elif not cleanedData.is_auto_cleanable():
                                self.__plugins_model.update(
                                    plugin,
                                    f"Attention manual cleaning required - NAV: {crcData.nav}. Cleaned - ITM: {crcData.itm} UDR: {crcData.udr}",
                                )
                                log_level = keep_logs.MANUAL
                            else:
                                self.__plugins_model.update(
                                    plugin,
                                    f"Attention unknown cleaning state - Original/Cleaned ITM: {crcData.itm}/{cleanedData.itm} UDR: {crcData.udr}/{cleanedData.udr} NAV: {crcData.nav}/{cleanedData.nav}",
                                )
                        else:
                            self.__plugins_model.update(
                                plugin,
                                f"Attention not cleaned - ITM: {crcData.itm} UDR: {crcData.udr} NAV: {crcData.nav}",
                            )
                    else:
                        self.__plugins_model.update(
                            plugin, f"Requires manual cleaning - NAV: {crcData.nav}"
                        )
                        log_level = keep_logs.MANUAL

                if log_level > keep_log_level:
                    os.remove(self.log_file_name(plugin))
            else:
                logging.error(f"Plugin {plugin['name']} was not cleaned: {result}")
                self.__plugins_model.update(plugin, result)
                self.reject()

        self.__main_screen.cancelButton.setText("Close")
        self.__stopped = True
        if not self.__canceled and self.__organizer.pluginSetting(
            CleanerPlugin.NAME(), "auto_close"
        ):
            self.close()

    def log_file_name(self, plugin: plugin) -> str:
        return str(self.__outputPath / f"{plugin['name']}_{plugin['crc']}.log")

    def clean(self, plugin: plugin) -> crc_cleaning_data | str:
        args = list(self.__xEditArgs)

        logFile = self.log_file_name(plugin)

        # Add unique per plugin args
        args.extend(
            (
                f'-R:"{logFile}"',
                f'"{plugin["name"]}"',
            )
        )

        logging.debug(
            f"Running MO2 Application: {self.__xEditExecutableName} Args: {args}"
        )
        exe = self.__organizer.startApplication(self.__xEditExecutableName, args)

        if exe == mobase.INVALID_HANDLE_VALUE:
            self.__canceled = True
            QMessageBox.critical(
                self,
                "Failed to start xEdit",
                f'Make sure xEdit is registered as an executable (Ctrl+E) with the name "{self.__xEditExecutableName}"',
            )
            return "Failed to start xEdit"

        waitResult, exitCode = self.__organizer.waitForApplication(exe, False)
        if not waitResult:
            self.__canceled = True
            return "Failed to wait for xEdit"

        if exitCode != 0:
            return f"xEdit exit code {exitCode}"

        cd = cleaning_data.LootData.from_xEdit_log(logFile)
        return cd if cd else "No LOOT cleaning data found in xEdit log file"


class CleanerPlugin(mobase.IPluginTool):

    __organizer: mobase.IOrganizer

    def __init__(self):
        super().__init__()

    def init(self, organizer: mobase.IOrganizer):
        self.__organizer = organizer
        return True

    @staticmethod
    def NAME() -> str:
        return "Batch Plugin Cleaner"

    def name(self) -> str:
        return CleanerPlugin.NAME()

    def author(self) -> str:
        return "bluebuiy & wxMichael & GoriRed"

    def displayName(self):
        return "Clean Plugins"

    def description(self) -> str:
        return f"Clean all plugins with one button. Requires {gameInfo[self.__organizer.managedGame().gameShortName()]["xEditName"]}"

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 2, 0, mobase.ReleaseType.FINAL)

    def isActive(self) -> bool:
        return self.__organizer.pluginSetting(self.name(), "enabled")  # type: ignore

    def tooltip(self) -> str:
        return "Clean all plugins at once"

    def settings(self) -> list[mobase.PluginSetting]:
        return [
            mobase.PluginSetting("enabled", "enable this plugin", True),
            mobase.PluginSetting("clean_beth", "Clean base game plugins", False),
            mobase.PluginSetting("clean_cc", "Clean Creation Club plugins", True),
            mobase.PluginSetting("clean_else", "Clean mod plugins", True),
            mobase.PluginSetting(
                "explicit_data_path",
                "If the data directory should be explicitly provided.  May need to be enabled if you get errors from xEdit.",
                False,
            ),
            mobase.PluginSetting(
                "explicit_ini_path",
                "If the ini path should be explicitly provided.  May need to be enabled if you get errors from xEdit.",
                False,
            ),
            # TODO: Re-enable this if I find a way to force xEdit to perform backups if disabled in GUI
            # mobase.PluginSetting(
            #    "save_dirty_plugins",
            #    "Saves xEdit backups of dirty plugins to 'Batch Plugin Cleaner' folder under MO2/Plugins/Data/ path.",
            #    True,
            # ),
            mobase.PluginSetting(
                "keep_logs",
                "xEdit log files to keep. 0=None, 1=Unknown, 3=Manual Cleaning Required, 4=Cleaned, 5=All",
                4,
            ),
            mobase.PluginSetting(
                "auto_close",
                "Auto close plugin selection window after clean.",
                True,
            ),
            mobase.PluginSetting(
                "exe_name_xedit",
                "Invoke xEdit as xEdit, not a game-specific name such as FO4Edit.",
                False,
            ),
            mobase.PluginSetting(
                "first_dynamic",
                "Will not auto select this plugin or any with higher priority",
                "",
            ),
            mobase.PluginSetting(
                "do_not_clean",
                "Will not allow cleaning of listed plugins even if known dirty. Comma separated list.",
                "",
            ),
        ]

    def icon(self) -> QIcon:
        return QIcon()

    def display(self) -> None:
        logging.debug(f"{self.name()} logging started")
        logging.debug(f"Game: {self.__organizer.managedGame().gameShortName()}")
        plugins = Plugins.All(self.__organizer)
        dialog = PluginSelectWindow(plugins, self._parentWidget())
        if dialog.exec():
            dialog = PluginProgressWindow(
                Plugins.Selected(plugins), self._parentWidget()
            )
            dialog.open()
            dialog.clean_all()

        logging.debug(f"{self.name()} logging finished")
