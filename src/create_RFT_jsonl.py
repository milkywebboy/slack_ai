#!/usr/bin/env python3
"""
Slack エクスポート JSON ファイルから RFT 用の JSONL ファイルを生成するスクリプト
生成形式: 各行が以下の JSON オブジェクトとなる
{
  "messages": [{"role": "user", "content": "質問文"}],
  "compliant": "yes",
  "explanation": "回答文"
}
使い方:
  python generate_rft_jsonl.py \
    --input_dir ./slack_export \
    --user_id U12345678 \
    --output_file rft_data.jsonl
"""
import os
import json
import glob
import argparse

def main():
    parser = argparse.ArgumentParser(
        description="Slack JSON から RFT 用 JSONL を生成"
    )
    parser.add_argument(
        "--input_dir", required=True,
        help="Slack JSON ファイルが格納されたディレクトリ"
    )
    parser.add_argument(
        "--user_id", required=True,
        help="自分の Slack ユーザー ID (例: U12345678)"
    )
    parser.add_argument(
        "--output_file", required=True,
        help="出力する JSONL ファイルのパス"
    )
    args = parser.parse_args()

    input_dir = args.input_dir
    my_id = args.user_id
    output_file = args.output_file

    parent_msgs = {}
    thread_replies = {}

    for filepath in glob.glob(os.path.join(input_dir, "**", "*.json"), recursive=True):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"{filepath} の読み込みエラー: {e}")
                continue
        if not isinstance(data, list):
            continue
        for msg in data:
            if not isinstance(msg, dict):
                continue
            text = msg.get("text")
            user = msg.get("user")
            if not text or not user:
                continue
            ts = msg.get("ts")
            thread_ts = msg.get("thread_ts", ts)
            if ts == thread_ts:
                parent_msgs[thread_ts] = msg
            else:
                thread_replies.setdefault(thread_ts, []).append(msg)

    with open(output_file, "w", encoding="utf-8") as out_f:
        # 他ユーザーからの質問 → 自分の返信
        for thread_ts, parent in parent_msgs.items():
            if parent.get("user") == my_id:
                continue
            question = parent.get("text", "").strip()
            if not question.endswith(("?", "？")):
                continue
            replies = sorted(thread_replies.get(thread_ts, []), key=lambda x: x.get("ts"))
            answer = next((r for r in replies if r.get("user") == my_id), None)
            if not answer:
                continue
            item = {
                "messages": [{"role": "user", "content": question}],
                "compliant": "yes",
                "explanation": answer.get("text", "").strip()
            }
            out_f.write(json.dumps(item, ensure_ascii=False) + "\n")

        # 自分自身の投稿
        for msg in parent_msgs.values():
            if msg.get("user") != my_id:
                continue
            text = msg.get("text", "").strip()
            item = {
                "messages": [{"role": "user", "content": text}],
                "compliant": "yes",
                "explanation": text
            }
            out_f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"完了: {output_file} に出力しました。")

if __name__ == "__main__":
    main()
