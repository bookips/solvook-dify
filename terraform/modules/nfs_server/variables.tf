variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "vpc_network_name" {
  type = string
}

variable "vpc_subnet_name" {
  type = string
}

variable "subnet_cidr" {
  type    = string
  default = "10.0.0.0/8"
}

variable "machine_type" {
  type    = string
  default = "e2-micro"
}

variable "disk_size_gb" {
  type    = number
  default = 10
}

variable "service_account_email" {
  type = string
}

variable "plugin_storage_bucket" {
  type = string
}
