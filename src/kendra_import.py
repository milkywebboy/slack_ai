import json
import boto3

# 設定値：JSONファイルパスとKendraインデックスIDを指定
json_file = 'drive_documents.json'
index_id = 'd1696ae6-2747-47ed-9d0c-e31c53fd6b53'  # ご自身のKendraインデックスIDに置き換えてください

# AWS認証情報は環境変数等で設定済みと仮定（Macの場合も同様）
kendra = boto3.client('kendra', region_name='us-east-1')

# JSONファイルを読み込み
with open(json_file, 'r', encoding='utf-8') as f:
    pages = json.load(f)

documents = []
batch_size = 10

for page in pages:
    # contentが空の場合はスキップ
    if not page.get('content'):
        continue

    # 追加属性の設定（必要に応じて変更してください）
    attributes = [
        {
            'Key': '_source_uri',
            'Value': {'StringValue': page.get('url', '')}
        },
        {
            'Key': 'createdTime',
            'Value': {'StringValue': page.get('createdTime', '')}
        },
        {
            'Key': 'modifiedTime',
            'Value': {'StringValue': page.get('modifiedTime', '')}
        },
        {
            'Key': 'owners',
            'Value': {
                'StringValue': ', '.join([owner.get('emailAddress', '') for owner in page.get('owners', [])])
            }
        }
        # collaborators等、他に必要な属性があればここに追加可能
    ]

    document = {
        'Id': page.get('id', ''),
        'Title': page.get('title', ''),
        'Blob': page.get('content').encode('utf-8'),
        'ContentType': 'PLAIN_TEXT',
        'Attributes': attributes
    }
    documents.append(document)

# 10件ごとにバッチで登録
for i in range(0, len(documents), batch_size):
    batch = documents[i:i + batch_size]
    response = kendra.batch_put_document(
        IndexId=index_id,
        Documents=batch
    )
    print(f"バッチ {i // batch_size + 1}: {response}")