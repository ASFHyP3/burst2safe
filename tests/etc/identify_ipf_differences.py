"""Utilities for adding new IPF version compatibility.

This script contains workflows for identifying changes in SAFE files related to IPF version upgrades.
This includes three work flows.

IDENTIFY_CHANGING_VERSIONS:
    Identifies IPF versions that changed the SAFE dataset structure by looking at the XML template support files.

DOWNLOAD_REPRESENTATIVE_SUPPORT:
    Downloads the XML template files associated with important versions so they can used for SAFE creation/testing.

FIND_REPRESENTATIVE_BURSTS:
    Identifies a set of bursts that contains a burst from each important IPF version (for testing).

IPF Changelog: https://sar-mpc.eu/processor/ipf/
"""

import argparse
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
    Version('2.43', True),
    Version('2.45', False),
    Version('2.52', False),
    Version('2.53', False),
    Version('2.60', True),
    Version('2.62', False),
    Version('2.70', False),
    Version('2.71', False),
    Version('2.72', False),
    Version('2.82', False),
    Version('2.84', False),
    Version('2.90', True),
    Version('2.91', False),
    Version('3.10', False),
    Version('3.20', False),
    Version('3.30', False),
    Version('3.31', False),
    Version('3.40', True),
    Version('3.51', False),
    Version('3.52', False),
    Version('3.61', False),
    Version('3.71', True),
    Version('3.80', True),
    Version('3.90', False),
    Version('3.91', False),
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
    burst_infos, versions = [], []
    for version in VERSIONS:
        if important_only and not version.important:
            continue
        matching_version = [x for x in results if x.umm['PGEVersionClass']['PGEVersion'] == f'00{version.id}']
        if len(matching_version) == 0:
            print(f'No bursts with version {version.id} found')
            continue
        burst_infos.append(get_burst_infos([matching_version[len(matching_version) // 2]], Path.cwd())[0])
        versions.append(version.id)
    return burst_infos, versions


def download_slcs(slcs, workdir):
    slc_results = asf.granule_search(slcs)
    slc_results.download(workdir)
    slc_paths = sorted(list(workdir.glob('*.zip')))
    return slc_paths


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


def extract_support_folder(slc_path, workdir):
    version = get_version(slc_path).replace('.', '')
    out_dir = workdir / f'support_{version}'
    out_dir.mkdir(exist_ok=True)
    slc_name = f'{slc_path.name.split(".")[0]}.SAFE'
    with ZipFile(slc_path) as zip_ref:
        for file_info in zip_ref.infolist():
            if file_info.filename.startswith(f'{slc_name}/support/') and not file_info.is_dir():
                source_file = zip_ref.open(file_info)
                target_path = out_dir / Path(file_info.filename).name
                with open(target_path, 'wb') as target_file:
                    shutil.copyfileobj(source_file, target_file)


def create_diffs(workdir):
    supports = sorted(workdir.glob('support*'))
    for i in range(len(supports) - 1):
        support1 = supports[i]
        support2 = supports[i + 1]
        diff_file = workdir / Path(f'diff_{support1.name}_{support2.name}.txt')
        diff_file.touch()
        os.system(f'git diff --no-index {support1} {support2} > {diff_file}')


def get_changes(workdir):
    files = sorted(list(workdir.glob('diff_support*txt')))
    has_changes = [file.name for file in files if os.path.getsize(file) > 0]
    return has_changes


def identify_changing_versions(workdir):
    slcs = [f'{burst.slc_granule}-SLC' for burst in find_representative_bursts(important_only=False)[0]]
    slc_paths = download_slcs(slcs, workdir)
    for slc_path in slc_paths:
        extract_support_folder(slc_path, workdir)
    create_diffs(workdir)
    has_changes = get_changes(workdir)
    print('Files with changes:')
    [print(file) for file in has_changes]


def download_representative_support(workdir):
    slcs = [f'{burst.slc_granule}-SLC' for burst in find_representative_bursts(important_only=True)[0]]
    slc_paths = download_slcs(slcs, workdir)
    for slc_path in slc_paths:
        extract_support_folder(slc_path, workdir)


def main():
    workflows = ['identify_changing_versions', 'download_representative_support', 'find_representative_bursts']
    parser = argparse.ArgumentParser(description='Utilities for adding new IPF version compatibility.')
    parser.add_argument('workflow', choices=workflows)
    parser.add_argument('--outdir', type=str, default='.', help='Output directory for downloaded files')
    args = parser.parse_args()

    args.outdir = Path(args.outdir)
    args.outdir.mkdir(exist_ok=True, parents=True)
    assert args.workflow in workflows, f'Unknown workflow: {args.workflow}'

    if args.workflow == 'identify_changing_versions':
        identify_changing_versions(workdir=args.outdir)
    elif args.workflow == 'download_representative_support':
        download_representative_support(workdir=args.outdir)
    elif args.workflow == 'find_representative_bursts':
        bursts, versions = find_representative_bursts(important_only=True)
        for burst, version in zip(bursts, versions):
            print(f'Found burst: {burst.granule} with version {version}')


if __name__ == '__main__':
    main()
