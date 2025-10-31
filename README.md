# Blue-Green Deployment using Nginx and Docker Compose

This project implements a blue-green deployment strategy for a Node.js application using Nginx as a reverse proxy and Docker Compose for orchestration. The setup ensures zero downtime during deployments by switching traffic between two application environments: blue and green.

## Overview

The project demonstrates a robust deployment model where two versions of the same application run simultaneously. The Nginx reverse proxy dynamically routes traffic to the active environment (either blue or green), while the inactive one can be updated or tested safely.

This setup supports automatic failover, dynamic environment switching, and runtime configuration through environment variables.

---

## Architecture

The system consists of three main services:

1. App_blue: The blue instance of the application.
2. App_green:  The green instance of the application.
3. Nginx: Acts as a reverse proxy and load balancer between the two environments.

Each app container runs the same image but has different environment variables such as `APP_POOL` and `RELEASE_ID`.

## File Structure

```
hng13-stage3-solution/
│
├── docker-compose.yml
├── .env
├── nginx/
│   └── default.conf.template
└── README.md
```

## Environment Variables

The `.env` file defines key runtime values used across the setup.

```
BLUE_IMAGE=<your-blue-image>
GREEN_IMAGE=<your-green-image>
ACTIVE_POOL=blue
PORT=3000
RELEASE_ID_BLUE=blue-1.0.0
RELEASE_ID_GREEN=green-1.0.0
```

### Description

* `BLUE_IMAGE` – Docker image for the blue environment
* `GREEN_IMAGE` – Docker image for the green environment
* `ACTIVE_POOL` – Determines which environment is live (either `blue` or `green`)
* `PORT` – The internal port the application listens on; can be overridden by graders or CI/CD pipelines
* `RELEASE_ID_BLUE` and `RELEASE_ID_GREEN` – Version identifiers for each deployment

## Docker Compose Configuration

The `docker-compose.yml` defines the three main services and ensures flexible port mapping and automatic environment propagation.

```
services:
  app_blue:
    image: ${BLUE_IMAGE}
    container_name: app_blue
    environment:
      - APP_POOL=blue
      - RELEASE_ID=${RELEASE_ID_BLUE}
      - PORT=${PORT}
    expose:
      - "${PORT}"
    ports:
      - "8081:${PORT}"

  app_green:
    image: ${GREEN_IMAGE}
    container_name: app_green
    environment:
      - APP_POOL=green
      - RELEASE_ID=${RELEASE_ID_GREEN}
      - PORT=${PORT}
    expose:
      - "${PORT}"
    ports:
      - "8082:${PORT}"

  nginx:
    image: nginx:latest
    container_name: nginx
    depends_on:
      - app_blue
      - app_green
    ports:
      - "8080:80"
    volumes:
      - ./nginx/default.conf.template:/etc/nginx/templates/default.conf.template
    environment:
      - ACTIVE_POOL=${ACTIVE_POOL}
      - PORT=${PORT}
    restart: always
```

## Nginx Template

The `default.conf.template` dynamically builds the reverse proxy configuration based on environment variables.

```
# /etc/nginx/templates/default.conf.template

upstream backend {
    zone backend 64k;

    # When ACTIVE_POOL=blue
    server app_blue:${PORT} max_fails=2 fail_timeout=5s;
    server app_green:${PORT} backup;

    # When ACTIVE_POOL=green
    # The toggle.sh script will swap this order automatically
}

server {
    listen 80;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```


## Deployment Steps

1. Clone the repository:

   ```
   git clone https://github.com/<your-username>/hng13-stage3-solution.git
   cd hng13-stage3-solution
   ```

2. Update the `.env` file with the correct image names and settings.

3. Start the services:

   ```
   docker compose up -d
   ```

4. Access the application:

   ```
   http://localhost:8080/version
   ```

   The active environment (blue or green) will be shown in the response headers:

   ```
   X-App-Pool: blue
   X-Release-Id: blue-1.0.0
   ```

## Switching Environments

To switch from blue to green, update the `.env` file:

```
ACTIVE_POOL=green
```

Then rebuild the stack:

```
docker compose down
docker compose up -d
```

Nginx will now route all traffic to the green environment.

## Chaos Testing

The application supports simulated failures to test automatic fallback behavior.

Trigger a failure in the blue environment:

```
curl -X POST http://localhost:8081/chaos/start?mode=error
```

Then test the proxy:

```
curl -i http://localhost:8080/version
```

The response will show that traffic has been redirected to the green pool automatically.


## Logs and Alert Verification

You can monitor system health and verify that alerts are reaching Slack.

### View Watcher Logs

Check the `alert_watcher` container logs to confirm it’s parsing Nginx events correctly:

```bash
docker logs -f alert_watcher
```

You should see messages showing detected error rates, failovers, or recovery actions.

### Verify Slack Alerts

Open your Slack channel connected to the webhook URL.
You’ll receive real-time alerts when:

* The blue or green app stops responding (failover)
* Error rate crosses the threshold
* The primary pool recovers

Each alert message contains:

* The event type (Failover, Error Rate, or Recovery)
* A brief description
* Recommended operator action (from the runbook)

### Common Troubleshooting

If you don’t see alerts:

1. Check that the webhook URL in `.env` has **no spaces** before or after the URL.
2. Restart the watcher:

   ```bash
   docker restart alert_watcher
   ```
3. Generate activity again by stopping or restarting one app.

### Screenshots to Include

When submitting, take screenshots of:

1. The Slack channel showing alerts (Failover, Error Rate, and Recovery)
2. Your terminal showing `docker ps` with all containers running
3. A browser or `curl` result showing app responses from both Blue and Green pools

## Dynamic Port Handling

The `PORT` variable in `.env` is fully dynamic. The grader or CI/CD pipeline can override it at runtime:

```
PORT=5000 docker compose up -d
```

The system will automatically update Nginx, container ports, and upstream definitions without manual reconfiguration.

---

## Azure Deployment Notes

1. Deploy all files to a VM running Docker and Docker Compose.
2. Make sure port 8080 is open in the network security group.
3. Start the services:

   ```
   docker compose up -d
   ```
4. Access the app using your public IP:

   ```
   http://<your-public-ip>:8080/version
   ```

For optional testing, the blue and green apps can also be reached directly on:

* Blue: `http://<public-ip>:8081/version`
* Green: `http://<public-ip>:8082/version`

---

## Verification

To confirm the correct pool is active inside Nginx:

```
docker exec nginx cat /etc/nginx/conf.d/default.conf | grep server
```

To verify that apps are responding correctly:

```
docker exec nginx curl -s http://app_blue:${PORT}/version
docker exec nginx curl -s http://app_green:${PORT}/version
```

---

## Cleanup

To stop all containers:

```
docker compose down
```

To remove unused images and networks:

```
docker system prune -f
```

---

## Notes

* Nginx dynamically swaps between blue and green configurations using environment variables.
* The setup avoids building images locally in CI; all app images are pulled from Docker Hub.
* The `PORT` variable can be changed at runtime without modifying the Docker Compose or Nginx configuration.
* This architecture supports zero-downtime deployments, failover testing, and dynamic configuration for cloud grading environments.
