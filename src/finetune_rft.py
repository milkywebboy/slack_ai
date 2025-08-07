# 1.まず、以下コマンドを実行
# $ openai api files.create --purpose fine-tune --file finetune.jsonl
# そのコマンドの結果で出るファイルIDを下記のtraining_fileに指定

# 2.このプログラムを実行
# $ python finetune.py

# 3.コンソールに表示されるJob IDの最新ステータスを確認
# $ curl https://api.openai.com/v1/fine_tuning/jobs/ftjob-ylJjL8WnYAeSH610Ch8QMhGh -H "Content-Type: application/json" -H "Authorization: Bearer $OPENAI_API_KEY"

from openai import OpenAI
from os import getenv

client = OpenAI(api_key=getenv("OPENAI_API_KEY"))

response = client.fine_tuning.jobs.create(
    training_file="file-4NF6CkJrprD86q7gHLXGHw",
    validation_file="file-7FsNJpCHBUeAzmm27358Rd",
    model="o4-mini-2025-04-16",
    method={
        "type": "reinforcement",
        "reinforcement": {
            "hyperparameters": {
                "eval_samples":      100,       # RFT 用ハイパラはここへ
                "eval_interval":     10,
                "compute_multiplier":1.0,
                "reasoning_effort":  "medium"
            },
            "grader": {
                "type":               "text_similarity",
                "name":               "slack_reply_similarity",
                "input":              "{{sample.output_text}}",
                "reference":          "{{sample.output_json.final_answer}}",
                "pass_threshold":     1,
                "evaluation_metric":  "fuzzy_match"
            }
        }
    },
    suffix="my-o4-mini-rft"
)
print(response)