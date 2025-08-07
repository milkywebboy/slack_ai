import requests
import json
import time
from requests.adapters import HTTPAdapter, Retry
from os import getenv

# --- 設定 ---
NOTION_API_KEY = getenv("NOTION_API_KEY")  # ご自身の統合トークンに置き換えてください
NOTION_VERSION = "2022-06-28"  # 最新の API バージョンを指定
BASE_URL = "https://api.notion.com/v1/"

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

# --- セッションの作成とリトライ設定 ---
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

# --- ページ検索・取得 ---
def search_notion_objects(session):
    """ワークスペース内の全オブジェクト（ページ・データベース）を取得"""
    url = BASE_URL + "search"
    results = []
    has_more = True
    next_cursor = None
    while has_more:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        response = session.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            print("Search APIエラー:", response.status_code, response.text)
            break
        data = response.json()
        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")
        time.sleep(0.1)
    return results

def query_database(session, database_id):
    """指定データベース内の全ページを取得"""
    url = BASE_URL + f"databases/{database_id}/query"
    pages = []
    has_more = True
    next_cursor = None
    while has_more:
        payload = {"page_size": 100}
        if next_cursor:
            payload["start_cursor"] = next_cursor
        response = session.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            print(f"データベース {database_id} クエリエラー:", response.status_code, response.text)
            break
        data = response.json()
        pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")
        time.sleep(0.1)
    return pages

# --- ブロック取得と再帰的テキスト抽出 ---
def get_blocks(session, block_id, start_cursor=None):
    """指定ブロック（またはページ）の子ブロックを1ページ分取得"""
    url = BASE_URL + f"blocks/{block_id}/children"
    params = {"page_size": 100}
    if start_cursor:
        params["start_cursor"] = start_cursor
    response = session.get(url, headers=headers, params=params, timeout=30)
    if response.status_code == 200:
        return response.json()
    else:
        print("ブロック取得エラー:", response.status_code, response.text)
        return None

def get_all_blocks(session, block_id):
    """ページまたはブロックの子ブロックを全件取得（ページネーション対応）"""
    all_blocks = []
    start_cursor = None
    while True:
        data = get_blocks(session, block_id, start_cursor)
        if not data:
            break
        all_blocks.extend(data.get("results", []))
        if data.get("has_more"):
            start_cursor = data.get("next_cursor")
            time.sleep(0.1)
        else:
            break
    return all_blocks

def extract_plain_text(block):
    """
    対応ブロックタイプ（paragraph, heading, list_item, quote, code など）から plain text を抽出
    """
    block_type = block.get("type")
    if block_type in ["paragraph", "heading_1", "heading_2", "heading_3",
                      "bulleted_list_item", "numbered_list_item", "quote", "code"]:
        texts = block.get(block_type, {}).get("rich_text", [])
        return "".join([t.get("plain_text", "") for t in texts])
    return ""

def get_recursive_text(session, block_id):
    """
    指定ブロック（またはページ）の子ブロックを再帰的に取得し、テキストを連結して返す
    """
    text = ""
    blocks = get_all_blocks(session, block_id)
    for block in blocks:
        block_text = extract_plain_text(block)
        if block_text:
            text += block_text + "\n"
        if block.get("has_children", False):
            child_text = get_recursive_text(session, block["id"])
            if child_text:
                text += child_text + "\n"
    return text.strip()

# --- ページ情報の処理 ---
def extract_page_title(page):
    """ページのタイトルを抽出する。データベースページの場合、titleタイプのプロパティを探索する"""
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            title = "".join([t.get("plain_text", "") for t in prop.get("title", [])])
            if title:
                return title
    return "Untitled Page"

def process_page(session, page):
    """ページ基本情報と本文（子ブロックのテキスト）を取得して返す"""
    page_id = page["id"]
    title = extract_page_title(page)
    content = get_recursive_text(session, page_id)
    url = page["url"]
    return {
        "id": page_id,
        "title": title,
        "content": content,
        "url": url
    }

# --- メイン処理 ---
def main():
    print("Notion オブジェクトの検索を開始します...")
    all_objects = search_notion_objects(session)
    print(f"全オブジェクト取得件数: {len(all_objects)}")

    standalone_pages = []  # データベースに属さないページ
    databases = []         # データベースオブジェクト
    database_pages = []    # データベース内のページ

    for obj in all_objects:
        if obj["object"] == "page":
            if obj.get("parent", {}).get("type") == "database_id":
                continue
            standalone_pages.append(obj)
        elif obj["object"] == "database":
            databases.append(obj)

    print(f"スタンドアロンページ数: {len(standalone_pages)}")
    print(f"データベース数: {len(databases)}")

    for db in databases:
        db_id = db["id"]
        pages_in_db = query_database(session, db_id)
        print(f"データベース {db_id} 内のページ数: {len(pages_in_db)}")
        database_pages.extend(pages_in_db)

    all_pages = standalone_pages + database_pages
    print(f"全ページ数: {len(all_pages)}")

    notion_documents = []
    print("各ページの内容を取得中...")
    for idx, page in enumerate(all_pages):
        try:
            doc = process_page(session, page)
            notion_documents.append(doc)
            print(f"[{idx+1}/{len(all_pages)}] 取得: {doc['title']} - content length: {len(doc['content'])}")
        except Exception as e:
            print(f"ページ {page['id']} の処理でエラー発生。スキップします。エラー内容: {e}")

    output_filename = "notion_documents.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(notion_documents, f, ensure_ascii=False, indent=2)

    print(f"全ページの内容を {output_filename} に保存しました。")
    session.close()

if __name__ == "__main__":
    main()