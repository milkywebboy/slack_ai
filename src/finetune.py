import openai
openai.api_key = ""

# ファイルのアップロード
training_file = openai.File.create(
    file=open("finetune.jsonl", "rb"),
    purpose="fine-tune"
)

# ファインチューニングジョブの作成
fine_tune_job = openai.FineTune.create(
    training_file=training_file.id,
    model="gpt-4o-2024-08-06",
    n_epochs=4,
)
print(fine_tune_job)