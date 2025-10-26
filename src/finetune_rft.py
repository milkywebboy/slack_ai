# 1.まず、以下コマンドを実行
# $ openai api files.create --purpose fine-tune --file finetune.jsonl
# そのコマンドの結果で出るファイルIDを下記のtraining_fileに指定

# 2.このプログラムを実行
# $ python finetune_rft.py

# 3.コンソールに表示されるJob IDの最新ステータスを確認
# $ curl https://api.openai.com/v1/fine_tuning/jobs/ftjob-fUaCEnQoyT1WK32ZKMndfTw9 -H "Content-Type: application/json" -H "Authorization: Bearer $OPENAI_API_KEY"

from openai import OpenAI
from os import getenv

client = OpenAI(api_key=getenv("OPENAI_API_KEY"))

job = client.fine_tuning.jobs.create(
    model="o4-mini-2025-04-16",
    training_file="file-4Eg9qxuDrGDVKn6VrnbPur",
    validation_file="file-KY4EPGgw459ESLphgSQ4Ro",
    method={
        "type": "reinforcement",
        "reinforcement": {
            "hyperparameters": {
                # RFT専用パラメータ（推奨レンジを順守）
                "eval_samples": 5,          # 1〜10 が有効
                "eval_interval": 15,         # 1〜25
                "compute_multiplier": 1.0,
                "reasoning_effort": "medium"
                # ※必要に応じて n_epochs / batch_size / learning_rate_multiplier もここに
            },
            "grader": {
                "type": "text_similarity",
                "name": "slack_reply_similarity",
                # サンプル（モデル出力）はテキスト。参照は学習データの final_answer を使う
                "input": "{{sample.output_text}}",
                "reference": "{{item.final_answer}}",
                "evaluation_metric": "fuzzy_match",
                "pass_threshold": 0.5       # 任意。厳しすぎる1.0は非推奨
            }
        }
    },
    suffix="my-o4-mini-rft"
)
print(job)