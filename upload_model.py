from huggingface_hub import HfApi, create_repo, login

login(token="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")

repo_id = "sunaoran/truthscan-bert"

create_repo(repo_id=repo_id, repo_type="model", exist_ok=True)

api = HfApi()

api.upload_folder(
    folder_path="D:/Fakenewsdetection/truthscan/bert_upload",
    repo_id=repo_id,
    repo_type="model"
)

print("✅ DONE 🚀")