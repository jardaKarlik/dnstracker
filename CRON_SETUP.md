# DNS Watchdog Agent - Deployment & Cron Setup Guide

## Installation

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env with your actual credentials
nano .env
```

**Required variables:**
- `ZONER_API_TOKEN` - Your ZONER API authentication token
- `PUSH_SERVICE_URL` - Your push notification service endpoint
- `PUSH_TOKEN` - Your push notification API token
- `DOMAINS_TO_MONITOR` - Comma-separated list of domains to monitor

### 3. Test the Agent
```bash
# Run a single check to verify everything works
python dns_watchdog_agent.py
```

You should see logs like:
```
2024-01-15 10:30:45,123 - INFO - DNS Watchdog Agent initialized for domains: example.com, mysite.cz
2024-01-15 10:30:45,234 - INFO - Starting DNS check for example.com
2024-01-15 10:30:46,345 - INFO - No changes detected for example.com
```

## Cron Setup

### Setting Up Custom Cron Schedule

#### Option 1: Standard Cron (Linux/macOS)

1. **Edit your crontab:**
```bash
crontab -e
```

2. **Add one of these cron expressions:**

**Every 15 minutes:**
```
*/15 * * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

**Every 30 minutes:**
```
*/30 * * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

**Every hour at :00:**
```
0 * * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

**Every 6 hours (0:00, 6:00, 12:00, 18:00):**
```
0 0,6,12,18 * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

**Every day at 2:30 AM:**
```
30 2 * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

**Multiple times per day (6 AM, 12 PM, 6 PM):**
```
0 6,12,18 * * * /usr/bin/python3 /path/to/dns_watchdog_agent.py >> /path/to/dns_watchdog_cron.log 2>&1
```

3. **Important:** Make sure to use absolute paths to Python and the script

4. **Verify installation:**
```bash
crontab -l    # List your cron jobs
```

---

#### Option 2: Using systemd Timer (Modern Linux)

If your system uses systemd, you can create a more robust timer:

1. **Create service file** `/etc/systemd/system/dns-watchdog.service`:
```ini
[Unit]
Description=DNS Watchdog Agent
After=network.target

[Service]
Type=oneshot
User=your_username
WorkingDirectory=/path/to/dns_watchdog
EnvironmentFile=/path/to/.env
ExecStart=/usr/bin/python3 /path/to/dns_watchdog_agent.py
StandardOutput=journal
StandardError=journal
```

2. **Create timer file** `/etc/systemd/system/dns-watchdog.timer`:
```ini
[Unit]
Description=DNS Watchdog Timer (every 15 minutes)
Requires=dns-watchdog.service

[Timer]
# Run every 15 minutes
OnBootSec=1min
OnUnitActiveSec=15min
AccuracySec=1s

[Install]
WantedBy=timers.target
```

3. **Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable dns-watchdog.timer
sudo systemctl start dns-watchdog.timer
sudo systemctl status dns-watchdog.timer
```

4. **Check logs:**
```bash
sudo journalctl -u dns-watchdog -f
```

---

#### Option 3: Docker Container with Cron

1. **Create Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY dns_watchdog_agent.py .
COPY .env .

# Install cron
RUN apt-get update && apt-get install -y cron

# Create cron job (every 15 minutes)
RUN echo "*/15 * * * * /usr/local/bin/python /app/dns_watchdog_agent.py >> /app/dns_watchdog.log 2>&1" | crontab -

CMD ["cron", "-f"]
```

2. **Build and run:**
```bash
docker build -t dns-watchdog .
docker run -d --name dns-watchdog dns-watchdog
```

---

## File Structure

```
.
├── dns_watchdog_agent.py      # Main agent script
├── requirements.txt            # Python dependencies
├── .env                        # Configuration (create from .env.example)
├── .env.example                # Configuration template
├── dns_watchdog.log            # Application logs
├── dns_watchdog_cron.log       # Cron execution logs
├── dns_state.json              # DNS records state (auto-created)
└── README.md                   # This file
```

## Monitoring & Debugging

### View Agent Logs
```bash
tail -f dns_watchdog.log
```

### View Cron Logs
```bash
tail -f dns_watchdog_cron.log
```

### Check Stored DNS State
```bash
cat dns_state.json | python -m json.tool
```

### Test Push Notifications

To test if push notifications work, temporarily modify `importance_score >= 20` to `importance_score > 0` in the agent, then run a check.

### Common Issues

**Issue:** "ZONER_API_TOKEN not set"
- Solution: Ensure `.env` file exists and has the correct variable name

**Issue:** Cron job doesn't execute
- Solution: 
  - Check `which python3` to get the correct path
  - Ensure the script has execute permissions: `chmod +x dns_watchdog_agent.py`
  - Check system cron logs: `grep CRON /var/log/syslog`

**Issue:** Push notifications not received
- Solution:
  - Verify `PUSH_SERVICE_URL` and `PUSH_TOKEN` are correct
  - Test with a manual API call to the push service
  - Check network connectivity from the cron environment

---

## Importance Scoring System

The agent automatically scores DNS changes based on record type:

| Category | Record Types | Score |
|----------|--------------|-------|
| **CRITICAL** | A, AAAA, MX | +10 |
| **HIGH** | CNAME, NS | +7 |
| **MEDIUM** | TXT, SPF, DKIM | +4 |
| **LOW** | SRV, CAA | +2 |
| **OTHER** | Any other | +1 |

**Alert Levels:**
- **🚨 CRITICAL** (score ≥ 20): Record removed or multiple critical changes
- **⚠️ WARNING** (score ≥ 10): Single critical record modified
- **ℹ️ INFO** (score > 0): Minor changes to low-priority records

---

## Push Notification Service Examples

### Firebase Cloud Messaging (FCM)
```
PUSH_SERVICE_URL=https://fcm.googleapis.com/fcm/send
PUSH_TOKEN=your_fcm_server_key
```

### Pushover
```
PUSH_SERVICE_URL=https://api.pushover.net/1/messages.json
PUSH_TOKEN=your_pushover_api_token
```

### Pushbullet
```
PUSH_SERVICE_URL=https://api.pushbullet.com/v2/pushes
PUSH_TOKEN=your_pushbullet_api_token
```

### Custom Webhook
```
PUSH_SERVICE_URL=https://your-server.com/webhook/notify
PUSH_TOKEN=your_webhook_secret_token
```

The agent sends JSON payloads with:
- `title` - Notification title
- `message` - Short message
- `domain` - Domain being monitored
- `importance_score` - Change severity score
- `changes` - Array of detected changes
- `timestamp` - When the change was detected

---

## Next Steps

1. ✅ Install dependencies: `pip install -r requirements.txt`
2. ✅ Configure `.env` with your credentials
3. ✅ Test the agent: `python dns_watchdog_agent.py`
4. ✅ Set up cron schedule
5. ✅ Monitor logs and verify notifications work
6. ✅ Fine-tune importance thresholds if needed
