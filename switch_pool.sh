#!/usr/bin/env bash
set -e

# Load current ACTIVE_POOL from .env
ACTIVE_POOL=$(grep '^ACTIVE_POOL=' .env | cut -d '=' -f2)

# Determine next pool
if [ "$ACTIVE_POOL" = "blue" ]; then
    NEW_POOL="green"
else
    NEW_POOL="blue"
fi

# Update the .env file
sed -i "s/^ACTIVE_POOL=.*/ACTIVE_POOL=${NEW_POOL}/" .env
echo "Switched ACTIVE_POOL to ${NEW_POOL}"

# Re-render Nginx config inside the container using updated environment
docker exec nginx sh -c "envsubst '\$ACTIVE_POOL \$PORT' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf"

# Reload Nginx to apply the new configuration
docker exec nginx nginx -s reload

echo "Nginx configuration reloaded. Now routing traffic to ${NEW_POOL}."
