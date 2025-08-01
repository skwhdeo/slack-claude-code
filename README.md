# Slack-Claude Code Bridge

Windows에서 Slack을 통해 Claude Code와 대화하는 브릿지 프로그램입니다.

> 🤖 This project and README were created using [Claude Code](https://claude.ai/code)

## 특징

- 채널별 영구 세션 지원 (각 채널이 독립적인 컨텍스트 유지)
- Windows 환경에 최적화 (UTF-8 한글 지원)
- 자동 세션 복구 기능
- ESC 명령으로 실행 중인 작업 취소 가능
- 시스템 메시지 필터링

## 설치

### 1. 필수 패키지 설치
```bash
pip install slack-sdk python-dotenv
```

### 2. 환경 변수 설정

`.env.example`을 복사하여 `.env` 파일을 생성하고 토큰을 입력합니다:

```bash
cp .env.example .env
```

`.env` 파일 내용:
```
SLACK_BOT_TOKEN=xoxb-로 시작하는 Bot User OAuth Token
SLACK_APP_TOKEN=xapp-로 시작하는 App-Level Token
```

## Slack 앱 설정

1. [Slack API Apps](https://api.slack.com/apps)에서 새 앱 생성
2. **Socket Mode** 활성화 (Settings > Socket Mode)
3. **Bot Token Scopes** 추가:
   - `app_mentions:read`
   - `channels:history`
   - `chat:write`
   - `im:history`
4. **Event Subscriptions** 활성화하고 이벤트 추가:
   - `message.channels`
   - `message.im`
5. 앱을 워크스페이스에 설치
6. 채널에 봇 초대: `/invite @봇이름`

## 실행

```bash
python slack_persistent.py
```

성공적으로 시작되면:
```
Connected as: [Bot Name]

Claude PERSISTENT bridge ready!
Each channel will have its own persistent session!
Context WILL BE preserved between commands using channel-based session IDs

Bot is running... Press Ctrl+C to stop
```

## 사용법

Slack 채널에서 메시지를 보내면 Claude Code가 응답합니다.

### 예시
```
pwd
ls
create a hello world python script
너는 누구니?
```

### 작업 취소 명령
실행 중인 작업을 중단하려면 다음 중 하나를 입력:
- `ESC`
- `ESCAPE`
- `취소`
- `CANCEL`

세션은 유지되며 현재 실행 중인 작업만 중단됩니다.

## 주의사항

- **채널별 독립 세션**: 각 채널이 독립적인 컨텍스트를 유지합니다
- **응답 시간**: 명령 처리에 수 초 소요될 수 있습니다
- **봇 중복 실행 방지**: 하나의 인스턴스만 실행하세요
- **세션 관리**: 세션 정보는 `~/.slack-claude-sessions.json`에 저장됩니다

## 문제 해결

### 인코딩 오류
```
UnicodeDecodeError: 'cp949' codec can't decode...
```
→ 최신 버전은 UTF-8을 강제 설정하여 해결됨

### 봇 중복 실행 문제
```bash
# 모든 Python 프로세스 종료
taskkill /F /IM python.exe

# 하나만 실행
python slack_persistent.py
```

### Claude 실행 확인
```bash
claude --version
```

### Slack 토큰 확인
`.env` 파일의 토큰이 올바른지 확인:
- Bot User OAuth Token: `xoxb-`로 시작
- App-Level Token: `xapp-`로 시작

## 로그 설명

- `[RECEIVED]`: Slack에서 받은 메시지
- `[SLACK SEND]`: Slack으로 보내는 메시지
- `[CLAUDE EXEC]`: Claude 실행 명령
- `[SUBPROCESS]`: 프로세스 실행 결과
- `[ERROR]`: 오류 발생
- `[BOT MESSAGE IGNORED]`: 봇 자신의 메시지 무시
- `[SYSTEM MESSAGE IGNORED]`: 시스템 메시지 무시

---

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>