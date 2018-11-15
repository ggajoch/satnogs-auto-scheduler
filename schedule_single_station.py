#!/usr/bin/env python
import json
import requests
import ephem
import math
import random
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.dates import DayLocator, HourLocator, DateFormatter, drange
from matplotlib import colors as mcolors

class satellite:
    """Satellite class"""

    def __init__(self, tle0, tle1, tle2):
        """Define a satellite"""

        self.tle0 = tle0
        self.tle1 = tle1
        self.tle2 = tle2
        if tle0[:2]=="0 ":
            self.name = tle0[2:]
        else:
            self.name = tle0
        self.id = tle1.split(" ")[1][:5]

def get_scheduled_passes_from_network(ground_station, tmin, tmax):
    # Get first page
    client = requests.session()

    # Loop
    start = True
    scheduledpasses = []
                
    while True:
        if start:
            r = client.get("https://network.satnogs.org/api/observations/?ground_station=%d"%ground_station)
            start = False
        else:
            nextpage = r.links.get("next")
            r = client.get(nextpage["url"])
    
        # r.json() is a list of dicts
        for o in r.json():
            satpass = {"id": o['norad_cat_id'],
                       "tr": datetime.strptime(o['start'].replace("Z", ""), "%Y-%m-%dT%H:%M:%S"),
                       "ts": datetime.strptime(o['end'].replace("Z", ""), "%Y-%m-%dT%H:%M:%S"),
                       "scheduled": True}

            if satpass['ts']>tmin and satpass['tr']<tmax:
                scheduledpasses.append(satpass)
        if satpass['ts']<tmin:
            break

    return scheduledpasses
        
def overlap(satpass, scheduledpasses):
    # No overlap
    overlap = False
    # Loop over scheduled passes
    for scheduledpass in scheduledpasses:
        # Test pass falls within scheduled pass
        if satpass['tr']>=scheduledpass['tr'] and satpass['ts']<scheduledpass['ts']:
            overlap = True
        # Scheduled pass falls within test pass
        elif scheduledpass['tr']>=satpass['tr'] and scheduledpass['ts']<satpass['ts']:
            overlap = True
        # Pass start falls within pass
        elif satpass['tr']>=scheduledpass['tr'] and satpass['tr']<scheduledpass['ts']:
            overlap = True
        # Pass end falls within end
        elif satpass['ts']>=scheduledpass['tr'] and satpass['ts']<scheduledpass['ts']:
            overlap = True
        if overlap == True:
            break
        
    return overlap
        
def ordered_scheduler(passes, scheduledpasses):
    """Loop through a list of ordered passes and schedule each next one that fits"""
    # Loop over passes
    for satpass in passes:
        # Schedule if there is no overlap with already scheduled passes
        if overlap(satpass, scheduledpasses)==False:
            scheduledpasses.append(satpass)
    
    return scheduledpasses

def random_scheduler(passes, scheduledpasses):
    """Schedule passes based on random ordering"""
    # Shuffle passes
    random.shuffle(passes)

    return ordered_scheduler(passes, scheduledpasses)

def efficiency(passes):

    # Loop over passes
    start = False
    for satpass in passes:
        if start==False:
            dt = satpass['ts']-satpass['tr']
            tmin = satpass['tr']
            tmax = satpass['ts']
            start = True
        else:
            dt += satpass['ts']-satpass['tr']
            if satpass['tr']<tmin: tmin=satpass['tr']
            if satpass['ts']>tmax: tmax=satpass['ts']
    # Total time covered
    dttot = tmax-tmin
    
    return dt.total_seconds(),dttot.total_seconds(), dt.total_seconds()/dttot.total_seconds()

def find_passes(satellites, observer, tmin, tmax, minimum_altitude):
    # Loop over satellites
    passes = []
    passid = 0
    for satellite in satellites:
        # Set start time
        observer.date = ephem.date(tmin)
        
        # Load TLE
        try:
            sat_ephem = ephem.readtle(str(satellite.tle0),
                                      str(satellite.tle1),
                                      str(satellite.tle2))
        except (ValueError, AttributeError):
            continue

        # Loop over passes
        keep_digging = True
        while keep_digging:
            try:
                tr, azr, tt, altt, ts, azs = observer.next_pass(sat_ephem)
            except ValueError:
                break  # there will be sats in our list that fall below horizon, skip
            except TypeError:
                break  # if there happens to be a non-EarthSatellite object in the list
            except Exception:
                break

            if tr is None:
                break

            # using the angles module convert the sexagesimal degree into
            # something more easily read by a human
            try:
                elevation = format(math.degrees(altt), '.0f')
                azimuth_r = format(math.degrees(azr), '.0f')
                azimuth_s = format(math.degrees(azs), '.0f')
            except TypeError:
                break
            passid += 1

            # show only if >= configured horizon and in next 6 hours,
            # and not directly overhead (tr < ts see issue 199)
            if tr < ephem.date(tmax):
                if (float(elevation) >= minimum_altitude and tr < ts):
                    valid = True
                    if tr < ephem.Date(datetime.now() +
                                       timedelta(minutes=5)):
                        valid = False
                    satpass = {'passid': passid,
                               'mytime': str(observer.date),
                               'name': str(satellite.name),
                               'id': str(satellite.id),
                               'tle1': str(satellite.tle1),
                               'tle2': str(satellite.tle2),
                               'tr': tr.datetime(),  # Rise time
                               'azr': azimuth_r,     # Rise Azimuth
                               'tt': tt.datetime(),  # Max altitude time
                               'altt': elevation,    # Max altitude
                               'ts': ts.datetime(),  # Set time
                               'azs': azimuth_s,     # Set azimuth
                               'valid': valid,
                               'scheduled': False}
                    passes.append(satpass)
                observer.date = ephem.Date(ts).datetime() + timedelta(minutes=1)
            else:
                keep_digging = False

    return passes

def get_groundstation_info(ground_station_id):
    # Get first page
    client = requests.session()

    # Loop
    start = True
    found = False
    while True:
        if start:
            r = client.get("https://network.satnogs.org/api/stations")
            start = False
        else:
            nextpage = r.links.get("next")
            try:
                r = client.get(nextpage["url"])
            except TypeError:
                break

        # Get info
        for o in r.json():
            if o['id'] == ground_station_id:
                found = True
                break

        # Exit
        if found:
            break
    if found:
        return o
    else:
        return {}

if __name__ == "__main__":
    # Settings
    ground_station_id = 39
    tlefile = "vhf.txt"
    length_hours = 2
    
    # Get ground station information
    ground_station = get_groundstation_info(ground_station_id)

    # Set observer
    observer = ephem.Observer()
    observer.lon = str(ground_station['lng'])
    observer.lat = str(ground_station['lat'])
    observer.elevation = ground_station['altitude']
    minimum_altitude = ground_station['min_horizon']

    tmin = datetime.utcnow()
    tmax = datetime.utcnow()+timedelta(hours=length_hours)

    # Read satellites
    with open(tlefile, "r") as f:
        lines = f.readlines()
        satellites = [satellite(lines[i], lines[i+1], lines[i+2])
                      for i in range(0, len(lines), 3)]


    # Find passes
    passes = find_passes(satellites, observer, tmin, tmax, minimum_altitude)

    # Priorities
    priorities = {"40069": 1.000, "25338": 0.990, "28654": 0.990, "33591": 0.990}
    
    # List of scheduled passes
    # scheduledpasses = []
    scheduledpasses = get_scheduled_passes_from_network(ground_station_id, tmin, tmax)
    print("Found %d scheduled passes between %s and %s on ground station %d\n"%(len(scheduledpasses), tmin, tmax, ground_station_id))
    
    # Get passes of priority objects
    prioritypasses = []
    normalpasses = []
    for satpass in passes:
        # Get user defined priorities
        if satpass['id'] in priorities:
            satpass['priority'] = priorities[satpass['id']]
            prioritypasses.append(satpass)
        else:
            satpass['priority'] = float(satpass['altt'])/90.0
            normalpasses.append(satpass)
            
    # Priority scheduler
    prioritypasses = sorted(prioritypasses, key=lambda satpass: -satpass['priority'])
    scheduledpasses = ordered_scheduler(prioritypasses, scheduledpasses)

    # Random scheduler
    normalpasses = sorted(normalpasses, key=lambda satpass: -satpass['priority'])
    scheduledpasses = ordered_scheduler(normalpasses, scheduledpasses)

    dt, dttot, eff = efficiency(scheduledpasses)
    print("%d passes scheduled out of %d, %.0f s out of %.0f s at %.3f%% efficiency"%(len(scheduledpasses), len(passes), dt, dttot, 100*eff))
    
    # Find unique objects
    satids = sorted(set([satpass['id'] for satpass in passes]))

    # Set up figure
    fig = plt.figure(figsize=(20,len(satids)*0.2))
    ax = fig.add_subplot(111)
    ax.set_xlim(tmin, tmax)
    ax.set_ylim(-3,len(satids)+1)
    ax.xaxis.set_major_locator(HourLocator(xrange(0, 25, 3)))
    ax.xaxis.set_minor_locator(HourLocator(xrange(0, 25, 1)))
    ax.xaxis.set_major_formatter(DateFormatter('%Y-%m-%d %H:%M:%S'))
    ax.grid()
    ax.get_yaxis().set_visible(False)
    fig.autofmt_xdate(rotation=0, ha='center')
    plt.xlabel("Time (UTC) for station #%d"%ground_station_id)
    
    # Get list of colors
    colors = [key for key in mcolors.BASE_COLORS.keys() if key!='w']

    # Loop over objects
    for i, satid in enumerate(satids):
        plt.text(tmax+timedelta(minutes=5), i-0.25, satid, color=colors[i%len(colors)])
        for satpass in passes:
            if satpass['id']==satid:
                width = satpass['ts']-satpass['tr']
                ax.add_patch(Rectangle((satpass['tr'], i-0.4), width, 0.8, color=colors[i%len(colors)]))
                # Plot scheduled passes
                if satpass in scheduledpasses:
                    ax.add_patch(Rectangle((satpass['tr'], -2.4), width, 0.8, color=colors[i%len(colors)]))

    # Time axis setter
    plt.savefig("schedule.png")


#    print("%d passes scheduled out of %d, %.0f s out of %.0f s at %.3f%% efficiency"%(len(scheduledpasses), len(passes), dt, dttot, 100*eff))

#    for satpass in scheduledpasses:
    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        if satpass['scheduled']==False:
            print("%s %s %3d %3d %3d %5.2f | %s %s"%(satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"), satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"), float(satpass['azr']), float(satpass['altt']), float(satpass['azs']),satpass['priority'],satpass['id'], satpass['name'].rstrip()))
        else:
            print("%s %s %3d %3d %3d %5.2f | %s %s"%(satpass['tr'].strftime("%Y-%m-%dT%H:%M:%S"), satpass['ts'].strftime("%Y-%m-%dT%H:%M:%S"), 0.0, 0.0, 0.0, 0.0, satpass['id'], ""))

    # Print schedule commands
    for satpass in sorted(scheduledpasses, key=lambda satpass: satpass['tr']):
        if satpass['scheduled']==False:
            print("firefox \"https://network.satnogs.org/observations/new/?norad=%s&ground_station_id=%d&start_date=%s&end_date=%s\""%(satpass['id'], ground_station_id, (satpass['tr']-timedelta(minutes=1)).strftime("%Y/%m/%d%%20%H:%M"), (satpass['ts']+timedelta(minutes=1)).strftime("%Y/%m/%d%%20%H:%M")))
