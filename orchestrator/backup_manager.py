"""Backup management using BorgBackup for supOS-bedrock
Handles scheduled and manual backups with restore capability
"""

import os
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import docker
from config import WORKSPACE

# Backup paths (configurable)
def get_backup_base():
    """Get backup base path from config or default"""
    config_file = Path("/volumes/supos/data/backend/system/backup_config.json")
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                return Path(config.get("backup_path", "/volumes/supos/backups"))
        except:
            pass
    return Path("/volumes/supos/backups")

# PostgreSQL connection
PG_CONTAINER = "postgresql"
PG_USER = "postgres"
PG_PASSWORD = "postgres"

# Paths to backup
VOLUMES_PATH = Path("/volumes/supos/data")
CONFIGS_PATH = Path(WORKSPACE)

client = docker.from_env()


class BackupManager:
    """Manages BorgBackup operations for supOS system"""

    def __init__(self):
        self.backup_base = get_backup_base()
        self.borg_repo = self.backup_base / "borg-repo"
        self.backup_lock = self.backup_base / ".backup.lock"
        self.ensure_borg_repo()

    def update_path(self, new_path: str):
        """Update backup path dynamically"""
        self.backup_base = Path(new_path)
        self.borg_repo = self.backup_base / "borg-repo"
        self.backup_lock = self.backup_base / ".backup.lock"
        self.ensure_borg_repo()
        print(f"Backup path updated to: {self.backup_base}")

    def ensure_borg_repo(self):
        """Initialize BorgBackup repository if not exists"""
        self.backup_base.mkdir(parents=True, exist_ok=True)

        if not (self.borg_repo / "config").exists():
            try:
                subprocess.run(
                    ["borg", "init", "--encryption=none", str(self.borg_repo)],
                    check=True,
                    capture_output=True,
                    text=True
                )
                print(f"Initialized Borg repository at {self.borg_repo}")
            except subprocess.CalledProcessError as e:
                raise Exception(f"Failed to init Borg repo: {e.stderr}")

    def acquire_lock(self) -> bool:
        """Acquire backup lock to prevent concurrent operations"""
        if self.backup_lock.exists():
            # Check if lock is stale (older than 4 hours)
            lock_age = datetime.now().timestamp() - self.backup_lock.stat().st_mtime
            if lock_age < 14400:  # 4 hours
                return False
            self.backup_lock.unlink()  # Remove stale lock

        self.backup_lock.touch()
        return True

    def release_lock(self):
        """Release backup lock"""
        self.backup_lock.unlink(missing_ok=True)

    def dump_databases(self, dump_path: Path) -> Dict[str, str]:
        """Dump all PostgreSQL databases"""
        dump_path.mkdir(parents=True, exist_ok=True)
        dumps = {}

        try:
            # Get list of databases
            result = subprocess.run(
                ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER,
                 "-t", "-c", "SELECT datname FROM pg_database WHERE datistemplate = false;"],
                capture_output=True,
                text=True,
                check=True,
                env={**os.environ, "PGPASSWORD": PG_PASSWORD}
            )

            databases = [db.strip() for db in result.stdout.split('\n') if db.strip()]

            # Dump each database
            for db_name in databases:
                dump_file = dump_path / f"{db_name}.sql"

                subprocess.run(
                    ["docker", "exec", PG_CONTAINER, "pg_dump", "-U", PG_USER,
                     "-d", db_name, "-f", f"/tmp/{db_name}.sql"],
                    check=True,
                    env={**os.environ, "PGPASSWORD": PG_PASSWORD}
                )

                # Copy dump from container
                subprocess.run(
                    ["docker", "cp", f"{PG_CONTAINER}:/tmp/{db_name}.sql", str(dump_file)],
                    check=True
                )

                dumps[db_name] = str(dump_file)
                print(f"Dumped database: {db_name}")

            return dumps

        except subprocess.CalledProcessError as e:
            raise Exception(f"Database dump failed: {e.stderr if e.stderr else str(e)}")

    def create_backup(self, backup_name: Optional[str] = None) -> Dict:
        """Create a new backup using BorgBackup"""
        if not self.acquire_lock():
            raise Exception("Backup already in progress")

        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_name = backup_name or f"backup_{timestamp}"

            # Create temporary dump directory
            temp_dump = self.backup_base / "temp_dumps" / timestamp
            temp_dump.mkdir(parents=True, exist_ok=True)

            # Step 1: Dump databases
            print("Dumping databases...")
            db_dumps = self.dump_databases(temp_dump / "databases")

            # Step 2: Create metadata file
            metadata = {
                "timestamp": timestamp,
                "name": archive_name,
                "databases": list(db_dumps.keys()),
                "created_at": datetime.now().isoformat()
            }

            metadata_file = temp_dump / "metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Step 3: Create Borg archive
            print(f"Creating Borg archive: {archive_name}")
            borg_cmd = [
                "borg", "create",
                "--stats",
                "--compression", "zstd,3",
                f"{self.borg_repo}::{archive_name}",
                str(temp_dump),
                str(VOLUMES_PATH),
                str(CONFIGS_PATH / ".env"),
                str(CONFIGS_PATH / "docker-compose-8c16g.yml"),
                str(CONFIGS_PATH / "docker-compose-4c8g.yml")
            ]

            result = subprocess.run(
                borg_cmd,
                capture_output=True,
                text=True,
                check=True
            )

            # Cleanup temp dumps
            subprocess.run(["rm", "-rf", str(temp_dump)], check=True)

            # Parse Borg output for stats
            stats = self._parse_borg_stats(result.stderr)

            return {
                "success": True,
                "archive_name": archive_name,
                "timestamp": timestamp,
                "databases": list(db_dumps.keys()),
                "stats": stats
            }

        except Exception as e:
            # Cleanup on error
            if temp_dump.exists():
                subprocess.run(["rm", "-rf", str(temp_dump)])
            raise Exception(f"Backup failed: {str(e)}")

        finally:
            self.release_lock()

    def list_backups(self) -> List[Dict]:
        """List all available backups"""
        try:
            result = subprocess.run(
                ["borg", "list", "--json", str(self.borg_repo)],
                capture_output=True,
                text=True,
                check=True
            )

            data = json.loads(result.stdout)
            backups = []

            for archive in data.get("archives", []):
                # Get detailed info
                info_result = subprocess.run(
                    ["borg", "info", "--json", f"{self.borg_repo}::{archive['name']}"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                info = json.loads(info_result.stdout)

                # Stats are in archives[0].stats (per-archive stats)
                archive_info = info.get("archives", [{}])[0]
                stats = archive_info.get("stats", {})

                backup_info = {
                    "name": archive["name"],
                    "timestamp": archive["time"],
                    "id": archive["id"],
                    "stats": {
                        "original_size": stats.get("original_size", 0),
                        "compressed_size": stats.get("compressed_size", 0),
                        "deduplicated_size": stats.get("deduplicated_size", 0)
                    }
                }
                backups.append(backup_info)

            backups.sort(key=lambda x: x["timestamp"], reverse=True)
            return backups

        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to list backups: {e.stderr}")
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise Exception(f"Failed to parse backup info: {str(e)}")

    def restore_backup(self, archive_name: str, target_path: Optional[str] = None) -> Dict:
        """Restore from a backup archive"""
        if not self.acquire_lock():
            raise Exception("Cannot restore: backup operation in progress")

        try:
            print(f"Starting restore from archive: {archive_name}")

            # Verify archive exists
            result = subprocess.run(
                ["borg", "list", "--json", str(self.borg_repo)],
                capture_output=True,
                text=True,
                check=True
            )
            archives = json.loads(result.stdout).get("archives", [])
            if not any(a["name"] == archive_name for a in archives):
                raise Exception(f"Archive not found: {archive_name}")

            # Step 1: Stop all services
            print("Stopping services...")
            self._stop_services()

            # Step 2: Extract archive to temporary location
            extract_temp = self.backup_base / "restore_temp"
            extract_temp.mkdir(parents=True, exist_ok=True)

            print(f"Extracting archive to {extract_temp}...")
            subprocess.run(
                ["borg", "extract", f"{self.borg_repo}::{archive_name}"],
                cwd=str(extract_temp),
                check=True,
                capture_output=True,
                text=True
            )

            # Step 3: Restore databases
            print("Restoring databases...")
            db_dump_paths = list(extract_temp.glob("*/databases"))
            if db_dump_paths:
                self._restore_databases(db_dump_paths[0])
            else:
                print("Warning: No database dumps found in backup")

            # Step 4: Restore volumes (carefully)
            print("Restoring volumes...")
            volumes_backup = list(extract_temp.glob("volumes/supos/data"))
            if volumes_backup:
                subprocess.run(
                    ["rsync", "-av", "--delete",
                     str(volumes_backup[0]) + "/", str(VOLUMES_PATH) + "/"],
                    check=True
                )

            # Step 5: Cleanup temp
            subprocess.run(["rm", "-rf", str(extract_temp)], check=True)

            # Step 6: Restart services
            print("Restarting services...")
            self._start_services()

            return {
                "success": True,
                "archive_name": archive_name,
                "restored_at": datetime.now().isoformat()
            }

        except Exception as e:
            # Attempt to restart services even on failure
            print(f"Restore error: {str(e)}")
            try:
                self._start_services()
            except:
                pass
            raise Exception(f"Restore failed: {str(e)}")

        finally:
            self.release_lock()

    def delete_backup(self, archive_name: str) -> Dict:
        """Delete a backup archive"""
        try:
            subprocess.run(
                ["borg", "delete", f"{self.borg_repo}::{archive_name}"],
                check=True,
                capture_output=True
            )

            # Compact repository
            subprocess.run(
                ["borg", "compact", str(self.borg_repo)],
                check=True
            )

            return {
                "success": True,
                "deleted": archive_name
            }

        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to delete backup: {e.stderr}")

    def _restore_databases(self, db_dump_path: Path):
        """Restore databases from SQL dumps"""
        for sql_file in db_dump_path.glob("*.sql"):
            db_name = sql_file.stem

            # Copy SQL file into container
            subprocess.run(
                ["docker", "cp", str(sql_file), f"{PG_CONTAINER}:/tmp/{sql_file.name}"],
                check=True
            )

            # Drop and recreate database
            subprocess.run(
                ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER,
                 "-c", f"DROP DATABASE IF EXISTS {db_name};"],
                env={**os.environ, "PGPASSWORD": PG_PASSWORD}
            )

            subprocess.run(
                ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER,
                 "-c", f"CREATE DATABASE {db_name};"],
                check=True,
                env={**os.environ, "PGPASSWORD": PG_PASSWORD}
            )

            # Restore from dump
            subprocess.run(
                ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER,
                 "-d", db_name, "-f", f"/tmp/{sql_file.name}"],
                check=True,
                env={**os.environ, "PGPASSWORD": PG_PASSWORD}
            )

            print(f"Restored database: {db_name}")

    def _stop_services(self):
        """Stop all Docker services"""
        subprocess.run(
            ["docker", "compose", "stop"],
            cwd=WORKSPACE,
            check=True
        )

    def _start_services(self):
        """Start all Docker services"""
        subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=WORKSPACE,
            check=True
        )

    def _parse_borg_stats(self, borg_output: str) -> Dict:
        """Parse Borg statistics from output"""
        stats = {
            "original_size": 0,
            "compressed_size": 0,
            "deduplicated_size": 0
        }

        # Parse Borg stats output
        for line in borg_output.split('\n'):
            if "Original size:" in line:
                stats["original_size"] = line.split()[-2]
            elif "Compressed size:" in line:
                stats["compressed_size"] = line.split()[-2]
            elif "Deduplicated size:" in line:
                stats["deduplicated_size"] = line.split()[-2]

        return stats


# Global instance
backup_manager = BackupManager()
