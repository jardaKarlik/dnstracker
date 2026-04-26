#!/usr/bin/env python3
"""
DNS Watchdog Agent - Monitors domain DNS records for changes
Runs on custom cron schedule, tracks state in JSON, sends push notifications
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import requests
from pathlib import Path
from push_adapters import create_adapter # <--- ADDED THIS LINE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('dns_watchdog.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ZonerAPIClient:
    """Client for ZONER REST API DNS operations"""
    
    BASE_URL = "https://api.czechia.com"
    
    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.session = requests.Session()
        self.session.headers.update({
            "authorizationToken": auth_token
        })
    
    def get_dns_records(self, domain: str) -> Optional[Dict]:
        """Fetch DNS records for a domain"""
        try:
            url = f"{self.BASE_URL}/api/DNS/{domain}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch DNS records for {domain}: {e}")
            return None
    
    def get_allowed_ips(self) -> Optional[List[str]]:
        """Fetch allowed IP addresses"""
        try:
            url = f"{self.BASE_URL}/api/Customer/AllowedIP"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch allowed IPs: {e}")
            return None


class DNSStateManager:
    """Manages DNS state persistence in JSON"""
    
    def __init__(self, state_file: str = "dns_state.json"):
        self.state_file = Path(state_file)
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load state from JSON file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}, starting fresh")
                return {}
        return {}
    
    def save_state(self):
        """Save state to JSON file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            logger.info("State saved successfully")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def get_domain_state(self, domain: str) -> Optional[Dict]:
        """Get stored state for a domain"""
        return self.state.get(domain)
    
    def set_domain_state(self, domain: str, records: Dict, timestamp: str = None):
        """Store state for a domain"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        self.state[domain] = {
            "timestamp": timestamp,
            "records_hash": self._hash_records(records),
            "records": records
        }
    
    @staticmethod
    def _hash_records(records: Dict) -> str:
        """Generate hash of DNS records for comparison"""
        record_str = json.dumps(records, sort_keys=True)
        return hashlib.sha256(record_str.encode()).hexdigest()


class ChangeDetector:
    """Detects and scores DNS changes"""
    
    # Priority levels for different record types
    CRITICAL_TYPES = {"A", "AAAA", "MX"}  # Critical for service
    HIGH_TYPES = {"CNAME", "NS"}  # Affects routing
    MEDIUM_TYPES = {"TXT", "SPF", "DKIM"}  # Security/verification
    LOW_TYPES = {"SRV", "CAA"}  # Less critical
    
    def __init__(self):
        self.change_history = []
    
    def detect_changes(self, old_records: Optional[Dict], new_records: Dict) -> Tuple[List[Dict], int]:
        """
        Detect changes between old and new DNS records.
        Returns: (list of changes, importance_score)
        """
        if old_records is None:
            # First run - all records are "new"
            changes = [
                {
                    "type": "initial_sync",
                    "records_count": len(new_records.get("records", [])),
                    "timestamp": datetime.now().isoformat()
                }
            ]
            return changes, 0  # Don't alert on first run
        
        old_recs = {r["name"]: r for r in old_records.get("records", [])}
        new_recs = {r["name"]: r for r in new_records.get("records", [])}
        
        changes = []
        importance_score = 0
        
        # Detect added records
        for name, new_rec in new_recs.items():
            if name not in old_recs:
                change = {
                    "action": "added",
                    "name": name,
                    "type": new_rec.get("type"),
                    "content": new_rec.get("content"),
                    "ttl": new_rec.get("ttl"),
                    "timestamp": datetime.now().isoformat()
                }
                changes.append(change)
                importance_score += self._score_record_type(new_rec.get("type"))
        
        # Detect removed records
        for name, old_rec in old_recs.items():
            if name not in new_recs:
                change = {
                    "action": "removed",
                    "name": name,
                    "type": old_rec.get("type"),
                    "content": old_rec.get("content"),
                    "ttl": old_rec.get("ttl"),
                    "timestamp": datetime.now().isoformat()
                }
                changes.append(change)
                importance_score += self._score_record_type(old_rec.get("type")) + 5  # Removal is worse
        
        # Detect modified records
        for name, new_rec in new_recs.items():
            if name in old_recs:
                old_rec = old_recs[name]
                if old_rec.get("content") != new_rec.get("content"):
                    change = {
                        "action": "modified",
                        "name": name,
                        "type": new_rec.get("type"),
                        "old_content": old_rec.get("content"),
                        "new_content": new_rec.get("content"),
                        "old_ttl": old_rec.get("ttl"),
                        "new_ttl": new_rec.get("ttl"),
                        "timestamp": datetime.now().isoformat()
                    }
                    changes.append(change)
                    importance_score += self._score_record_type(new_rec.get("type")) + 3  # Modification is significant
        
        return changes, importance_score
    
    @staticmethod
    def _score_record_type(record_type: str) -> int:
        """Score the importance of a record type change"""
        if record_type in ChangeDetector.CRITICAL_TYPES:
            return 10
        elif record_type in ChangeDetector.HIGH_TYPES:
            return 7
        elif record_type in ChangeDetector.MEDIUM_TYPES:
            return 4
        elif record_type in ChangeDetector.LOW_TYPES:
            return 2
        return 1



class DNSWatchdogAgent:
    """Main watchdog agent orchestrator"""
    
    def __init__(self):
        # Load environment variables
        self.api_token = os.getenv("ZONER_API_TOKEN")
        self.push_service_type = os.getenv("PUSH_SERVICE_TYPE", "webhook") # Default to generic webhook
        self.push_service_url = os.getenv("PUSH_SERVICE_URL")
        self.push_token = os.getenv("PUSH_TOKEN")
        self.domains_to_monitor = os.getenv("DOMAINS_TO_MONITOR", "").split(",")
        
        # Validate environment variables
        if not self.api_token:
            raise ValueError("ZONER_API_TOKEN environment variable not set")
        if not self.push_service_url:
            raise ValueError("PUSH_SERVICE_URL environment variable not set for push notifications")
        
        self.domains_to_monitor = [d.strip() for d in self.domains_to_monitor if d.strip()]
        if not self.domains_to_monitor:
            raise ValueError("DOMAINS_TO_MONITOR environment variable not set or empty")
        
        # Initialize components
        self.api_client = ZonerAPIClient(self.api_token)
        self.state_manager = DNSStateManager()
        self.change_detector = ChangeDetector()
        
        # Initialize notification sender using the factory
        adapter_kwargs = {}
        push_service_type_lower = self.push_service_type.lower()

        if push_service_type_lower in ["discord", "slack", "webhook"]:
            # These services primarily use a webhook URL
            if not self.push_service_url:
                raise ValueError(f"PUSH_SERVICE_URL environment variable not set for {self.push_service_type} notifications")
            adapter_kwargs["webhook_url"] = self.push_service_url
            # Only generic webhook uses PUSH_TOKEN as an auth_token
            if push_service_type_lower == "webhook" and self.push_token:
                adapter_kwargs["auth_token"] = self.push_token
        elif push_service_type_lower == "firebase":
            if not self.push_token:
                raise ValueError("PUSH_TOKEN (server_key) environment variable not set for Firebase")
            adapter_kwargs["server_key"] = self.push_token
            if os.getenv("FCM_DEVICE_TOKEN"): # Optional device token for Firebase
                adapter_kwargs["device_token"] = os.getenv("FCM_DEVICE_TOKEN")
        elif push_service_type_lower == "pushover":
            if not self.push_token:
                raise ValueError("PUSH_TOKEN (api_token) environment variable not set for Pushover")
            if not os.getenv("PUSHOVER_USER_KEY"):
                raise ValueError("PUSHOVER_USER_KEY environment variable not set for Pushover")
            adapter_kwargs["api_token"] = self.push_token
            adapter_kwargs["user_key"] = os.getenv("PUSHOVER_USER_KEY")
        elif push_service_type_lower == "pushbullet":
            if not self.push_token:
                raise ValueError("PUSH_TOKEN (access_token) environment variable not set for Pushbullet")
            adapter_kwargs["access_token"] = self.push_token
        else:
            raise ValueError(f"Unknown or unsupported PUSH_SERVICE_TYPE: {self.push_service_type}")

        self.notification_sender = create_adapter(self.push_service_type, **adapter_kwargs)
        
        logger.info(f"DNS Watchdog Agent initialized for domains: {', '.join(self.domains_to_monitor)}")
    
    def run_check(self, domain: str) -> bool:
        """
        Run a single DNS check for a domain.
        
        Args:
            domain: Domain to check
        
        Returns:
            True if check completed successfully, False otherwise
        """
        logger.info(f"Starting DNS check for {domain}")
        
        # Fetch current DNS records
        current_records = self.api_client.get_dns_records(domain)
        if current_records is None:
            logger.error(f"Failed to fetch DNS records for {domain}")
            return False
        
        # Get previous state
        previous_state = self.state_manager.get_domain_state(domain)
        previous_records = previous_state.get("records") if previous_state else None
        
        # Detect changes
        changes, importance_score = self.change_detector.detect_changes(previous_records, current_records)
        
        # Save new state
        self.state_manager.set_domain_state(domain, current_records)
        self.state_manager.save_state()
        
        # Trigger notifications based on importance
        if changes:
            if previous_records is None:
                logger.info(f"Initial sync for {domain} - no notification sent")
            elif importance_score >= 20:
                title = f"🚨 CRITICAL: DNS changes detected on {domain}"
                message = f"{len(changes)} DNS record(s) changed - requires immediate attention"
                logger.warning(f"Critical changes detected for {domain} (score: {importance_score})")
                self.notification_sender.send(title, message, changes, importance_score, domain)
            elif importance_score >= 10:
                title = f"⚠️ WARNING: DNS changes detected on {domain}"
                message = f"{len(changes)} DNS record(s) changed - review required"
                logger.warning(f"Warning: DNS changes for {domain} (score: {importance_score})")
                self.notification_sender.send(title, message, changes, importance_score, domain)
            elif importance_score > 0:
                title = f"ℹ️ INFO: DNS changes on {domain}"
                message = f"{len(changes)} DNS record(s) changed"
                logger.info(f"Info: Minor DNS changes for {domain} (score: {importance_score})")
                self.notification_sender.send(title, message, changes, importance_score, domain)
        else:
            logger.info(f"No changes detected for {domain}")
        
        return True
    
    def run_full_check(self) -> Dict[str, bool]:
        """
        Run DNS checks for all monitored domains.
        
        Returns:
            Dict mapping domain to check result
        """
        logger.info("=" * 60)
        logger.info("Running full DNS watchdog check")
        logger.info("=" * 60)
        
        results = {}
        for domain in self.domains_to_monitor:
            try:
                results[domain] = self.run_check(domain)
            except Exception as e:
                logger.error(f"Exception checking {domain}: {e}", exc_info=True)
                results[domain] = False
        
        logger.info("=" * 60)
        logger.info("Full check completed")
        logger.info("=" * 60)
        
        return results


def main():
    """Entry point for the watchdog agent"""
    try:
        agent = DNSWatchdogAgent()
        results = agent.run_full_check()
        
        # Log summary
        successful = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(f"Check summary: {successful}/{total} domains checked successfully")
        
        # Exit with error code if any checks failed
        exit(0 if successful == total else 1)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
