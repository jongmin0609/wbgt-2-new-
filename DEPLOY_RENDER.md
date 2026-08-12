# Render HTTPS 배포 가이드

이 프로젝트를 어디서나 열리는 HTTPS 링크로 배포하려면 Render Web Service를
사용합니다. 배포용 앱은 `cloud_app.py` 하나이며, 대시보드와 PC 입력 페이지가
한 사이트 안의 탭으로 들어 있습니다.

## 준비

1. GitHub에 이 프로젝트 폴더를 새 저장소로 올립니다.
2. Render 계정을 만듭니다.
3. Render에서 `New` -> `Blueprint` 또는 `New Web Service`를 선택합니다.

## Blueprint 방식

저장소 루트의 `render.yaml`을 Render가 읽어 자동으로 설정합니다.

- Build command: `pip install -r requirements.txt`
- Start command: `streamlit run cloud_app.py --server.address=0.0.0.0 --server.port=$PORT --server.headless=true`
- Environment variable: `WGBT_DATA_DIR=/tmp/wgbt-data`
- Optional environment variable: `WGBT_ADMIN_CODE=원하는_관리자_코드`

Render는 Web Service에 `onrender.com` HTTPS 주소를 제공합니다. 커스텀 도메인을
연결하면 HTTP 요청도 HTTPS로 리다이렉트되고 TLS 인증서가 자동 생성/갱신됩니다.

## 저장 데이터

다중 작업자 앱의 런타임 데이터는 `WGBT_DATA_DIR` 위치의 JSON 파일에 저장됩니다.
기기 권한은 `devices.json`, 작업자별 현재 상태는 `workers.json`, 경고 이상 기록은
`risk_events.json`에 저장됩니다.

기본값인 `/tmp/wgbt-data`는 무료 배포가 먼저 성공하도록 둔 임시 저장 경로입니다.
Render 무료 Web Service는 장기 파일 저장을 보장하지 않고, 유휴 상태 후 재시작될
수 있습니다. 측정값을 재시작 후에도 유지하려면 유료 Web Service에 Persistent
Disk를 붙이고 `WGBT_DATA_DIR`을 디스크 마운트 경로(예: `/var/data`)로 바꾸거나
Supabase 같은 외부 데이터베이스로 저장소를 바꿔야 합니다.

## 도메인 연결

1. Render 서비스 화면에서 `Settings` -> `Custom Domains`로 이동합니다.
2. 원하는 도메인 또는 서브도메인을 추가합니다.
3. Render가 알려주는 DNS 레코드를 도메인 업체 화면에 등록합니다.
4. Render에서 Verify를 누릅니다.

완료되면 예를 들어 `https://heat.example.com` 같은 주소로 접속할 수 있습니다.
