#!/usr/bin/python
from datetime import datetime
from paho.mqtt.publish import single
import sys
import time

from utils import get_redis
from consts import MAX_LOG_LINES, LOG_KEY, MQTT_CHANNEL, MQTT_KWARGS


def read_log(parse_time=False):
    s = get_redis()

    ret = []

    try:
        for line in s.lrange(LOG_KEY, 0, -1):
            line = line.split()

            ret.append({'time': datetime.fromtimestamp(float(line[0])), 'cmd': line[1]})
    except Exception:
        raise

    return ret


def work(cmd):
    s = get_redis()

    last_log = s.lindex(LOG_KEY, 0)
    if (not last_log) or last_log.split()[1] != cmd:
        s.lpush(LOG_KEY, '%.3f %s' % (time.time(), cmd))
        s.ltrim(LOG_KEY, 0, MAX_LOG_LINES - 1)

    single(MQTT_CHANNEL, cmd, retain=True, **MQTT_KWARGS)


def main():
    cmd = sys.argv[1].lower()

    work(cmd)


if '__main__' == __name__:
    main()
