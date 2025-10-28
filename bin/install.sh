#!/bin/bash

set -e

# --- Detect non-interactive mode ---
NON_INTERACTIVE=false
if [[ "$1" == "--non-interactive" ]]; then
    NON_INTERACTIVE=true
    shift
fi

# --- 1. Initialization ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sed -i 's/\r$//' "$SCRIPT_DIR/../.env"
source "$SCRIPT_DIR/../.env"
source "$SCRIPT_DIR/global/log.sh"
source "$SCRIPT_DIR/global/choose-profile-command.sh"
platform=$(uname -s)
info "Starting installation on platform: $platform"
echo

# --- 2. Configuration Setup ---
source "$SCRIPT_DIR/util/handle-volumes-path.sh"

# IP selection: skip if non-interactive and ENTRANCE_DOMAIN already set
if [[ "$NON_INTERACTIVE" == true ]]; then
    info "Non-interactive mode: using ENTRANCE_DOMAIN=$ENTRANCE_DOMAIN"
else
    source "$SCRIPT_DIR/util/select-ip-address.sh"
fi

# --- 3. Dependency Installation ---
source "$SCRIPT_DIR/deb/install-docker.sh"

# --- 4. Service Profile Selection ---
if [[ "$NON_INTERACTIVE" == true ]]; then
    SELECTED_PROFILES=${SELECTED_PROFILES:-""}
    info "Non-interactive mode: selected profiles='$SELECTED_PROFILES'"

    # Convert to profile args
    profileCommand=""
    activeServices="emqx,nodered,keycloak,kong,postgresql,chat2db,portainer,tsdb"

    # Only add profiles if SELECTED_PROFILES is not empty
    if [[ -n "$SELECTED_PROFILES" ]]; then
        IFS=',' read -ra PROFILES <<< "$SELECTED_PROFILES"
        for profile in "${PROFILES[@]}"; do
            if [[ -n "$profile" ]]; then  # Skip empty strings
                profileCommand+="--profile $profile "
                activeServices+=",$profile"
            fi
        done
    fi

    # Save to active-services.txt
    OUTPUT_FILE=$SCRIPT_DIR/global/active-services.txt
    mkdir -p "$(dirname "$OUTPUT_FILE")"
    echo "$activeServices" > "$OUTPUT_FILE"
    echo "$profileCommand" >> "$OUTPUT_FILE"

    # Set COMPOSE_PROFILE_ARGS for docker compose
    COMPOSE_PROFILE_ARGS=()
    if [[ -n "$SELECTED_PROFILES" ]]; then
        IFS=',' read -ra PROFILES <<< "$SELECTED_PROFILES"
        for profile in "${PROFILES[@]}"; do
            if [[ -n "$profile" ]]; then
                COMPOSE_PROFILE_ARGS+=("--profile" "$profile")
            fi
        done
    fi
else
    # Interactive mode: original behavior
    source "$SCRIPT_DIR/util/select-service-profile.sh"
fi

# --- 5. Pre-run Initialization ---
source "$SCRIPT_DIR/util/set-temp-env.sh" "$SCRIPT_DIR/../" "${COMPOSE_PROFILE_ARGS[@]}"
source "$SCRIPT_DIR/init/init-keycloak-sql.sh" "$SCRIPT_DIR/.."
source "$SCRIPT_DIR/init/init-kong-property.sh" "$SCRIPT_DIR/.."

DOCKER_COMPOSE_FILE="$SCRIPT_DIR/../docker-compose-8c16g.yml"
if [ "$OS_RESOURCE_SPEC" == "1" ]; then
  DOCKER_COMPOSE_FILE="$SCRIPT_DIR/../docker-compose-4c8g.yml"
fi

# --- 6. Volume and Image Management ---
echo "Start creating volumes"
if [ -d "$VOLUMES_PATH/postgresql" ]; then
  info "Existing installation detected. Stopping services and updating volumes..."
  source "$SCRIPT_DIR/stop.sh"
  source "$SCRIPT_DIR/init/update-volumes.sh"
else
  info "New installation detected. Initializing volumes..."
  source "$SCRIPT_DIR/init/init-volumes.sh"
fi

# Copy active-services.txt to final destination
SOURCE_CONFIG_FILE="$SCRIPT_DIR/global/active-services.txt"
FINAL_CONFIG_FILE="$VOLUMES_PATH/backend/system/active-services.txt"
if [ -f "$SOURCE_CONFIG_FILE" ]; then
    info "Activating selected service profile..."
    mkdir -p "$(dirname "$FINAL_CONFIG_FILE")"
    cp "$SOURCE_CONFIG_FILE" "$FINAL_CONFIG_FILE"
fi

if [ -d "$SCRIPT_DIR/../images/" ] && [ "$(ls -A "$SCRIPT_DIR/../images/")" ]; then
  source "$SCRIPT_DIR/util/load-images.sh"
fi

# --- 7. Main Execution ---
info "Starting Docker containers in detached mode..."
if ! docker compose --env-file "$SCRIPT_DIR/../.env" --env-file "$SCRIPT_DIR/../.env.tmp" --project-name supos "${COMPOSE_PROFILE_ARGS[@]}" -f "$DOCKER_COMPOSE_FILE" up -d; then
    error "Failed to start Docker containers. Please check the logs above."
    exit 1
fi
info "Containers started successfully. Waiting for services to become healthy..."
echo

# --- 8. Post-init ---
{
    source "$SCRIPT_DIR/init/init-nodered.sh"  && \
    source "$SCRIPT_DIR/init/init-eventflow.sh"  && \
    source "$SCRIPT_DIR/init/hide-nodered.sh"  && \
    source "$SCRIPT_DIR/init/init-minio.sh" "$1" > /dev/null 2>&1 && \
    source "$SCRIPT_DIR/init/init-portainer.sh"
} || {
    error "One of the post-startup initialization scripts failed. Please check the logs above."
    exit 1
}

# --- 9. Success ---
echo -e "\n============================================================"
echo -e "🎉  All services are up and running!"
echo -e "👉  Open the platform in your browser:\n"

if [[ "$ENTRANCE_PORT" == "80" || "$ENTRANCE_PORT" == "443" ]]; then
  PLATFORM_URL="${ENTRANCE_PROTOCOL}://${ENTRANCE_DOMAIN}/home"
else
  PLATFORM_URL="${ENTRANCE_PROTOCOL}://${ENTRANCE_DOMAIN}:${ENTRANCE_PORT}/home"
fi

echo -e "      $PLATFORM_URL\n"
echo -e "    Default user name: supos\n"
echo -e "            password: supos\n"
echo -e "============================================================"

exit 0
