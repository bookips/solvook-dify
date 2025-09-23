# Dify WORKFLOW BATCH PROCESSOR SYSTEM

## 1. 개요

이 시스템은 Google Sheets에 저장된 데이터를 읽어 Dify LLM 워크플로우를 병렬로 실행하고, 그 결과를 안정적으로 처리하기 위해 설계되었습니다. **Cloud Run (Cloud Functions 2nd gen 기반)**, Cloud Tasks, Firestore를 사용하여 효율적이고 안정적인 데이터 처리를 보장합니다.

## 2. 아키텍처

Terraform으로 배포되는 `loader`와 `worker`는 Cloud Functions (2nd gen) 리소스로 정의되어 있지만, **내부적으로 Cloud Run 서비스로 실행됩니다.** 이는 Cloud Functions (2nd gen)이 Cloud Run의 강력한 기능과 확장성을 기반으로 하기 때문입니다.

-   **Cloud Scheduler**: 주기적으로 `Loader` Cloud Run 서비스를 트리거합니다.
-   **Cloud Run (Loader)**: Google Sheets에서 데이터를 읽고, Firestore의 처리 상태를 확인하여 처리해야 할 데이터에 대한 태스크를 Cloud Tasks에 생성합니다.
-   **Cloud Tasks**: `Loader`로부터 받은 태스크를 큐에 저장하고, `Worker`에게 분산하여 전달합니다. 실패 시 설정된 정책에 따라 자동으로 재시도합니다.
-   **Cloud Run (Worker)**: Cloud Tasks로부터 태스크를 받아 Dify API를 호출하여 실제 워크플로우를 실행하고, 결과를 Firestore에 업데이트합니다. **동시에 실행되는 Worker 인스턴스의 수는 Cloud Tasks 큐 설정으로 제어됩니다.**
-   **Firestore**: 각 데이터의 처리 상태(`PENDING`, `PROCESSING`, `SUCCESS`, `FAILED`)를 저장하고 관리합니다.

## 3. 설정 및 배포 (Terraform)

### 3.1. 사전 준비 사항

1.  **Terraform 설치**: Terraform CLI를 설치합니다.
2.  **GCP 인증**: `gcloud auth application-default login` 명령어를 실행하여 Terraform이 GCP에 접근할 수 있도록 인증합니다.
3.  **소스 코드 버킷 생성**: Cloud Function(2nd gen) 소스 코드를 업로드할 Google Cloud Storage 버킷이 Terraform에 의해 자동으로 생성됩니다.
4.  **Google Sheets API 활성화**: GCP 프로젝트에서 Google Sheets API를 활성화합니다.
5.  **서비스 계정 생성 및 키 저장**:
    -   Google Sheets에 접근할 수 있는 권한(`roles/sheets.reader`)을 가진 서비스 계정을 생성하고, 키(JSON)를 다운로드합니다.
    -   **Google Sheets API 인증 정보 생성 및 등록**:
        1.  `gcloud` CLI를 사용하여 `dify-batch-processor-credentials`라는 이름으로 시크릿을 생성합니다.
            ```bash
            gcloud secrets create dify-batch-processor-credentials --replication-policy="automatic"
            ```
        2.  다운로드한 서비스 계정 키 파일(`.gcp/solvook-infra-2b84d4594582.json`)을 사용하여 시크릿 버전을 추가합니다.
            ```bash
            gcloud secrets versions add dify-batch-processor-credentials --data-file="./.gcp/solvook-infra-2b84d4594582.json"
            ```

    -   **Dify API Key 생성 및 등록**:
        1.  `gcloud` CLI를 사용하여 시크릿을 생성합니다.
            ```bash
            gcloud secrets create dify-api-key --replication-policy="automatic"
            ```
        2.  Dify API 키 값을 시크릿 버전으로 추가합니다. `YOUR_DIFY_API_KEY` 부분을 실제 키 값으로 변경하세요.
            ```bash
            printf "YOUR_DIFY_API_KEY" | gcloud secrets versions add dify-api-key --data-file=-
            ```
6.  **Firestore 설정**: Native 모드로 Firestore 데이터베이스를 생성합니다.

### 3.2. Terraform 변수 설정

`terraform/environments/dev/terraform.tfvars` 파일에 아래 변수들을 추가하거나 수정합니다.

```hcl
# Dify Data Processor Variables
spreadsheet_id                      = "YOUR_GOOGLE_SHEET_ID"
sheet_name                          = "Sheet1"
unique_id_column                    = "0" # 또는 "ROW_NUMBER"
dify_api_endpoint                   = "https://your-dify-api.example.com/v1/workflows/run"
dify_api_key_secret_id              = "dify-api-key"
dify_api_timeout_minutes            = 5 # Dify API 호출 타임아웃 (분)
google_sheets_credentials_secret_id = "dify-batch-processor-credentials"
```

### 3.3. 병렬 실행 설정 (Concurrency)
Worker 서비스의 동시 실행 인스턴스 수는 Dify API 서버의 부하를 관리하는 데 매우 중요합니다. 이 설정은 Terraform의 Cloud Tasks 큐 리소스에서 관리할 수 있습니다.

**파일**: `terraform/modules/dify_batch_processor/main.tf`
**리소스**: `google_cloud_tasks_queue`

`rate_limits` 블록을 추가하여 동시에 실행될 Worker 서비스의 최대 인스턴스 수를 제어할 수 있습니다. 예를 들어, 최대 5개로 제한하려면 아래와 같이 수정합니다.

```terraform
resource "google_cloud_tasks_queue" "dify_batch_processor_queue" {
  # ... existing configuration ...

  rate_limits {
    max_concurrent_dispatches = 5
  }
}
```
> **참고**: 현재 코드에는 `rate_limits` 블록이 설정되어 있지 않으므로, 필요에 따라 직접 추가해야 합니다.

### 3.4. Terraform 배포

1.  `dev` 환경 디렉터리로 이동합니다.
    ```bash
    cd terraform/environments/dev
    ```
2.  Terraform을 초기화합니다.
    ```bash
    terraform init
    ```
3.  Terraform 실행 계획을 확인합니다.
    ```bash
    terraform plan
    ```
4.  계획에 문제가 없으면 리소스를 배포합니다.
    ```bash
    terraform apply
    ```

배포가 완료되면 `dify-batch-processor-loader` 서비스의 URL이 출력됩니다. 이 URL을 사용하여 Cloud Scheduler를 설정하거나 직접 호출하여 데이터 처리를 시작할 수 있습니다.

### 3.5. 모니터링

Terraform 배포 시 `dify-batch-processor Monitoring Dashboard`라는 이름의 커스텀 대시보드가 자동으로 생성됩니다. GCP 콘솔의 **Monitoring > Dashboards** 메뉴에서 해당 대시보드를 찾아 아래와 같은 지표를 실시간으로 확인할 수 있습니다.

-   **Loader/Worker 서비스 실행 횟수**: 각 서비스의 시간당 실행 횟수
-   **Worker 서비스 실행 시간 (p50)**: Worker 서비스의 50 percentile 실행 시간
-   **Cloud Tasks 큐 깊이**: 처리 대기 중인 태스크의 수
-   **서비스 에러 로그**: `loader` 및 `worker` 서비스에서 발생한 심각도 `ERROR` 수준의 로그

## 4. 코드 수정 포인트 (TODO)

-   `loader/main.py`: `get_sheets_service()` 함수 내에 Secret Manager에서 Google Sheets 서비스 계정 키를 가져오는 로직을 구현해야 합니다.
-   `worker/main.py`: `dify_payload`를 실제 Dify 워크플로우의 입력 형식에 맞게 수정해야 합니다.