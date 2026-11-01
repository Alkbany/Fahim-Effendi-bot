# Free VM deployment

Fahim is a persistent Discord Gateway bot. Deploy it as a long-running process or container, not as a static site, serverless function, scheduled job, or a web service that sleeps when idle.

This guide is provider-neutral. It is written for a Linux VM that you are authorized to administer. Oracle Cloud Always Free is one possible source of a VM, but free capacity and continued availability are not guaranteed.

## Before you start

You need:

- A Linux VM with outbound internet access.
- Docker Engine and the Docker Compose plugin installed.
- A Discord bot token, Gemini API key, and MongoDB connection string.
- Access to the GitHub repository.

No inbound application port is required. Fahim initiates outbound connections to Discord, Gemini, and MongoDB. Keep the VM firewall closed to inbound traffic except for the administration method you intentionally use (for example, SSH from a trusted network).

## Deploy

1. Connect to your VM using its supported secure administration method.
2. Install Docker Engine and the Docker Compose plugin using the official instructions for your Linux distribution: https://docs.docker.com/engine/install/
3. Enable Docker at boot:

   ```bash
   sudo systemctl enable --now docker
   ```

4. Clone the repository and enter its directory:

   ```bash
   git clone <your-repository-url>
   cd Fahim-Effendi-bot
   ```

5. Create the environment file locally on the VM. Do not commit it:

   ```bash
   cp .env.example .env
   chmod 600 .env
   nano .env
   ```

   Fill in the required values: `DISCORD_TOKEN`, `GEMINI_API_KEY`, and `MONGO_URI`. Keep the file private and never paste its contents into chats, issues, screenshots, or logs.

6. Build and start Fahim:

   ```bash
   sudo docker compose up -d --build
   ```

7. Check startup logs:

   ```bash
   sudo docker compose logs --tail=100 fahim
   ```

   You should see successful MongoDB initialization and the Discord bot's ready/initialization log. If startup fails, inspect the error without sharing secret values.

## Routine operations

Update to the latest main branch:

```bash
git pull --ff-only
sudo docker compose up -d --build
```

Follow logs:

```bash
sudo docker compose logs -f fahim
```

Stop Fahim:

```bash
sudo docker compose down
```

The Compose service uses `restart: unless-stopped`, so Docker restarts the container after a process or VM restart, provided Docker itself is enabled at boot.

## Network and data

- The bot does not need a public HTTP endpoint or an inbound application port.
- Allow outbound HTTPS (TCP 443) to Discord and Gemini.
- Allow outbound access to the MongoDB deployment and port required by its connection string. For MongoDB Atlas, configure its network access rules for the VM's outbound public IP where possible; do not open the database to the entire internet.
- Conversation and memory data are stored in MongoDB, not in the container filesystem. Keep a separate database backup plan.
- Never put credentials in the Dockerfile, Compose file, source code, or GitHub Actions logs.

## Free-tier limitations

Free compute is not the same as a guaranteed always-on service.

- Always Free VM availability depends on the provider, home region, and available capacity.
- Oracle states that idle Always Free compute instances may be reclaimed when their CPU, network, and (for A1) memory utilization remain below the documented thresholds over a seven-day period. A small bot with little traffic may be at risk. Read the current policy before relying on it: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Free web-service plans that sleep on inactivity are unsuitable for a bot that needs a continuous Discord Gateway connection.
- A provider may restart, suspend, or discontinue free resources. Do not treat this as production-grade uptime.
- Do not enable a paid plan, add a payment method, or exceed free quotas unless the account owner explicitly approves it.

## Security checklist

- Use a private repository.
- Keep `.env` out of Git; the repository's `.gitignore` and `.dockerignore` already exclude it.
- Use a dedicated VM account and restrict SSH access.
- Do not expose MongoDB publicly; allow only the deployment's required network source where supported.
- Rotate any credential that may have been exposed.
- Review provider billing and resource limits regularly.
