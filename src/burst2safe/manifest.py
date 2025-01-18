import hashlib
from copy import deepcopy
from pathlib import Path
from typing import List, Optional, Union

import lxml.etree as ET
import numpy as np
from shapely.geometry import Polygon

from burst2safe.utils import calculate_crc16


SAFE_NS = 'http://www.esa.int/safe/sentinel-1.0'
NAMESPACES = {
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'gml': 'http://www.opengis.net/gml',
    'xfdu': 'urn:ccsds:schema:xfdu:1',
    'safe': SAFE_NS,
    's1': f'{SAFE_NS}/sentinel-1',
    's1sar': f'{SAFE_NS}/sentinel-1/sar',
    's1sarl1': f'{SAFE_NS}/sentinel-1/sar/level-1',
    's1sarl2': f'{SAFE_NS}/sentinel-1/sar/level-2',
    'gx': 'http://www.google.com/kml/ext/2.2',
}


def get_footprint_string(bbox: Polygon, x_first=True) -> str:
    """Get a string representation of the footprint of the product.

    Args:
        bbox: The bounding box of the product
        x_first: Whether to put the x coordinate first or second

    Returns:
        A string representation of the product footprint
    """
    coords = [(np.round(y, 6), np.round(x, 6)) for x, y in bbox.exterior.coords]
    # TODO: order assumes descending
    coords = [coords[2], coords[3], coords[0], coords[1]]
    if x_first:
        coords_str = ' '.join([f'{x},{y}' for x, y in coords])
    else:
        coords_str = ' '.join([f'{y},{x}' for x, y in coords])
    return coords_str


class Manifest:
    """Class representing a SAFE manifest."""

    def __init__(
        self,
        content_units: List[ET._Element],
        metadata_objects: List[ET._Element],
        data_objects: List[ET._Element],
        bbox: Polygon,
        template_manifest: ET._Element,
    ):
        """Initialize a Manifest object.

        Args:
            content_units: A list of contentUnit elements
            metadata_objects: A list of metadataObject elements
            data_objects: A list of dataObject elements
            bbox: The bounding box of the product
            template_manifest: The template manifest to generate unalterd metadata from
        """
        self.content_units = content_units
        self.metadata_objects = metadata_objects
        self.data_objects = data_objects
        self.bbox = bbox
        self.template = template_manifest
        self.version = 'esa/safe/sentinel-1.0/sentinel-1/sar/level-1/slc/standard/iwdp'

        # Updated by methods
        self.information_package_map: Optional[ET._Element] = None
        self.metadata_section: Optional[ET._Element] = None
        self.data_object_section: Optional[ET._Element] = None
        self.xml: Union[ET._Element, ET._ElementTree, None] = None
        self.path: Optional[Path] = None
        self.crc: Optional[str] = None

    def create_information_package_map(self):
        """Create the information package map."""
        xdfu_ns = NAMESPACES['xfdu']
        information_package_map = ET.Element(f'{{{xdfu_ns}}}informationPackageMap')
        parent_content_unit = ET.Element(
            f'{{{xdfu_ns}}}contentUnit',
            unitType='SAFE Archive Information Package',
            textInfo='Sentinel-1 IW Level-1 SLC Product',
            dmdID='acquisitionPeriod platform generalProductInformation measurementOrbitReference measurementFrameSet',
            pdiID='processing',
        )
        for content_unit in self.content_units:
            parent_content_unit.append(content_unit)

        information_package_map.append(parent_content_unit)
        self.information_package_map = information_package_map

    def create_metadata_section(self):
        """Create the metadata section."""
        metadata_section = ET.Element('metadataSection')
        for metadata_object in self.metadata_objects:
            metadata_section.append(metadata_object)

        ids_to_keep = [
            'processing',
            'platform',
            'measurementOrbitReference',
            'generalProductInformation',
            'acquisitionPeriod',
            'measurementFrameSet',
            's1Level1ProductSchema',
            's1Level1NoiseSchema',
            's1Level1RfiSchema',
            's1Level1CalibrationSchema',
            's1ObjectTypesSchema',
            's1Level1MeasurementSchema',
            's1Level1ProductPreviewSchema',
            's1Level1QuicklookSchema',
            's1MapOverlaySchema',
        ]
        for obj in self.template.find('metadataSection'):  # type: ignore[union-attr]
            if obj.get('ID') in ids_to_keep:
                metadata_section.append(deepcopy(obj))

        coordinates = metadata_section.find('.//{*}coordinates')
        assert coordinates is not None
        coordinates.text = get_footprint_string(self.bbox)

        self.metadata_section = metadata_section

    def create_data_object_section(self):
        """Create the data object section."""
        self.data_object_section = ET.Element('dataObjectSection')
        for data_object in self.data_objects:
            self.data_object_section.append(data_object)

    def assemble(self):
        """Assemble the components of the SAFE manifest."""
        self.create_information_package_map()
        self.create_metadata_section()
        self.create_data_object_section()

        manifest = ET.Element('{%s}XFDU' % NAMESPACES['xfdu'], nsmap=NAMESPACES)
        manifest.set('version', self.version)
        assert self.information_package_map is not None
        assert self.metadata_section is not None
        assert self.data_object_section is not None
        manifest.append(self.information_package_map)
        manifest.append(self.metadata_section)
        manifest.append(self.data_object_section)
        manifest_tree = ET.ElementTree(manifest)

        ET.indent(manifest_tree, space='  ')
        self.xml = manifest_tree

    def write(self, out_path: Path, update_info: bool = True) -> None:
        """Write the SAFE manifest to a file. Optionally update the path and CRC.

        Args:
            out_path: The path to write the manifest to
            update_info: Whether to update the path and CRC
        """
        assert isinstance(self.xml, ET._ElementTree)
        self.xml.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')
        if update_info:
            self.path = out_path
            self.crc = calculate_crc16(self.path)


class Kml:
    """Class representing a SAFE manifest."""

    def __init__(self, bbox: Polygon):
        """Initialize a KML object.

        Args:
            bbox: The bounding box of the product
        """
        self.bbox = bbox
        self.xml: Union[ET._Element, ET._ElementTree, None] = None

    def assemble(self):
        """Assemble the components of the SAFE KML preview file."""
        kml = ET.Element('kml', nsmap=NAMESPACES)
        document = ET.SubElement(kml, 'Document')
        doc_name = ET.SubElement(document, 'name')
        doc_name.text = 'Sentinel-1 Map Overlay'

        folder = ET.SubElement(document, 'Folder')
        folder_name = ET.SubElement(folder, 'name')
        folder_name.text = 'Sentinel-1 Scene Overlay'

        ground_overlay = ET.SubElement(folder, 'GroundOverlay')
        ground_overlay_name = ET.SubElement(ground_overlay, 'name')
        ground_overlay_name.text = 'Sentinel-1 Image Overlay'
        icon = ET.SubElement(ground_overlay, 'Icon')
        href = ET.SubElement(icon, 'href')
        # TODO: we intentionally don't create this image because we don't know how to.
        href.text = 'quick-look.png'
        lat_lon_quad = ET.SubElement(ground_overlay, f'{{{NAMESPACES["gx"]}}}LatLonQuad')
        coordinates = ET.SubElement(lat_lon_quad, 'coordinates')
        coordinates.text = get_footprint_string(self.bbox, x_first=False)

        kml_tree = ET.ElementTree(kml)
        ET.indent(kml_tree, space='  ')
        self.xml = kml_tree

    def write(self, out_path: Path, update_info: bool = True) -> None:
        """Write the SAFE kml to a file.

        Args:
            out_path: The path to write the manifest to
            update_info: Whether to update the path
        """
        assert isinstance(self.xml, ET._ElementTree)
        self.xml.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')
        if update_info:
            self.path = out_path
            with open(out_path, 'rb') as f:
                file_bytes = f.read()
                self.size_bytes = len(file_bytes)
                self.md5 = hashlib.md5(file_bytes).hexdigest()

    def update_path(self, safe_path: Path):
        """Update the path based on new a SAFE path.

        Args:
            safe_path: The new SAFE path
        """
        parts = self.path.parts
        parent_index = parts.index(safe_path.parent.name)
        self.path = safe_path / Path(*parts[parent_index + 2 :])


class Preview:
    """Class representing a product preview HTML file."""

    def __init__(
        self,
        name: str,
        product: List[str],
        calibration: List[str],
        measurement: List[str],
        rfi: List[str] = [],
    ):
        """Initialize a Preview object.

        Args:
            name: The name of the product
            product: A list of product annotation files
            calibration: A list of calibration annotation files
            measurement: A list of measurement annotation files
            rfi: A list of rfi annotation files
        """
        self.name = '_'.join(name.split('_')[:-1])
        self.product = product
        self.calibration = calibration
        self.measurement = measurement
        self.rfi = rfi
        self.preview = ['map-overlay.kml', 'product-preview.html', 'quick-look.png']
        self.preview_icon = ['logo.png']
        self.support = [
            's1-level-1-product.xsd',
            's1-level-1-noise.xsd',
            's1-level-1-calibration.xsd',
            's1-object-types.xsd',
            's1-map-overlay.xsd',
            's1-product-preview.xsd',
            's1-level-1-measurement.xsd',
            's1-level-1-quicklook.xsd',
        ]
        if len(self.rfi) > 0:
            self.support.append('s1-level-1-rfi.xsd')
        self.html: Optional[ET._ElementTree] = None
        self.path: Optional[Path] = None

    def create_base(self):
        """Create the base HTML product preview."""
        namespaces = {'xsd': 'http://www.w3.org/2001/XMLSchema', 'fn': 'http://www.w3.org/2005/xpath-functions'}
        html = ET.Element('html', nsmap=namespaces)
        head = ET.SubElement(html, 'head')
        ET.SubElement(head, 'meta', attrib={'http-equiv': 'Content-Type', 'content': 'text/html; charset=utf-8'})

        # Create the head section
        nsmap = {'xsd': 'http://www.w3.org/2001/XMLSchema', 'fn': 'http://www.w3.org/2005/xpath-functions'}
        html = ET.Element('html', nsmap=nsmap)
        head = ET.SubElement(html, 'head')

        # Meta element
        ET.SubElement(head, 'meta', attrib={'http-equiv': 'Content-Type', 'content': 'text/html; charset=UTF-8'})

        # Title element
        title = ET.SubElement(head, 'title')
        title.text = self.name

        # Style element
        style = ET.SubElement(head, 'style', attrib={'type': 'text/css'})
        style.text = """
        h1 {font-size:20px}
        h2 {font-size: 18px}
        """

        # Create the body section
        body = ET.SubElement(html, 'body')

        # Add image and title
        ET.SubElement(body, 'img', attrib={'src': 'icons/logo.png'})
        h1 = ET.SubElement(body, 'h1')
        h1.text = self.name

        # Add manifest link
        h2_manifest = ET.SubElement(body, 'h2')
        a_manifest = ET.SubElement(h2_manifest, 'a', attrib={'href': '../manifest.safe'})
        a_manifest.text = 'manifest.safe'

        return html

    def add_subsection(self, body, name, files):
        """Add a file set subsection to the HTML preview."""
        h2 = ET.SubElement(body, 'h2')
        h2.text = name
        ul = ET.SubElement(body, 'ul')
        for file in files:
            li = ET.SubElement(ul, 'li')
            a = ET.SubElement(li, 'a', attrib={'href': f'../{name}/{file}'})
            a.text = file

    def add_img(self, body):
        """Add the image to the HTML preview."""
        ET.SubElement(body, 'img', attrib={'style': 'float:right', 'src': '../preview/quick-look.png'})

    def assemble(self):
        """Assemble the HTML preview."""
        html = self.create_base()
        body = html.find('.//body')

        self.add_subsection(body, 'annotation', self.product)
        self.add_subsection(body, 'annotation/calibration', self.calibration)
        if len(self.rfi) > 0:
            self.add_subsection(body, 'annotation/rfi', self.rfi)
        self.add_subsection(body, 'measurement', self.measurement)
        self.add_img(body)
        self.add_subsection(body, 'preview', self.preview)
        self.add_subsection(body, 'preview/icons', self.preview_icon)
        self.add_subsection(body, 'support', self.support)

        html_tree = ET.ElementTree(html)
        ET.indent(html_tree, space='  ')
        self.html = html_tree

    def write(self, out_path: Path, update_info=True) -> None:
        """Write the html to a file.

        Args:
            out_path: The path to write the annotation to.
            update_info: Whether to update the size and md5 attributes of the html.
        """
        assert self.html is not None
        self.html.write(out_path, pretty_print=True, xml_declaration=True, encoding='utf-8')

        if update_info:
            self.path = out_path
            with open(out_path, 'rb') as f:
                file_bytes = f.read()
                self.size_bytes = len(file_bytes)
                self.md5 = hashlib.md5(file_bytes).hexdigest()

    def update_path(self, safe_path: Path):
        """Update the path based on new a SAFE path.

        Args:
            safe_path: The new SAFE path
        """
        assert self.path is not None
        parts = self.path.parts
        parent_index = parts.index(safe_path.parent.name)
        self.path = safe_path / Path(*parts[parent_index + 2 :])
