"""S12 L1: every layer of every road-network version in the manifest's months, as stored.

    python -m src.clean.s12_parse

Needs data/interim/manifest/RdNet_IRNP.gdb.zip.csv (python -m src.clean.manifest ...).
A bundle member `<YYYYMMDD-HHMM>-RdNet_IRNP.gdb.zip` is one version: a zipped Esri File
Geodatabase with 17 layers (docs/raw_data.md, S12). GDAL reads it in place, nothing is extracted:
    /vsizip/{/vsizip/<bundle>/<member>}/RdNet_IRNP.gdb
Members that are not `*-RdNet_IRNP.gdb.zip` (the bundle's data-dictionary.pdf pointer) are
skipped and listed.

Output:
- data/interim/l1/s12/<LAYER>/<bundle YYYYMM>.parquet, one row per feature of every version in
  the bundle:
    bundle, index      the version (the zip member, see the manifest)
    OBJECTID           the feature id
    <fields>           every attribute, in the layer's order, with the type GDAL gives (string,
                       int16 / int32, double, timestamp[ms]); null stays null
    SHAPE              the geometry as ISO WKB (see below); only in layers with geometry
  The versions of one bundle must have the same columns, otherwise this raises.
- data/interim/checks/s12_layers.csv, one row per version and layer: bundle, index, member,
  layer, geometry_type (as GDAL reports it, with Z / M), crs, n_features, fields (name:type).

Geometry: pyogrio turns measured geometries into 2D (warning "Measured (M) geometry types are
not supported", which is silenced here), and 6 layers carry real M values (VEHICLE_RESTRICTION,
SPEED_LIMIT, PROHIBITION, PERMIT, PEDESTRIAN_ZONE, BUS_ONLY_LANE). So the attributes come from
pyogrio.raw.read_arrow and the geometry from GDAL's C API through ctypes (OGR_G_ExportToIsoWkb,
little-endian), which keeps Z, M and curves (with GDAL's non-linear geometry flag on, which pyogrio turns off:
otherwise curves come back as approximating lines). Both use the same GDAL library (checked by
version).
The two reads must give the same feature ids in the same order, and in a layer whose type has
neither Z nor M the two WKBs must be byte-identical (a check of the ctypes path).

Not kept: File Geodatabase metadata beyond the above (domains, aliases, indexes, relationships);
see the data specification in data/raw/static.data.gov.hk/td/road-network-v2/RdNet_IRNP.gdb.zip/
data-dictionary/.
"""

from __future__ import annotations

import csv
import ctypes
import sys
import warnings
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.clean.s1_parse import L1_DIR
from src.clean.s1_periods import OUT_DIR as CHECKS_DIR
from src.config import RAW_DIR

RESOURCE = "RdNet_IRNP.gdb.zip"
BUNDLES = RAW_DIR / "static.data.gov.hk/td/road-network-v2/RdNet_IRNP.gdb.zip/bundle"
GDB = "RdNet_IRNP.gdb"
OUT_DIR = L1_DIR / "s12"
LAYERS = CHECKS_DIR / "s12_layers.csv"
LAYER_COLUMNS = ["bundle", "index", "member", "layer", "geometry_type", "crs", "n_features", "fields"]
# The lib/ of the environment pyogrio is installed in (<env>/lib/pythonX.Y/site-packages/pyogrio),
# not sys.prefix: a venv with system site packages uses the base environment's pyogrio and GDAL.
# Checked with conda's pyogrio, which links that library; gdal() checks the version against pyogrio.
# TODO: pyogrio wheels from pip bundle their own GDAL elsewhere; not checked, so this raises there.
GDAL_LIB = Path(pyogrio.__file__).parents[3] / ("libgdal.dylib" if sys.platform == "darwin" else "libgdal.so")
WKB_NONE = 100  # OGRwkbGeometryType wkbNone: a layer without geometry
M_WARNING = r"Measured \(M\) geometry types are not supported"


def gdal() -> ctypes.CDLL:
    """The GDAL library of this Python environment, with the OGR functions used here."""
    if not GDAL_LIB.exists():
        raise FileNotFoundError(f"{GDAL_LIB} not found (the GDAL library pyogrio uses)")
    lib = ctypes.CDLL(str(GDAL_LIB))
    p, s, i = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    for name, res, args in [
        ("GDALVersionInfo", s, [s]), ("GDALAllRegister", None, []),
        ("GDALOpenEx", p, [s, ctypes.c_uint, p, p, p]), ("GDALClose", None, [p]),
        ("GDALDatasetGetLayerByName", p, [p, s]),
        ("OGR_L_GetGeomType", i, [p]), ("OGR_L_ResetReading", None, [p]),
        ("OGR_L_GetNextFeature", p, [p]), ("OGR_F_GetFID", ctypes.c_int64, [p]),
        ("OGR_F_GetGeometryRef", p, [p]), ("OGR_F_Destroy", None, [p]),
        ("OGR_G_WkbSizeEx", ctypes.c_size_t, [p]), ("OGR_G_ExportToIsoWkb", i, [p, i, s]),
        ("OGR_GT_HasZ", i, [i]), ("OGR_GT_HasM", i, [i]), ("OGRGeometryTypeToName", s, [i]),
        ("OGRGetNonLinearGeometriesEnabledFlag", i, []), ("OGRSetNonLinearGeometriesEnabledFlag", None, [i]),
    ]:
        f = getattr(lib, name)
        f.restype, f.argtypes = res, args
    version = lib.GDALVersionInfo(b"RELEASE_NAME").decode()
    if version != pyogrio.__gdal_version_string__:
        raise RuntimeError(f"{GDAL_LIB} is GDAL {version}, pyogrio uses {pyogrio.__gdal_version_string__}")
    lib.GDALAllRegister()
    return lib


def geometries(lib: ctypes.CDLL, ds: int, layer: str, where: str) -> tuple[int, list[int], list[bytes | None]]:
    """(layer geometry type, feature ids, ISO WKB or None) in reading order, through the C API."""
    lyr = lib.GDALDatasetGetLayerByName(ds, layer.encode())
    if not lyr:
        raise ValueError(f"{where}: GDAL finds no layer {layer}")
    # With this flag off, the C API returns curves as approximating lines. pyogrio turns it off,
    # so it is turned on for these reads and restored afterwards.
    before = lib.OGRGetNonLinearGeometriesEnabledFlag()
    lib.OGRSetNonLinearGeometriesEnabledFlag(1)
    try:
        gtype = lib.OGR_L_GetGeomType(lyr)
        fids, wkbs = [], []
        lib.OGR_L_ResetReading(lyr)
        while f := lib.OGR_L_GetNextFeature(lyr):
            fids.append(lib.OGR_F_GetFID(f))
            g = lib.OGR_F_GetGeometryRef(f)
            if g:
                buf = ctypes.create_string_buffer(lib.OGR_G_WkbSizeEx(g))
                if lib.OGR_G_ExportToIsoWkb(g, 1, buf) != 0:
                    raise ValueError(f"{where}: {layer} feature {fids[-1]}: WKB export failed")
                wkbs.append(buf.raw)
            else:
                wkbs.append(None)
            lib.OGR_F_Destroy(f)
    finally:
        lib.OGRSetNonLinearGeometriesEnabledFlag(before)
    return gtype, fids, wkbs


def _describe(wkb: bytes | None) -> str:
    return "null" if wkb is None else f"ISO type {int.from_bytes(wkb[1:5], 'little')}, {len(wkb)} bytes"


def read_layer(lib: ctypes.CDLL, ds: int, path: str, layer: str, where: str) -> tuple[pa.Table, dict]:
    """One layer of one version: attributes from pyogrio, geometry from the C API."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=M_WARNING)
        meta, table = pyogrio.raw.read_arrow(path, layer=layer, return_fids=True)
    fid_col, geom_col = meta["fid_column"], meta["geometry_name"]
    if fid_col not in table.column_names:
        raise ValueError(f"{where}: {layer}: no feature id column {fid_col!r} in {table.column_names}")
    gtype, fids, wkbs = geometries(lib, ds, layer, where)
    if table[fid_col].to_pylist() != fids:
        raise ValueError(f"{where}: {layer}: feature ids differ between pyogrio and the C API")
    if gtype == WKB_NONE:
        if geom_col or any(w is not None for w in wkbs):
            raise ValueError(f"{where}: {layer}: no geometry type, but geometry found")
    else:
        if not geom_col:
            raise ValueError(f"{where}: {layer}: geometry type {gtype}, but pyogrio gives no geometry column")
        if not (lib.OGR_GT_HasZ(gtype) or lib.OGR_GT_HasM(gtype)):
            arrow = table[geom_col].to_pylist()
            diff = [k for k, (a, b) in enumerate(zip(arrow, wkbs)) if a != b]
            if diff:
                k = diff[0]
                raise ValueError(f"{where}: {layer}: 2D layer, but {len(diff)} of {len(wkbs)} geometries differ "
                                 f"between pyogrio and the C API; first: feature {fids[k]}, "
                                 f"{_describe(arrow[k])} vs {_describe(wkbs[k])}")
        table = table.set_column(table.column_names.index(geom_col), geom_col, pa.array(wkbs, pa.binary()))
    info = {"layer": layer, "geometry_type": lib.OGRGeometryTypeToName(gtype).decode(), "crs": meta["crs"],
            "n_features": table.num_rows,
            "fields": ";".join(f"{f.name}:{f.type}" for f in table.schema if f.name != geom_col)}
    return table, info


def build() -> None:
    with (MANIFEST_DIR / f"{RESOURCE}.csv").open() as f:
        firsts = [r for r in csv.DictReader(f) if r["group"] == f"{r['bundle']}:{r['index']}"]
    lib = gdal()
    layer_rows = []
    for bundle in sorted({r["bundle"] for r in firsts}):
        tables: dict[str, list[pa.Table]] = {}
        infos = zipfile.ZipFile(BUNDLES / bundle).infolist()
        for r in (r for r in firsts if r["bundle"] == bundle):
            i, where = int(r["index"]), f"{bundle}:{r['index']} {r['member']}"
            if not r["member"].endswith(f"-{RESOURCE}"):
                print(f"skipped {where}: not {RESOURCE}")
                continue
            # the manifest keeps the file name only; the zip member has a folder before it
            member = infos[i].filename
            if member.rsplit("/", 1)[-1] != r["member"]:
                raise ValueError(f"{where}: zip member {i} is {member}")
            path = f"/vsizip/{{/vsizip/{BUNDLES / bundle}/{member}}}/{GDB}"
            ds = lib.GDALOpenEx(path.encode(), 0x04, None, None, None)  # GDAL_OF_VECTOR
            if not ds:
                raise ValueError(f"{where}: GDAL cannot open {path}")
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message=M_WARNING)
                    names = [str(n) for n, _ in pyogrio.list_layers(path)]
                for name in names:
                    table, info = read_layer(lib, ds, path, name, where)
                    if {"bundle", "index"} & set(table.column_names):
                        raise ValueError(f"{where}: {name} has a column named bundle or index")
                    n = table.num_rows
                    table = pa.Table.from_arrays(
                        [pa.array([bundle] * n, pa.string()), pa.array([i] * n, pa.int32()), *table.columns],
                        names=["bundle", "index", *table.column_names])
                    tables.setdefault(name, []).append(table)
                    layer_rows.append({"bundle": bundle, "index": i, "member": r["member"], **info})
            finally:
                lib.GDALClose(ds)
            print(f"{where}: {len(names)} layers")
        for name, parts in sorted(tables.items()):
            out = OUT_DIR / name / f"{bundle[:6]}.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.concat_tables(parts), out.with_suffix(".parquet.part"), compression="zstd")
            out.with_suffix(".parquet.part").replace(out)
        print(f"{bundle}: {len(tables)} layers written to {OUT_DIR}/<LAYER>/{bundle[:6]}.parquet")
    LAYERS.parent.mkdir(parents=True, exist_ok=True)
    with LAYERS.open("w", newline="") as f:
        w = csv.DictWriter(f, LAYER_COLUMNS)
        w.writeheader()
        w.writerows(layer_rows)
    print(f"{len(layer_rows)} version x layer rows: {LAYERS}")


if __name__ == "__main__":
    build()
