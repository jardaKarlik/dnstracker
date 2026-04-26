#!/usr/bin/env python3
"""
Push Notification Adapters for different services
Supports Firebase, Pushover, Pushbullet, generic webhooks
"""

import logging
import requests
from abc import ABC, abstractmethod
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class PushNotificationAdapter(ABC):
    """Abstract base class for push notification adapters"""
    
    @abstractmethod
    def send(self, title: str, message: str, changes: List[Dict], 
             importance_score: int, domain: str) -> bool:
        """Send notification through the service"""
        pass


class FirebaseCloudMessaging(PushNotificationAdapter):
    """Firebase Cloud Messaging adapter"""
    
    def __init__(self, server_key: str, device_token: str = None):
        self.server_key = server_key
        self.device_token = device_token
        self.url = "https://fcm.googleapis.com/fcm/send"
    
    def send(self, title: str, message: str, changes: List[Dict], 
             importance_score: int, domain: str) -> bool:
        """Send notification via FCM"""
        try:
            payload = {
                "notification": {
                    "title": title,
                    "body": message,
                    "sound": "default",
                    "priority": self._get_priority(importance_score)
                },
                "data": {
                    "domain": domain,
                    "importance_score": str(importance_score),
                    "changes_count": str(len(changes)),
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            if self.device_token:
                payload["to"] = self.device_token
            else:
                payload["condition"] = "('dns-alerts' in topics)"
            
            headers = {
                "Authorization": f"key={self.server_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(self.url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"FCM notification sent for {domain}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"FCM notification failed: {e}")
            return False
    
    @staticmethod
    def _get_priority(importance_score: int) -> str:
        """Map importance score to FCM priority"""
        return "high" if importance_score >= 10 else "normal"


class PushoverAdapter(PushNotificationAdapter):
    """Pushover.net adapter"""
    
    def __init__(self, api_token: str, user_key: str):
        self.api_token = api_token
        self.user_key = user_key
        self.url = "https://api.pushover.net/1/messages.json"
    
    def send(self, title: str, message: str, changes: List[Dict], 
             importance_score: int, domain: str) -> bool:
        """Send notification via Pushover"""
        try:
            payload = {
                "token": self.api_token,
                "user": self.user_key,
                "title": title,
                "message": message,
                "priority": self._get_priority(importance_score),
                "retry": 30,
                "expire": 3600,
                "url": f"https://example.com/dns/{domain}",  # Customize as needed
                "url_title": f"View {domain}"
            }
            
            response = requests.post(self.url, data=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Pushover notification sent for {domain}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"Pushover notification failed: {e}")
            return False
    
    @staticmethod
    def _get_priority(importance_score: int) -> int:
        """Map importance score to Pushover priority (-2 to 2)"""
        if importance_score >= 20:
            return 2  # Emergency
        elif importance_score >= 10:
            return 1  # High
        else:
            return 0  # Normal


class PushbulletAdapter(PushNotificationAdapter):
    """Pushbullet adapter"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.url = "https://api.pushbullet.com/v2/pushes"
    
    def send(self, title: str, message: str, changes: List[Dict], 
             importance_score: int, domain: str) -> bool:
        """Send notification via Pushbullet"""
        try:
            change_summary = "\n".join([
                f"{c.get('action', '?').upper()}: {c.get('name')} ({c.get('type')})"
                for c in changes[:5]  # Limit to first 5 changes
            ])
            if len(changes) > 5:
                change_summary += f"\n... and {len(changes) - 5} more changes"
            
            payload = {
                "type": "note",
                "title": title,
                "body": f"{message}\n\n{change_summary}"
            }
            
            headers = {
                "Access-Token": self.access_token,
                "Content-Type": "application/json"
            }
            
            response = requests.post(self.url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Pushbullet notification sent for {domain}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"Pushbullet notification failed: {e}")
            return False


class SlackAdapter(PushNotificationAdapter):
    """Slack webhook adapter"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def send(self, title: str, message: str, changes: List[Dict], 
             importance_score: int, domain: str) -> bool:
        """Send notification via Slack"""
        try:
            # Determine color based on importance
            if importance_score >= 20:
                color = "danger"  # Red
            elif importance_score >= 10:
                color = "warning"  # Orange
            else:
                color = "#439FE0"  # Blue
            
            # Format changes for Slack
            change_fields = []
            for i, change in enumerate(changes[:5]):  # Limit to 5 changes for brevity
                action = change.get("action", "UNKNOWN").replace("_", " ").title()
                field = change.get("field", "N/A").replace("_", " ").title()
                old_value = str(change.get("old_value")) if change.get("old_value") is not None else "N/A"
                new_value = str(change.get("new_value")) if change.get("new_value") is not None else "N/A"

                if action == "Initial Sync Available":
                    value = "Domain found to be available on initial check."
                elif action == "Initial Sync Registered":
                    value = "Domain found to be registered on initial check."
                elif action == "Became Available":
                    value = f"Domain changed from registered to AVAILABLE!"
                elif action == "Became Registered":
                    value = f"Domain changed from available to REGISTERED."
                else:
                    value = f"{field}: {old_value} -> {new_value}"

                change_fields.append({
                    "title": f"Change {i+1} ({action})",
                    "value": value,
                    "short": False # Set to False for better readability of multi-line values
                })

            if len(changes) > 5:
                change_fields.append({
                    "title": "More Changes",
                    "value": f"... and {len(changes) - 5} more changes",
                    "short": True
                })
            
            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": title,
                        "text": message,
                        "fields": [
                            {
                                "title": "Domain",
                                "value": domain,
                                "short": True
                            },
                            {
                                "title": "Importance",
                                "value": str(importance_score),
                                "short": True
                            },
                            {
                                "title": "Changes Count",
                                "value": str(len(changes)),
                                "short": True
                            }
                        ] + change_fields,
                        "ts": int(datetime.now().timestamp())
                    }
                ]
            }
            
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Slack notification sent for {domain}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"Slack notification failed: {e}")
            return False


class DiscordAdapter(PushNotificationAdapter):
    """Discord webhook adapter"""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    def send(self, title: str, message: str, changes: List[Dict], 
             importance_score: int, domain: str) -> bool:
        """Send notification via Discord"""
        try:
            # Determine color based on importance (decimal format for Discord)
            if importance_score >= 20:
                color = 15158332  # Red
                emoji = "🚨"
            elif importance_score >= 10:
                color = 15105570  # Orange
                emoji = "⚠️"
            else:
                color = 3447003  # Blue
                emoji = "ℹ️"
            
            # Format changes
            change_lines = []
            for change in changes[:5]: # Limit to 5 changes for brevity
                action = change.get("action", "UNKNOWN").replace("_", " ").title()
                field = change.get("field", "N/A").replace("_", " ").title()
                old_value = str(change.get("old_value")) if change.get("old_value") is not None else "N/A"
                new_value = str(change.get("new_value")) if change.get("new_value") is not None else "N/A"

                if action == "Initial Sync Available":
                    change_lines.append(f"📋 Domain found to be available on initial check.")
                elif action == "Initial Sync Registered":
                    change_lines.append(f"📋 Domain found to be registered on initial check.")
                elif action == "Became Available":
                    change_lines.append(f"🎉 Domain changed from registered to AVAILABLE!")
                elif action == "Became Registered":
                    change_lines.append(f"✅ Domain changed from available to REGISTERED.")
                else:
                    action_emoji = {
                        "Added": "➕",
                        "Removed": "➖",
                        "Modified": "✏️"
                    }.get(action, "❓")
                    change_lines.append(f"{action_emoji} {field}: `{old_value}` -> `{new_value}`")

            if len(changes) > 5:
                change_lines.append(f"... and {len(changes) - 5} more changes")
            
            payload = {
                "embeds": [
                    {
                        "title": f"{emoji} {title}",
                        "description": message,
                        "color": color,
                        "fields": [
                            {
                                "name": "Domain",
                                "value": domain,
                                "inline": True
                            },
                            {
                                "name": "Importance Score",
                                "value": str(importance_score),
                                "inline": True
                            },
                            {
                                "name": "Changes",
                                "value": "\n".join(change_lines),
                                "inline": False
                            }
                        ],
                        "timestamp": datetime.now().isoformat()
                    }
                ]
            }
            
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Discord notification sent for {domain}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"Discord notification failed: {e}")
            return False


class GenericWebhookAdapter(PushNotificationAdapter):
    """Generic HTTP webhook adapter"""
    
    def __init__(self, webhook_url: str, auth_token: str = None):
        self.webhook_url = webhook_url
        self.auth_token = auth_token
    
    def send(self, title: str, message: str, changes: List[Dict], 
             importance_score: int, domain: str) -> bool:
        """Send notification via generic webhook"""
        try:
            payload = {
                "title": title,
                "message": message,
                "domain": domain,
                "importance_score": importance_score,
                "changes": changes,
                "timestamp": datetime.now().isoformat()
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            
            response = requests.post(self.webhook_url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Generic webhook notification sent for {domain}")
            return True
        
        except requests.RequestException as e:
            logger.error(f"Generic webhook notification failed: {e}")
            return False


def create_adapter(service_type: str, **kwargs) -> PushNotificationAdapter:
    """Factory function to create notification adapters"""
    
    adapters = {
        "firebase": FirebaseCloudMessaging,
        "pushover": PushoverAdapter,
        "pushbullet": PushbulletAdapter,
        "slack": SlackAdapter,
        "discord": DiscordAdapter,
        "webhook": GenericWebhookAdapter
    }
    
    adapter_class = adapters.get(service_type.lower())
    if not adapter_class:
        raise ValueError(f"Unknown service type: {service_type}")
    
    return adapter_class(**kwargs)
