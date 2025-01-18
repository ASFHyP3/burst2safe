# mypy: disable-error-code="union-attr"
import json
import warnings
from argparse import Namespace
from binascii import crc_hqx
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union

import lxml.etree as ET
from asf_search.Products.S1BurstProduct import S1BurstProduct
from osgeo import gdal, ogr, osr
from shapely.geometry import box, shape


gdal.UseExceptions()
warnings.filterwarnings('ignore')


@dataclass
class BurstInfo:
    """Dataclass for storing burst information."""

    granule: Optional[str]
    slc_granule: Optional[str]
    swath: str
    polarization: str
    burst_id: Optional[int]
    burst_index: int
    direction: str
    absolute_orbit: int
    relative_orbit: int
    date: Optional[datetime]
    data_url: Optional[str]
    data_path: Optional[Path]
    metadata_url: Optional[str]
    metadata_path: Path
    start_utc: Optional[datetime] = None
    stop_utc: Optional[datetime] = None
    length: Optional[int] = None
    width: Optional[int] = None

    def add_shape_info(self):
        """Add shape information to the BurstInfo object."""
        annotation = get_subxml_from_metadata(self.metadata_path, 'product', self.swath, self.polarization)
        self.length = int(annotation.find('swathTiming/linesPerBurst').text)  # type: ignore[arg-type]
        self.width = int(annotation.find('swathTiming/samplesPerBurst').text)  # type: ignore[arg-type]

    def add_start_stop_utc(self):
        """Add start and stop UTC to burst info.
        There is spatial overlap between bursts, so burst start/stop times will overlap as well.
        """
        annotation = get_subxml_from_metadata(self.metadata_path, 'product', self.swath, self.polarization)
        start_utcs = [datetime.fromisoformat(x.find('azimuthTime').text) for x in annotation.findall('.//burst')]  # type: ignore[arg-type]
        self.start_utc = start_utcs[self.burst_index]

        azimuth_time_interval = float(annotation.find('.//azimuthTimeInterval').text)  # type: ignore[arg-type]
        assert self.length is not None
        burst_time_interval = timedelta(seconds=(self.length - 1) * azimuth_time_interval)
        self.stop_utc = self.start_utc + burst_time_interval


def create_burst_info(product: S1BurstProduct, work_dir: Path) -> BurstInfo:
    """Create a BurstInfo object given a granule.

    Args:
        product: A S1BurstProduct object
        work_dir: The directory to save the data to.
    """
    slc_granule = product.umm['InputGranules'][0].split('-')[0]

    burst_granule = product.properties['fileID']
    direction = product.properties['flightDirection'].upper()
    polarization = product.properties['polarization'].upper()
    absolute_orbit = int(product.properties['orbit'])
    relative_orbit = int(product.properties['pathNumber'])
    data_url = product.properties['url']
    metadata_url = product.properties['additionalUrls'][0]

    swath = product.properties['burst']['subswath'].upper()
    burst_id = int(product.properties['burst']['relativeBurstID'])
    burst_index = int(product.properties['burst']['burstIndex'])

    date_format = '%Y%m%dT%H%M%S'
    burst_time_str = burst_granule.split('_')[3]
    burst_time = datetime.strptime(burst_time_str, date_format)
    data_path = work_dir / f'{burst_granule}.tiff'
    metadata_path = work_dir / f'{slc_granule}_{polarization}.xml'

    burst_info = BurstInfo(
        burst_granule,
        slc_granule,
        swath,
        polarization,
        burst_id,
        burst_index,
        direction,
        absolute_orbit,
        relative_orbit,
        burst_time,
        data_url,
        data_path,
        metadata_url,
        metadata_path,
    )
    return burst_info


def get_burst_infos(products: Iterable[S1BurstProduct], work_dir: Optional[Path]) -> List[BurstInfo]:
    """Get burst information from ASF Search.

    Args:
        products: A list of S1BurstProduct objects.
        work_dir: The directory to save the data to.

    Returns:
        A list of BurstInfo objects.
    """
    work_dir = optional_wd(work_dir)
    burst_info_list = []
    for product in products:
        burst_info = create_burst_info(product, work_dir)
        burst_info_list.append(burst_info)

    return burst_info_list


def sort_burst_infos(burst_info_list: List[BurstInfo]) -> Dict:
    """Sort BurstInfo objects by swath and polarization.

    Args:
        burst_info_list: List of BurstInfo objects.

    Returns:
        Dictionary of sorted BurstInfo objects. First key is swath, second key is polarization.
    """
    burst_infos: dict = {}
    for burst_info in burst_info_list:
        if burst_info.swath not in burst_infos:
            burst_infos[burst_info.swath] = {}

        if burst_info.polarization not in burst_infos[burst_info.swath]:
            burst_infos[burst_info.swath][burst_info.polarization] = []

        burst_infos[burst_info.swath][burst_info.polarization].append(burst_info)

    swaths = list(burst_infos.keys())
    polarizations = list(burst_infos[swaths[0]].keys())
    for swath, polarization in zip(swaths, polarizations):
        burst_infos[swath][polarization] = sorted(burst_infos[swath][polarization], key=lambda x: x.burst_id)

    return burst_infos


def optional_wd(wd: Optional[Union[Path, str]] = None) -> Path:
    """Return the working directory as a Path object

    Args:
        wd: Optional working directory as a Path or string

    Returns:
        Path to your input working directory or the current working directory.
    """
    return Path(wd).resolve() if wd is not None else Path.cwd()


def calculate_crc16(file_path: Path) -> str:
    """Calculate the CRC16 checksum for a file.

    Args:
        file_path: Path to file to calculate checksum for

    Returns:
        CRC16 checksum as a hexadecimal string
    """
    with open(file_path, 'rb') as f:
        data = f.read()

    crc = f'{crc_hqx(data, 0xFFFF):04X}'
    return crc


def get_subxml_from_metadata(
    metadata_path: Path, xml_type: str, subswath: Optional[str] = None, polarization: Optional[str] = None
) -> Optional[ET._Element]:
    """Extract child xml info from ASF combined metadata file.

    Args:
        metadata_path: Path to metadata file
        xml_typ: Desired type of metadata to obtain (product, noise, calibration, or rfi)
        subswath: Desired subswath to obtain data for
        polarization: Desired polarization to obtain data for

    Returns:
        lxml Element for desired metadata
    """
    with open(metadata_path) as metadata_file:
        metadata = ET.parse(metadata_file).getroot()

    if xml_type == 'manifest':
        desired_metadata = metadata.find('manifest/{urn:ccsds:schema:xfdu:1}XFDU')
        return desired_metadata

    possible_types = ['product', 'noise', 'calibration', 'rfi']
    if xml_type not in possible_types:
        raise ValueError(f'Metadata type {xml_type} not one of {" ".join(possible_types)}')

    if subswath is None or polarization is None:
        raise ValueError('subswath and polarization must be provided for non-manifest files')

    correct_type = [x for x in metadata.find('metadata').iterchildren() if x.tag == xml_type]
    correct_swath = [x for x in correct_type if x.find('swath').text == subswath]
    correct_pol = [x for x in correct_swath if x.find('polarisation').text == polarization]

    if not correct_pol:
        desired_metadata = None
    else:
        desired_metadata = correct_pol[0].find('content')

    return desired_metadata


def flatten(list_of_lists: List[List]) -> List:
    """Flatten a list of lists."""
    return [item for sublist in list_of_lists for item in sublist]


def drop_duplicates(input_list: List) -> List:
    """Drop duplicates from a list, while preserving order."""
    return list(dict.fromkeys(input_list))


def set_text(element: ET._Element, text: Union[str, int]) -> None:
    """Set the text of an element if it is not None.

    Args:
        element: The element to set the text of.
        text: The text to set the element to.
    """
    if not isinstance(text, str) and not isinstance(text, int):
        raise ValueError('Text must be a string or an integer.')

    element.text = str(text)


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
            try:
                args.extent = box(*[float(x) for x in args.extent])
            except ValueError:
                args.extent = vector_to_shapely_latlon_polygon(args.extent[0])
            except ValueError:
                raise ValueError('--extent cannot be interpreted as a bounding box or geometry file.')

    return args
