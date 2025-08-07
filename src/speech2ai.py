import os
import json
import time
import threading
import pyaudio
import websocket
import base64
import requests
import numpy as np
import struct

# --- 送信用関数 ---
def send_audio_message(ws, audio_data):
    encoded = base64.b64encode(audio_data).decode("utf-8")
    msg = {
        "type": "input_audio_buffer.append",
        "audio": encoded
    }
    ws.send(json.dumps(msg))
    # print("送信: チャンクサイズ", len(audio_data))  # デバッグログ（コメントアウト）

def send_commit(ws):
    msg = {"type": "input_audio_buffer.commit"}
    try:
        ws.send(json.dumps(msg))
        # print("コミットメッセージ送信")  # デバッグログ（コメントアウト）
    except Exception as e:
        print("Commit送信時のエラー（接続閉鎖のため無視）:", e)

# --- REST APIで転写セッション作成 ---
def create_transcription_session(api_key):
    url = "https://api.openai.com/v1/realtime/transcription_sessions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "OpenAI-Beta": "realtime"
    }
    payload = {
        "input_audio_transcription": {
            "model": "gpt-4o-mini-transcribe",
            "language": "ja"
        },
        "turn_detection": {
            "type": "server_vad",
            "silence_duration_ms": 1000
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print("セッション作成エラー:", response.status_code, response.text)
        return None
    data = response.json()
    session_id = data.get("id")
    client_secret = data.get("client_secret")
    print("セッション作成成功。ID:", session_id)
    return session_id, client_secret

# --- WebSocket受信ハンドラ ---
transcription_result = ""

def on_message(ws, message):
    global transcription_result
    try:
        data = json.loads(message)
        event_type = data.get("type", "")
        if event_type == "conversation.item.input_audio_transcription.completed":
            transcription_result = data.get("transcript", "")
            print("最終結果:", transcription_result)
        # else:
            # print("受信:", data)  # デバッグログ（コメントアウト）
    except Exception as e:
        print("メッセージ解析エラー:", e)

def on_error(ws, error):
    print("WebSocketエラー:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket接続終了:", close_status_code, close_msg)

# --- 話者識別（簡易版） ---
def perform_speaker_diarization(audio_chunks):
    try:
        import librosa
        from sklearn.cluster import KMeans
    except ImportError:
        print("librosa と scikit-learn をインストールしてください。")
        return None
    # すべてのチャンクを連結して1次元のfloat32配列に変換
    audio_bytes = b"".join(audio_chunks)
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    sr = 16000  # 送信したサンプリングレート
    # 正規化
    audio_np = audio_np / 32768.0
    # 1秒毎に区切る
    frame_length = sr
    n_frames = int(np.ceil(len(audio_np) / frame_length))
    features = []
    segments = []
    for i in range(n_frames):
        start = i * frame_length
        end = min((i+1) * frame_length, len(audio_np))
        frame = audio_np[start:end]
        if len(frame) < 0.5 * frame_length:
            continue
        mfcc = librosa.feature.mfcc(y=frame, sr=sr, n_mfcc=13)
        mfcc_mean = np.mean(mfcc, axis=1)
        features.append(mfcc_mean)
        segments.append((start/sr, end/sr))
    if len(features) == 0:
        return None
    features = np.array(features)
    # 話者数は仮に2とする（必要に応じて変更）
    k = 2
    kmeans = KMeans(n_clusters=k, random_state=0).fit(features)
    labels = kmeans.labels_
    diarization = []
    for seg, label in zip(segments, labels):
        diarization.append((seg[0], seg[1], f"Speaker {label+1}"))
    return diarization

# --- WebSocket接続後、音声データ送信 ---
# session_audio には送信した音声データのリストを保存
session_audio = []

def on_open(ws):
    def run_audio():
        global session_audio
        p = pyaudio.PyAudio()
        try:
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                            input=True, frames_per_buffer=1024)
        except Exception as e:
            print("マイクストリームオープンエラー:", e)
            return

        # セッション更新メッセージ送信
        update_msg = {
            "type": "transcription_session.update",
            "session": {
                "input_audio_transcription": {
                    "model": "gpt-4o-mini-transcribe",
                    "language": "ja"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "silence_duration_ms": 1000
                }
            }
        }
        ws.send(json.dumps(update_msg))
        # print("セッション更新メッセージ送信")  # コメントアウト

        # 固定録音期間（例：10秒）分、音声チャンクをJSON形式で送信
        RECORD_SECONDS = 10
        start_time = time.time()
        chunk_counter = 0
        session_audio = []
        while time.time() - start_time < RECORD_SECONDS:
            try:
                data = stream.read(1024, exception_on_overflow=False)
                chunk_counter += 1
                session_audio.append(data)
                send_audio_message(ws, data)
                # print(f"チャンク {chunk_counter}: {len(data)} バイト送信")  # コメントアウト
            except Exception as e:
                print("オーディオ送信エラー:", e)
                break
            time.sleep(0.01)
        total_audio = b"".join(session_audio)
        duration_sec = len(total_audio) / (16000 * 2.0)
        print(f"送信済み音声の合計録音時間: {duration_sec:.3f}秒")
        if duration_sec < 0.1:
            extra_samples = int((0.1 - duration_sec) * 16000)
            extra_bytes = extra_samples * 2
            extra_silence = b"\x00" * extra_bytes
            send_audio_message(ws, extra_silence)
            print(f"追加で{extra_bytes}バイトの無音を送信してコミット条件を満たしました。")
        if ws.sock and ws.sock.connected:
            send_commit(ws)
        else:
            print("接続は既に閉じています。コミット送信をスキップします。")
        stream.stop_stream()
        stream.close()
        p.terminate()
    threading.Thread(target=run_audio, daemon=True).start()

# --- 音声入力待機 ---
def wait_for_speech():
    print("音声入力待機中...")
    p = pyaudio.PyAudio()
    try:
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                        input=True, frames_per_buffer=1024)
    except Exception as e:
        print("音声入力ストリームオープンエラー:", e)
        return False
    detected = False
    while not detected:
        try:
            data = stream.read(1024, exception_on_overflow=False)
        except Exception as e:
            continue
        audio_array = np.frombuffer(data, dtype=np.int16)
        rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2))
        if rms > 100:
            detected = True
        else:
            time.sleep(0.1)
    stream.stop_stream()
    stream.close()
    p.terminate()
    print("音声検出、セッションを開始します。")
    return True

# --- メインループ ---
def main():
    global transcription_result, session_audio
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("APIキーが設定されていません。")
        return

    # REST APIで転写セッション作成
    session_info = create_transcription_session(openai_api_key)
    if session_info is None:
        return
    session_id, ephemeral_token = session_info
    if isinstance(ephemeral_token, dict):
        ephemeral_token = ephemeral_token.get("value", "")
    if not ephemeral_token:
        print("エフェメラルトークンの取得に失敗しました。")
        return

    ws_url = "wss://api.openai.com/v1/realtime"
    headers = [
        f"Authorization: Bearer {ephemeral_token}",
        "OpenAI-Beta: realtime=v1"
    ]
    
    while True:
        if not wait_for_speech():
            break
        transcription_result = ""
        print("会話セッション開始")
        ws = websocket.WebSocketApp(ws_url,
                                    header=headers,
                                    on_open=on_open,
                                    on_message=on_message,
                                    on_error=on_error,
                                    on_close=on_close)
        ws.run_forever()
        if transcription_result:
            print("\n=== 会話セグメント ===")
            print(transcription_result)
            print("======================\n")
        else:
            print("会話セグメントはありませんでした。")
        # 話者識別を実施
        diarization = perform_speaker_diarization(session_audio)
        if diarization:
            print("\n=== 話者識別結果 ===")
            for seg in diarization:
                print(f"{seg[0]:.2f}秒～{seg[1]:.2f}秒: {seg[2]}")
            print("======================\n")
        else:
            print("話者識別結果は得られませんでした。")
        time.sleep(0.5)

# --- 簡易話者識別 ---
def perform_speaker_diarization(audio_chunks):
    try:
        import librosa
        from sklearn.cluster import KMeans
    except ImportError:
        print("librosa と scikit-learn をインストールしてください。")
        return None
    audio_data = b"".join(audio_chunks)
    audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
    sr = 16000
    # 正規化
    audio_np = audio_np / 32768.0
    frame_length = sr  # 1秒分
    n_frames = int(np.ceil(len(audio_np) / frame_length))
    features = []
    segments = []
    for i in range(n_frames):
        start = i * frame_length
        end = min((i+1)*frame_length, len(audio_np))
        frame = audio_np[start:end]
        if len(frame) < 0.5 * frame_length:
            continue
        mfcc = librosa.feature.mfcc(y=frame, sr=sr, n_mfcc=13)
        mfcc_mean = np.mean(mfcc, axis=1)
        features.append(mfcc_mean)
        segments.append((start/sr, end/sr))
    if len(features) == 0:
        return None
    features = np.array(features)
    k = 2
    kmeans = KMeans(n_clusters=k, random_state=0).fit(features)
    labels = kmeans.labels_
    diarization = []
    for seg, label in zip(segments, labels):
        diarization.append((seg[0], seg[1], f"Speaker {label+1}"))
    return diarization

if __name__ == "__main__":
    main()
