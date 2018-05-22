from flask import Flask, request, session, render_template, redirect, url_for
from utils import login_required, read_boiler_all, read_boiler, update_boiler, remove_boiler, sync_crontab, B, DAYS, ON_CMD, OFF_CMD, WEB_DATE_FORMAT, WEB_TIME_FORMAT
from boiler import read_log, work as boiler_work
from datetime import datetime

import time
import subprocess

from consts import PASSWORD

app = Flask(__name__)
app.secret_key = '1234'


def _web_time():
    return time.mktime(time.localtime())


@app.route('/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if 'username' in session:
            return redirect(request.args.get('next') or url_for('items'))

        return render_template('login.html',
                               next=request.args.get('next') or '',
                               time=_web_time())

    if request.form['password'] != PASSWORD:
        return render_template('login.html',
                               message='Bad login!',
                               next=request.args.get('next') or '',
                               time=_web_time())

    session['username'] = request.form['username']

    return redirect(request.form.get('next') or url_for('items'))


@app.route('/logout/')
def logout():
    session.pop('username', None)

    return redirect(url_for('login'))


@app.route('/')
@login_required
def items():
    items = read_boiler_all()

    return render_template('items.html',
                           message=request.args.get('message') or '',
                           items=items,
                           time=_web_time(),
                           log=read_log(True))


@app.route('/edit/', methods=['GET', 'POST'])
@login_required
def edit():
    item_id = request.args.get('id')
    item, token = read_boiler(item_id)
    item = item or B()

    if request.method == 'GET':
        return render_template('edit.html',
                               token=token,
                               item=item,
                               days=[(str(i), d) for i, d in enumerate(DAYS)],
                               time=_web_time())

    if not request.form['days']:
        return redirect(url_for('items', message='No day(s) in request!'))

    if not request.form['days']:
        return redirect(url_for('items', message='No time in request!'))

    item = B(request.form['schedule_type'],
             request.form['days'],
             request.form['on_time'] or datetime.now().strftime(WEB_TIME_FORMAT),
             request.form['duration'],
             item_id,
             web=True)

    if not update_boiler(item, request.form['token']):
        return redirect(url_for('items', message='Edit operation out of sync!'))

    if not request.form['on_time']:
        subprocess.call(ON_CMD.split())

    sync_crontab(False)

    return redirect(url_for('items'))


@app.route('/delete/')
@login_required
def delete():
    item_id = int(request.args['id'])
    item, token = read_boiler(item_id)

    sure = bool(request.args.get('sure'))

    if not sure:
        return render_template('delete.html',
                               token=token,
                               item=item,
                               time=_web_time())

    if not remove_boiler(item, request.args['token']):
        return redirect(url_for('items', message='Delete operation out of sync!'))

    sync_crontab(False)

    return redirect(url_for('items'))


@app.route('/turn_on/')
@login_required
def turn_on():
    duration = request.args.get('duration')

    # TODO: Look for an appropriate existing item and add to its duration

    if duration:
        items, token = read_boiler()

        new_item = B('once',
                     datetime.now().strftime(WEB_DATE_FORMAT),
                     datetime.now().strftime(WEB_TIME_FORMAT),
                     duration,
                     web=True)

        if not update_boiler(new_item, token, insert_on_top=True):
            return redirect(url_for('items', message='Edit operation out of sync!'))

        sync_crontab(False)

    boiler_work(ON_CMD.split()[1])

    return redirect(url_for('items'))


@app.route('/turn_off/')
@login_required
def turn_off():
    boiler_work(OFF_CMD.split()[1])

    return redirect(url_for('items'))
