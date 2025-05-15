"""Identify differences in Sentinel-1 IPF versions by downloading representative SLCs and extracting support files.

IPF list: https://sar-mpc.eu/processor/ipf/
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

import asf_search as asf
import lxml.etree as ET

from burst2safe.utils import get_burst_infos


@dataclass
class Version:
    id: str
    important: bool


VERSIONS = [
    Version('2.36', True),
    Version('2.43', False),
    Version('2.45', True),
    Version('2.52', False),
    Version('2.53', False),  # may not need
    Version('2.60', True),
    Version('2.62', False),
    Version('2.70', False),
    Version('2.71', False),
    Version('2.72', False),
    Version('2.82', False),
    Version('2.84', False),  # may not need
    Version('2.90', True),
    Version('2.91', False),
    Version('3.10', False),
    Version('3.20', False),
    Version('3.30', False),  # may not need
    Version('3.31', False),
    Version('3.40', True),
    Version('3.51', False),
    Version('3.52', False),  # may not need
    Version('3.61', False),
    Version('3.71', True),
    Version('3.80', True),
    Version('3.90', True),
    Version('3.91', True),
]


def find_representative_bursts(important_only=False):
    options = {
        'intersectsWith': 'POLYGON((12.2376 41.741,12.2607 41.741,12.2607 41.7609,12.2376 41.7609,12.2376 41.741))',
        'dataset': 'SLC-BURST',
        'relativeOrbit': 117,
        'flightDirection': 'Ascending',
        'polarization': 'VV',
        'maxResults': 2000,
    }
    results = asf.search(**options)
    burst_infos = []
    for version in VERSIONS:
        if important_only and not version.important:
            continue
        matching_version = [x for x in results if x.umm['PGEVersionClass']['PGEVersion'] == f'00{version.id}']
        if len(matching_version) == 0:
            print(f'No bursts with version {version.id} found')
            continue
        burst_infos.append(get_burst_infos(matching_version[:1], Path.cwd())[0])

    return burst_infos


def download_slcs():
    slcs = [f'{burst.slc_granule}-SLC' for burst in find_representative_bursts()]
    slc_results = asf.granule_search(slcs)
    slc_results.download('.')


def get_version(slc_path):
    slc_name = f'{slc_path.name.split(".")[0]}.SAFE'
    with ZipFile(slc_path) as z:
        manifest_str = z.read(f'{slc_name}/manifest.safe')
        manifest = ET.fromstring(manifest_str)

    version_xml = [elem for elem in manifest.findall('.//{*}software') if elem.get('name') == 'Sentinel-1 IPF'][0]
    return version_xml.get('version')


def get_versions(slc_paths):
    versions = [(slc_path.name, get_version(slc_path)) for slc_path in slc_paths]
    versions.sort(key=lambda x: x[1])


def extract_support_folder(slc_path):
    version = get_version(slc_path).replace('.', '')
    out_dir = Path(f'support_{version}')
    out_dir.mkdir(exist_ok=True)
    slc_name = f'{slc_path.name.split(".")[0]}.SAFE'
    with ZipFile(slc_path) as zip_ref:
        for file_info in zip_ref.infolist():
            if file_info.filename.startswith(f'{slc_name}/support/') and not file_info.is_dir():
                source_file = zip_ref.open(file_info)
                target_path = out_dir / Path(file_info.filename).name
                with open(target_path, 'wb') as target_file:
                    shutil.copyfileobj(source_file, target_file)


def create_diffs():
    supports = sorted(Path().glob('support*'))
    for i in range(len(supports) - 1):
        support1 = supports[i]
        support2 = supports[i + 1]
        diff_file = Path(f'diff_{support1.name}_{support2.name}.txt')
        diff_file.touch()
        os.system(f'git diff --no-index {support1} {support2} > {diff_file}')


def identify_changing_versions():
    download_slcs()
    slc_paths = sorted(list(Path().glob('*.zip')))
    for slc_path in slc_paths:
        extract_support_folder(slc_path)
    create_diffs()


def download_changing_metadata():
    bursts = find_representative_bursts()
    sorted_bursts = sorted(bursts, key=lambda x: x.date)

    important_versions = []
    for version, burst in zip(VERSIONS, sorted_bursts):
        if version.important:
            print(version.id, burst.granule)
            important_versions.append(burst)

    for burst in important_versions:
        asf.download_url(burst.metadata_url, path='.', filename=burst.metadata_path.name)


def download_representative_support(important_only=True):
    slcs = [f'{burst.slc_granule}-SLC' for burst in find_representative_bursts(important_only=important_only)]
    slc_results = asf.granule_search(slcs)
    slc_results.download('.')
    slc_paths = sorted(list(Path().glob('*.zip')))
    for slc_path in slc_paths:
        extract_support_folder(slc_path)


if __name__ == '__main__':
    # identify_changing_versions()
    # download_changing_metadata()
    download_representative_support(important_only=False)
