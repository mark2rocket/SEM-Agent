# Railway 배포 설정 가이드

## 현재 상태
- ✅ GitHub 저장소 생성 및 코드 푸시 완료
- ✅ Railway 프로젝트 생성 완료 (sem-agent.up.railway.app)
- ❌ 환경 변수 미설정으로 502 에러 발생 중

## 해결 방법

### 옵션 1: Railway CLI 사용 (권장)

#### 1단계: Railway 로그인
```bash
railway login
```
브라우저가 열리면 Railway 계정으로 로그인하세요.

#### 2단계: 프로젝트 연결
```bash
railway link
```
목록에서 `SEM-Agent` 프로젝트를 선택하세요.

#### 3단계: 데이터베이스 서비스 추가
Railway 대시보드에서:
1. **PostgreSQL** 추가: New → Database → Add PostgreSQL
2. **Redis** 추가: New → Database → Add Redis

서비스 추가 후 잠시 기다리면 `DATABASE_URL`과 `REDIS_URL`이 자동으로 설정됩니다.

#### 4단계: 환경 변수 자동 설정
```bash
./setup-railway-env.sh
```

이 스크립트는 로컬 `.env` 파일의 모든 필요한 환경 변수를 Railway에 자동으로 설정합니다.

#### 5단계: 배포 확인
```bash
# 배포 로그 확인
railway logs

# 상태 확인
curl https://sem-agent.up.railway.app/health
```

---

### 옵션 2: Railway 대시보드 사용

#### 1단계: 데이터베이스 추가
1. Railway 대시보드 접속: https://railway.app
2. SEM-Agent 프로젝트 선택
3. **New** → **Database** → **Add PostgreSQL**
4. **New** → **Database** → **Add Redis**

#### 2단계: 환경 변수 설정
프로젝트 → **Variables** 탭 → 다음 변수들을 추가:

**Slack 설정:**
```
SLACK_CLIENT_ID=<로컬 .env에서 복사>
SLACK_CLIENT_SECRET=<로컬 .env에서 복사>
SLACK_SIGNING_SECRET=<로컬 .env에서 복사>
SLACK_BOT_TOKEN=<로컬 .env에서 복사>
SLACK_APP_TOKEN=<로컬 .env에서 복사>
SLACK_REDIRECT_URI=https://sem-agent.up.railway.app/oauth/slack/callback
SLACK_ALERT_CHANNEL=#alerts
```

**Google 설정:**
```
GOOGLE_CLIENT_ID=<로컬 .env에서 복사>
GOOGLE_CLIENT_SECRET=<로컬 .env에서 복사>
GOOGLE_REDIRECT_URI=https://sem-agent.up.railway.app/oauth/google/callback
GOOGLE_DEVELOPER_TOKEN=<로컬 .env에서 복사>
GOOGLE_LOGIN_CUSTOMER_ID=<로컬 .env에서 복사>
```

**Gemini AI:**
```
GEMINI_API_KEY=<로컬 .env에서 복사>
```

**보안 설정:**
```
TOKEN_ENCRYPTION_KEY=<로컬 .env에서 복사>
SECRET_KEY=<로컬 .env에서 복사>
```

**Celery 설정:**
```
CELERY_BROKER_URL=${{REDIS_URL}}
CELERY_RESULT_BACKEND=${{REDIS_URL}}
CELERY_TIMEZONE=Asia/Seoul
```

**환경 설정:**
```
ENVIRONMENT=production
DEBUG=false
```

#### 3단계: 재배포 대기
환경 변수를 저장하면 Railway가 자동으로 재배포합니다.
약 1-2분 후 https://sem-agent.up.railway.app/health 에서 확인하세요.

---

## 배포 후 확인사항

### 1. 헬스 체크
```bash
curl https://sem-agent.up.railway.app/health
```
예상 응답:
```json
{"status":"healthy","environment":"production"}
```

### 2. Slack 이벤트 구독 설정
Slack App 설정 페이지에서:
1. **Event Subscriptions** 활성화
2. **Request URL**: `https://sem-agent.up.railway.app/slack/events`
3. URL 검증 성공 확인

### 3. Slack OAuth 리디렉션 URL 업데이트
Slack App 설정:
1. **OAuth & Permissions**
2. **Redirect URLs**: `https://sem-agent.up.railway.app/oauth/slack/callback` 추가

### 4. Google OAuth 리디렉션 URL 업데이트
Google Cloud Console:
1. API & Services → Credentials
2. OAuth 2.0 Client ID 선택
3. **Authorized redirect URIs**: `https://sem-agent.up.railway.app/oauth/google/callback` 추가

---

## 트러블슈팅

### 여전히 502 에러가 발생하는 경우

#### 로그 확인
```bash
railway logs --follow
```

#### 일반적인 원인:
1. **환경 변수 누락**: 모든 필수 변수가 설정되었는지 확인
2. **데이터베이스 미연결**: PostgreSQL, Redis 서비스가 추가되었는지 확인
3. **잘못된 변수 값**: 특수문자가 올바르게 이스케이프되었는지 확인

#### Railway 서비스 상태 확인
```bash
railway status
```

### 데이터베이스 연결 테스트
Railway 대시보드에서 PostgreSQL 서비스의 **Connect** 탭을 확인하여 `DATABASE_URL`이 올바르게 설정되었는지 확인하세요.

---

## 다음 단계

배포가 성공하면:
1. ✅ Slack 워크스페이스에 봇 초대
2. ✅ `/sem help` 명령어로 봇 테스트
3. ✅ Google Ads 계정 연동
4. ✅ 첫 리포트 생성 테스트
