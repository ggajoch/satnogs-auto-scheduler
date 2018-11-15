# auto-scheduler

This is a tool to automatically compute passes of satellites on the
SatNOGS network. It uses code from the SatNOGS network scheduler. A
file with two-line elements of satellites to schedule needs to be
provided, as well as a SatNOGS station number. The scheduler will then
calculate passes and sort them based on the priorities dictionary, or
otherwise by their culmination altitude. The output are firefox
queries that allow the user to quickly calculate ('c' key) and
schedule ('s' key) passes using the SatNOGS API.