# auto-scheduler

This is a tool to automatically compute passes of satellites on the
SatNOGS network. It uses code from the SatNOGS network scheduler. It requires
[python-satellitetle](https://gitlab.com/librespacefoundation/python-satellitetle) for downloading TLEs.

## Dependencies

```bash
sudo apt-get install libxml2-dev libxslt1-dev
pip install -r requirements.txt
```

## Configuration

Copy the env-dist file to .env and set your legacy SatNOGS Network credentials.

## Test run

Perform a test run to download orbital elements and transmitter priorities (these are stored in `/tmp/cache`) with

```bash
schedule_single_station.py -s <ground station ID> -n
```

The `-n` option computes the passes but does not schedule them. To schedule these passes, run

```bash
schedule_single_station.py -s <ground station ID>
```

## Setup priority scheduling

The following commands will add a list consisting of all DUV, BPSK1k2, BPSK9k6, [G]MSK and [G]FSK transmitters into `priorities_37.txt`.
Please change the station id (here `37` - in the cache file and the list file name) to your corresponding one!

```bash
awk '{if ($3>=80) print $0 }' /tmp/cache/transmitters_37.txt | grep -e "FSK" | awk '{printf("%s 1.0 %s\n",$1,$2)}' > priorities_37.txt
awk '{if ($3>=0) print $0 }' /tmp/cache/transmitters_37.txt | grep -e "BPSK1k2" | awk '{printf("%s 1.0 %s\n",$1,$2)}' >> priorities_37.txt
awk '{if ($3>=0) print $0 }' /tmp/cache/transmitters_37.txt | grep -e "BPSK9k6" | awk '{printf("%s 1.0 %s\n",$1,$2)}' >> priorities_37.txt
awk '{if ($3>=80) print $0 }' /tmp/cache/transmitters_37.txt | grep -e "MSK" | awk '{printf("%s 1.0 %s\n",$1,$2)}' >> priorities_37.txt
sort -n -k 4 /tmp/cache/transmitters_37.txt | grep -e "DUV" | awk '{printf("%s 1.0 %s\n",$1,$2)}' >> priorities_37.txt
```

## Add cron-job

Start editing your default user's cron (select your preferred editor):
```bash
crontab -e
```

Add a line like this - execute the scheduling script on each full hour:
```bash
0 */1 * * * <path_to_auto_scheduler>/schedule_single_station.py -s <station_id> -d 1.2 -P <path_to_priority_list>/<priority_file>.txt -f -z
```

Omit the `-f` option to also fill in the gaps, but be aware if using a rotator setup! This will wear-out your rotator very quickly!
Add `-w 60` for a delay if you want to give your rotator a bit of time (60 s) to reset or home.


## Usage

The following command will list all available command-line arguments:
```bash
./schedule_single_station.py --help
```

## License
[![license](https://img.shields.io/badge/license-AGPL%203.0-6672D8.svg)](LICENSE)
Copyright 2019 - Cees Bassa, Fabian Schmidt, Pierros Papadeas
