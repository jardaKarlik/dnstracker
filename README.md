# DNS Watchdog Agent 🛡️

A Python-based background agent that monitors DNS records for your domains in real-time, detects changes, evaluates their importance, and sends push notifications only when needed.

**Features:**
- ✅ Monitors multiple domains simultaneously
- ✅ Detects changes in DNS records (added, removed, modified)
- ✅ Scores importance based on record type (critical, high, medium, low)
- ✅ Persistent state tracking in JSON
- ✅ Push notifications via Firebase, Pushover, Pushbullet, Slack, Discord, or custom webhooks
- ✅ Custom cron scheduling (every 15 min, hourly, daily, etc.)
- ✅ Comprehensive logging
- ✅ Environment variable configuration
- ✅ Zero external dependencies beyond requests library

---

## Quick Start

### 1. Install
```bash
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
# Edit .env with your credentials
nano .env
```

### 3. Test
```bash
python dns_watchdog_agent.py
```

### 4. Schedule with Cron
```bash
# Every 15 minutes
*/15 * * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

See [CRON_SETUP.md](CRON_SETUP.md) for detailed scheduling options.

---

## Configuration

### Required Environment Variables

```bash
# ZONER API Authentication
ZONER_API_TOKEN=your_api_token_here

# Push Notification Service & Token
PUSH_SERVICE_URL=https://your-push-service-url
PUSH_TOKEN=your_push_token_here

# Domains to Monitor (comma-separated)
DOMAINS_TO_MONITOR=example.com,mysite.cz,another-domain.info
```

### How to Get Credentials

#### ZONER API Token
1. Log in to [ZONER/Czechia.com](https://www.czechia.com)
2. Go to Settings → API
3. Copy your REST API token

#### Push Notification Services

**Firebase Cloud Messaging (FCM):**
1. Create a project at [Firebase Console](https://console.firebase.google.com)
2. Go to Project Settings → Service Accounts
3. Generate a new key → Server Key is your `PUSH_TOKEN`

```bash
PUSH_SERVICE_URL=https://fcm.googleapis.com/fcm/send
PUSH_TOKEN=your_fcm_server_key
```

**Pushover:**
1. Sign up at [Pushover.net](https://pushover.net)
2. Create application
3. Get Application Key and User Key

```bash
PUSH_SERVICE_URL=https://api.pushover.net/1/messages.json
PUSH_TOKEN=your_pushover_token
```

**Pushbullet:**
1. Create account at [Pushbullet.com](https://www.pushbullet.com)
2. Get API token from Settings

```bash
PUSH_SERVICE_URL=https://api.pushbullet.com/v2/pushes
PUSH_TOKEN=your_pushbullet_token
```

**Slack:**
1. Create Incoming Webhook at [Slack Apps](https://api.slack.com/apps)
2. Use webhook URL as `PUSH_SERVICE_URL`

```bash
PUSH_SERVICE_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
PUSH_TOKEN=unused  # (not used for Slack)
```

**Discord:**
1. Create webhook in your Discord server
2. Use webhook URL as `PUSH_SERVICE_URL`

```bash
PUSH_SERVICE_URL=https://discordapp.com/api/webhooks/YOUR/WEBHOOK
PUSH_TOKEN=unused  # (not used for Discord)
```

---

## How It Works

### DNS Change Detection Process

```
┌─────────────────────────────────────────┐
│   Run Check (via Cron)                  │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   Fetch Current DNS Records from ZONER  │
│   /api/DNS/{domain}                     │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   Load Previous State from JSON          │
│   (dns_state.json)                      │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   Detect Changes                        │
│   - Added records?                      │
│   - Removed records?                    │
│   - Modified records?                   │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   Score Importance                      │
│   A/AAAA/MX: +10 (critical)             │
│   CNAME/NS: +7 (high)                   │
│   TXT/SPF: +4 (medium)                  │
│   SRV/CAA: +2 (low)                     │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   Decide on Notification                │
│   Score ≥ 20? → 🚨 CRITICAL             │
│   Score ≥ 10? → ⚠️  WARNING              │
│   Score > 0?  → ℹ️  INFO                 │
│   Score = 0?  → 🤫 Silent                │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   Save New State                        │
│   Update dns_state.json                 │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   Send Push Notification (if needed)    │
│   Firebase/Pushover/Slack/etc.          │
└─────────────────────────────────────────┘
```

### Importance Scoring System

| Change Type | Record Type | Base Score | Additional |
|-------------|-------------|------------|-----------|
| **ADDED** | A, AAAA, MX | +10 | - |
| | CNAME, NS | +7 | - |
| | TXT, SPF, DKIM | +4 | - |
| | Other | +1 | - |
| **MODIFIED** | A, AAAA, MX | +10 | +3 = 13 |
| | CNAME, NS | +7 | +3 = 10 |
| | TXT, SPF, DKIM | +4 | +3 = 7 |
| **REMOVED** | A, AAAA, MX | +10 | +5 = 15 |
| | CNAME, NS | +7 | +5 = 12 |
| | TXT, SPF, DKIM | +4 | +5 = 9 |

**Alert Thresholds:**
- **🚨 CRITICAL**: Score ≥ 20 (e.g., multiple critical records removed)
- **⚠️ WARNING**: Score ≥ 10 (e.g., single A record modified)
- **ℹ️ INFO**: Score > 0 (e.g., TXT record added)
- **🤫 Silent**: Score = 0 or no changes detected

---

## File Structure

```
dns-watchdog/
├── dns_watchdog_agent.py       # Main agent (core logic)
├── push_adapters.py             # Push notification adapters
├── requirements.txt             # Python dependencies
├── .env.example                 # Configuration template
├── .env                         # Your actual config (create from .env.example)
├── dns_state.json               # Current DNS state (auto-created)
├── dns_watchdog.log             # Application logs
├── dns_watchdog_cron.log        # Cron execution logs
├── CRON_SETUP.md                # Detailed scheduling guide
└── README.md                    # This file
```

---

## Usage Examples

### Monitor a Single Domain
```bash
ZONER_API_TOKEN=xxx \
PUSH_SERVICE_URL=https://... \
PUSH_TOKEN=yyy \
DOMAINS_TO_MONITOR=example.com \
python dns_watchdog_agent.py
```

### Monitor Multiple Domains
```bash
DOMAINS_TO_MONITOR=example.com,mysite.cz,another-domain.info \
python dns_watchdog_agent.py
```

### Run Every 15 Minutes
```bash
*/15 * * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

### Run Multiple Times a Day
```bash
# 6 AM, 12 PM, 6 PM, Midnight
0 0,6,12,18 * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

---

## Logs & Debugging

### View Application Logs
```bash
tail -f dns_watchdog.log
```

### View Recent Check Runs
```bash
grep "Starting DNS check" dns_watchdog.log
```

### View Detected Changes
```bash
grep "changes detected" dns_watchdog.log
```

### View Notifications Sent
```bash
grep "notification sent" dns_watchdog.log
```

### View Full DNS State
```bash
cat dns_state.json | python -m json.tool
```

### Check Specific Domain State
```bash
python -c "import json; state=json.load(open('dns_state.json')); print(json.dumps(state['example.com'], indent=2))"
```

---

## Troubleshooting

### Problem: "ZONER_API_TOKEN not set"
**Solution:** Ensure `.env` file exists and contains `ZONER_API_TOKEN`
```bash
cat .env | grep ZONER_API_TOKEN
```

### Problem: Cron job doesn't execute
**Solution:** 
1. Use absolute path to Python: `which python3`
2. Make script executable: `chmod +x dns_watchdog_agent.py`
3. Check cron logs: `grep CRON /var/log/syslog`
4. Test manually: `/usr/bin/python3 /path/to/dns_watchdog_agent.py`

### Problem: Push notifications not received
**Solution:**
1. Verify service credentials in `.env`
2. Test with manual API call:
```bash
curl -X POST "https://api.pushover.net/1/messages.json" \
  -d "token=YOUR_TOKEN&user=YOUR_USER&title=Test&message=Testing"
```
3. Check application logs: `tail -f dns_watchdog.log`

### Problem: No changes detected (even though I changed DNS)
**Solution:**
1. DNS changes may take time to propagate (TTL-dependent)
2. Check stored state: `cat dns_state.json`
3. Run agent manually to trigger fresh check
4. Check if change is actually in ZONER API records

### Problem: Too many/too few notifications
**Solution:** Adjust importance thresholds in `dns_watchdog_agent.py`:
- To get more alerts: Change `>= 10` to `>= 5`
- To get fewer alerts: Change `>= 10` to `>= 15`

---

## Advanced Configuration

### Using Different Push Adapters

The `push_adapters.py` module supports multiple services out of the box:

```python
from push_adapters import create_adapter

# Firebase
adapter = create_adapter("firebase", server_key="xxx", device_token="yyy")

# Pushover
adapter = create_adapter("pushover", api_token="xxx", user_key="yyy")

# Slack
adapter = create_adapter("slack", webhook_url="https://hooks.slack.com/...")

# Discord
adapter = create_adapter("discord", webhook_url="https://discordapp.com/...")

# Custom Webhook
adapter = create_adapter("webhook", webhook_url="https://...", auth_token="xxx")
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY dns_watchdog_agent.py push_adapters.py .
COPY .env .
RUN apt-get update && apt-get install -y cron
RUN echo "*/15 * * * * python /app/dns_watchdog_agent.py >> /app/dns_watchdog.log 2>&1" | crontab -
CMD ["cron", "-f"]
```

### Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: dns-watchdog
spec:
  schedule: "*/15 * * * *"  # Every 15 minutes
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: dns-watchdog
            image: dns-watchdog:latest
            env:
            - name: ZONER_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: dns-watchdog-secrets
                  key: api-token
            - name: PUSH_SERVICE_URL
              valueFrom:
                configMapKeyRef:
                  name: dns-watchdog-config
                  key: push-url
            - name: PUSH_TOKEN
              valueFrom:
                secretKeyRef:
                  name: dns-watchdog-secrets
                  key: push-token
            - name: DOMAINS_TO_MONITOR
              valueFrom:
                configMapKeyRef:
                  name: dns-watchdog-config
                  key: domains
          restartPolicy: OnFailure
```

---

## API Reference

### ZonerAPIClient

```python
client = ZonerAPIClient(auth_token)

# Get DNS records for a domain
records = client.get_dns_records("example.com")

# Get allowed IP addresses
ips = client.get_allowed_ips()
```

### DNSStateManager

```python
state = DNSStateManager("dns_state.json")

# Get domain state
domain_state = state.get_domain_state("example.com")

# Set domain state
state.set_domain_state("example.com", records)
state.save_state()
```

### ChangeDetector

```python
detector = ChangeDetector()

# Detect changes between states
changes, importance_score = detector.detect_changes(old_records, new_records)
```

### DNSWatchdogAgent

```python
agent = DNSWatchdogAgent()

# Run single domain check
result = agent.run_check("example.com")

# Run full check for all monitored domains
results = agent.run_full_check()
```

---

## Performance & Limitations

- **API Calls:** 1 per domain per check
- **Memory:** ~5MB base + 1MB per domain
- **State File:** ~10-50KB per domain
- **Network:** Uses ZONER REST API (respects rate limits)
- **Concurrency:** Currently sequential (single-threaded)

### Scaling for Many Domains

For 100+ domains, consider:
1. Splitting into multiple cron jobs with different domains
2. Using database instead of JSON for state
3. Implementing multi-threaded checks
4. Using separate notification batching

---

## Security Considerations

- ✅ API tokens stored in `.env` (not in code)
- ✅ Environment-variable based configuration
- ✅ HTTPS for all API calls
- ✅ Push tokens transmitted securely
- ✅ No sensitive data logged
- ✅ State file contains only DNS records (public info)

**Best Practices:**
1. Keep `.env` file out of version control
2. Rotate API tokens regularly
3. Use separate API tokens for different services
4. Run agent with limited filesystem permissions
5. Monitor agent logs for suspicious activity

---

## Contributing & Extending

### Adding a New Push Adapter

```python
from push_adapters import PushNotificationAdapter

class MyServiceAdapter(PushNotificationAdapter):
    def __init__(self, config):
        self.config = config
    
    def send(self, title, message, changes, importance_score, domain):
        # Implement your service integration
        return True
```

### Customizing Importance Scoring

Edit `ChangeDetector` class:
```python
CRITICAL_TYPES = {"A", "AAAA", "MX", "YOUR_TYPE"}
HIGH_TYPES = {"CNAME", "NS", "YOUR_TYPE"}
```

---

## License

MIT License - Use freely for personal and commercial projects.

---

## Support

For issues or questions:
1. Check the logs: `tail -f dns_watchdog.log`
2. Review [CRON_SETUP.md](CRON_SETUP.md) for scheduling
3. Test manually: `python dns_watchdog_agent.py`
4. Verify credentials: `cat .env | grep -v "^#"`

---

## Version History

- **v1.0** (2024-01) - Initial release with core functionality
  - ZONER API integration
  - Multi-domain monitoring
  - Change detection & importance scoring
  - Multiple push adapters
  - Cron scheduling support
