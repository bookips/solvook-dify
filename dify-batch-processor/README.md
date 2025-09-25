# Dify WORKFLOW BATCH PROCESSOR SYSTEM

## 1. 개요

이 시스템은 Google Sheets에 저장된 데이터를 읽어 Dify LLM 워크플로우를 병렬로 실행하고, 그 결과를 안정적으로 처리하기 위해 설계되었습니다. **Cloud Run (Cloud Functions 2nd gen 기반)**, Cloud Tasks, **Firestore (Datastore Mode)**를 사용하여 효율적이고 안정적인 데이터 처리를 보장합니다.

## 2. 아키텍처

Terraform으로 배포되는 `loader`와 `worker`는 Cloud Functions (2nd gen) 리소스로 정의되어 있지만, **내부적으로 Cloud Run 서비스로 실행됩니다.** 이는 Cloud Functions (2nd gen)이 Cloud Run의 강력한 기능과 확장성을 기반으로 하기 때문입니다.

-   **Cloud Scheduler**: 주기적으로 `Loader` Cloud Run 서비스를 트리거합니다.
-   **Cloud Run (Loader)**: Google Sheets에서 데이터를 읽고, Firestore의 처리 상태를 확인하여 처리해야 할 데이터에 대한 태스크를 Cloud Tasks에 생성합니다.
-   **Cloud Tasks**: `Loader`로부터 받은 태스크를 큐에 저장하고, `Worker`에게 분산하여 전달합니다. 실패 시 설정된 정책에 따라 자동으로 재시도합니다.
-   **Cloud Run (Worker)**: Cloud Tasks로부터 태스크를 받아 Dify API를 호출하여 실제 워크플로우를 실행하고, 결과를 Firestore에 업데이트합니다. **동시에 실행되는 Worker 인스턴스의 수는 Cloud Tasks 큐 설정으로 제어됩니다.**
-   **Firestore (Datastore Mode)**: 각 데이터의 처리 상태(`PENDING`, `PROCESSING`, `SUCCESS`, `FAILED`)를 저장하고 관리합니다.

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
6.  **Firestore 설정**: GCP 프로젝트에서 **Datastore 모드**로 Firestore 데이터베이스를 활성화합니다.

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
-   **Loader/Worker 서비스 CPU, Memory 지표**: 각 서비스의 CPU, Memory  지표
-   **Worker 서비스 실행 시간 (p50)**: Worker 서비스의 50 percentile 실행 시간
-   **Cloud Tasks 큐 깊이**: 처리 대기 중인 태스크의 수
-   **서비스 에러 로그**: `loader` 및 `worker` 서비스에서 발생한 심각도 `ERROR` 수준의 로그

## 4. 로컬 개발 및 테스트 (Makefile 사용)

`loader`와 `worker` 함수를 로컬 환경에서 테스트할 수 있습니다. `Makefile`을 사용하여 복잡한 설정 및 실행 과정을 간소화했습니다. 로컬 테스트는 실제 GCP 서비스 대신 Firestore 에뮬레이터를 사용합니다.

### 4.1. 사전 준비 사항

1.  **Python & Poetry**: 프로젝트 의존성 관리를 위해 필요합니다.
2.  **Google Cloud CLI**: Firestore 에뮬레이터를 설치하고 실행하기 위해 필요합니다. 아래 명령어를 실행하여 `beta` 컴포넌트와 에뮬레이터를 설치하세요.
    ```bash
    gcloud components install beta
    gcloud components install cloud-firestore-emulator
    ```
3.  **Java 8+ JRE**: Firestore 에뮬레이터는 Java로 실행되므로, 시스템에 Java 8 이상의 버전이 설치되어 있어야 합니다.
4.  **GCP 서비스 계정 키**: `loader`가 Google Sheets에 접근하기 위해 필요합니다. (`.gcp/` 디렉터리에 JSON 키 파일 저장)

### 4.2. 테스트 설정

1.  **(최초 1회)** `dify-batch-processor` 디렉터리에서 아래 명령어를 실행하여 Python 의존성을 설치합니다.
    ```bash
    make install
    ```

2.  **(최초 1회)** 환경 변수 설정 파일을 생성합니다.
    ```bash
    make setup
    ```
    이 명령어는 `.env.example` 파일을 복사하여 `.env` 파일을 생성합니다. 생성된 `.env` 파일을 열어 `YOUR_...`로 표시된 값들을 실제 프로젝트에 맞게 수정해야 합니다.

### 4.3. 로컬 테스트 워크플로우

테스트를 위해서는 최소 3개의 터미널 세션이 필요합니다. 모든 명령어는 `dify-batch-processor` 디렉터리에서 실행합니다.

1.  **터미널 1: Firestore 에뮬레이터 실행**
    Firestore 데이터베이스를 로컬에서 시뮬레이션하기 위해 에뮬레이터를 시작합니다.
    ```bash
    make run-emulator
    ```
    > **참고**: 테스트가 끝나면 `make stop-emulator` 명령어로 에뮬레이터를 중지할 수 있습니다.

2.  **터미널 2: Worker 실행**
    `worker` 함수를 로컬 서버로 실행하여 HTTP 요청을 받을 준비를 합니다.
    ```bash
    make run-worker
    ```

3.  **터미널 3: Worker 테스트**
    실행 중인 `worker`에게 테스트용 `curl` 요청을 보내 정상적으로 작동하는지 확인합니다.
    ```bash
    make test-worker
    ```
    `worker` 터미널(터미널 2)에 성공 로그가 출력되는지 확인합니다. Firestore 에뮬레이터에 `SUCCESS` 상태의 문서가 생성되었는지는 아래 방법으로 확인할 수 있습니다.

    #### 에뮬레이터 데이터 확인
    
    Firestore 에뮬레이터는 데이터 확인을 위한 웹 UI를 제공합니다. 이 방법을 사용하는 것을 권장합니다.
    
    1.  웹 브라우저에서 `http://localhost:4000` 으로 접속합니다.
    2.  **Kind** 목록에서 `dify_batch_process_status`를 선택합니다.
    3.  **Key / ID** 목록에서 확인하고 싶은 ID(예: `local-test-from-make`)를 클릭하면 우측에 저장된 데이터(`status`, `result` 등)를 확인할 수 있습니다.

4.  **터미널 2: Loader 실행**
    `worker` 테스트가 끝나면, 터미널 2에서 `Ctrl+C`로 `worker`를 중지하고 `loader`를 실행합니다.
    ```bash
    make run-loader
    ```

5.  **터미널 3: Loader 테스트**
    `loader` 함수를 트리거하여 Google Sheets에서 데이터를 읽고 Firestore 에뮬레이터에 `PENDING` 상태로 기록하는지 확인합니다.
    ```bash
    make test-loader
    ```
    > **참고**: `loader`는 로컬에서 Cloud Tasks 태스크를 생성하지 못하고 오류를 출력할 수 있으나, 이는 정상적인 동작입니다. Firestore 에뮬레이터에 데이터가 `PENDING` 상태로 기록되었는지 확인하는 것이 중요합니다.

언제든지 `make help` 명령어를 실행하면 사용 가능한 모든 스크립트와 설명을 확인할 수 있습니다.

### 4.4. 문제 해결 (Troubleshooting)

#### `CONSUMER_INVALID` 에러 발생 시

로컬 환경에서 `loader` 또는 `worker` 실행 시, Cloud Tasks나 Firestore API 호출에서 `PermissionDenied: 403 ... reason: "CONSUMER_INVALID"` 와 같은 에러가 발생할 수 있습니다.

*   **원인**: 이 에러는 IAM 권한 부족이 아니라, GCP 조직에 설정된 **VPC 서비스 제어(VPC Service Controls)**와 같은 보안 정책 때문일 가능성이 매우 높습니다. 이 정책은 신뢰할 수 없는 네트워크(예: 로컬 개발 환경)에서 GCP 서비스로의 API 호출을 차단합니다.

*   **해결 방안**: 가장 확실한 해결책은 보안 경계 **내부**에서 코드를 실행하는 것입니다. GCP 프로젝트 내에 작은 GCE(Google Compute Engine) VM 인스턴스를 생성하고, 해당 VM에 접속하여 개발 환경을 구성한 뒤 `make run-loader`나 `make run-worker`를 실행하면 이 문제를 우회할 수 있습니다. 모든 API 호출이 GCP 내부 네트워크에서 발생하므로 보안 정책에 의해 차단되지 않습니다.
