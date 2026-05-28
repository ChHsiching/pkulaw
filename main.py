import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from src.crawler import run

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Progress has been saved. Run again to resume.")
