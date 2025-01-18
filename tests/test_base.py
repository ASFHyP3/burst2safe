# mypy: disable-error-code="union-attr"
from datetime import datetime, timedelta
from pathlib import Path

import lxml.etree as ET
import pytest

from burst2safe import base


METADATA_TYPE = 'product'
VERSION = '3.71'
IMAGE_NUMBER = 1


@pytest.fixture
def annotation(burst_infos):
    return base.Annotation(burst_infos, METADATA_TYPE, VERSION, IMAGE_NUMBER)


@pytest.fixture
def elem_lists():
    start_time1 = datetime.fromisoformat('2020-01-01T00:00:00')
    elem_list1 = ET.Element('fooList')

    elem_list2 = ET.Element('fooList')
    start_time2 = datetime.fromisoformat('2020-01-01T00:01:00')

    for i in range(5):
        for elem_list, start_time in zip([elem_list1, elem_list2], [start_time1, start_time2]):
            element = ET.Element('foo')
            time = (start_time + timedelta(seconds=i * 15)).isoformat()
            ET.SubElement(element, 'azimuthTime').text = time
            ET.SubElement(element, 'line').text = str(i * 100)
            elem_list.append(element)

    elem_list2.remove(elem_list2[-1])
    return [elem_list1, elem_list2]


class TestListOfListElements:
    def test_init(self, elem_lists):
        start_line = 100
        slc_lengths = [400, 300]
        list_of_lists = base.ListOfListElements(elem_lists, start_line, slc_lengths)
        assert list_of_lists.name == 'fooList'
        assert list_of_lists.subelement_name == 'foo'
        assert list_of_lists.time_field == 'azimuthTime'
        assert list_of_lists.has_line is True

    def test_get_unique_elements(self, elem_lists):
        slc_lengths = [400, 300]
        list_of_lists = base.ListOfListElements(elem_lists, slc_lengths=slc_lengths)
        remaining_elements = list_of_lists.get_unique_elements()
        assert len(remaining_elements) == 8

        lines = [x.find('line').text for x in remaining_elements]
        assert lines == ['0', '100', '200', '300', '400', '500', '600', '700']

    def test_create_time_filtered_list(self, elem_lists):
        start_line = 100
        slc_lengths = [400, 300]
        list_of_lists = base.ListOfListElements(elem_lists, start_line, slc_lengths)

        time1 = datetime.fromisoformat('2020-01-01T00:00:15')
        time2 = datetime.fromisoformat('2020-01-01T00:01:15')
        filtered = list_of_lists.create_filtered_list((time1, time2))
        assert len(filtered) == 5
        lines = [x.find('line').text for x in filtered]
        assert lines == ['0', '100', '200', '300', '400']

        filtered = list_of_lists.create_filtered_list((time1, time2), line_bounds=(200.0, 300.0))
        assert len(filtered) == 2
        lines = [x.find('line').text for x in filtered]
        assert lines == ['200', '300']


def test_create_content_unit():
    simple_name = 'test_annotation'
    unit_type = 'Metadata Unit'
    rep_id = 'S1Level1TestSchema'

    content_unit = base.create_content_unit(simple_name, unit_type, rep_id)

    assert isinstance(content_unit, ET._Element)
    assert content_unit.tag == '{urn:ccsds:schema:xfdu:1}contentUnit'
    assert content_unit.get('unitType') == unit_type
    assert content_unit.get('repID') == rep_id
    assert content_unit.findall('.//dataObjectPointer')[0].get('dataObjectID') == simple_name


def test_create_metadata_object():
    simple_name = 'test_annotation'

    metadata_object = base.create_metadata_object(simple_name)

    assert isinstance(metadata_object, ET._Element)
    assert metadata_object.tag == 'metadataObject'
    assert metadata_object.get('ID') == f'{simple_name}Annotation'
    assert metadata_object.get('classification') == 'DESCRIPTION'
    assert metadata_object.get('category') == 'DMD'
    assert metadata_object.findall('.//dataObjectPointer')[0].get('dataObjectID') == simple_name


def test_create_data_object():
    simple_name = 'test_annotation'
    relative_path = Path('./test_annotation.xml')
    rep_id = 'S1Level1TestSchema'
    mime_type = 'text/xml'
    size_bytes = 1000
    md5 = 'md5hash'

    data_object = base.create_data_object(simple_name, relative_path, rep_id, mime_type, size_bytes, md5)

    assert isinstance(data_object, ET._Element)
    assert data_object.tag == 'dataObject'
    assert data_object.get('ID') == simple_name
    assert data_object.get('repID') == rep_id

    byte_stream = data_object.find('.//byteStream')
    assert byte_stream.get('mimeType') == mime_type
    assert byte_stream.get('size') == str(size_bytes)

    file_location = byte_stream.find('.//fileLocation')
    assert file_location.get('locatorType') == 'URL'
    assert file_location.get('href') == f'./{relative_path}'

    checksum = byte_stream.find('.//checksum')
    assert checksum.get('checksumName') == 'MD5'
    assert checksum.text == md5


class TestAnnotation:
    def test_annotation_init(self, annotation, burst_infos):
        assert annotation.burst_infos == burst_infos
        assert annotation.metadata_type == METADATA_TYPE
        assert annotation.major_version == 3
        assert annotation.minor_version == 71
        assert annotation.image_number == IMAGE_NUMBER
        assert annotation.metadata_paths == [burst_infos[0].metadata_path, burst_infos[1].metadata_path]
        assert annotation.swath == burst_infos[0].swath
        assert annotation.pol == burst_infos[0].polarization
        assert annotation.start_line == 8 * 1508
        assert annotation.stop_line == 10 * 1508

    def test_create_ads_header(self, annotation):
        assert annotation.ads_header is None
        annotation.create_ads_header()
        assert annotation.ads_header is not None
        assert annotation.ads_header.find('startTime').text is not None  # type: ignore[unreachable]
        assert annotation.ads_header.find('stopTime').text is not None
        assert annotation.ads_header.find('imageNumber').text == '001'

    def test_str_method(self, annotation):
        annotation.xml = ET.Element('test')
        assert isinstance(annotation.__str__(), str)
        assert annotation.__str__().startswith('<test')

    def test_write_method(self, annotation, tmp_path):
        annotation.xml = ET.ElementTree(ET.Element('test'))

        annotation.write(tmp_path / 'test_annotation.xml', update_info=False)
        assert (tmp_path / 'test_annotation.xml').exists()
        assert annotation.size_bytes is None
        assert annotation.md5 is None

        annotation.write(tmp_path / 'test_annotation.xml', update_info=True)
        assert annotation.size_bytes is not None
        assert annotation.size_bytes > 0  # type: ignore[unreachable]
        assert annotation.md5 is not None

    def test_create_manifest_components(self, annotation):
        annotation.path = Path('test.SAFE/s1-iw2-vv-annotation.xml')
        annotation.size_bytes = 1000
        annotation.md5 = 'md5hash'
        content_unit, metadata_object, data_object = annotation.create_manifest_components()

        assert isinstance(content_unit, ET._Element)
        assert content_unit.get('unitType') == 'Metadata Unit'
        assert content_unit.get('repID') == 's1Level1ProductSchema'

        assert isinstance(metadata_object, ET._Element)
        assert metadata_object.find('dataObjectPointer').get('dataObjectID') == 'products1iw2vvannotation'

        assert isinstance(data_object, ET._Element)
        assert data_object.get('ID') == 'products1iw2vvannotation'
        assert data_object.get('repID') == 's1Level1ProductSchema'
        assert data_object.find('byteStream').get('size') == '1000'
        assert data_object.find('byteStream/checksum').text == 'md5hash'
