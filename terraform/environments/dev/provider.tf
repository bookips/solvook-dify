terraform {
  backend "gcs" {
    bucket = "solvook-terraform-remote-backend" # replace with your bucket name
    prefix = "dify"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}