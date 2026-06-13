terraform {
  required_version = ">= 1.6"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.76"
    }
  }
}

# ── Provider ─────────────────────────────────────────────────────────────────
# API token format: USER@REALM!TOKENID=SECRET
# e.g.  root@pam!terraform=58927d08-4d41-4837-8fe8-cbb47fca321f
provider "proxmox" {
  endpoint  = "https://${var.proxmox_host}:8006/"
  api_token = var.proxmox_api_token
  insecure  = true   # set to false if you have a valid TLS cert on Proxmox
}

# ── LXC Container ────────────────────────────────────────────────────────────
resource "proxmox_virtual_environment_container" "octo_scrape" {
  node_name   = var.proxmox_node
  vm_id       = var.container_id
  description = "Octo Scrape — Octopus Energy offer monitor"
  tags        = ["octo-scrape", "docker"]

  start_on_boot = true
  started       = true

  # Ubuntu 24.04 LXC template
  # Run on Proxmox host first:
  #   pveam update
  #   pveam download local ubuntu-24.04-standard_24.04-2_amd64.tar.zst
  operating_system {
    template_file_id = "local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
    type             = "ubuntu"
  }

  cpu {
    cores = 2
  }

  memory {
    dedicated = 2048
  }

  disk {
    datastore_id = var.storage
    size         = 20
  }

  network_interface {
    name   = "eth0"
    bridge = "vmbr0"
  }

  # nesting=true is required to run Docker inside LXC
  features {
    nesting = true
  }

  initialization {
    hostname = "octo-scrape"

    user_account {
      # SSH public key — the matching private key lets you connect as root
      # Generate with:  ssh-keygen -t ed25519 -C "octo-scrape" -f ~/.ssh/octo_scrape_deploy
      keys     = [var.ssh_public_key]
      password = var.root_password
    }

    # DHCP — Proxmox assigns IP from your router
    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }
  }
}
