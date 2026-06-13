output "container_id" {
  description = "Proxmox VMID of the created container"
  value       = proxmox_virtual_environment_container.octo_scrape.vm_id
}

output "next_steps" {
  description = "What to do after terraform apply"
  value       = <<-EOT

    ✓ Container ${proxmox_virtual_environment_container.octo_scrape.vm_id} created on ${var.proxmox_node}.

    Next steps:
    1. Find the container IP in the Proxmox web UI:
         Datacenter → ${var.proxmox_node} → CT ${proxmox_virtual_environment_container.octo_scrape.vm_id} → Summary → IP address

    2. Copy the provision script to the container:
         scp -i ~/.ssh/octo_scrape_deploy scripts/provision.sh root@<IP>:/root/provision.sh

    3. SSH in and run it:
         ssh -i ~/.ssh/octo_scrape_deploy root@<IP>
         bash /root/provision.sh

    4. Follow the prompts to complete Infisical login and start the app.

    5. Open the web UI:
         http://<IP>:8000
  EOT
}
