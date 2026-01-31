# PRD: SEM (Search Advertising AI Agent) for Slack

**Version:** 1.1.0
**Status:** Approved (Option B: Human-in-the-Loop + Weekly Default + Gemini Powered)
**Author:** PRD Jem (Senior PM)

---

## 1. Problem Statement & Goals

### 1.1 Problem
- **데이터 과부하 & 알림 피로:** 매일 확인하기 부담스러운 지표들은 오히려 무시되기 쉬움.
- **예산 누수 방치:** 성과가 없는 검색어(Low Efficiency Keywords)를 적시에 발견하지 못함.
- **실행 지연:** 문제 발견 후 조치(제외 키워드 등록)를 위해 별도 웹사이트 로그인 필요.

### 1.2 Goals
- **접근성 & 유연성:** 슬랙에서 데이터 조회 및 리포팅 주기를 사용자 입맛대로 설정 가능.
- **맥락 있는 인사이트:** Gemini를 활용하여 단순 수치 나열이 아닌, 변화의 원인을 설명하는 자연어 브리핑 제공.
- **안정적 자동화:** AI가 감지하고 인간이 승인하는 프로세스.

---

## 2. Target User

- **Primary:** 구글 검색 광고를 직접 운영하며, 핵심적인 변화 흐름을 놓치고 싶지 않은 마케터.
- **Needs:** 매주 월요일 한 주간의 성과 정리, 수시로 발생하는 비효율 키워드 즉각 차단.

---

## 3. User Stories & Acceptance Criteria

### [Epic 1] 온보딩 및 계정 연동 (Onboarding)

**Story 1.1:** 사용자는 슬랙 채널에 봇을 초대한 후, 구글 애즈 계정을 연동해야 한다.

**Flow:**
1. 봇 초대 및 OAuth2 인증 진행.
2. 광고 계정 선택 완료 시 기본 설정 적용.
3. **Success Message:** "세팅 완료! 📅 **매주 월요일 오전 9시**에 주간 리포트가 발송됩니다."
4. 메시지 하단에 `[리포트 주기 변경하기]` 버튼 즉시 노출.

**Acceptance Criteria:**
- [ ] AC1.1.1: OAuth 완료 후 60초 이내에 환영 메시지 발송
- [ ] AC1.1.2: 환영 메시지에 `[리포트 주기 변경하기]` 버튼 포함
- [ ] AC1.1.3: 기본 설정 = 주간 리포트, 월요일 09:00 KST
- [ ] AC1.1.4: OAuth 실패/거부 시 명확한 오류 메시지 제공
- [ ] AC1.1.5: 이미 연동된 계정 재연동 시 기존 설정 유지

---

### [Epic 2] 데이터 분석 및 리포팅 (Reporting & Configuration)

**Story 2.1:** 시스템은 기본적으로 주간 리포트를 발송하며, Gemini가 분석한 인사이트를 포함한다.

- **Default Schedule:** 매주 월요일 09:00 KST
- **Content:** 지난주(월~일) 성과 요약
- **AI Analysis (Gemini):**
  - 단순 증감률 표기를 넘어, Gemini에게 수치 데이터를 프롬프트로 전달하여 3줄 요약 코멘트 생성.
  - 예: "전주 대비 전환율이 2% 상승했습니다. 특히 '모바일' 기기에서의 효율 개선이 주된 원인으로 보입니다."

**Acceptance Criteria:**
- [ ] AC2.1.1: 리포트에 비용, 전환, ROAS 포함
- [ ] AC2.1.2: 전주 대비 변화율 표시 (🔺/🔻 이모지)
- [ ] AC2.1.3: Gemini 인사이트 3문장 이내
- [ ] AC2.1.4: 리포트 생성 30초 이내 완료
- [ ] AC2.1.5: 한국어로 렌더링

**Story 2.2:** 사용자는 자동 리포팅 주기를 조회하고 수정할 수 있어야 한다.

- **Trigger:** 슬랙 명령어 `/sem-config` 또는 설정 버튼 클릭.
- **UI (Modal):**
  - **리포트 주기 설정:** [매일 / 매주(Default) / 매월 / 끄기] 라디오 버튼 선택.
  - **발송 시간 설정:** [09:00 / 14:00 / 18:00] 등 시간 선택.
- **Outcome:** 설정 저장 시 즉시 DB(Scheduler)에 반영되고 확인 메시지 발송.

**Acceptance Criteria:**
- [ ] AC2.2.1: `/sem-config` 입력 시 설정 모달 표시
- [ ] AC2.2.2: 주기 변경 즉시 스케줄러에 반영
- [ ] AC2.2.3: 변경 확인 메시지 발송

**Story 2.3:** 사용자는 필요시 즉시(On-demand) 리포트를 요청할 수 있다.

- **Interaction:** `/sem-report` 입력 시 기간 선택(어제/지난주/커스텀) 후 즉시 응답.

**Acceptance Criteria:**
- [ ] AC2.3.1: `/sem-report` 입력 시 기간 선택 모달 표시
- [ ] AC2.3.2: 선택 후 60초 이내 리포트 발송

---

### [Epic 3] 검색어 제외 최적화 (Optimization)

**Story 3.1:** 시스템은 비효율 검색어를 감지하여 사용자 승인 하에 제외 처리한다.

- **Logic:** 주기적 모니터링 (예: 1시간 간격)
- **Interaction:**
  - 봇: "🚨 비효율 검색어 감지: '무료 다운로드' (비용: 15,000원, 전환: 0)"
  - 버튼: **`[🚫 제외 키워드 등록]`**, **`[👀 무시하기]`**
- **Action:** `[제외 키워드 등록]` 클릭 시 API 호출로 즉시 제외 반영.

**Acceptance Criteria:**
- [ ] AC3.1.1: 비효율 키워드 감지 시 슬랙 알림 발송
- [ ] AC3.1.2: 알림에 비용, 전환 수 포함
- [ ] AC3.1.3: `[제외 키워드 등록]` 클릭 시 Google Ads에 즉시 반영
- [ ] AC3.1.4: `[무시하기]` 클릭 시 해당 키워드 24시간 재알림 제외
- [ ] AC3.1.5: 승인 요청 24시간 후 자동 만료
- [ ] AC3.1.6: 모든 승인/거부 기록 감사 로그 저장

---

## 4. Functional Requirements

### 4.1 Data & AI
- **Google Ads API:** `GoogleAdsService.SearchStream`, `CampaignCriterionService`
- **AI Model:** **Google Gemini Pro (via Vertex AI or AI Studio API)**
  - 역할: 리포트 생성 시 원본 데이터(JSON)를 입력받아 자연어 인사이트(Summary Text) 생성
- **Slack API:** Block Kit (Modal for Settings, Buttons for Actions)

### 4.2 System Logic
- **Dynamic Scheduler:** 사용자별 설정(Daily/Weekly)을 DB에서 읽어와 유동적으로 작업을 수행하는 스케줄러 구현 필요 (Cron 표현식을 DB에 저장하여 관리)

---

## 5. UI/UX Guidelines

### 5.1 Weekly Report Card (with Gemini)
```
[Header] 📅 [지난주] 주간 성과 리포트 (W3 May)
[Section 1: Key Metrics]
• 비용: ₩1,050,000 (🔺5%)
• 전환: 85건 (🔺12%)
• ROAS: 410% (🔺+20%p)
---------------------------------------------
[Section 2: Gemini Insight 🧠]
"전반적으로 효율이 개선된 한 주였습니다.
 1. CPC가 소폭 상승했으나, 전환율(CVR) 상승폭이 더 커서 ROAS가 개선되었습니다.
 2. 주말보다 평일 오후 시간대 효율이 좋았습니다."
---------------------------------------------
[Actions] [상세 보기] [설정 변경]
```

### 5.2 Negative Keyword Alert
```
🚨 비효율 검색어 감지

키워드: "무료 다운로드"
캠페인: 브랜드 캠페인
비용: ₩15,000
클릭: 25회
전환: 0건

[🚫 제외 키워드 등록]  [👀 무시하기]
```

---

## 6. Tech Stack Recommendation

| Component | Technology | Rationale |
|-----------|------------|-----------|
| LLM | Google Gemini 1.5 Flash/Pro | JSON 데이터 분석 및 요약에 탁월 |
| Backend | Python (FastAPI) | 비동기 처리, 타입 힌트 지원 |
| Database | PostgreSQL | 사용자 설정 저장, JSONB 지원 |
| Scheduling | Celery Beat | 동적 스케줄링 지원 우수 |
| Cache | Redis | 세션, 캐시, Celery 브로커 |

---

## 7. Design Decisions

### 7.1 Option A vs B vs C (Historical)

| Option | Description | Decision |
|--------|-------------|----------|
| A | 완전 자동화 (AI가 자동으로 키워드 제외) | Rejected - 리스크 높음 |
| **B** | **Human-in-the-Loop (AI 감지 + 사용자 승인)** | **Selected** |
| C | 리포트만 제공 (키워드 제외 기능 없음) | Rejected - 가치 부족 |

### 7.2 Rationale for Option B
1. **안전성:** 광고 예산 관련 변경은 사용자 승인 필수
2. **신뢰 구축:** AI 추천의 정확도를 사용자가 직접 검증
3. **법적 책임:** 자동 조치로 인한 손실 책임 회피

---

## 8. Constraints

### 8.1 Scope Boundaries (V1)

**In Scope:**
- 단일 Google Ads 계정 연동 (멀티 계정은 V2)
- 주간 리포트 기본 (일간/월간 선택 가능)
- 제외 키워드 자동화 (승인 필수)
- 한국어 UI/메시지

**Out of Scope (V2+):**
- 멀티 Google Ads 계정
- 입찰 자동 조정
- 광고 문구 생성
- Microsoft/Meta Ads 연동

### 8.2 Technical Constraints
- **Google Ads API:** 일일 15,000 요청 기본 쿼터
- **Gemini API:** 60 RPM (Flash), 10 RPM (Pro)
- **Slack API:** 초당 1메시지 per 채널

---

## 9. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| 온보딩 완료율 | > 80% | OAuth 시작 → 완료 |
| 주간 리포트 열람률 | > 60% | Slack 메시지 읽음 |
| 키워드 승인 응답 시간 | < 4시간 | 알림 → 결정 |
| 비효율 키워드 제거로 인한 비용 절감 | > 10% | 월간 비용 비교 |

---

## 10. Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| 멀티 계정 지원? | V1은 단일 계정, V2에서 지원 |
| 타임존 처리? | 사용자 설정 타임존 (기본 KST) |
| 승인 만료 시간? | 24시간 후 자동 만료 (무시 처리) |
| Gemini 예산? | 월 $100 (Flash 기본, Pro는 월간 리포트만) |
| GDPR? | V1은 한국 대상, GDPR은 V2에서 고려 |
