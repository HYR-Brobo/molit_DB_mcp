"""
국토교통 협력형 분석센터 MCP 서버
AI(Claude)가 국토부 데이터를 스스로 검색·조회하며 공모전 아이디어를 탐색하게 해주는 도구 모음.

필요한 것:  pip install "mcp[cli]" requests
인증키:     환경변수 MOLIT_KEY (MCP 등록할 때 같이 넣어줌)
"""

import os

import requests

try:                                            # mcp 2.x
    from mcp.server.mcpserver import MCPServer as Server
except ImportError:                             # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server

BASE = "http://openapi.molit.go.kr/api/openapi"
SEARCH_URL = f"{BASE}/search/getOpenApiSearchList"
DATASET_URL = f"{BASE}/dataset/getOpenApiDatasetList"
KEY = os.environ.get("MOLIT_KEY", "")

CATEGORIES = ["국토도시", "주택토지", "교통물류", "항공", "도로철도", "일반", "융합(기타)"]

mcp = Server(
    "molit-data",
    instructions="국토교통 협력형 분석센터의 데이터 목록을 검색·조회한다. "
                 "데이터 값이 아니라 데이터 설명(메타데이터)을 주므로, 아이디어 탐색·데이터 조합 구상에 쓴다.",
)


# ───────────── 내부 함수 ─────────────
def _call(url: str, params: dict) -> dict:
    if not KEY:
        raise RuntimeError("MOLIT_KEY 환경변수에 인증키가 없습니다.")
    r = requests.get(url, params={"serviceKey": KEY, "returnType": "JSON", **params}, timeout=20)
    r.raise_for_status()
    data = r.json()
    header = data.get("header") or {}
    code = str(header.get("resultCode", ""))
    if code.startswith("ERROR"):
        raise RuntimeError(f"{code}: {header.get('resultMsg')}")
    return data


def _items(data: dict) -> list:
    """응답 계층이 문서상 애매해서, 결과 리스트가 있을 법한 자리를 차례로 찾음."""
    for path in (("items",), ("body", "items"), ("data",), ("response", "body", "items")):
        cur = data
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if isinstance(cur, list):
            return cur
        if isinstance(cur, dict) and isinstance(cur.get("item"), list):
            return cur["item"]
    return []


def _total(data: dict):
    for src in (data, data.get("header") or {}, data.get("body") or {}):
        if isinstance(src, dict) and "totalCount" in src:
            return src["totalCount"]
    return None


def _short(text, n=300):
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[:n] + "…"


# ───────────── AI가 쓰는 도구 ─────────────
@mcp.tool()
def search_data(query: str, categories: list[str] | None = None, page: int = 1) -> dict:
    """국토교통 데이터를 키워드로 검색한다. 데이터 '값'이 아니라 '설명'(제목·설명·기관·키워드)을 돌려준다.

    탐색 요령:
    - 한 단어로 시작해서 결과에 나온 키워드로 넓혀갈 것 (예: 통학 → 셔틀 → 환승 → 정류장).
    - 결과가 많으면 categories로 좁히기. 가능한 값: 국토도시, 주택토지, 교통물류, 항공, 도로철도, 일반, 융합(기타)
    - total이 perPage보다 크면 page를 올려 더 볼 수 있음.
    """
    params = {"page": page, "perPage": 20, "searchQuery": query}
    if categories:
        params["categoryNames"] = ",".join(c for c in categories if c in CATEGORIES)
    data = _call(SEARCH_URL, params)
    return {
        "query": query,
        "page": page,
        "total": _total(data),
        "results": [
            {
                "title": it.get("title"),
                "category": it.get("categoryName"),
                "agency": it.get("agentName"),
                "keywords": it.get("keyword"),
                "description": _short(it.get("description")),
                "url": it.get("detailPage"),
                "modified": it.get("modified"),
            }
            for it in _items(data)
        ],
    }


@mcp.tool()
def get_dataset(title: str = "", creator: str = "", page: int = 1) -> dict:
    """제목 또는 제공기관으로 데이터셋을 조회한다. 데이터 기간·라이선스·포함된 파일 목록(다운로드 주소)까지 나온다.

    쓰는 때:
    - search_data로 찾은 데이터가 쓸 만해 보일 때, 그 제목으로 상세 확인.
    - 두 데이터를 엮을 수 있는지 볼 때, 기간(period)이 겹치는지 확인.
    - 공모전 제출용이면 license(이용허락범위)도 확인.
    title·creator 중 하나 이상 넣을 것. 부분 일치로 찾힘.
    """
    params = {"page": page, "perPage": 20}
    if title:
        params["title"] = title
    if creator:
        params["creator"] = creator
    data = _call(DATASET_URL, params)
    return {
        "total": _total(data),
        "datasets": [
            {
                "title": ds.get("title"),
                "category": ds.get("conceptName"),
                "creator": ds.get("creatorNm"),
                "publisher": ds.get("publisherNm"),
                "keywords": ds.get("keyword"),
                "description": _short(ds.get("description"), 500),
                "period": f"{ds.get('temporalStartDate', '')} ~ {ds.get('temporalEndDate', '')}",
                "license": ds.get("license"),
                "access": ds.get("accessRights"),
                "page_url": ds.get("landingPage"),
                "files": [
                    {"name": f.get("dataNm"), "url": f.get("urlOutr")}
                    for f in (ds.get("datasetDataList") or [])
                ],
            }
            for ds in _items(data)
        ],
    }


@mcp.tool()
def raw_response(api: str, query: str) -> str:
    """[점검용] API 원본 응답을 그대로 본다. api는 'search' 또는 'dataset'.
    다른 도구 결과가 계속 비어 있을 때만 사용해서 응답 구조를 확인할 것."""
    import json
    if api == "search":
        data = _call(SEARCH_URL, {"page": 1, "perPage": 3, "searchQuery": query})
    else:
        data = _call(DATASET_URL, {"page": 1, "perPage": 3, "title": query})
    return json.dumps(data, ensure_ascii=False, indent=2)[:4000]


# ───────────── 탐색 시작용 프롬프트 ─────────────
@mcp.prompt()
def contest_ideas(theme: str) -> str:
    """공모전 아이디어 탐색을 시작하는 프롬프트."""
    return f"""'{theme}'을(를) 주제로 국토교통 데이터 공모전 아이디어를 찾아줘.

1. search_data로 '{theme}'와 관련 단어들을 검색해 후보 데이터를 넓게 모아.
   결과에 나온 키워드를 다음 검색어로 써서 최소 5번 이상 넓혀가.
2. 서로 엮을 수 있어 보이는 데이터는 get_dataset으로 기간·지역 단위·라이선스를 확인해.
3. 데이터 2~3개를 조합한 아이디어 3개를 제안해. 각 아이디어마다:
   - 어떤 데이터를 무엇을 기준으로(시간·위치·지역코드 등) 합치는지
   - 그걸로 풀 수 있는 문제와 결과물(분석/서비스)
   - 걸리는 점 (기간 불일치, 파일 없음, 비공개 등)
4. 데이터 설명만 보고 판단한 것이니, 실제 파일을 열어 확인해야 할 점도 적어줘."""


# ───────────── 웹(claude.ai)용 실행 ─────────────
def run_web():
    """claude.ai 웹 커넥터용. 비밀 토큰이 맞는 요청만 통과시킨다."""
    import hmac
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    token = os.environ.get("MCP_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("MCP_TOKEN 환경변수에 16자 이상 비밀 토큰을 넣어주세요.")

    app = mcp.streamable_http_app(
        stateless_http=True,
        # 외부 주소(터널 도메인)로 들어오는 요청을 막지 않도록. 대신 아래 토큰 검사로 보호.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    expected = f"Bearer {token}".encode()

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            auth = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(auth, expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await app(scope, receive, send)

    # 클라우드(Render 등)는 HOST/PORT를 지정해줌. 집 PC + 터널이면 기본값 그대로.
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(guarded, host=host, port=port)


if __name__ == "__main__":
    import sys
    if "--web" in sys.argv:
        run_web()           # claude.ai 웹 커넥터용 (터널과 함께 사용)
    else:
        mcp.run()           # Claude Desktop / Claude Code 로컬용
