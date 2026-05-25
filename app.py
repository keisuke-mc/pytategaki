from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import re
import unicodedata

app = Flask(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

def fetch_article(url: str) -> dict:
    """URLからテキストと見出しを取得"""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "html.parser")

    # タイトル
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True)
    if soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    # 不要タグ除去
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "noscript", "iframe", "ads",
                     "figure", "figcaption"]):
        tag.decompose()

    # 本文候補セレクタ（優先順）
    candidates = [
        "article", "main", "[role='main']",
        ".article-body", ".post-content", ".entry-content",
        ".content", "#content", ".main-content",
    ]
    body_el = None
    for sel in candidates:
        body_el = soup.select_one(sel)
        if body_el:
            break
    if body_el is None:
        body_el = soup.body or soup

    # 段落・見出し構造を保持して抽出
    blocks = []
    for el in body_el.find_all(
        ["h1", "h2", "h3", "h4", "p", "li", "blockquote", "dt", "dd"],
        recursive=True
    ):
        text = el.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text or len(text) < 2:
            continue
        tag = el.name
        if tag in ("h1", "h2"):
            kind = "heading"
        elif tag in ("h3", "h4"):
            kind = "subheading"
        elif tag == "blockquote":
            kind = "quote"
        else:
            kind = "body"
        blocks.append({"kind": kind, "text": text})

    # 重複除去（連続する同テキスト）
    deduped = []
    prev = None
    for b in blocks:
        if b["text"] != prev:
            deduped.append(b)
            prev = b["text"]

    # サイト名(ドメイン)
    from urllib.parse import urlparse
    domain = urlparse(url).netloc

    return {
        "title": title,
        "domain": domain,
        "url": url,
        "blocks": deduped,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/fetch", methods=["POST"])
def fetch():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URLを入力してください"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        article = fetch_article(url)
        if not article["blocks"]:
            return jsonify({"error": "本文テキストを取得できませんでした"}), 422
        return jsonify(article)
    except requests.exceptions.Timeout:
        return jsonify({"error": "接続がタイムアウトしました"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"取得エラー: {e}"}), 502
    except Exception as e:
        return jsonify({"error": f"予期しないエラー: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
