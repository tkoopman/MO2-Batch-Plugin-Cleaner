# Created by GoriRed
# Version: 1.2
# License: CC-BY-NC
# https://github.com/tkoopman/MO2-Batch-Plugin-Cleaner

import binascii
import csv
import enum
import logging
import re
import os
import site
import traceback

site.addsitedir(os.path.join(os.path.dirname(__file__), "lib"))

from yaml import Dumper


from pathlib import Path
from typing import Any, Callable

import yaml


def convert_to_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int):
        return value

    try:
        return int(value)
    except ValueError:
        return default


class crc32:

    def __init__(self, crc: int | str):
        if isinstance(crc, int):
            self.crc = crc
        else:
            self.crc = int(crc, 16)

    @staticmethod
    def from_file(filename: str | Path, chunk_size: int = 16384) -> "crc32":
        if isinstance(filename, str):
            filename = Path(filename)
        if not filename.is_file():
            return crc32(0)

        try:
            with open(filename, "rb") as file:
                crc = 0
                while chunk := file.read(chunk_size):
                    crc = binascii.crc32(chunk, crc)
                return crc32(crc & 0xFFFFFFFF)
        except Exception as e:
            logging.error(f'Error calculating CRC of "{filename}"')
            logging.error(traceback.format_exception(e))
            return crc32(0)

    @staticmethod
    def crc32_presenter(dumper: Dumper, data: "crc32"):
        return dumper.represent_int(str(data))  # type: ignore

    def __str__(self) -> str:
        return f"0x{self.crc:X}"

    def __repr__(self) -> str:
        return f"0x{self.crc:X}"

    def __int__(self) -> int:
        return self.crc

    def __hash__(self) -> int:
        return hash(self.crc)

    @staticmethod
    def _compare(lhs: Any, rhs: Any, method: Callable[[int, int], bool]) -> bool:
        lhs = (
            lhs.crc
            if isinstance(lhs, crc32)
            else crc32(lhs).crc if isinstance(lhs, str) else lhs
        )

        rhs = (
            rhs.crc
            if isinstance(rhs, crc32)
            else crc32(rhs).crc if isinstance(rhs, str) else rhs
        )

        if isinstance(lhs, int) and isinstance(rhs, int):
            return method(lhs, rhs)

        return NotImplemented

    def __lt__(self, other: Any) -> bool:
        return crc32._compare(self, other, lambda l, r: l < r)

    def __le__(self, other: Any) -> bool:
        return crc32._compare(self, other, lambda l, r: l <= r)

    def __eq__(self, other: Any) -> bool:
        return crc32._compare(self, other, lambda l, r: l == r)

    def __ge__(self, other: Any) -> bool:
        return crc32._compare(self, other, lambda l, r: l >= r)

    def __gt__(self, other: Any) -> bool:
        return crc32._compare(self, other, lambda l, r: l > r)

    def __ne__(self, other: Any) -> bool:
        return crc32._compare(self, other, lambda l, r: l != r)


class source(enum.Enum):
    LOOT = enum.auto()
    USER = enum.auto()


class cleaning_data:

    def __init__(self, itm: int, udr: int, nav: int, source: source):
        self.itm = itm
        self.udr = udr
        self.nav = nav
        self.source = source

    @staticmethod
    def from_dict(data: Any, source: source) -> "cleaning_data | None":

        if isinstance(data, dict):
            itm = convert_to_int(data["itm"]) if "itm" in data else 0  # type: ignore
            udr = convert_to_int(data["udr"]) if "udr" in data else 0  # type: ignore
            nav = convert_to_int(data["nav"]) if "nav" in data else 0  # type: ignore

            return cleaning_data(itm, udr, nav, source)

        return None

    def is_clean(self) -> bool:
        return not self.itm and not self.udr and not self.nav

    def is_auto_cleanable(self) -> bool:
        return self.itm > 0 or self.udr > 0

    def requires_manual_fix(self) -> bool:
        return self.nav > 0


class crc_cleaning_data(dict[str, dict[crc32, cleaning_data]]):
    def __init__(self):
        super().__init__()  # type: ignore

    def __getitem__(self, key: str):
        return super().__getitem__(key.casefold())

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return super().__contains__(key.casefold())
        return False

    def __setitem__(self, key: str, value: dict[crc32, cleaning_data]) -> None:
        super().__setitem__(key.casefold(), value)

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key.casefold())

    def find(self, name: str, crc: crc32 | None) -> cleaning_data | None:
        name = name.casefold()
        if crc and name in self and crc in self[name]:
            return self[name][crc]
        return None

    def update_data(self, new_data: "crc_cleaning_data") -> None:
        for name in new_data:
            if name not in self:
                self[name] = {}
            for crc in new_data[name]:
                self[name][crc] = new_data[name][crc]


class CsvData:
    @staticmethod
    def load(filename: str | Path) -> crc_cleaning_data:
        crc_data = crc_cleaning_data()
        if isinstance(filename, str):
            filename = Path(filename)

        if not filename.is_file():
            logging.debug(f'File "{filename}" not found.')
            return crc_data

        try:
            with open(filename, "r") as csvFile:
                reader = csv.DictReader(csvFile)
                for line in reader:
                    name = line["name"] if "name" in line else None
                    if name:
                        cd = cleaning_data.from_dict(line, source.USER)
                        crc = line["crc"] if "crc" in line else None
                        if cd and crc:
                            name = name.casefold()
                            if name not in crc_data:
                                crc_data[name] = {}

                            crc_data[name][crc32(crc)] = cd
            logging.debug(f'Read user cleaning data from "{filename}".')
        except Exception as e:
            logging.error(f'Error reading "{filename}"')
            logging.error(traceback.format_exception(e))

        return crc_data

    @staticmethod
    def save(
        data: crc_cleaning_data,
        filename: str | Path,
        only_source: source | None = source.USER,
    ) -> None:
        try:
            with open(filename, "w", newline="") as csvFile:
                writer = csv.DictWriter(
                    csvFile, ["crc", "name", "itm", "udr", "nav"], lineterminator="\n"
                )
                writer.writeheader()
                for name in sorted(data.keys()):
                    for crc in sorted(data[name]):
                        cd = data[name][crc]
                        if only_source is None or only_source == cd.source:
                            writer.writerow(
                                {
                                    "crc": str(crc),
                                    "name": name,
                                    "itm": cd.itm,
                                    "udr": cd.udr,
                                    "nav": cd.nav,
                                }
                            )
            logging.debug(f'Saved user cleaning data to "{filename}".')
        except Exception as e:
            logging.error(f'Error writing to "{filename}"')
            logging.error(traceback.format_exception(e))


class LootData:
    PRELUDE = """\
prelude:
  common:
    - &quickClean
      util: ''
    - &reqManualFix
      util: ''
plugins:
"""

    @staticmethod
    def __from_raw(data: Any, source: source) -> crc_cleaning_data | None:
        if not isinstance(data, dict) or "plugins" not in data:
            logging.error("Invalid LOOT data format")
            return None

        data = data["plugins"]
        if not isinstance(data, list):
            logging.error("Invalid LOOT data format")
            return None

        crc_data = crc_cleaning_data()
        for plugin in data:  # type: ignore
            if isinstance(plugin, dict):
                name = plugin["name"] if "name" in plugin else None  # type: ignore
                if isinstance(name, str):
                    for state in ["dirty", "clean"]:
                        if state in plugin:
                            raw_data = plugin[state]  # type: ignore
                            if isinstance(raw_data, list):
                                for e in raw_data:  # type: ignore
                                    if isinstance(e, dict):
                                        cd = cleaning_data.from_dict(e, source)
                                        crc = e["crc"] if "crc" in e else None  # type: ignore
                                        if cd and isinstance(crc, str):
                                            name = name.casefold()
                                            if name not in crc_data:
                                                crc_data[name] = {}
                                            crc_data[name][crc32(crc)] = cd
        return crc_data

    @staticmethod
    def from_xEdit_log(logFile: str | Path) -> crc_cleaning_data | None:
        if isinstance(logFile, str):
            logFile = Path(logFile)

        if logFile.is_file():
            with open(logFile, mode="r", encoding="utf-8", errors="ignore") as file:
                text = file.read()
                file.close()
                lme = re.search(
                    r"LOOT Masterlist Entries[\r\n]+((?:  .*[\r\n]+)+)",
                    text,
                    re.RegexFlag.NOFLAG,
                )
                if lme:
                    extractedYaml = LootData.PRELUDE + lme.group(1)
                    raw = yaml.load(extractedYaml, Loader=yaml.loader.BaseLoader)
                    return LootData.__from_raw(raw, source.USER)

        logging.error(f'No LOOT cleaning data found in xEdit log file "{logFile}".')
        return None

    @staticmethod
    def load(filename: str) -> "crc_cleaning_data | None":
        if not Path(filename).is_file():
            logging.debug(f'File "{filename}" not found.')
            return None

        try:
            with open(filename, "r") as file:
                text = file.read()
                file.close()
                raw = yaml.load(text, Loader=yaml.loader.BaseLoader)
                logging.debug(f'Read LOOT master list file "{filename}".')
                return LootData.__from_raw(raw, source.LOOT)
        except Exception as e:
            logging.error(f'Error reading "{filename}"')
            logging.error(traceback.format_exception(e))
