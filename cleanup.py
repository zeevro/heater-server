from datetime import datetime, timedelta
import utils


MAX_RETRIES = 5


def main():
    success = False
    retries = 0
    while (not success) and retries <= MAX_RETRIES:
        success = True

        token = utils.read_boiler(None)[1]

        for item in reversed(utils.read_boiler_all()):
            if item.schedule_type != 'once':
                continue
            off_time = datetime.combine(datetime.strptime(item.days, utils.DATE_FORMAT), item.on_time.time()) + timedelta(minutes=item.duration)
            print(off_time)
            if off_time + timedelta(days=1) < datetime.now():
                if not utils.remove_boiler(item, token):
                    success = False
                    retries += 1
                    break
                token = utils.read_boiler(None)[1]

    utils.sync_crontab(utils.read_boiler_all())


if __name__ == '__main__':
    main()
