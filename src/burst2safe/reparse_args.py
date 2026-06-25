import json
from argparse import Namespace
from datetime import datetime

from osgeo import gdal, ogr, osr
from shapely.geometry import box, shape


gdal.UseExceptions()

def reparse_args(args: Namespace, tool: str) -> Namespace:
    """Parse the arguments for burst2safe and burst2stack CLIs.

    Args:
        args: The parsed argument namespace.
        tool: The tool to parse arguments for (burst2safe or burst2stack).

    Returns:
        The parsed argument namespace.
    """
    arg_dict = args.__dict__
    tool_keywords = {
        'burst2safe': ['orbit', 'extent'],
        'burst2stack': ['rel_orbit', 'start_date', 'end_date', 'extent'],
    }
    keywords = tool_keywords[tool]

    using_granule = len(arg_dict.get('granules', [])) > 0
    used_keyword = [arg_dict.get(x, None) is not None for x in keywords]
    using_keywords = any(used_keyword)

    if arg_dict.get('mode', None) is None:
        args.mode = 'IW'

    if using_granule and using_keywords:
        raise ValueError(f'Cannot provide both granules and any of {", ".join(keywords)} arguments.')

    if not using_granule and not all(used_keyword):
        raise ValueError(f'Must provide at least {", ".join(keywords)} arguments.')

    if tool == 'burst2stack':
        args.start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        args.end_date = datetime.strptime(args.end_date, '%Y-%m-%d')

    if using_keywords:
        if args.mode not in ['IW', 'EW']:
            raise ValueError('--mode must be either IW or EW.')
        if args.pols:
            args.pols = [pol.upper() for pol in args.pols]
        if args.swaths:
            args.swaths = [swath.upper() for swath in args.swaths]

        if args.extent:
            if len(args.extent) == 1:
                args.extent = vector_to_shapely_latlon_polygon(args.extent[0])
            elif len(args.extent) == 4:
                args.extent = get_bbox(args.extent)
            else:
                raise ValueError(
                    'The argument provided to --extent could not be interpreted as a bounding box (W S E N in lat/lon) or a geometry file.'
                )
    return args

def vector_to_shapely_latlon_polygon(vector_file_path):
    dataset = ogr.Open(vector_file_path)

    if dataset is None:
        raise ValueError(f'Could not open file: {vector_file_path}')

    layer = dataset.GetLayer()

    feature_count = layer.GetFeatureCount()
    if feature_count != 1:
        raise ValueError(f'File contains {feature_count} features, but exactly one is required.')

    feature = layer.GetFeature(0)
    geom = feature.GetGeometryRef()
    if geom.GetGeometryType() != ogr.wkbPolygon:
        raise ValueError('The feature is not a polygon.')

    source_srs = layer.GetSpatialRef()
    if int(source_srs.GetAuthorityCode(None)) != 4326:
        target_srs = osr.SpatialReference()
        target_srs.ImportFromEPSG(4326)
        transform = osr.CoordinateTransformation(source_srs, target_srs)
        geom.Transform(transform)

    polygon = shape(json.loads(geom.ExportToJson()))
    dataset = None

    return polygon



def get_bbox(extent):
    """Returns the extent if it meets the requirements

    Args:
        extent: lat/lon list in the format (W S E N)

    Returns:
        Bounding box
    """
    if not all(item.count('.') <= 1 and item.count('-') <= 1 for item in extent):
        raise ValueError('One item in the extent has multiple points')
    elif not all(item.replace('.', '').replace('-', '').isdigit() for item in extent):
        raise ValueError('One item in the extent is not a number')
    elif not (abs(float(extent[0])) <= 180 and abs(float(extent[2])) <= 180):
        raise ValueError('The longitudes are not between -180 and 180')
    elif float(extent[0]) >= float(extent[2]):
        raise ValueError('The west longitude is larger than the east longitude')
    elif not (abs(float(extent[1])) <= 90 and abs(float(extent[3])) <= 90):
        raise ValueError('The latitudes are not between -90 and 90')
    elif float(extent[1]) >= float(extent[3]):
        raise ValueError('The south latitude is larger than the north latitude')
    else:
        return box(*[float(x) for x in extent])  # type: ignore[arg-type]
