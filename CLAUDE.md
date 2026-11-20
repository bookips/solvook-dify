# solvook-dify

Dify self-hosted(GCP Cloud Run) 인프라 Terraform과, Dify 워크플로우를 일괄 실행하는 `dify-batch-processor`가 함께 있는 레포. 원본은 DeNA/dify-google-cloud-terraform 포크이므로, README 상단의 일반 안내는 이 레포의 실제 구성과 다를 수 있다.

## 운영 전제
- 환경은 `terraform/environments/dev` 하나뿐이고, **이게 운영이다.** 이름만 보고 dev로 취급하지 말 것.
- `terraform apply`는 로컬에서만 한다. CI(`.github/workflows/`)는 `fmt`, `validate`만 돌린다. apply는 사용자가 명시적으로 요청할 때만 실행한다.

## Terraform 실행 자격증명
- 셸의 `GOOGLE_APPLICATION_CREDENTIALS`는 다른 SA를 가리키는 경우가 있다. terraform 명령에서는 `.gcp/solvook-infra-2b84d4594582.json`(`dify-batch-processor-sa`)로 덮어써서 실행한다. `.gcp/`는 gitignore 대상이며 저장소에는 없다.
- 이 SA는 Secret Manager IAM 바인딩을 바꿀 수 없다(`secretmanager.secrets.setIamPolicy` 403). 의도된 설계다. `google_secret_manager_secret_iam_member`를 건드리는 apply는 owner 권한 계정의 ADC로 실행한다(`unset GOOGLE_APPLICATION_CREDENTIALS`). **SA에 권한을 추가하는 것으로 해결하지 말 것.**

## 시크릿
- 시크릿은 Secret Manager 참조로 주입된다(Cloud Run `secret_key_ref`, Cloud Functions `secret_environment_variables`). `main.tf`에서 평문 값은 `local.shared_env_vars`, 시크릿 참조는 `local.shared_secret_env_vars`로 나뉜다.
- **시크릿 값 교체는 새 버전을 추가한 뒤 리비전을 재배포하면 된다.** `terraform apply`는 필요 없다. 재배포하지 않으면 옛 값이 계속 살아 있다.
- 예외적으로 평문으로 남아 있는 것이 있다. `GOOGLE_STORAGE_SERVICE_ACCOUNT_JSON_BASE64`(terraform이 생성한 키라 state에 이미 있음)와 Slack 알림 채널의 `auth_token`(API가 시크릿 참조를 지원하지 않음)이다.
- `aws_tools` 플러그인은 자격증명 설정 없이 boto3 기본 체인을 쓴다. 그래서 AWS 키는 `dify-plugin-daemon` 컨테이너의 환경변수에서 읽힌다.

## Cloud Run 멀티 컨테이너 함정 (`dify-service`)
- 사이드카 중 **하나라도** startup probe에 실패하면 인스턴스 전체가 종료된다.
- `dify-worker`(Celery)는 포트를 열지 않는다. 그래서 같은 인스턴스에 있는 plugin-daemon의 5003 포트를 TCP probe로 본다. HTTP probe를 붙이면 안 된다.
- google provider는 한 번 설정한 `startup_probe` 블록을 **제거하지 못한다.** 바꿔야 하면 다른 타입으로 교체한다.
- apply가 중간에 실패하면 state와 실제 서비스가 어긋날 수 있다. `deletion_protection` 때문에 `-replace`는 막혀 있다. 새 리비전이 필요하면 `gcloud run services update --update-labels=force-redeploy=$(date +%s)`를 쓴다.
- dify-web(v1.13.0+)은 non-root로 실행된다. 그래서 `PM2_HOME=/tmp/.pm2`가 필요하다.
- `MIGRATION_ENABLED=true`가 api와 worker 양쪽에 공유된다. 그래서 둘 다 `flask upgrade-db`를 실행하고, 이 명령은 먼저 Redis 락을 잡는다. Redis에 연결할 수 없으면 기동 직후 죽는다. 원인 로그가 보이지 않으면 `PYTHONUNBUFFERED=1`을 설정한다.

## 알려진 장애: 콜드 스타트 직후 플러그인 미준비
- `min_instance_count = 0`이라 0대에서 새로 뜨는 인스턴스는 약 90초 동안 플러그인이 준비되지 않는다. 플러그인을 동시 2개씩 순차로 기동하기 때문이다. 그런데 probe는 1초 만에 통과하므로 그 사이 들어온 요청이 `no available node, plugin runtime not found`로 실패한다.
- 대응: batch processor poller가 이 에러로 실패한 run을 `PENDING`으로 되돌려 최대 `MAX_TRANSIENT_RETRIES`(기본 2)회 다시 실행한다. `min_instance_count`는 비용 때문에 0으로 유지하기로 했다.
- 분석과 계획: `docs/plans/2026-11-20-batch-poller-transient-retry.md`

## 이미지와 레지스트리
- Cloud Run은 amd64만 실행한다. Apple Silicon에서 받은 이미지는 arm64이므로, `docker manifest inspect`로 amd64 digest를 찾아 그 digest로 pull/push한다.
- Artifact Registry 구성:
  - `dify-api-repo`, `dify-nginx-repo`는 직접 push하는 일반 저장소다. 빌드는 `docker/`에 있다.
  - `dify-web-repo`, `dify-sandbox-repo`, `dify-plugin-daemon-repo`는 Docker Hub 원격 프록시라 push할 수 없다. 버전은 tfvars 태그만 바꾸면 된다.
- Cloud SQL에 `vector`, `uuid-ossp` 확장을 수동으로 설치해야 한다(Cloud SQL Studio).

## dify-batch-processor
- 구조: loader → dispatcher → Cloud Tasks → worker → poller. worker는 `workflow_started`만 받고 끝나며, 성공·실패 판정은 poller가 한다.
- 상태 저장소는 **PostgreSQL `batch_process_status`** 테이블이다. README 일부와 `GEMINI.md`의 Firestore/Datastore 설명은 옛 내용이다. 함수명 `update_datastore` 등은 그 시절 이름이 남은 것이다.
- `shared/utils.py`의 `_KNOWN_COLUMNS`와 `check_and_upsert_status`의 `known_cols`에 없는 키는 **에러 없이 버려진다.** 컬럼을 추가하면 두 목록과 실제 DB 스키마를 함께 바꿔야 한다. 테스트(`tests/test_status_columns.py`)가 `retry_count` 누락을 잡는다.
- 테스트: `cd dify-batch-processor && poetry run pytest`. 함수마다 `config.py`가 따로 있어 `tests/conftest.py`의 `load_function`으로만 import한다.
- 배포는 terraform `modules/dify_batch_processor`가 소스를 zip으로 묶어 Cloud Functions gen2로 올린다. 이 zip에 `shared/`가 포함되므로, 공용 코드를 바꾸면 해당 함수들을 모두 재배포해야 한다.
- 워크플로우 ID와 커리큘럼·카테고리의 매핑은 `terraform.tfvars`의 `*_workflow_id` 값과 loader 설정에 있다.
