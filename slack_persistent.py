import os
import sys
import time
import threading
import queue
import subprocess
import re
import uuid
import json
from pathlib import Path
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk import WebClient
from dotenv import load_dotenv

load_dotenv()

class ClaudePersistentBridge:
    def __init__(self, bot_token, app_token):
        self.web_client = WebClient(token=bot_token)
        self.socket_client = SocketModeClient(
            app_token=app_token,
            web_client=self.web_client
        )
        self.bot_user_id = None
        self.processed_messages = set()
        self.startup_time = time.time()
        
        # 세션 저장 파일 경로
        self.session_file = Path.home() / ".slack-claude-sessions.json"
        
        # 채널별 세션 관리 - 파일에서 로드
        self.load_sessions()
        self.channel_first_run = {}  # 채널별 첫 실행 여부
        
        # 현재 실행 중인 Claude 프로세스
        self.current_process = None
        self.process_lock = threading.Lock()
        
    def load_sessions(self):
        """저장된 세션 정보 로드"""
        self.channel_sessions = {}
        self.existing_claude_sessions = set()  # Claude가 실제로 알고 있는 세션들
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.channel_sessions = data
                print(f"[SESSION] Loaded {len(self.channel_sessions)} saved sessions")
            except Exception as e:
                print(f"[SESSION] Error loading sessions: {e}")
    
    def save_sessions(self):
        """세션 정보 저장"""
        try:
            with open(self.session_file, 'w') as f:
                json.dump(self.channel_sessions, f)
            print(f"[SESSION] Saved {len(self.channel_sessions)} sessions")
        except Exception as e:
            print(f"[SESSION] Error saving sessions: {e}")
    
    def kill_current_process(self):
        """현재 실행 중인 Claude 프로세스 강제 종료"""
        with self.process_lock:
            if self.current_process and self.current_process.poll() is None:
                print("[PROCESS] Killing current Claude process...")
                try:
                    self.current_process.terminate()
                    time.sleep(0.5)
                    if self.current_process.poll() is None:
                        self.current_process.kill()
                    print("[PROCESS] Claude process killed")
                except Exception as e:
                    print(f"[PROCESS] Error killing process: {e}")
                finally:
                    self.current_process = None
    
    def get_session_id_for_channel(self, channel_id):
        """채널 ID로부터 세션 ID 생성/조회"""
        if channel_id not in self.channel_sessions:
            # 채널 ID와 타임스탬프를 조합하여 고유한 세션 ID 생성
            # 이렇게 하면 재시작 시마다 새로운 세션 ID가 생성됨
            timestamp = str(int(time.time() * 1000))  # 밀리초 단위 타임스탬프
            unique_string = f"slack_channel_{channel_id}_{timestamp}"
            session_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_string))
            
            self.channel_sessions[channel_id] = session_id
            self.channel_first_run[channel_id] = True  # 새 세션은 첫 실행으로 표시
            self.save_sessions()  # 새 세션 저장
            print(f"[SESSION] Created unique session ID for channel {channel_id}: {session_id}")
        else:
            # 기존 세션이 있는 경우
            if channel_id not in self.channel_first_run:
                self.channel_first_run[channel_id] = False  # 이미 세션이 있으므로 첫 실행 아님
        
        return self.channel_sessions[channel_id]
    
    def run_claude_command(self, command, channel_id):
        """Claude 명령 실행 - 채널별 세션 유지"""
        try:
            # 환경변수 설정
            env = os.environ.copy()
            env.update({
                'FORCE_COLOR': '0',
                'NO_COLOR': '1',
                'PYTHONIOENCODING': 'utf-8',
                'LC_ALL': 'C.UTF-8',
                'LANG': 'ko_KR.UTF-8'
            })
            
            # PATH에서 Git Bash 제거
            if 'PATH' in env:
                paths = env['PATH'].split(os.pathsep)
                filtered_paths = [p for p in paths if 'Git' not in p and 'bash' not in p.lower()]
                env['PATH'] = os.pathsep.join(filtered_paths)
                
            env['COMSPEC'] = r'C:\Windows\System32\cmd.exe'
            
            # 채널별 세션 ID 가져오기
            session_id = self.get_session_id_for_channel(channel_id)
            is_first = self.channel_first_run.get(channel_id, True)
            
            # Claude 명령 실행 - 채널별 세션
            if is_first:
                # 첫 실행: 새 세션 시작
                cmd = f'claude --dangerously-skip-permissions --print --session-id {session_id} "{command}"'
                self.channel_first_run[channel_id] = False
                print(f"[SESSION] Starting new session for channel {channel_id}: {session_id}")
            else:
                # 이후 실행: 세션 재개
                cmd = f'claude --dangerously-skip-permissions --print --resume {session_id} "{command}"'
                print(f"[SESSION] Resuming session for channel {channel_id}: {session_id}")
            
            print(f"[CLAUDE CMD] Executing command:")
            print(f"[CLAUDE CMD] {cmd}")
            print(f"[CLAUDE CMD] Session UUID: {session_id}")
            print(f"[CLAUDE CMD] Channel ID: {channel_id}")
            print(f"[CLAUDE CMD] Is first run: {is_first}")
            
            # Windows 콘솔 코드 페이지를 UTF-8로 설정
            chcp_cmd = f'chcp 65001 > nul && {cmd}'
            
            # 프로세스 실행 및 추적 (바이트 모드로 실행 후 수동 디코딩)
            with self.process_lock:
                self.current_process = subprocess.Popen(
                    chcp_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,  # 바이트 모드
                    env=env,
                    shell=True,
                    executable=r'C:\Windows\System32\cmd.exe'
                )
            
            try:
                stdout_bytes, stderr_bytes = self.current_process.communicate(timeout=600)
                
                # 바이트를 문자열로 디코딩 (UTF-8 우선, 실패시 CP949)
                def decode_output(data):
                    if not data:
                        return ""
                    try:
                        return data.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            return data.decode('cp949')
                        except:
                            return data.decode('utf-8', errors='replace')
                
                stdout = decode_output(stdout_bytes)
                stderr = decode_output(stderr_bytes)
                
                result = type('Result', (), {
                    'returncode': self.current_process.returncode,
                    'stdout': stdout,
                    'stderr': stderr
                })()
            except subprocess.TimeoutExpired:
                self.kill_current_process()
                return "Command timed out (600s)"
            finally:
                with self.process_lock:
                    self.current_process = None
            
            print(f"[SUBPROCESS] Return code: {result.returncode}")
            stdout_safe = result.stdout if result.stdout else "(empty)"
            stderr_safe = result.stderr if result.stderr else "(empty)"
            
            print(f"[SUBPROCESS] stdout: {stdout_safe[:500]}{'...' if len(stdout_safe) > 500 else ''}")
            print(f"[SUBPROCESS] stderr: {stderr_safe[:500]}{'...' if len(stderr_safe) > 500 else ''}")
            
            # 세션이 없는 경우 처리
            if (("Execution error" in stdout_safe or 
                 "No conversation found with session ID" in stderr_safe) 
                and is_first == False):
                print(f"[SESSION] Session {session_id} not found in Claude, creating new session...")
                # 새 세션으로 재시도
                self.channel_first_run[channel_id] = True
                # 기존 세션 ID는 유지하되 첫 실행으로 표시
                return self.run_claude_command(command, channel_id)
            
            # 세션이 성공적으로 생성/사용된 경우 기록
            if result.returncode == 0 and "Execution error" not in stdout_safe:
                print(f"[SESSION] Session {session_id} successfully created/used")
            
            # 세션 ID 충돌 처리
            if result.returncode != 0 and "Session ID" in stderr_safe and "is already in use" in stderr_safe:
                print(f"[SESSION] Session ID {session_id} is already in use, regenerating...")
                # 기존 세션 정보 삭제하고 새로 생성
                if channel_id in self.channel_sessions:
                    del self.channel_sessions[channel_id]
                if channel_id in self.channel_first_run:
                    del self.channel_first_run[channel_id]
                self.save_sessions()
                # 재시도
                return self.run_claude_command(command, channel_id)
            
            if result.returncode == 0:
                output = (result.stdout or "").strip()
                if not output:
                    return "Command executed successfully (no output)"
                    
                # ANSI 코드 제거
                clean_output = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', output)
                
                # 불필요한 메시지 제거
                lines = clean_output.split('\n')
                filtered_lines = []
                
                for line in lines:
                    line = line.strip()
                    if line and not any(skip in line for skip in [
                        "Welcome to Claude",
                        "/help for help",
                        "cwd:",
                        "Tips for getting",
                        "? for shortcuts"
                    ]):
                        filtered_lines.append(line)
                
                return '\n'.join(filtered_lines) if filtered_lines else "Command executed successfully (no output)"
            else:
                stderr_msg = (result.stderr or "Unknown error").strip()
                return f"Error: {stderr_msg}"
                
        except subprocess.TimeoutExpired:
            return "Command timed out (600s)"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def send_to_claude(self, text, channel_id):
        """Claude에 명령 전송"""
        try:
            print(f"\n[RECEIVED] Channel: {channel_id}, Message: {text}")
            
            # 처리 중 메시지
            processing_msg = "Processing..."
            print(f"[SLACK SEND] {processing_msg}")
            self.web_client.chat_postMessage(
                channel=channel_id,
                text=processing_msg,
                username="Claude Bot"
            )
            
            # Claude 실행 - 채널 ID 전달
            print(f"[CLAUDE EXEC] Running command: {text}")
            response = self.run_claude_command(text, channel_id)
            print(f"[CLAUDE RESPONSE] {response[:200]}{'...' if len(response) > 200 else ''}")
            
            # 응답 전송
            if len(response) > 3000:
                chunks = [response[i:i+3000] for i in range(0, len(response), 3000)]
                for i, chunk in enumerate(chunks):
                    chunk_msg = f"```\n{chunk}\n``` ({i+1}/{len(chunks)})"
                    print(f"[SLACK SEND] Chunk {i+1}/{len(chunks)}: {len(chunk)} chars")
                    self.web_client.chat_postMessage(
                        channel=channel_id,
                        text=chunk_msg,
                        username="Claude Bot"
                    )
            else:
                response_msg = f"```\n{response}\n```"
                print(f"[SLACK SEND] Response: {len(response)} chars")
                self.web_client.chat_postMessage(
                    channel=channel_id,
                    text=response_msg,
                    username="Claude Bot"
                )
                
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(f"[SLACK SEND] {error_msg}")
            
            if "channel_not_found" not in str(e):
                try:
                    self.web_client.chat_postMessage(
                        channel=channel_id,
                        text=error_msg
                    )
                except:
                    print("[ERROR] Failed to send error message to Slack")
    
    def handle_message(self, client, req):
        if req.type == "events_api":
            if not req.payload:
                client.ack(req)
                return
            event = req.payload.get("event", {})
            
            print(f"\n[EVENT] type={event.get('type')}, user={event.get('user')}, bot_id={event.get('bot_id')}, channel={event.get('channel')}")
            
            if event.get("type") == "message":
                # 봇 메시지 무시
                if event.get("bot_id") or event.get("user") == self.bot_user_id:
                    print(f"[BOT MESSAGE IGNORED] bot_id={event.get('bot_id')}, user={event.get('user')}")
                    client.ack(req)
                    return
                    
                # subtype 체크
                if event.get("subtype") in ["bot_message", "message_changed", "message_deleted"]:
                    print(f"[SUBTYPE IGNORED] {event.get('subtype')}")
                    client.ack(req)
                    return
                
                # 중복 확인
                msg_id = f"{event.get('channel')}_{event.get('ts')}"
                if msg_id in self.processed_messages:
                    print(f"[DUPLICATE MESSAGE] {msg_id}")
                    client.ack(req)
                    return
                
                self.processed_messages.add(msg_id)
                print(f"[NEW MESSAGE] {msg_id}")
                
                # 메시지 처리
                text = event.get("text", "").strip()
                channel_id = event.get("channel", "")
                
                # 시스템 메시지 필터링
                if not channel_id or not text:
                    return
                    
                if any(keyword in text for keyword in [
                    "퇴장되었습니다",
                    "has been removed",
                    "was added to",
                    "joined the channel",
                    "left the channel"
                ]):
                    print(f"[SYSTEM MESSAGE IGNORED] {text[:50]}...")
                    return
                
                # ESC 명령 처리
                if text.upper() in ['ESC', 'ESCAPE', '에스여이피', '취소', 'CANCEL']:
                    print("[ESC COMMAND] Cancelling current operation...")
                    self.kill_current_process()
                    self.web_client.chat_postMessage(
                        channel=channel_id,
                        text="❌ Current operation cancelled. Session preserved.",
                        username="Claude Bot"
                    )
                    return
                
                if text:
                    # 스레드로 비동기 처리
                    threading.Thread(
                        target=self.send_to_claude, 
                        args=(text, channel_id), 
                        daemon=True
                    ).start()
        
        client.ack(req)

def main():
    """Main entry point"""
    bridge = ClaudePersistentBridge(
        bot_token=os.getenv("SLACK_BOT_TOKEN"),
        app_token=os.getenv("SLACK_APP_TOKEN")
    )
    
    try:
        # 봇 정보
        try:
            auth_test = bridge.web_client.auth_test()
            if auth_test and "user_id" in auth_test:
                bridge.bot_user_id = auth_test["user_id"]
                print(f"Connected as: {auth_test.get('user', 'Unknown')} (ID: {bridge.bot_user_id})")
            else:
                print(f"Failed to get bot info from Slack: auth_test is {auth_test}")
                sys.exit(1)
        except Exception as e:
            print(f"Failed to get bot info from Slack: {e}")
            sys.exit(1)
        
        print("\nClaude PERSISTENT bridge ready!")
        print("Each channel will have its own persistent session!")
        print("Context WILL BE preserved between commands using channel-based session IDs")
        
        # Socket Mode 연결
        bridge.socket_client.socket_mode_request_listeners.append(bridge.handle_message)
        bridge.socket_client.connect()
        
        print("\nBot is running... Press Ctrl+C to stop")
        
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()