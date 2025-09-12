# Terraform for Dify on Google Cloud

![Google Cloud](https://img.shields.io/badge/Google%20Cloud-4285F4?logo=google-cloud&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-1.9.5-blue.svg)


![Dify GCP Architecture](images/dify-google-cloud-architecture.png)

<a href="./README_ja.md"><img alt="日本語のREADME" src="https://img.shields.io/badge/日本語-d9d9d9"></a>

> [!NOTE]
> - Dify v1.0.0 (and later) is supported now! Try it and give us feedbacks!!
> - If you fail to install any plugin, try several times and succeed in many cases.

## Overview
This repository allows you to automatically set up Google Cloud resources using Terraform and deploy Dify in a highly available configuration.

## Features
- Serverless hosting
- Auto-scaling
- Data persistence

## Prerequisites
- Google Cloud account
- Terraform installed
- gcloud CLI installed

## Configuration
- Set environment-specific values in the `terraform/environments/dev/terraform.tfvars` file.

> [!IMPORTANT]
> **Secret Management using Google Secret Manager**
> This project uses [Google Secret Manager](https://cloud.google.com/secret-manager) to handle all sensitive data securely. All secrets are fetched dynamically at runtime and are not stored in the repository.
>
> **Before running `terraform apply`, you must create the following secrets in Google Secret Manager:**
>
> | Secret Name                           | Description                                       | How to Generate                               |
> | ------------------------------------- | ------------------------------------------------- | --------------------------------------------- |
> | `dify-secret-key`                     | Dify application `SECRET_KEY`.                    | `openssl rand -base64 42`                     |
> | `dify-db-password`                    | Password for the Cloud SQL PostgreSQL database.   | Generate a strong password.                   |
> | `dify-plugin-daemon-key`              | Secret key for the Dify plugin daemon.            | `openssl rand -base64 42`                     |
> | `dify-plugin-dify-inner-api-key`      | Inner API key for Dify plugins.                   | `openssl rand -base64 42`                     |
> | `dify-slack-webhook-url`              | The full Slack Incoming Webhook URL for alerts.   | From your Slack App configuration.            |
> | `dify-aws-access-key-id`              | AWS Access Key ID (if using AWS services).        | From your AWS IAM user.                       |
> | `dify-aws-secret-access-key`          | AWS Secret Access Key (if using AWS services).    | From your AWS IAM user.                       |
>
> **Permissions:** The user or service account running `terraform apply` must have the **`Secret Manager Secret Accessor`** (`roles/secretmanager.secretAccessor`) IAM role to access these secrets.

- Create a GCS bucket to manage Terraform state in advance, and replace "your-tfstate-bucket" in the `terraform/environments/dev/provider.tf` file with the name of the created bucket.

## Getting Started
1. Clone the repository:
    ```sh
    git clone https://github.com/DeNA/dify-google-cloud-terraform.git
    ```

2. Initialize Terraform:
    ```sh
    cd terraform/environments/dev
    terraform init
    ```

3. Make Artifact Registry repository:
    ```sh
    terraform apply -target=module.registry
    ```

4. Build & push container images:
    ```sh
    cd ../../..
    sh ./docker/cloudbuild.sh <your-project-id> <your-region>
    ```
    You can also specify a version of the dify-api image.
    ```sh
    sh ./docker/cloudbuild.sh <your-project-id> <your-region> <dify-api-version>
    ```
    If no version is specified, the latest version is used by default.

5. Terraform plan:
    ```sh
    cd terraform/environments/dev
    terraform plan
    ```

6. Terraform apply:
    ```sh
    terraform apply
    ```


## Cleanup
```sh
terraform destroy
```

Note: Cloud Storage, Cloud SQL, VPC, and VPC Peering cannot be deleted with the `terraform destroy` command. These are critical resources for data persistence. Access the console and carefully delete them. After that, use the `terraform destroy` command to ensure all resources have been deleted.

## Troubleshooting

### Error creating Slack Notification Channel (`invalid_auth`)

When running `terraform apply`, you may encounter an `invalid_auth` error while creating the `google_monitoring_notification_channel` for Slack, even if your webhook URL is correct.

```
│ Error: Error creating NotificationChannel: googleapi: Error 400: invalid_auth
```

This can be caused by a rare inconsistency in the GCP API when the channel is created via Terraform. If you have verified your webhook URL is correct (e.g., by testing it with `curl`), the workaround is to create the channel manually in the GCP console and then import it into your Terraform state.

**Resolution Steps:**

1.  **Create the Channel Manually in GCP:**
    - Go to the GCP Console: **Monitoring > Alerting**.
    - Click **EDIT NOTIFICATION CHANNELS**.
    - Under **Slack**, click **ADD NEW** and create the channel using your webhook URL.

2.  **Ensure the Resource Exists in Your Terraform Code:**
    Make sure the notification channel resource is defined in your Terraform configuration (e.g., `modules/cloudrun/main.tf`). The `terraform import` command requires a corresponding resource block in the code.
    ```terraform
    resource "google_monitoring_notification_channel" "slack" {
      display_name = "Slack"
      type         = "slack"
      labels = {
        channel_name = var.slack_channel_name
      }
      sensitive_labels {
        auth_token = var.slack_webhook_url
      }
    }
    ```

3.  **Find the Notification Channel's Full ID:**
    Use the `gcloud` CLI to find the full name/ID of the channel you just created. Replace `[YOUR_CHANNEL_DISPLAY_NAME]` with the name you gave it in the console.
    ```sh
    gcloud beta monitoring channels list --filter="displayName='[YOUR_CHANNEL_DISPLAY_NAME]'" --format="value(name)"
    ```
    The output will look something like `projects/[your-project-id]/notificationChannels/[channel-id]`.

4.  **Run `terraform import`:**
    From the `terraform/environments/dev` directory, run the import command. Replace `[FULL_CHANNEL_ID_FROM_PREVIOUS_STEP]` with the value you just copied.
    ```sh
    terraform import module.cloudrun.google_monitoring_notification_channel.slack [FULL_CHANNEL_ID_FROM_PREVIOUS_STEP]
    ```
    You should see an "Import successful!" message.

5.  **Verify the State:**
    Run `terraform plan`. The output should be `No changes. Your infrastructure matches the configuration.`. This confirms the manually created channel is now fully managed by Terraform.

## References
- [Dify](https://dify.ai/)
- [GitHub](https://github.com/langgenius/dify)

## License
This software is licensed under the MIT License. See the LICENSE file for more details.
