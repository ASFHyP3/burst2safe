from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import pytest
from osgeo import ogr, osr
from shapely.geometry import Polygon, box

from burst2safe import reparse_args


def create_polygon(out_path: Path, bounds: Iterable[Iterable[float]], epsg: int = 4326):
    polygons = [box(*bound) for bound in bounds]  # type: ignore[arg-type]
    driver = ogr.GetDriverByName('GeoJSON')

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)

    vector_file = driver.CreateDataSource(str(out_path))

    layer = vector_file.CreateLayer('test', srs, geom_type=ogr.wkbPolygon)
    for polygon in polygons:
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(ogr.CreateGeometryFromWkt(polygon.wkt))
        layer.CreateFeature(feature)
        feature = None
    vector_file = None


def test_vector_to_shapely_latlon_polygon(tmp_path):
    vector_file = tmp_path / 'test.geojson'
    bounds = [[0, 0, 1, 1]]

    create_polygon(vector_file, bounds)
    polygon = reparse_args.vector_to_shapely_latlon_polygon(vector_file)
    assert isinstance(polygon, Polygon)
    assert polygon.bounds == (0, 0, 1, 1)

    create_polygon(vector_file, bounds, 32606)
    polygon = reparse_args.vector_to_shapely_latlon_polygon(vector_file)
    assert isinstance(polygon, Polygon)
    assert polygon.bounds != (0, 0, 1, 1)

    bounds.append([1, 1, 2, 2])
    with pytest.raises(ValueError, match='File contains*'):
        create_polygon(vector_file, bounds)
        reparse_args.vector_to_shapely_latlon_polygon(vector_file)


def test_get_bbox():
    extent = ['1.0', '0.0', '2.0', '2..0']
    with pytest.raises(ValueError, match='.*multiple points'):
        reparse_args.get_bbox(extent)

    extent = ['1.0', 'm', '2.0', '2.0']
    with pytest.raises(ValueError, match='.*not a number'):
        reparse_args.get_bbox(extent)

    extent = ['1.0', '0.0', '200.0', '2.0']
    with pytest.raises(ValueError, match='.*not between -180 and 180'):
        reparse_args.get_bbox(extent)

    extent = ['2.0', '0.0', '0.0', '1.0']
    with pytest.raises(ValueError, match='.*larger than the east longitude'):
        reparse_args.get_bbox(extent)

    extent = ['1.0', '0.0', '2.0', '200.0']
    with pytest.raises(ValueError, match='.*not between -90 and 90'):
        reparse_args.get_bbox(extent)

    extent = ['1.0', '2.0', '2.0', '0.0']
    with pytest.raises(ValueError, match='.*larger than the north latitude'):
        reparse_args.get_bbox(extent)

    extent = ['1.0', '0.0', '2.0', '1.0']
    assert reparse_args.get_bbox(extent) == box(1, 0, 2, 1)


def test_reparse_args_burst2safe():
    class MockArgs:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.__dict__['mode'] = None

    args1 = MockArgs(granules=['granule1', 'granule2'], orbit=123)
    with pytest.raises(ValueError, match='Cannot provide*'):
        reparse_args.reparse_args(args1, 'burst2safe')  # type: ignore[arg-type]

    args2 = MockArgs(orbit=123)
    with pytest.raises(ValueError, match='Must provide*'):
        reparse_args.reparse_args(args2, 'burst2safe')  # type: ignore[arg-type]

    args3 = MockArgs(orbit=123, extent=['0', '0', '1', '1'], pols=['vv'], swaths=['iw1'])
    out_args = reparse_args.reparse_args(args3, 'burst2safe')  # type: ignore[arg-type]
    assert out_args.pols == ['VV']
    assert out_args.swaths == ['IW1']
    assert out_args.extent == box(0, 0, 1, 1)

    granules = ['S1_136231_IW2_20200604T022312_VV_7C85-BURST', 'S1_136232_IW2_20200604T022315_VV_7C85-BURST']
    args4 = MockArgs(granules=granules)
    out_args = reparse_args.reparse_args(args4, 'burst2safe')  # type: ignore[arg-type]
    assert out_args.granules == granules


def test_reparse_args_burst2stack():
    class MockArgs:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    args1 = MockArgs(rel_orb=123)
    with pytest.raises(ValueError, match='Must provide*'):
        reparse_args.reparse_args(args1, 'burst2stack')  # type: ignore[arg-type]

    args2 = MockArgs(
        rel_orbit=123,
        start_date='2021-01-01',
        end_date='2021-02-01',
        extent=['0', '0', '1', '1'],
        pols=['vv'],
        swaths=['iw1'],
    )
    out_args = reparse_args.reparse_args(args2, 'burst2stack')  # type: ignore[arg-type]
    assert out_args.start_date == datetime.fromisoformat('2021-01-01')
    assert out_args.end_date == datetime.fromisoformat('2021-02-01')
    assert out_args.pols == ['VV']
    assert out_args.swaths == ['IW1']
    assert out_args.extent == box(0, 0, 1, 1)
