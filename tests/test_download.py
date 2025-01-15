from collections import namedtuple

from burst2safe import download


def test_get_url_dict(tmp_path):
    DummyBurst = namedtuple('DummyBurst', ['data_path', 'data_url', 'metadata_path', 'metadata_url'])
    burst_infos = [
        DummyBurst(
            data_path=tmp_path / 'data1.tif',
            data_url='http://data1.tif',
            metadata_path=tmp_path / 'metadata1.xml',
            metadata_url='http://metadata1.xml',
        ),
        DummyBurst(
            data_path=tmp_path / 'data2.tiff',
            data_url='http://data2.tiff',
            metadata_path=tmp_path / 'metadata2.xml',
            metadata_url='http://metadata2.xml',
        ),
    ]
    url_dict = download.get_url_dict(burst_infos)  # type: ignore[arg-type]
    expected = {
        tmp_path / 'data1.tif': 'http://data1.tif',
        tmp_path / 'metadata1.xml': 'http://metadata1.xml',
        tmp_path / 'data2.tiff': 'http://data2.tiff',
        tmp_path / 'metadata2.xml': 'http://metadata2.xml',
    }
    assert url_dict == expected

    del expected[tmp_path / 'data1.tif']
    (tmp_path / 'data1.tif').touch()
    url_dict = download.get_url_dict(burst_infos)  # type: ignore[arg-type]
    assert url_dict == expected
