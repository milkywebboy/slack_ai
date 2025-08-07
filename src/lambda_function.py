import json
import os
import boto3
import openai
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 環境変数から設定値を取得
KENDRA_INDEX_ID = os.environ.get('KENDRA_INDEX_ID', 'e1503ef7-270d-48e7-848d-6d1d356d411c')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
# CHATGPT_MODELは gpt-4 などを利用
CHATGPT_MODEL = os.environ.get('CHATGPT_MODEL', 'ft:gpt-4o-2024-08-06:techfund-inc::B5TwK9je')

# boto3 クライアント作成
kendra = boto3.client('kendra', region_name='us-east-1')
openai.api_key = OPENAI_API_KEY

def lambda_handler(event, context):
    try:
        query_text = event.get('query', 'default search term')
        # Kendraの検索実行
        kendra_response = kendra.query(
            IndexId=KENDRA_INDEX_ID,
            QueryText=query_text
        )
        documents = kendra_response.get('ResultItems', [])
        retrieved_text = "\n".join(
            item.get('DocumentExcerpt', {}).get('Text', '')
            for item in documents
        )
        # ChatGPT-4 へのプロンプト作成（日本語で回答するように指示）
        prompt = (
            f"メンバーからの質問: {query_text}\n\n"
            f"その質問に関連するドキュメント情報:\n{retrieved_text}\n\n"
            "上記の質問に対して、回答を日本語で提供してください。"
        )
        completion = openai.ChatCompletion.create(
            model=CHATGPT_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        answer = completion.choices[0].message["content"]
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json; charset=UTF-8"
            },
            "body": json.dumps({
                "query": query_text,
                "kendra_results": documents,
                "chatgpt_answer": answer
            }, ensure_ascii=False)
        }
    except Exception as e:
        logger.error("Exception occurred", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }