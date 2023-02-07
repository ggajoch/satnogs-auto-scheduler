# Changelog

## unreleased

- Added station-agnostic caching of SatNOGS Netowork transmitter statistics and the SatNOGS DB
  satellite information. For now those files get updated each time the station-specific cache receives
  an update.
- Added the usage of satellite names from SatNOGS DB in log output.
- Removed scheduling for satellites with the "frequency misuse" flag in SatNOGS DB.
  Unless the user had special SSA permissions those passes were not scheduled already but made the
  batch-scheduling fail often times. This change follows the
  [change](https://community.libre.space/t/changes-in-network-and-db-for-satellites-that-violate-frequency-regulations/9395)
  in SatNOGS for satellites that violate frequency regulations.
- Removed the deprecated method of fetching TLEs from various sources,
  always fetch TLEs from SatNOGS DB now.

### Breaking Changes

The SatNOGS DB API Token is always required now. Thus TLEs are fetched from SatNOGS DB diretly
which has multiple benefits. It is much faster than the old method, removes errors when a satellite
entry is using TLEs produced by "new" sources (e.g. SatNOGS Team) and enables output improvements.

## 0.2 - 2023-02-06 - 2b77522

First release in 2023.

## v0.1 - 2018-12-02 - 1a844c7

Initial stable release.
