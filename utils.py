from datetime import datetime, timedelta
from subprocess import call
from os import remove
from functools import wraps
from flask import session, redirect, request, url_for
from threading import Thread
import redis
import uuid

from consts import HEATER_ITEMS_KEY, HEATER_TOKEN_KEY, REDIS_KWARGS


DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
DAYS_REV = dict(map(reversed, enumerate(DAYS)))

TIME_FORMAT = '%H%M'
DATE_FORMAT = '%Y%m%d'

WEB_TIME_FORMAT = '%I:%M %p'
WEB_DATE_FORMAT = '%d/%m/%Y'

ON_CMD = '/var/www/boiler.py on >> /var/log/boiler-error.log 2>&1'
OFF_CMD = '/var/www/boiler.py off >> /var/log/boiler-error.log 2>&1'

TMP_CRON_PATH = '/tmp/tmp_cron'

CRONTAB_CMD = ['crontab']


redis_connection = None


def get_redis():
    global redis_connection

    if redis_connection is None:
        redis_connection = redis.Redis(decode_responses=True, **REDIS_KWARGS)

    return redis_connection


def login_required(f):
    @wraps(f)
    def helper(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login', next=request.path))

        return f(*args, **kwargs)

    return helper


class Cron(object):
    def __init__(self, minute='*', hour='*', day='*', month='*', weekday='*', task=''):
        self.minute = minute
        self.hour = hour
        self.day = day
        self.month = month
        self.weekday = weekday
        self.task = task

    def pack(self):
        return ' '.join(map(str, [self.minute, self.hour, self.day, self.month, self.weekday, self.task])) + '\n'

    @classmethod
    def parse(cls, s):
        return cls(*s.split(None, 5))


def new_date():
    return datetime.now().strftime(DATE_FORMAT)


def new_time():
    return (datetime.now() + timedelta(minutes=1)).strftime(TIME_FORMAT)


def get_ranges(items, str_func=str, sep=',', range_sep='-'):
    r = []
    t = None
    for i in sorted(items) + [None]:
        if t is None:
            t = [i, i]
        elif i == t[1] + 1:
            t[1] = i
        else:
            if t[0] == t[1]:
                r.append(str_func(t[0]))
            else:
                r.append(range_sep.join(map(str_func, t)))
            t = [i, i]
    return sep.join(r)


class B(object):
    def __init__(self, schedule_type='once', days=new_date(), on_time=new_time(), duration=20, id_=None, web=False):
        self.schedule_type = schedule_type
        self.days = datetime.strptime(days, WEB_DATE_FORMAT).strftime(DATE_FORMAT) if (web and schedule_type == 'once') else days
        self.on_time = datetime.strptime(on_time, WEB_TIME_FORMAT) if web else datetime.strptime(on_time, TIME_FORMAT)
        self.duration = int(duration)
        self.id = id_

    @property
    def days_str(self):
        try:
            if self.schedule_type == 'weekly':
                return get_ranges(map(int, self.days.split(',')), DAYS.__getitem__, ', ', ' - ')

            if self.schedule_type == 'once':
                return datetime.strptime(self.days, DATE_FORMAT).strftime(WEB_DATE_FORMAT)

            return ''
        except Exception:
            return ''

    @property
    def web_time(self):
        return self.on_time.strftime(WEB_TIME_FORMAT)

    def __str__(self):
        return '%s %s %s for %d minutes' % (self.schedule_type.title(),
                                            self.days_str,
                                            self.on_time.strftime('%I:%M %p'),
                                            self.duration)

    def pack(self):
        return '%s %s %s %d' % (self.schedule_type,
                                self.days,
                                self.on_time.strftime(TIME_FORMAT),
                                self.duration)

    @property
    def crons(self):
        if self.schedule_type == 'weekly':
            off_time = self.on_time + timedelta(minutes=self.duration)
            on_weekdays = get_ranges(map(int, self.days.split(',')))
            if off_time.day > self.on_time.day:
                off_weekdays = get_ranges((int(i) + 1) % 6 for i in self.days.split(','))
            else:
                off_weekdays = on_weekdays

            return [Cron(minute=self.on_time.minute,
                         hour=self.on_time.hour,
                         weekday=on_weekdays,
                         task=ON_CMD),
                    Cron(minute=off_time.minute,
                         hour=off_time.hour,
                         weekday=off_weekdays,
                         task=OFF_CMD)]

        if self.schedule_type == 'once':
            on_date = datetime.strptime(self.days, DATE_FORMAT) + timedelta(hours=self.on_time.hour, minutes=self.on_time.minute)
            off_date = on_date + timedelta(minutes=self.duration)

            return [Cron(minute=on_date.minute,
                         hour=on_date.hour,
                         day=on_date.day,
                         month=on_date.month,
                         task=ON_CMD),
                    Cron(minute=off_date.minute,
                         hour=off_date.hour,
                         day=off_date.day,
                         month=off_date.month,
                         task=OFF_CMD)]

        return []

    @classmethod
    def parse(cls, s, id_=None):
        return cls(*s.split(), id_=id_)


def read_boiler_all():
    s = get_redis()

    if s.get(HEATER_TOKEN_KEY) is None:
        s.set(HEATER_TOKEN_KEY, uuid.uuid4())

    return [B.parse(line, n) for n, line in enumerate(s.lrange(HEATER_ITEMS_KEY, 0, -1))]


def read_boiler(id_=None):
    s = get_redis()

    token = s.get(HEATER_TOKEN_KEY)

    if id_ is None:
        return None, token

    t = s.lindex(HEATER_ITEMS_KEY, id_)

    if t is None:
        return None, token

    return B.parse(t, id_), token


def update_boiler(item, token, insert_on_top=False):
    s = get_redis()

    if str(token) != str(s.get(HEATER_TOKEN_KEY)):
        return False

    with s.pipeline() as p:

        if item.id is None:
            (p.lpush if insert_on_top else p.rpush)(HEATER_ITEMS_KEY, item.pack())
        else:
            p.lset(HEATER_ITEMS_KEY, item.id, item.pack())

        p.set(HEATER_TOKEN_KEY, uuid.uuid4())

        p.execute()

    return True


def remove_boiler(item, token):
    s = get_redis()

    if str(token) != str(s.get(HEATER_TOKEN_KEY)):
        return False

    with s.pipeline() as p:
        p.lrem(HEATER_ITEMS_KEY, item.pack(), 1)
        p.set(HEATER_TOKEN_KEY, uuid.uuid4())
        p.execute()

    return True


def sync_crontab(wait=True):
    if not wait:
        Thread(target=sync_crontab).start()
        return

    crons = [Cron(minute='*/10', task='python /var/www/cleanup.py').pack()]
    for b in read_boiler_all():
        crons += [c.pack() for c in b.crons]
    crontab = ''.join(crons)

    with open(TMP_CRON_PATH, 'w') as out_f:
        out_f.write(crontab)

    ret = call(CRONTAB_CMD + [TMP_CRON_PATH])

    remove(TMP_CRON_PATH)

    return ret
