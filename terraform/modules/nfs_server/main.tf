resource "google_compute_instance" "nfs_server" {
  name         = "dify-nfs-server"
  machine_type = var.machine_type
  zone         = "${var.region}-b"
  project      = var.project_id

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.disk_size_gb
      type  = "pd-standard"
    }
  }

  network_interface {
    network    = var.vpc_network_name
    subnetwork = var.vpc_subnet_name
  }

  service_account {
    email  = var.service_account_email
    scopes = ["storage-ro"]
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -e

    # Install and start NFS server
    if ! systemctl is-active --quiet nfs-kernel-server; then
      apt-get update -y
      apt-get install -y nfs-kernel-server
    fi

    mkdir -p /export/plugin-storage
    chown -R nobody:nogroup /export/plugin-storage
    chmod 777 /export/plugin-storage
    echo '/export/plugin-storage *(rw,sync,no_subtree_check,no_root_squash)' > /etc/exports
    exportfs -ra
    systemctl enable nfs-kernel-server
    systemctl restart nfs-kernel-server

    # One-time: copy plugin data from GCS (skip venv and __pycache__)
    if [ ! -d /export/plugin-storage/cwd ]; then
      gsutil -m rsync -r -x '.*\.venv/.*|.*__pycache__/.*' \
        gs://${var.plugin_storage_bucket}/ /export/plugin-storage/
      chown -R nobody:nogroup /export/plugin-storage
      chmod -R 777 /export/plugin-storage
    fi
  EOF

  tags = ["nfs-server"]

  allow_stopping_for_update = true
}

resource "google_compute_firewall" "nfs_allow" {
  name    = "allow-nfs-from-cloudrun"
  network = var.vpc_network_name
  project = var.project_id

  allow {
    protocol = "tcp"
    ports    = ["2049"]
  }

  allow {
    protocol = "udp"
    ports    = ["2049"]
  }

  source_ranges = [var.subnet_cidr]
  target_tags   = ["nfs-server"]
}
