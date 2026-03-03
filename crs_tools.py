import math
import os
import configparser
from typing import Dict, Optional, Tuple

from qgis.PyQt.QtCore import QSettings
from qgis.core import QgsCoordinateReferenceSystem


USK2000_EPSG_MIN = 6381
USK2000_EPSG_MAX = 6387

SK63_REGION_EPSG_MIN = 7825
SK63_REGION_EPSG_MAX = 7831


def _normalize_lon_deg(lon_deg: float) -> float:
    lon = float(lon_deg)
    while lon <= -180.0:
        lon += 360.0
    while lon > 180.0:
        lon -= 360.0
    return lon


def epsg_by_longitude(
    lon_deg: float,
    epsg_min: int,
    epsg_max: int,
    zone_width_deg: float = 3.0,
    first_zone_central_meridian_deg: float = 21.0,
) -> Optional[int]:
    """
    Selects an EPSG code within [epsg_min, epsg_max] based on longitude.

    Assumption: zones are consecutive and have equal width (default 3°), with
    central meridians: 21, 24, 27, 30, 33, 36, 39 (for 7 zones).
    """
    try:
        epsg_min = int(epsg_min)
        epsg_max = int(epsg_max)
        if epsg_max < epsg_min:
            return None

        n_zones = epsg_max - epsg_min + 1
        if n_zones <= 0:
            return None

        lon = _normalize_lon_deg(float(lon_deg))

        half = float(zone_width_deg) / 2.0
        lower_boundary = float(first_zone_central_meridian_deg) - half
        idx0 = int(math.floor((lon - lower_boundary) / float(zone_width_deg)))
        idx0 = max(0, min(n_zones - 1, idx0))
        return epsg_min + idx0
    except Exception:
        return None


def usk2000_epsg_by_longitude(lon_deg: float) -> Optional[int]:
    return epsg_by_longitude(lon_deg, USK2000_EPSG_MIN, USK2000_EPSG_MAX)


def sk63_region_epsg_by_longitude(lon_deg: float) -> Optional[int]:
    return epsg_by_longitude(lon_deg, SK63_REGION_EPSG_MIN, SK63_REGION_EPSG_MAX)


def is_usk2000_epsg(authid: str) -> bool:
    try:
        s = (authid or "").strip().upper()
        if not s.startswith("EPSG:"):
            return False
        code = int(s.split(":", 1)[1])
        return USK2000_EPSG_MIN <= code <= USK2000_EPSG_MAX
    except Exception:
        return False


def _read_ini_wkt2_map(ini_path: str) -> Dict[str, str]:
    cfg = configparser.ConfigParser()
    cfg.optionxform = str  # keep case
    cfg.read(ini_path, encoding="utf-8")
    out: Dict[str, str] = {}
    for section in cfg.sections():
        name = str(section).strip()
        wkt2 = str(cfg.get(section, "wkt2", fallback="") or "").strip()
        if name and wkt2:
            out[name] = wkt2
    return out


def import_custom_crs_from_wkt2_ini_once(
    ini_path: str,
    settings_key_prefix: str,
) -> Tuple[int, int]:
    """
    Imports custom CRS definitions from an ini file into QGIS user CRS database.

    Returns: (imported_ok, imported_failed).
    """
    try:
        ini_path = os.path.abspath(str(ini_path))
        if not os.path.exists(ini_path):
            return 0, 0

        mtime = int(os.path.getmtime(ini_path))
        key_mtime = f"{settings_key_prefix}/mtime"
        key_done = f"{settings_key_prefix}/done"

        prev_mtime = QSettings().value(key_mtime, None)
        prev_done = QSettings().value(key_done, False)
        try:
            prev_mtime_i = int(prev_mtime) if prev_mtime is not None else None
        except Exception:
            prev_mtime_i = None

        if bool(prev_done) and prev_mtime_i == mtime:
            return 0, 0

        wkt_map = _read_ini_wkt2_map(ini_path)
        ok_count = 0
        bad_count = 0

        for name, wkt2 in wkt_map.items():
            try:
                crs = QgsCoordinateReferenceSystem()
                created = False
                if hasattr(crs, "createFromWkt"):
                    created = bool(crs.createFromWkt(wkt2))
                else:
                    crs = QgsCoordinateReferenceSystem(wkt2)
                    created = crs.isValid()

                if not created or not crs.isValid():
                    bad_count += 1
                    continue

                crs.saveAsUserCrs(name)
                ok_count += 1
            except Exception:
                bad_count += 1

        QSettings().setValue(key_mtime, mtime)
        QSettings().setValue(key_done, True)
        return ok_count, bad_count
    except Exception:
        return 0, 0


def import_sk63_cpt_custom_crs_once(plugin_dir: str) -> Tuple[int, int]:
    ini_path = os.path.join(str(plugin_dir), "templates", "crs63cpt_wkt2.ini")
    return import_custom_crs_from_wkt2_ini_once(
        ini_path=ini_path,
        settings_key_prefix="xml_ua/crs_import/crs63cpt_wkt2",
    )
