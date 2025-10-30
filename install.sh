#!/bin/bash

################################################################################
# Picklist to Quotation Converter - Production Installer for Ubuntu 24 LTS
# Repository: https://github.com/ruolez/picklist-quotation
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GITHUB_REPO="https://github.com/ruolez/picklist-quotation.git"
INSTALL_DIR="/opt/picklist-quotation"
ENV_FILE="$INSTALL_DIR/.env"
HOST_PORT=80

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

detect_ip() {
    # Try multiple methods to detect IP
    local ip=""

    # Method 1: hostname -I (most reliable on Ubuntu)
    ip=$(hostname -I | awk '{print $1}')

    # Method 2: ip route
    if [[ -z "$ip" ]]; then
        ip=$(ip route get 1.1.1.1 | awk '{print $7; exit}')
    fi

    # Method 3: ifconfig (if available)
    if [[ -z "$ip" ]] && command -v ifconfig &> /dev/null; then
        ip=$(ifconfig | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -1)
    fi

    echo "$ip"
}

validate_ip() {
    local ip=$1
    local valid_ip_regex="^([0-9]{1,3}\.){3}[0-9]{1,3}$"

    if [[ $ip =~ $valid_ip_regex ]]; then
        # Check each octet is <= 255
        IFS='.' read -ra OCTETS <<< "$ip"
        for octet in "${OCTETS[@]}"; do
            if [[ $octet -gt 255 ]]; then
                return 1
            fi
        done
        return 0
    fi
    return 1
}

prompt_ip_address() {
    local detected_ip=$(detect_ip)

    echo ""
    print_header "Network Configuration"

    if [[ -n "$detected_ip" ]]; then
        print_info "Detected IP address: $detected_ip"
        echo ""
        read -p "Use this IP address? (y/n): " use_detected

        if [[ "$use_detected" =~ ^[Yy]$ ]]; then
            SERVER_IP="$detected_ip"
            print_success "Using IP: $SERVER_IP"
            return
        fi
    fi

    # Manual IP entry
    while true; do
        echo ""
        read -p "Enter the server IP address: " SERVER_IP

        if validate_ip "$SERVER_IP"; then
            print_success "Valid IP address: $SERVER_IP"
            break
        else
            print_error "Invalid IP address format. Please try again."
        fi
    done
}

install_docker() {
    if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
        print_success "Docker and Docker Compose already installed"
        return
    fi

    print_info "Installing Docker and Docker Compose..."

    # Update package index
    apt-get update -qq

    # Install prerequisites
    apt-get install -y -qq ca-certificates curl gnupg lsb-release

    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Set up Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker Engine
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Start Docker service
    systemctl start docker
    systemctl enable docker

    print_success "Docker and Docker Compose installed successfully"
}

backup_data() {
    if [[ -d "$INSTALL_DIR/data" ]]; then
        local backup_file="$INSTALL_DIR/data-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
        print_info "Backing up existing data to $backup_file..."
        tar -czf "$backup_file" -C "$INSTALL_DIR" data
        print_success "Data backed up successfully"
        return 0
    fi
    return 1
}

restore_data() {
    local backup_dir="$1"
    if [[ -d "$backup_dir" ]]; then
        print_info "Restoring data from backup..."
        cp -r "$backup_dir" "$INSTALL_DIR/data"
        print_success "Data restored successfully"
    fi
}

################################################################################
# Installation Functions
################################################################################

install_application() {
    print_header "Installing Picklist to Quotation Converter"

    # Check if already installed
    if [[ -d "$INSTALL_DIR" ]]; then
        print_warning "Application directory already exists at $INSTALL_DIR"
        read -p "Remove existing installation and reinstall? (y/n): " reinstall
        if [[ ! "$reinstall" =~ ^[Yy]$ ]]; then
            print_info "Installation cancelled"
            exit 0
        fi
        remove_application
    fi

    # Prompt for IP address
    prompt_ip_address

    # Install Docker
    install_docker

    # Clone repository
    print_info "Cloning repository from GitHub..."
    git clone "$GITHUB_REPO" "$INSTALL_DIR"
    print_success "Repository cloned successfully"

    # Create data directory
    mkdir -p "$INSTALL_DIR/data"
    chmod 755 "$INSTALL_DIR/data"

    # Create .env file
    print_info "Creating environment configuration..."
    cat > "$ENV_FILE" <<EOF
# Picklist to Quotation Converter Configuration
# Generated on $(date)

# Server Configuration
HOST_PORT=$HOST_PORT
FLASK_ENV=production
ALLOWED_ORIGIN=http://$SERVER_IP

# Database Configuration
# Configure these through the web UI at http://$SERVER_IP/settings
EOF
    print_success "Environment configuration created"

    # Build and start containers
    print_info "Building Docker containers (this may take a few minutes)..."
    cd "$INSTALL_DIR"
    docker compose up -d --build

    # Wait for application to start
    print_info "Waiting for application to start..."
    sleep 5

    # Check if container is running
    if docker ps | grep -q picklist-quotation-converter; then
        print_success "Application started successfully!"
        echo ""
        print_header "Installation Complete!"
        echo ""
        print_success "Access the application at: http://$SERVER_IP"
        echo ""
        print_info "Next steps:"
        echo "  1. Navigate to http://$SERVER_IP/settings"
        echo "  2. Configure your SQL Server connections"
        echo "  3. Set quotation defaults"
        echo "  4. Start the polling service"
        echo ""
        print_info "Useful commands:"
        echo "  - View logs: docker logs -f picklist-quotation-converter"
        echo "  - Restart: cd $INSTALL_DIR && docker compose restart"
        echo "  - Stop: cd $INSTALL_DIR && docker compose down"
        echo ""
    else
        print_error "Failed to start application. Check logs with:"
        echo "  docker logs picklist-quotation-converter"
        exit 1
    fi
}

update_application() {
    print_header "Updating Picklist to Quotation Converter"

    # Check if installed
    if [[ ! -d "$INSTALL_DIR" ]]; then
        print_error "Application not found at $INSTALL_DIR"
        print_info "Use 'Install' option to perform a fresh installation"
        exit 1
    fi

    cd "$INSTALL_DIR"

    # Backup data
    backup_data
    local backup_status=$?

    # Stop containers
    print_info "Stopping application..."
    docker compose down

    # Pull latest changes
    print_info "Pulling latest changes from GitHub..."
    git fetch origin
    git reset --hard origin/main
    print_success "Code updated successfully"

    # Rebuild and restart
    print_info "Rebuilding containers..."
    docker compose up -d --build

    # Wait for application to start
    print_info "Waiting for application to start..."
    sleep 5

    if docker ps | grep -q picklist-quotation-converter; then
        print_success "Application updated and restarted successfully!"
        echo ""
        print_info "Access the application at: http://$(cat $ENV_FILE | grep ALLOWED_ORIGIN | cut -d= -f2 | cut -d: -f2 | cut -d/ -f3)"
    else
        print_error "Failed to start application after update"
        if [[ $backup_status -eq 0 ]]; then
            print_warning "Data backup is available in $INSTALL_DIR"
        fi
        exit 1
    fi
}

remove_application() {
    print_header "Removing Picklist to Quotation Converter"

    if [[ ! -d "$INSTALL_DIR" ]]; then
        print_warning "Application not found at $INSTALL_DIR"
        return
    fi

    cd "$INSTALL_DIR"

    # Confirm removal
    echo ""
    print_warning "This will remove the application and all containers"
    read -p "Keep database files? (y/n): " keep_data
    echo ""
    read -p "Are you sure you want to continue? (y/n): " confirm

    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Removal cancelled"
        exit 0
    fi

    # Stop and remove containers
    print_info "Stopping and removing containers..."
    docker compose down -v

    # Remove Docker images
    print_info "Removing Docker images..."
    docker rmi $(docker images | grep picklist-quotation | awk '{print $3}') 2>/dev/null || true

    # Backup data if requested
    if [[ "$keep_data" =~ ^[Yy]$ ]] && [[ -d "$INSTALL_DIR/data" ]]; then
        local backup_dir="/root/picklist-quotation-data-backup-$(date +%Y%m%d-%H%M%S)"
        print_info "Backing up data to $backup_dir..."
        cp -r "$INSTALL_DIR/data" "$backup_dir"
        print_success "Data backed up to: $backup_dir"
    fi

    # Remove installation directory
    print_info "Removing installation directory..."
    cd /tmp
    rm -rf "$INSTALL_DIR"

    print_success "Application removed successfully"

    if [[ "$keep_data" =~ ^[Yy]$ ]]; then
        echo ""
        print_info "Your data has been preserved in: $backup_dir"
    fi
}

################################################################################
# Main Menu
################################################################################

show_menu() {
    clear
    echo ""
    print_header "Picklist to Quotation Converter - Installer"
    echo ""
    echo "  1) Install - Fresh installation"
    echo "  2) Update  - Pull latest from GitHub"
    echo "  3) Remove  - Uninstall application"
    echo "  4) Exit"
    echo ""
}

main() {
    check_root

    while true; do
        show_menu
        read -p "Select an option (1-4): " choice

        case $choice in
            1)
                install_application
                break
                ;;
            2)
                update_application
                break
                ;;
            3)
                remove_application
                break
                ;;
            4)
                print_info "Exiting installer"
                exit 0
                ;;
            *)
                print_error "Invalid option. Please select 1-4"
                sleep 2
                ;;
        esac
    done
}

# Run main function
main
