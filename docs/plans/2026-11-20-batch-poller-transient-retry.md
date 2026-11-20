# Batch Processor: 플러그인 콜드 스타트 실패 자동 재시도

- 작성일: 2026-11-20
- 상태: **구현 완료(브랜치 `feat/poller-transient-retry`).** 2026-11-20 운영 DB에 `retry_count` ALTER 적용, 조건부 쓰기 확인 스크립트 통과. **`terraform apply` 전** — §6 배포 순서 참고
- 대상: `dify-batch-processor` (poller, shared, loader), 운영 DB `batch_process_status`

## 1. 배경

### 증상
batch processor가 실행하는 Dify 워크플로우가 가끔 아래 에러로 실패한다.

```
req_id: 4a007fffb6 PluginDaemonInternalServerError: no available node, plugin runtime not found
```

대상 워크플로우:
- `0a179409-d6ee-46e2-bf78-83fd7d415123` (high passage analysis)
- `9aa5df68-9912-4a74-8379-04eee2db8994` (high passage workbook)

에러는 워크플로우 종류와 상관없이 발생한다. 원인은 Dify 인프라 쪽에 있다.

### 원인
`dify-service`(Cloud Run)는 `min_instance_count = 0`이라 유휴 상태에서 인스턴스가 0대로 줄어든다. 새 인스턴스가 뜨면 아래 순서로 진행된다.

1. plugin-daemon의 startup probe(TCP 5003)가 약 1초 만에 통과하고, Cloud Run은 곧바로 트래픽을 보낸다.
2. plugin-daemon은 설치된 플러그인 9개를 **동시에 2개씩** 순서대로 띄운다. 하나당 10~20초가 걸린다.
3. 아직 뜨지 않은 플러그인을 호출한 요청은 위 에러로 실패한다. 다른 노드도 없으므로 대신 처리해 줄 곳이 없다.

2026-11-20 사례의 타임라인:

| 시각 (UTC) | 이벤트 |
|---|---|
| 02:17:06 | 인스턴스 콜드 스타트 |
| 02:17:13 | startup probe 통과, 플러그인 순차 기동 시작 |
| 02:18:14–16 | `json_process` 툴 호출 약 40건 실패 |
| 02:18:39 | `json_process` 준비 완료 |
| 02:18:44 | 마지막 플러그인 준비 완료 (콜드 스타트 후 약 98초) |

최근 30일 동안 에러가 난 3건(10/22, 10/26, 11/20)은 모두 **인스턴스 시작 후 42~69초 사이**에만 발생했다.

### 검토한 대안
| 방안 | 판단 |
|---|---|
| `min_instance_count = 1` | 가장 확실하다. 다만 상시 비용이 든다. 이 문서에서는 다루지 않는다 |
| **batch processor 재시도** | **이 문서의 범위.** 일시적인 실패를 클라이언트 쪽에서 흡수한다 |
| 미사용 플러그인 제거 | 준비 시간만 줄 뿐 문제가 없어지지는 않는다. 별도로 진행할 수 있다 |
| 플러그인 준비 완료 기준 probe | plugin-daemon에 해당 엔드포인트가 없어 비용 대비 효과가 낮다 |

## 2. 설계

### 재시도 위치: poller
worker([worker/main.py](../../dify-batch-processor/worker/main.py))는 스트림에서 `workflow_started`를 받으면 바로 `PROCESSING`으로 기록하고 끝난다. 플러그인 실패는 그 이후 실행 도중에 일어나므로 worker는 이 에러를 볼 수 없다. 실패는 poller가 Dify run 상태를 조회할 때 처음 드러난다.

### 흐름
```
PROCESSING ──(poller: status=failed, 재시도 대상 에러, retry_count < 상한)──▶ PENDING
                                                                         │
                         dispatcher(1분 주기) → QUEUED → worker → PROCESSING ◀┘
PROCESSING ──(poller: 그 외 failed, 또는 상한 도달)──▶ FAILED   (기존 동작)
```

- 재투입은 기존 dispatcher 경로를 그대로 쓴다. 새 큐나 스케줄러는 만들지 않는다.
- poller(3분)와 dispatcher(1분) 주기 때문에 재실행까지 최소 1~4분이 걸린다. 플러그인 준비 시간(약 98초)보다 길기 때문에 별도 backoff는 넣지 않는다.

### 재시도 대상 판정
Dify run 응답의 `error` 문자열에 아래 두 문구가 **모두** 포함되면 재시도 대상으로 본다(허용 목록 방식). 처음에는 "둘 중 하나"였으나, 코드 리뷰 후 2026-11-20에 좁혔다. `no available node`는 무관한 컴포넌트의 에러에도 나올 수 있는데, 잘못 재시도하면 워크플로우 전체를 다시 돌려 비용이 든다. 판정을 놓쳐도 결과는 지금처럼 `FAILED`일 뿐이다.

- `no available node`
- `plugin runtime not found`

그 밖의 실패(프롬프트 오류, 입력 오류 등)는 지금처럼 바로 `FAILED`로 처리한다.

### 재시도 상한
- 새 컬럼 `retry_count`로 횟수를 기록한다. 상한이 없으면 실패가 반복될 때 무한히 재투입된다.
- 상한은 `MAX_TRANSIENT_RETRIES` 환경변수로 받는다. 기본값은 **2** 이다. `0`이면 재시도하지 않는다.
- 시트에서 다시 실행하면(loader가 FAILED 행을 PENDING으로 올리는 경우) `retry_count`를 0으로 초기화한다.

### 조건부 쓰기 (2026-11-20 리뷰 후 추가)
- 재시도로 PROCESSING → PENDING → PROCESSING 순환이 생겼다. 그래서 poller가 예전에 조회한 행으로 쓰면 새 실행을 재투입하거나 FAILED로 덮어쓸 수 있다.
- poller의 모든 쓰기는 `update_datastore(..., expect={"status": "PROCESSING", "timestamp": <조회한 값>})`로 한다. SQL은 `ON CONFLICT ... DO UPDATE ... WHERE ... IS NOT DISTINCT FROM`이고, NULL timestamp도 일치로 본다. 조건이 맞지 않으면 쓰지 않는다.
- 지금 설정(poller 인스턴스 1개, 한 번에 조회하는 행 최대 2개)에서는 겹칠 일이 사실상 없다. 그래도 순환이 생긴 이상 코드로 막아 둔다. AST 정적 감사 테스트가 `expect=` 없는 poller 쓰기를 잡는다.

## 3. 변경 목록

### 3.1 DB 스키마
```sql
ALTER TABLE batch_process_status ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
```
- 운영 DB에 직접 적용한다.
- [scripts/migrate_datastore_to_postgres.py](../../dify-batch-processor/scripts/migrate_datastore_to_postgres.py)의 `CREATE TABLE`에도 같은 내용을 반영한다.

### 3.2 `shared/utils.py`
- `_KNOWN_COLUMNS`에 `retry_count`를 추가한다.
  - **주의:** 목록에 없는 키는 에러 없이 버려진다. 이 항목이 빠지면 `retry_count`가 늘 0으로 남아 무한 재시도가 된다.
- `check_and_upsert_status`의 `known_cols`에도 `retry_count`를 추가한다. 위 목록과 별도로 관리되는 중복 목록이다.
  - (2026-11-20 리뷰 후) 중복 목록을 없애고 `_KNOWN_COLUMNS`에서 파생한 `_DATA_COLUMNS`를 쓰도록 바꿨다.

### 3.3 `poller/main.py`, `poller/config.py`
- `is_retryable(error_message) -> bool` 함수를 추가한다.
- `status == "failed"` 분기를 다음과 같이 바꾼다.
  - 재시도 대상이고 `retry_count < MAX_TRANSIENT_RETRIES`이면 `PENDING`으로 되돌린다. 이때 `workflow_run_id=None`, `retry_count+1`로 바꾸고, `message`에 재시도 사유를 남긴다.
  - 그렇지 않으면 기존처럼 `FAILED`로 처리한다.
- `retry_count`가 None인 기존 행은 0으로 취급한다.
- `Config.MAX_TRANSIENT_RETRIES`를 추가한다(기본 2).

### 3.4 `loader/main.py`
- `check_and_upsert_status` 호출 시 넘기는 `data`에 `retry_count: 0`을 추가한다.

### 3.5 Terraform (선택) — **적용하지 않음**
- 코드 기본값(2)을 그대로 쓰므로 terraform 변경 없이 배포한다. 상한을 바꿔야 할 때 아래를 추가한다.
- `terraform/modules/dify_batch_processor`에서 poller 환경변수로 `MAX_TRANSIENT_RETRIES`를 넘긴다.
- poller zip에는 이미 `shared/`가 포함되어 있어 utils 변경은 자동으로 반영된다.

### 3.6 문서
- [dify-batch-processor/README.md](../../dify-batch-processor/README.md)의 poller 설명과 상태 흐름에 "일시적 실패면 PENDING으로 재투입, 최대 N회"를 추가한다.

## 4. 검증 계획

레포에는 아직 테스트가 없으므로 pytest를 개발 의존성으로 추가한다. 테스트에서는 DB(`update_datastore`, `get_entities_from_datastore`)와 Dify 응답(`requests.get`)을 mock한다.

### 4.1 착수 전 검증도구 (구현 전에 실패해야 함)
| # | 시나리오 | 기대 결과 |
|---|---|---|
| 1 | 실제 로그 문자열로 `failed`, `retry_count=0` | `PENDING`, `retry_count=1`, `workflow_run_id=None` |
| 2 | 같은 에러, `retry_count = 상한-1` | `PENDING` (마지막 재시도) |
| 3 | 같은 에러, `retry_count = 상한` | `FAILED` |
| 4 | 같은 에러, `retry_count = None` (기존 행) | 0으로 취급해 `PENDING` |
| 5 | 다른 에러 메시지로 `failed` | 바로 `FAILED` (기존 동작) |
| 6 | `succeeded`, `partial-succeeded` | `SUCCESS` (기존 동작) |
| 7 | `running` | 상태 변경 없음 (기존 동작) |
| 8 | `update_datastore(..., data={"retry_count": 1})`가 만든 SQL | `retry_count` 컬럼이 포함된다 |
| 9 | `check_and_upsert_status`에 `retry_count: 0` 전달 | upsert SQL에 포함된다 |

### 4.2 구현 직후 검증도구 (구현이 새로 만든 축)
- PENDING으로 되돌린 행을 dispatcher가 다시 집어 가는지 확인한다. `data`와 `workflow_id`가 그대로 남아 있어야 한다.
- 한 번의 poller 실행 안에서 재시도 대상과 일반 실패가 섞여 있을 때 각각 맞게 분기되는지 확인한다.
- 8번 테스트가 장식이 아닌지 확인한다. `_KNOWN_COLUMNS`에서 `retry_count`를 일부러 빼고 실패하는지 본 뒤 되돌린다.

### 4.3 배포 후 확인
- 다음 콜드 스타트 때 로그에 재시도 메시지가 남는지, 해당 행이 최종적으로 `SUCCESS`가 되는지 확인한다.
- `SELECT status, retry_count, count(*) FROM batch_process_status GROUP BY 1,2;`로 분포를 확인한다.

## 5. 커밋 계획
1. `test: add poller transient retry tests` (pytest 설정 + 4.1 테스트, 이 시점에는 실패)
2. `feat: retry plugin cold-start failures in poller` (3.2~3.4 구현)
3. `test: ...` (4.2 테스트)
4. `docs: describe transient retry in batch processor README` (3.6, 스키마 스크립트 반영 포함)

스테이징은 파일 경로를 지정해서 한다.

## 6. 배포 순서
1. 운영 DB에 [scripts/sql/2026-11-20-add-retry-count.sql](../../dify-batch-processor/scripts/sql/2026-11-20-add-retry-count.sql) 적용 (Cloud SQL Studio, 여러 번 실행해도 안전)
   - **반드시 함수 배포보다 먼저 적용한다.** 순서가 바뀌면:
     - **loader**: 모든 실행이 첫 행에서 `column retry_count does not exist`로 500이 난다. 시트의 어떤 행도 큐에 들어가지 않는다.
     - **poller**: `update_datastore`가 예외를 삼켜 행이 `PROCESSING`에 머물고, 30분 타임아웃 뒤 `FAILED`가 된다.
   - `migrate_datastore_to_postgres.py`로 스키마를 맞추지 않는다. `CREATE TABLE IF NOT EXISTS`라서 기존 테이블에는 아무 일도 하지 않고, Datastore 데이터를 다시 가져오는 스크립트다.
   - 적용 후 조건부 쓰기 확인: proxy를 띄우고(`./scripts/cloud-sql-proxy.sh`) `dify-batch-processor/`에서 `DB_HOST=localhost DB_PORT=15432 poetry run python scripts/verify_conditional_write.py` 실행. `ALL CHECKS PASSED`, exit 0이어야 한다. 임시 테이블·읽기 전용 세션·롤백 안에서만 돌아서 실제 테이블에는 쓰지 않는다(ALTER 적용 전에 돌려도 된다).
2. `terraform apply`로 재배포. 코드가 바뀐 것은 poller와 loader지만, 4개 함수(loader·dispatcher·worker·poller)의 zip에 모두 `shared/utils.py`가 들어가므로 네 함수가 모두 다시 배포된다.
3. 4.3 확인

롤백: poller를 이전 버전으로 재배포한다. 컬럼은 남겨 둬도 기존 코드에 영향이 없다.

## 7. 결정이 필요한 사항
2026-11-20 결정:
- [x] **워크플로우를 처음부터 다시 돌려도 괜찮은지** → 괜찮다(사용자 확인). 재시도는 처음부터 다시 실행한다.
- [x] 재시도 상한 값 → **2**
- [x] polling 요청 자체의 실패(Dify 5xx 등) → **이번 범위에서 제외.** 지금처럼 즉시 `FAILED`.
- [x] `min_instance_count = 1` 함께 적용 → **적용하지 않는다.** 현재 설정(0) 유지.

## 8. 범위 밖
- worker 단계의 HTTP 실패 재시도 (Cloud Tasks 재시도 정책)
- 미사용 플러그인 정리, plugin-daemon 기동 동시성 조정
- `min_instance_count` 변경
