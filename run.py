from myapp import app
from sys import argv


def main():
    try:
        port = int(argv[1])
        assert 0 < port < 0x10000
    except Exception:
        port = 8080

    app.run(host='0.0.0.0', port=port, debug=True)


if __name__ == '__main__':
    main()
