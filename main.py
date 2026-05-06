import sys
sys.path.insert(0, '/opt/weixin-auto-generator')

from scheduler import Scheduler

if __name__ == "__main__":
    scheduler = Scheduler()
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        scheduler.generate_and_publish()
    else:
        scheduler.run()
