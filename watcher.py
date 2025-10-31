import os
import json
import time
import logging
import requests
from collections import deque
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class LogWatcher:
    """
    Watches Nginx access logs for failovers and high error rates,
    sending alerts to Slack when thresholds are exceeded.
    """
    def __init__(self):
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL', '')
        self.error_threshold = float(os.getenv('ERROR_RATE_THRESHOLD', '2'))
        self.window_size = int(os.getenv('WINDOW_SIZE', '200'))
        self.cooldown_sec = int(os.getenv('ALERT_COOLDOWN_SEC', '300'))
        self.maintenance_mode = os.getenv('MAINTENANCE_MODE', 'false').lower() == 'true'
        self.log_file = '/var/log/nginx/access.log'
        
        self.last_pool = None
        self.request_window = deque(maxlen=self.window_size)
        self.last_failover_alert = 0
        self.last_error_rate_alert = 0
        
        logger.info(f"Watcher started with threshold={self.error_threshold}%, window={self.window_size}")


    def send_slack_alert(self, alert_type, message, details=None):
        """
        Sends a clean, user-friendly alert message to Slack.
        """
        now = time.time()

        if self.maintenance_mode:
            logger.info(f"[MAINTENANCE MODE] {alert_type} alert suppressed.")
            return
        
        if alert_type == 'failover':
            if now - self.last_failover_alert < self.cooldown_sec:
                return
            self.last_failover_alert = now
        elif alert_type == 'error_rate':
            if now - self.last_error_rate_alert < self.cooldown_sec:
                return
            self.last_error_rate_alert = now

        color = '#E53935' if alert_type == 'error_rate' else '#1E88E5'

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"{alert_type.replace('_', ' ').title()} Alert",
                    "text": message,
                    "fields": [
                        {"title": "Time", "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "short": True},
                        {"title": "Type", "value": alert_type, "short": True}
                    ],
                    "footer": "Blue/Green Deployment Monitor"
                }
            ]
        }

        if details:
            for key, value in details.items():
                payload["attachments"][0]["fields"].append({
                    "title": key,
                    "value": str(value),
                    "short": True
                })

        if self.slack_webhook:
            try:
                resp = requests.post(self.slack_webhook, json=payload, timeout=5)
                if resp.status_code == 200:
                    logger.info(f"[SLACK] {alert_type} alert sent successfully.")
                else:
                    logger.error(f"Slack returned status {resp.status_code}")
            except Exception as e:
                logger.error(f"Failed to send Slack alert: {e}")
        else:
            logger.info(f"[ALERT] {alert_type.upper()}: {message}")


    def check_failover(self, pool):
        """
        Detects when traffic switches between blue and green pools.
        """
        if self.last_pool is None:
            self.last_pool = pool
            logger.info(f"Initial pool detected: {pool}")
            return

        if pool and pool != self.last_pool:
            message = f"Traffic switched from '{self.last_pool}' to '{pool}'."
            details = {
                "Previous Pool": self.last_pool,
                "Current Pool": pool,
                "Recommended Action": "Verify that the new pool is stable and responding correctly."
            }
            logger.warning(f"[FAILOVER] {message}")
            self.send_slack_alert('failover', message, details)
            self.last_pool = pool


    def check_error_rate(self):
        """
        Checks the recent window of requests for error rates exceeding threshold.
        """
        if len(self.request_window) < 20:
            return
        
        total = len(self.request_window)
        errors = sum(1 for x in self.request_window if x)
        rate = (errors / total) * 100

        if rate > self.error_threshold:
            message = f"High error rate detected: {rate:.2f}% over the last {total} requests."
            details = {
                "Error Rate": f"{rate:.2f}%",
                "Threshold": f"{self.error_threshold}%",
                "Errors": errors,
                "Total Requests": total,
                "Suggested Action": "Inspect backend health and consider rerouting traffic."
            }
            logger.warning(f"[ERROR RATE] {message}")
            self.send_slack_alert('error_rate', message, details)


    def tail_log(self):
        """
        Continuously reads the Nginx access log and processes JSON entries.
        """
        logger.info(f"Monitoring log file: {self.log_file}")

        while not os.path.exists(self.log_file):
            logger.info("Waiting for log file to become available...")
            time.sleep(2)

        try:
            with open(self.log_file, 'r') as f:
                f.seek(0, 2)
                logger.info("Watcher is now monitoring new log entries.")

                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue

                    try:
                        log_entry = json.loads(line.strip())
                        pool = log_entry.get('pool', '')
                        upstream_status = log_entry.get('upstream_status', '')
                        had_error = False

                        if upstream_status:
                            statuses = str(upstream_status).split(', ')
                            had_error = any(s.startswith('5') for s in statuses if s.strip())

                        self.request_window.append(had_error)

                        if pool:
                            self.check_failover(pool)
                        
                        self.check_error_rate()
                    except json.JSONDecodeError:
                        continue

        except KeyboardInterrupt:
            logger.info("Watcher stopped manually.")
        except Exception as e:
            logger.error(f"Watcher encountered an error: {e}")
            raise


if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.tail_log()
