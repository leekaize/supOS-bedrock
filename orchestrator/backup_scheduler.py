"""Backup scheduler for automated backups
Uses APScheduler for cron-like scheduling without system dependencies
"""

import json
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from backup_manager import backup_manager

SCHEDULE_FILE = Path("/volumes/supos/data/backend/system/backup_schedule.json")


class BackupScheduler:
    """Manages scheduled backups using APScheduler"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.job_id = "auto_backup"
        self.load_schedule()
        self.scheduler.start()

    def load_schedule(self):
        """Load schedule from config file and apply it"""
        if SCHEDULE_FILE.exists():
            try:
                with open(SCHEDULE_FILE, 'r') as f:
                    config = json.load(f)

                if config.get("enabled"):
                    self._schedule_backup(config)
            except Exception as e:
                print(f"Failed to load backup schedule: {e}")

    def _schedule_backup(self, config: dict):
        """Schedule backup job with given config"""
        # Remove existing job if present
        if self.scheduler.get_job(self.job_id):
            self.scheduler.remove_job(self.job_id)

        # Parse schedule
        schedule_type = config.get("schedule_type", "daily")

        if schedule_type == "daily":
            hour = config.get("hour", 2)
            minute = config.get("minute", 0)
            trigger = CronTrigger(hour=hour, minute=minute)

        elif schedule_type == "weekly":
            day_of_week = config.get("day_of_week", 0)  # 0 = Monday
            hour = config.get("hour", 2)
            minute = config.get("minute", 0)
            trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)

        elif schedule_type == "custom":
            # Custom cron expression
            cron_expr = config.get("cron_expression", "0 2 * * *")
            trigger = CronTrigger.from_crontab(cron_expr)

        else:
            raise ValueError(f"Invalid schedule type: {schedule_type}")

        # Add job
        self.scheduler.add_job(
            self._execute_backup,
            trigger=trigger,
            id=self.job_id,
            replace_existing=True,
            kwargs={
                "retention_days": config.get("retention_days", 30),
                "max_backups": config.get("max_backups", 10)
            }
        )

        print(f"Scheduled backup: {schedule_type} at {config.get('hour', 2)}:{config.get('minute', 0):02d}")

    def _execute_backup(self, retention_days: int = 30, max_backups: int = 10):
        """Execute scheduled backup with retention policy"""
        try:
            print(f"Starting scheduled backup at {datetime.now()}")

            # Create backup
            result = backup_manager.create_backup()
            print(f"Backup created: {result['archive_name']}")

            # Apply retention policy
            self._apply_retention(retention_days, max_backups)

        except Exception as e:
            print(f"Scheduled backup failed: {e}")

    def _apply_retention(self, retention_days: int, max_backups: int):
        """Delete old backups based on retention policy"""
        try:
            backups = backup_manager.list_backups()

            # Sort by timestamp (newest first)
            backups.sort(key=lambda x: x["timestamp"], reverse=True)

            # Keep only max_backups most recent
            if len(backups) > max_backups:
                for backup in backups[max_backups:]:
                    print(f"Deleting old backup (exceeds max): {backup['name']}")
                    backup_manager.delete_backup(backup['name'])

            # Delete backups older than retention_days
            cutoff = datetime.now().timestamp() - (retention_days * 86400)
            for backup in backups:
                backup_time = datetime.fromisoformat(backup["timestamp"].replace("Z", "+00:00")).timestamp()
                if backup_time < cutoff:
                    print(f"Deleting expired backup: {backup['name']}")
                    backup_manager.delete_backup(backup['name'])

        except Exception as e:
            print(f"Retention cleanup failed: {e}")

    def update_schedule(self, config: dict) -> dict:
        """Update backup schedule

        Args:
            config: Schedule configuration dict

        Returns:
            Dict with update result
        """
        try:
            # Validate config
            required_fields = ["enabled", "schedule_type"]
            for field in required_fields:
                if field not in config:
                    raise ValueError(f"Missing required field: {field}")

            # Save config
            SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SCHEDULE_FILE, 'w') as f:
                json.dump(config, f, indent=2)

            # Apply schedule
            if config["enabled"]:
                self._schedule_backup(config)
            else:
                # Disable schedule
                if self.scheduler.get_job(self.job_id):
                    self.scheduler.remove_job(self.job_id)

            return {
                "success": True,
                "message": "Backup schedule updated",
                "config": config
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_schedule(self) -> dict:
        """Get current backup schedule configuration"""
        if SCHEDULE_FILE.exists():
            try:
                with open(SCHEDULE_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass

        # Default config
        return {
            "enabled": False,
            "schedule_type": "daily",
            "hour": 2,
            "minute": 0,
            "retention_days": 30,
            "max_backups": 10
        }

    def get_next_run(self) -> dict:
        """Get next scheduled backup time"""
        job = self.scheduler.get_job(self.job_id)
        if job:
            return {
                "scheduled": True,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None
            }
        return {
            "scheduled": False,
            "next_run": None
        }

    def shutdown(self):
        """Shutdown scheduler"""
        self.scheduler.shutdown()


# Global instance
backup_scheduler = BackupScheduler()
