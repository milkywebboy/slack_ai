# 1.まず、以下コマンドを実行
# $ openai api files.create --purpose fine-tune --file finetune.jsonl
# そのコマンドの結果で出るファイルIDを下記のtraining_fileに指定

# 2.このプログラムを実行
# $ python finetune.py

# 3.コンソールに表示されるJob IDの最新ステータスを確認
# $ curl https://api.openai.com/v1/fine_tuning/jobs/ftjob-XXX \
#  -H "Content-Type: application/json" \
#  -H "Authorization: Bearer $OPENAI_API_KEY"

from openai import OpenAI
from os import getenv

client = OpenAI(api_key=getenv("OPENAI_API_KEY"))

# ファインチューニングジョブの作成
response = client.fine_tuning.jobs.create(
    training_file="file-1ucG27vBvax7VX7adG5XLX",  # アップロード済み学習データのファイルID
#    validation_file="file-YYYYYYYYYYYYYYYY",  # （任意）検証データのファイルID
    model="o4-mini-2025-04-16",               # ベースモデル（スナップショット名）
    hyperparameters={                       # （任意）ハイパーパラメータの指定
        "n_epochs": 3,
        "batch_size": 4,
        "learning_rate_multiplier": 0.1
    },
    suffix="interview-memo"              # （任意）ファインチューニング後モデル名の接尾辞
)
print("Job ID:", response.id, "Status:", response.status)