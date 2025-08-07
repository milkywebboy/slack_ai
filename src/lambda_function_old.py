import json
import boto3
import os

# 環境変数または直接値を設定
KENDRA_INDEX_ID = os.environ.get('KENDRA_INDEX_ID', 'e1503ef7-270d-48e7-848d-6d1d356d411c')
# Bedrock では、オンデマンド呼び出しではなくインファレンスプロファイルを利用する必要があります
BEDROCK_INFERENCE_PROFILE_ARN = os.environ.get('BEDROCK_INFERENCE_PROFILE_ARN', 'arn:aws:bedrock:us-east-1:039861401280:inference-profile/my-profile')

# boto3 クライアント作成
kendra = boto3.client('kendra', region_name='us-east-1')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

def lambda_handler(event, context):
    # イベントから検索クエリを取得
    query_text = event.get('query', 'default search term')
    
    # Kendra の Query API を呼び出す
    kendra_response = kendra.query(
        IndexId=KENDRA_INDEX_ID,
        QueryText=query_text
    )
    
    # 検索結果からドキュメントの抜粋を連結
    documents = kendra_response.get('ResultItems', [])
    retrieved_text = "\n".join(
        item.get('DocumentExcerpt', {}).get('Text', '')
        for item in documents
    )
    
    # Amazon Bedrock に問い合わせるためのペイロード作成
    bedrock_payload = {
        "prompt": f"User query: {query_text}\nRetrieved documents:\n{retrieved_text}\nAnswer:",
        "maxTokens": 150
    }
    
    # invoke_model のパラメータはすべて小文字のキーを使用し、modelId にインファレンスプロファイル ARN を指定
    invoke_params = {
        'body': json.dumps(bedrock_payload).encode('utf-8'),
        'contentType': 'application/json',
        'modelId': BEDROCK_INFERENCE_PROFILE_ARN
    }
    
    # Bedrock のモデル呼び出し
    bedrock_response = bedrock.invoke_model(**invoke_params)
    result = json.loads(bedrock_response['body'].read())
    
    # 結果を返す
    return {
        'statusCode': 200,
        'body': json.dumps({
            'query': query_text,
            'kendra_results': documents,
            'bedrock_result': result
        })
    }