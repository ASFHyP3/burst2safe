import filecmp
import shutil
import subprocess
from pathlib import Path

import pytest
from shapely import box

from burst2safe.burst2safe import burst2safe


CURRENT_BRANCH = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip().decode('utf-8')


def bit_for_bit(reference: Path, secondary: Path):
    filecmp.clear_cache()
    return filecmp.cmp(reference, secondary, shallow=False)


@pytest.mark.golden()
@pytest.mark.dependency()
def test_burst2safe_iw():
    work_path = Path.cwd() / CURRENT_BRANCH / 'iw'
    work_path.mkdir(parents=True, exist_ok=True)
    burst2safe(
        granules=[],
        orbit=51936,
        extent=box(*[-117.3, 35.5, -117.2, 35.6]),
        polarizations=['VV', 'VH'],
        keep_files=False,
        work_dir=work_path,
    )


@pytest.mark.golden()
@pytest.mark.dependency()
def test_burst2safe_ew():
    work_path = Path.cwd() / CURRENT_BRANCH / 'ew'
    work_path.mkdir(parents=True, exist_ok=True)
    burst2safe(
        granules=[],
        orbit=54631,
        extent=box(*[-53.6, 66.6, -53.3, 66.8]),
        polarizations=['HH', 'HV'],
        mode='EW',
        keep_files=False,
        work_dir=work_path,
    )


@pytest.mark.golden()
@pytest.mark.dependency(depends=['test_burst2safe_iw', 'test_burst2safe_ew'])
def test_make_archive():
    work_path = Path.cwd() / CURRENT_BRANCH
    shutil.make_archive(str(work_path), 'tar', work_path)


@pytest.mark.golden()
@pytest.mark.parametrize('mode', ['iw', 'ew'])
def test_golden_compare(mode):
    main_branch = 'main'
    develop_branch = 'develop'

    for tar_name in [f'{main_branch}.tar', f'{develop_branch}.tar']:
        tar_path = Path.cwd() / tar_name
        extract_dir = tar_path.with_suffix('')
        if not extract_dir.exists():
            extract_dir.mkdir(exist_ok=True)
            shutil.unpack_archive(tar_path, extract_dir)

    main_safe = list((Path.cwd() / main_branch / mode).glob('*.SAFE'))[0]
    develop_safe = list((Path.cwd() / develop_branch / mode).glob('*.SAFE'))[0]
    assert main_safe.name == develop_safe.name

    main_files = sorted([x.resolve() for x in main_safe.rglob('*')])
    develop_files = sorted([x.resolve() for x in develop_safe.rglob('*')])

    main_set = set([f.relative_to(main_safe) for f in main_files])
    develop_set = set([f.relative_to(develop_safe) for f in develop_files])

    only_in_main = [str(x) for x in main_set - develop_set]
    assert not only_in_main

    only_in_develop = [str(x) for x in develop_set - main_set]
    assert not only_in_develop

    differing_files = []
    for main_file, develop_file in zip(main_files, develop_files):
        if main_file.is_dir():
            continue

        if not bit_for_bit(main_file, develop_file):
            differing_files.append(develop_file.relative_to(develop_safe))

    differing_files = [str(x) for x in differing_files]
    assert not differing_files
