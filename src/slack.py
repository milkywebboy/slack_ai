import json
import os
import zipfile

# 設定
zip_path = 'slack_export.zip'
extract_dir = 'slack_export'
output_file = 'finetune_chat.jsonl'
your_user_id = "U03RHU7RP"  # 例: "U12345678"
your_mention = f"<@{your_user_id}>"

# ZIPファイルを解凍
with zipfile.ZipFile(zip_path, 'r') as z:
    z.extractall(extract_dir)

# 全メッセージを収集
all_messages = []
for root, dirs, files in os.walk(extract_dir):
    for file in files:
        if file.endswith('.json'):
            file_path = os.path.join(root, file)
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except Exception:
                    continue
                if isinstance(data, list):
                    for m in data:
                        if isinstance(m, dict):
                            all_messages.append(m)

# タイムスタンプ順にソート
all_messages.sort(key=lambda m: float(m.get("ts", "0")))

# チャット形式（"messages"リスト）としてjsonl出力
with open(output_file, 'w', encoding='utf-8') as out_f:
    i = 0
    while i < len(all_messages):
        msg = all_messages[i]
        sender = msg.get("user", "")
        text = msg.get("text", "").strip()
        
        # 他ユーザーからの「私宛」メッセージ（あなたへのメンションが含まれる場合）をユーザ発話として扱う
        if sender != your_user_id and your_mention in text:
            prompt_text = text
            i += 1
            # 連続する他ユーザーからの私宛メッセージを結合
            while i < len(all_messages):
                next_msg = all_messages[i]
                if next_msg.get("user", "") != your_user_id and your_mention in next_msg.get("text", ""):
                    prompt_text += "\n" + next_msg.get("text", "").strip()
                    i += 1
                else:
                    break
            # 直後の私からの返信をassistant発話とする
            if i < len(all_messages) and all_messages[i].get("user", "") == your_user_id:
                assistant_text = all_messages[i].get("text", "").strip()
                chat_obj = {
                    "messages": [
                        {"role": "user", "content": prompt_text},
                        {"role": "assistant", "content": assistant_text}
                    ]
                }
                out_f.write(json.dumps(chat_obj, ensure_ascii=False) + "\n")
                i += 1
            else:
                # 返信がない場合はスキップ（もしくは補完する方法も検討可能）
                continue
        # 私からの単独メッセージの場合（前にユーザ発話がない）
        elif sender == your_user_id:
            assistant_text = text
            chat_obj = {
                "messages": [
                    {"role": "user", "content": ""},  # ユーザー発話は空文字
                    {"role": "assistant", "content": assistant_text}
                ]
            }
            out_f.write(json.dumps(chat_obj, ensure_ascii=False) + "\n")
            i += 1
        else:
            i += 1