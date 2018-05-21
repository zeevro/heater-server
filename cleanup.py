import utils


def main():
    utils.sync_crontab(utils.read_boiler_all())


if __name__ == '__main__':
    main()
