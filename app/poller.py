import threading
import time
from typing import Optional
from converter import PicklistConverter
from database import SQLiteManager


class PollingService:
    def __init__(self, converter: PicklistConverter, sqlite_manager: SQLiteManager):
        self.converter = converter
        self.sqlite_manager = sqlite_manager
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def _poll_loop(self):
        """Background polling loop"""
        while self.running:
            try:
                # Get polling interval from database
                defaults = self.sqlite_manager.get_quotation_defaults()
                interval = defaults.get('polling_interval_seconds', 60) if defaults else 60

                # Convert all pending picklists
                self.converter.convert_all_pending()

                # Sleep for the configured interval
                for _ in range(interval):
                    if not self.running:
                        break
                    time.sleep(1)

            except Exception as e:
                print(f"Polling error: {str(e)}")
                time.sleep(5)

    def start(self) -> tuple[bool, str]:
        """Start the polling service"""
        with self.lock:
            if self.running:
                return (False, "Polling service is already running")

            self.running = True
            self.thread = threading.Thread(target=self._poll_loop, daemon=True)
            self.thread.start()
            return (True, "Polling service started")

    def stop(self) -> tuple[bool, str]:
        """Stop the polling service"""
        with self.lock:
            if not self.running:
                return (False, "Polling service is not running")

            self.running = False
            if self.thread:
                self.thread.join(timeout=5)
            return (True, "Polling service stopped")

    def is_running(self) -> bool:
        """Check if polling service is running"""
        with self.lock:
            return self.running

    def get_status(self) -> dict:
        """Get polling service status"""
        defaults = self.sqlite_manager.get_quotation_defaults()
        interval = defaults.get('polling_interval_seconds', 60) if defaults else 60

        return {
            'running': self.is_running(),
            'interval_seconds': interval
        }
