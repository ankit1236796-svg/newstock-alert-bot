# Production Deployment on Ubuntu 24.04 LTS

This guide deploys NewStock Alert Bot on an Ubuntu VPS with Docker and Docker Compose.

## VPS setup

```bash
sudo apt update
sudo apt upgrade -y
sudo adduser newstock
sudo usermod -aG sudo newstock
sudo mkdir -p /opt/newstock-alert-bot
sudo chown newstock:newstock /opt/newstock-alert-bot
su - newstock
```

Keep SSH key authentication enabled, disable password SSH logins if possible, and restrict firewall access:

```bash
sudo ufw allow OpenSSH
sudo ufw enable
```

## Docker installation

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
```

## Docker Compose installation

Ubuntu 24.04 uses the Docker Compose plugin installed above. Verify it with:

```bash
docker compose version
```

## Clone repository

```bash
cd /opt
git clone <REPOSITORY_URL> newstock-alert-bot
cd newstock-alert-bot
```

## Configure `.env`

```bash
cp .env.example .env
nano .env
chmod 600 .env
```

Set at least `BOT_TOKEN`. Keep the production SQLite default unless you intentionally use another durable database path:

```env
BOT_TOKEN=123456:replace-with-botfather-token
APP_ENV=production
DATABASE_URL=sqlite+aiosqlite:////app/data/newstock_alert_bot.sqlite3
```

Never commit `.env` or backups containing production data.

## First deployment

```bash
./scripts/deploy.sh
```

Check container health and logs:

```bash
docker compose ps
./scripts/logs.sh
```

## Updating the bot

```bash
./scripts/backup.sh
./scripts/update.sh
```

The update script performs a fast-forward `git pull`, rebuilds the image, and recreates the service.

## Restarting services

```bash
./scripts/restart.sh
```

## Viewing logs

```bash
./scripts/logs.sh
TAIL=500 ./scripts/logs.sh
```

## Stopping services

```bash
./scripts/stop.sh
```

## Backup & Restore

Backups are tarballs of the persistent `/app/data` directory stored under `backups/`.

Create a backup:

```bash
./scripts/backup.sh
```

Restore a backup:

```bash
./scripts/restore.sh backups/newstock-alert-bot-YYYYMMDDTHHMMSSZ.tar.gz
```

After restore, confirm the bot is healthy:

```bash
docker compose ps
./scripts/logs.sh
```
