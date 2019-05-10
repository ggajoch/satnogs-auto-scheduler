# auto-scheduler

This is a tool to automatically compute passes of satellites on the
SatNOGS network. It uses code from the SatNOGS network scheduler. It requires
[python-satellitetle](https://gitlab.com/librespacefoundation/python-satellitetle) for downloading TLEs.

## Dependencies

```
pip install -r requirements.txt
```

## Configuration

Copy the env-dist file to .env and set your legacy SatNOGS Network credentials.


## Usage

The following command will list all available command-line arguments:
```
./schedule_single_station.py --help
```

## License
[![license](https://img.shields.io/badge/license-AGPL%203.0-6672D8.svg)](LICENSE)
Copyright 2019 - Cees Bassa, Fabian Schmidt, Pierros Papadeas
