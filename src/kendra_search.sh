## インデックス自体を試す
aws kendra query --index-id 08e26a11-26b3-4b12-b8d4-bf7e7382e15f --query-text "NotionDocument"

## Lambda登録（まずZip化）
zip function.zip lambda_function.py

## 登録時
aws lambda create-function \
  --function-name KendraBedrockRAGFunction \
  --runtime python3.8 \
  --role arn:aws:iam::039861401280:role/LambdaRAGExecutionRole \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function.zip

## アップデート時
aws lambda update-function-code --function-name KendraBedrockRAGFunction --zip-file fileb://function.zip

## 検索してみる
## aws kendra query --index-id e1503ef7-270d-48e7-848d-6d1d356d411c --query-text "NotionDocument"
aws lambda invoke --function-name KendraBedrockRAGFunction --payload '{"query": "報酬原則に照らし合わせると、私が今月40FPを発揮しているのに昇給しないのはおかしいですよね？"}' --cli-binary-format raw-in-base64-out output.json