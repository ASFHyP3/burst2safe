# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.4]

### Changed
* Fixed typo in naming SAFE file using VH and HV polarizations.

## [1.4.3]

### Changed
* Updated IPF version tests for versions >=3.80 and verified compatibility with Sentinel-1C data.

## [1.4.2]

### Changed
* Upgraded the `reusable-mypy` action to [v0.15.0](https://github.com/ASFHyP3/actions/releases/tag/v0.15.0) and replaced the `--ignore-missing-imports` option with `disable_error_code = ["import-untyped"]` as recommended by <https://github.com/ASFHyP3/actions/issues/225>, then ignored or fixed the resulting `mypy` errors.

## [1.4.1]

### Added
* The [`static-analysis`](.github/workflows/static-analysis.yml) workflow now includes `mypy` for type checking.

### Removed
* Removed `black` from the [`static-analysis`](.github/workflows/static-analysis.yml) workflow.

### Fixed
* Add missing [`src/burst2safe/__init__.py`](./src/burst2safe/__init__.py) file.

## [1.4.0]

### Added
* download.py to support asynchronous downloads.
* Support for EDL token based authentication.

### Changed
* Authorization behavior so that EDL credentials from an EDL token are prioritized above a username/password in either a netrc or the environment.
* Authorization behavior so that EDL username/password from a user's netrc are prioritized. Now writes username/password to the netrc if they are provided as environment variables.
* Switched to an asynchronous download approach.
* In burst2stack.py all input files are now downloaded first.

## [1.3.1]

### Changed
* Updated the [LICENSE](./LICENSE), CICD workflows, and documentation to reflect that this project is now managed by the ASF Tools team (previously Forrest Williams was the sole contributor).
* Update `ruff` configuration to conform to our latest standards.

## [1.3.0]

### Added
* Capability for `local2safe` to take multiple bursts as input

### Changed
* Interface for `local2safe` so that it takes a dictionary describing a set of bursts as input
* `local2safe` CLI so that it takes a JSON describing a set of bursts as input

## [1.2.0]

### Added
* `local2safe`, a utility that creates single-burst SAFEs using burst extractor data and metadata outputs that are available locally.
* `burst_id.py`, using functionality created by Ben Barton, calculates a burst's ESA Burst ID.

## [1.1.1]

### Changed
* Slightly refactored `measurement.create_geotiff` to create a blank geotiff first, then write to it
* Reduced tifffile minimum version from 2024.0.0 to 2022.04.022 to support ISCE2 workflows.
* Pinned numpy to < 2.1.0 to avoid [this data type issue](https://github.com/shapely/shapely/issues/2098)

## [1.1.0]

### Added
* Preview directory with all components except quick-look
* KML and Preview SAFE components
* KML, product-preview, and schema components to manifest

### Changed
* Creation time of measurement tiffs is now set to the end of SLC processing. This ensures consistent filenames of repeatedly created SAFEs because the name is dependent on measurement tiff checksums.

### Fixed
* KML preview file is now included to support processors that grab the SAFE footprint from this file.

## [1.0.0]

### Added
* Marked version 1.0.0 release of package. Package is now stable enough to use in production workloads.

## [0.6.0]

### Added
* Support for EW collection mode SLCs.

## [0.5.0]

### Added
* Support for [s1-reader](https://github.com/isce-framework/s1-reader) and OPERA workflows by adding ability to include 0-burst annotation files when using `--all-anns` CLI flag.

## [0.4.2]

### Added
* Support for Python 3.9

## [0.4.1]

### Fixed
* Bug in CLI parsing of granule case for `burst2safe`.

### Removed
* `--pols` as a required argument for `burst2safe` and `burst2stack`. Default value is now `VV`.

## [0.4.0]

### Added
* `burst2stack` tool for creating stacks of SAFEs.
* The ability to specify swaths and minimum number of bursts when using tool.
* The ability to specify the SAFE extent by either bounding box or vector file.

### Fixed
* `Safe.get_name()` so that it correctly parses `Safe` objects with only cross-pol data.

### Changed
* Moved all search/download functionality to `search.py` module.
* `--bbox` argument to `--extent`.

## [0.3.5]

### Fixed
* Polarization code now accurately reflects bursts contained in SAFE.
* Measurement GeoTiff metadata now correctly specifies Sentinel-1 A or B.

### Added
* CLI argument for specifying output directory.

## [0.3.4]

### Added
* Separate check of Earthdata credentials prior to download.

## [0.3.3]

### Added
* Retries of download functionality to improve robustness of download step.

## [0.3.2]

### Fixed
* Bug introduced in `0.3.1` where the `download_bursts` function would not work for a single worker.

## [0.3.1]

### Fixed
* Race condition in `download_bursts` function by switching to parallel, instead of threaded, downloads.

## [0.3.0]

### Added
* Support for IPF >=3.40 RFI annotation files.
* Support for IPF <=2.90.
* IPF-specific support files.
* Calculation of `platformHeading` and `burst/byteOffset` fields.

### Fixed
* Path information for annotation/measurement files are now are updated when the SAFE path is.
* Bug when burst widths are different by one pixel

### Changed
* Test suite to use test data from 2024 (IPF version 3.71).

## [0.2.0]

### Added
* Functionality for ensure input bursts are eligible for merging.
* A test suite for the library.
* Docstrings for the majority of methods/functions.
* Bounding-box based interface for specifying bursts to merge.
* Removal of intermediate files after merging.

### Changed
* Refactored many components of the library to enable simpler testing.
* Correctly set product unique identifier in SAFE name.

## [0.1.0]

### Added
* First working version of the library.

## [0.0.1]

### Added
* Create project structure and CI/CD tooling.

## [0.0.0]

### Added
* Initial version of project.
