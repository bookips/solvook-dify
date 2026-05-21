output "nfs_server_ip" {
  value = google_compute_instance.nfs_server.network_interface[0].network_ip
}
