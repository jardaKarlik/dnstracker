#!/usr/bin/env python3
"""
DNS Watchdog Agent - Monitors domain WHOIS records for changes
Runs on custom cron schedule, tracks state in JSON, sends push notifications
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import whois # <--- ADDED THIS LINE
from push_adapters import create_adapter

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


# Removed ZonerAPIClient class entirely


class WhoisClient:
    """Client for WHOIS domain information lookups"""

    def get_domain_info(self, domain: str) -> Optional[Dict]:
        """Fetch WHOIS information for a domain"""
        try:
            # Use whois.query for structured data
            whois_data = whois.query(domain)

            if not whois_data:
                logger.warning(f"No WHOIS data found for {domain}")
                return None

            # Extract relevant fields and standardize
            info = {
                "domain_name": whois_data.domain_name,
                "registrar": whois_data.registrar,
                "creation_date": whois_data.creation_date.isoformat() if whois_data.creation_date else None,
                "expiration_date": whois_data.expiration_date.isoformat() if whois_data.expiration_date else None,
                "last_updated": whois_data.last_updated.isoformat() if whois_data.last_updated else None,
                "name_servers": sorted([ns.lower() for ns in whois_data.name_servers]) if whois_data.name_servers else [],
                "status": whois_data.status,
                "registrant_name": whois_data.registrant_name,
                "registrant_organization": whois_data.registrant_organization,
                "dnssec": whois_data.dnssec # Add DNSSEC status
            }

            # Handle cases where some fields might be lists (e.g., status, name_servers)
            for key in ["creation_date", "expiration_date", "last_updated", "status"]:
                if isinstance(info.get(key), list):
                    info[key] = info[key][0] if info[key] else None
            if isinstance(info.get("name_servers"), str):
                info["name_servers"] = [info["name_servers"].lower()]


            return info
        except Exception as e:
            logger.error(f"Failed to fetch WHOIS info for {domain}: {e}", exc_info=True)
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
    
    def set_domain_state(self, domain: str, whois_info: Dict, timestamp: str = None):
        """Store WHOIS info for a domain"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        self.state[domain] = {
            "timestamp": timestamp,
            "whois_hash": self._hash_whois_info(whois_info), # Updated hash key
            "whois_info": whois_info # Store WHOIS info
        }
    
    @staticmethod
    def _hash_whois_info(whois_info: Dict) -> str: # Updated method name and signature
        """Generate hash of critical WHOIS info for comparison"""
        # Select critical fields for hashing to avoid alerts on trivial changes
        critical_fields = {
            "expiration_date": whois_info.get("expiration_date"),
            "status": whois_info.get("status"),
            "registrant_name": whois_info.get("registrant_name"),
            "registrant_organization": whois_info.get("registrant_organization"),
            "name_servers": whois_info.get("name_servers"),
            "dnssec": whois_info.get("dnssec")
        }
        info_str = json.dumps(critical_fields, sort_keys=True)
        return hashlib.sha256(info_str.encode()).hexdigest()


class ChangeDetector:
    """Detects and scores WHOIS changes"""
    
    # Critical WHOIS fields whose changes are highly important
    CRITICAL_WHOIS_FIELDS = {
        "expiration_date": 20, # Very critical if changes
        "status": 20,          # Very critical
        "name_servers": 15,    # High importance
        "registrant_name": 10, # Moderate importance
        "registrant_organization": 10, # Moderate importance
        "registrar": 5,        # Lower importance, but still good to know
        "dnssec": 15           # High importance if DNSSEC status changes
    }
    
    def __init__(self):
        self.change_history = []
    
    def detect_changes(self, old_info: Optional[Dict], new_info: Dict) -> Tuple[List[Dict], int]: # Updated method signature
        """
        Detect changes between old and new WHOIS info.
        Returns: (list of changes, importance_score)
        """
        if old_info is None:
            # First run - all records are "new" (initial sync)
            changes = [
                {
                    "action": "initial_sync",
                    "domain_name": new_info.get("domain_name"),
                    "timestamp": datetime.now().isoformat()
                }
            ]
            return changes, 0  # Don't alert on first run

        changes = []
        importance_score = 0
        
        for field, score_value in self.CRITICAL_WHOIS_FIELDS.items():
            old_val = old_info.get(field)
            new_val = new_info.get(field)

            if old_val != new_val:
                change = {
                    "action": "modified",
                    "field": field,
                    "old_value": old_val,
                    "new_value": new_val,
                    "timestamp": datetime.now().isoformat()
                }
                changes.append(change)
                importance_score += score_value
        
        return changes, importance_score
    
    # Removed _score_record_type as it's no longer relevant


class DNSWatchdogAgent:
    """Main watchdog agent orchestrator"""
    
    def __init__(self):
        # Load environment variables
        # ZONER_API_TOKEN is no longer needed
        self.push_service_type = os.getenv("PUSH_SERVICE_TYPE", "webhook") # Default to generic webhook
        self.push_service_url = os.getenv("PUSH_SERVICE_URL")
        self.push_token = os.getenv("PUSH_TOKEN")
        # Optional keys for specific adapters
        self.pushover_user_key = os.getenv("PUSHOVER_USER_KEY")
        self.fcm_device_token = os.getenv("FCM_DEVICE_TOKEN")


        self.domains_to_monitor = os.getenv("DOMAINS_TO_MONITOR", "").split(",")
        
        # Validate environment variables (simplified for WHOIS)
        # ZONER_API_TOKEN is not validated here as it's not used
        if not self.push_service_url and self.push_service_type.lower() not in ["pushover", "firebase", "pushbullet"] : # Push service URL is crucial for webhooks
            raise ValueError("PUSH_SERVICE_URL environment variable not set for webhook-based push notifications")
        
        self.domains_to_monitor = [d.strip() for d in self.domains_to_monitor if d.strip()]
        if not self.domains_to_monitor:
            raise ValueError("DOMAINS_TO_MONITOR environment variable not set or empty")
        
        # Initialize components
        self.whois_client = WhoisClient() # <--- NEW: WHOIS client
        self.state_manager = DNSStateManager()
        self.change_detector = ChangeDetector()
        
        # Initialize notification sender using the factory (improved logic from previous fix)
        adapter_kwargs: Dict[str, Any] = {}
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
            if self.fcm_device_token:
                adapter_kwargs["device_token"] = self.fcm_device_token
        elif push_service_type_lower == "pushover":
            if not self.push_token:
                raise ValueError("PUSH_TOKEN (api_token) environment variable not set for Pushover")
            if not self.pushover_user_key:
                raise ValueError("PUSHOVER_USER_KEY environment variable not set for Pushover")
            adapter_kwargs["api_token"] = self.push_token
            adapter_kwargs["user_key"] = self.pushover_user_key
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
        Run a single WHOIS check for a domain.
        
        Args:
            domain: Domain to check
        
        Returns:
            True if check completed successfully, False otherwise
        """
        logger.info(f"Starting WHOIS check for {domain}")
        
        # Fetch current WHOIS info
        current_whois_info = self.whois_client.get_domain_info(domain) # <--- UPDATED
        if current_whois_info is None:
            logger.error(f"Failed to fetch WHOIS info for {domain}")
            return False
        
        # Get previous state
        previous_state = self.state_manager.get_domain_state(domain)
        previous_whois_info = previous_state.get("whois_info") if previous_state else None # <--- UPDATED
        
        # Detect changes
        changes, importance_score = self.change_detector.detect_changes(previous_whois_info, current_whois_info) # <--- UPDATED
        
        # Save new state
        self.state_manager.set_domain_state(domain, current_whois_info) # <--- UPDATED
        self.state_manager.save_state()
        
        # Trigger notifications based on importance
        if changes:
            if previous_whois_info is None:
                logger.info(f"Initial sync for {domain} - no notification sent")
                # For karlik.cz, if it's currently available, this is where we'd notify
                # However, initial sync is not an alert
            elif importance_score >= 20:
                title = f"🚨 CRITICAL: WHOIS changes detected on {domain}"
                message = f"{len(changes)} critical WHOIS field(s) changed - requires immediate attention"
                logger.warning(f"Critical changes detected for {domain} (score: {importance_score})")
                self.notification_sender.send(title, message, changes, importance_score, domain)
            elif importance_score >= 10:
                title = f"⚠️ WARNING: WHOIS changes detected on {domain}"
                message = f"{len(changes)} important WHOIS field(s) changed - review required"
                logger.warning(f"Warning: WHOIS changes for {domain} (score: {importance_score})")
                self.notification_sender.send(title, message, changes, importance_score, domain)
            elif importance_score > 0:
                title = f"ℹ️ INFO: WHOIS changes on {domain}"
                message = f"{len(changes)} WHOIS field(s) changed"
                logger.info(f"Info: Minor WHOIS changes for {domain} (score: {importance_score})")
                self.notification_sender.send(title, message, changes, importance_score, domain)
        else:
            logger.info(f"No changes detected for {domain}")
        
        return True
    
    def run_full_check(self) -> Dict[str, bool]:
        """
        Run WHOIS checks for all monitored domains.
        
        Returns:
            Dict mapping domain to check result
        """
        logger.info("=" * 60)
        logger.info("Running full WHOIS watchdog check")
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
