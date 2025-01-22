import lxml.etree as ET
import pytest
from shapely.geometry import Polygon

from burst2safe.manifest import Manifest
from burst2safe.utils import get_subxml_from_metadata


@pytest.fixture
def manifest(test_data1_xml):
    content_units = [ET.Element('content_unit')]
    metadata_objects = [ET.Element('metadata_object')]
    data_objects = [ET.Element('data_object')]
    bbox = Polygon([(1, 1), (1, 2), (2, 2), (2, 1), (1, 1)])
    template_manifest = get_subxml_from_metadata(test_data1_xml, 'manifest')
    assert template_manifest is not None
    test_manifest = Manifest(content_units, metadata_objects, data_objects, bbox, template_manifest)
    return test_manifest


class TestManifest:
    def test_init(self, manifest):
        assert len(manifest.content_units) == 1
        assert len(manifest.metadata_objects) == 1
        assert len(manifest.data_objects) == 1

        assert manifest.information_package_map is None
        assert manifest.metadata_section is None
        assert manifest.data_object_section is None

    def test_create_information_package_map(self, manifest):
        manifest.create_information_package_map()
        assert manifest.information_package_map is not None
        assert manifest.information_package_map.tag == '{urn:ccsds:schema:xfdu:1}informationPackageMap'
        assert len(manifest.information_package_map.find('{urn:ccsds:schema:xfdu:1}contentUnit')) == 1

    def test_create_metadata_section(self, manifest):
        manifest.create_metadata_section()
        assert manifest.metadata_section is not None
        assert manifest.metadata_section.tag == 'metadataSection'
        assert manifest.metadata_section.find('.//{*}coordinates').text == '2.0,2.0 1.0,2.0 1.0,1.0 2.0,1.0'

    def test_create_data_object_section(self, manifest):
        manifest.create_data_object_section()
        assert manifest.data_object_section is not None
        assert manifest.data_object_section.tag == 'dataObjectSection'
        assert len(manifest.data_object_section) == 1

    def test_assemble(self, manifest):
        manifest.assemble()
        assert isinstance(manifest.xml, ET._ElementTree)
        assert manifest.xml.getroot().tag == '{urn:ccsds:schema:xfdu:1}XFDU'
        assert manifest.xml.getroot().get('version') == 'esa/safe/sentinel-1.0/sentinel-1/sar/level-1/slc/standard/iwdp'
        assert manifest.xml.find('{*}informationPackageMap') is not None
        assert manifest.xml.find('metadataSection') is not None
        assert manifest.xml.find('dataObjectSection') is not None

    def test_write(self, manifest, tmp_path):
        manifest_path = tmp_path / 'manifest.safe'
        manifest.assemble()
        manifest.write(manifest_path)
        assert manifest_path.exists()
        assert manifest.path == manifest_path
        assert manifest.crc is not None
