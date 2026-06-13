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

# ── Ubuntu 24.04 LXC template ────────────────────────────────────────────────
# Downloads the template from the official Proxmox mirror if not already present.
resource "proxmox_virtual_environment_download_file" "ubuntu_2404" {
  node_name    = var.proxmox_node
  content_type = "vztmpl"
  datastore_id = "local"
  url          = "http://download.proxmox.com/images/system/ubuntu-24.04-standard_24.04-2_amd64.tar.zst"
  overwrite    = false   # skip download if template already exists
}

# ── LXC Container ────────────────────────────────────────────────────────────
resource "proxmox_virtual_environment_container" "octo_scrape" {
  node_name   = var.proxmox_node
  vm_id       = var.container_id
  description = "Octo Scrape — Octopus Energy offer monitor"
  tags        = ["octo-scrape", "docker"]

  start_on_boot = true
  started       = true
  unprivileged  = true   # required to set nesting via API token

  operating_system {
    template_file_id = proxmox_virtual_environment_download_file.ubuntu_2404.id
    type             = "ubuntu"
  }

  depends_on = [proxmox_virtual_environment_download_file.ubuntu_2404]

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
