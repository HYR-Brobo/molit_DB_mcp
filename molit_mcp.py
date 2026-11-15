"""
국토교통 협력형 분석센터 MCP 서버
AI(Claude)가 국토부 데이터를 스스로 검색·조회하며 공모전 아이디어를 탐색하게 해주는 도구 모음.

필요한 것:  pip install "mcp[cli]" requests
인증키:     환경변수 MOLIT_KEY (MCP 등록할 때 같이 넣어줌)
"""

import contextvars
import datetime
import functools
import os
import re
import time
from typing import Annotated, Literal

import requests
from pydantic import Field

try:                                            # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _BaseServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:                             # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _BaseServer
    from mcp.server.fastmcp.exceptions import ToolError

# openapi.molit.go.kr은 DNS가 127.0.0.1을 돌려줘서 어디서든 접속 거부됨. 실제 API는 여기.
HOST = "data.molit.go.kr"
PATH = "/api/openapi"
SEARCH_URL = "/search/getOpenApiSearchList"
DATASET_URL = "/dataset/getOpenApiDatasetList"
# https 먼저, 안 되면 http. 둘 다 실패하면 각각의 실패 이유를 함께 돌려줌.
SCHEMES = ("https", "http")
# 상세 페이지 화면이 쓰는 사이트 내부 API. 인증키 없이 POST로 부름.
DETAIL_URL = f"https://{HOST}/api/search/analsDetail"
KEY = os.environ.get("MOLIT_KEY", "")

Category = Literal["국토도시", "주택토지", "교통물류", "항공", "도로철도", "일반", "융합(기타)"]
DataType = Literal["dataset", "dataservice", "all"]
PER_PAGE = 20

# 도구 이름을 바꾸면, 이미 연결돼 있던 커넥터는 옛 도구 목록을 그대로 들고 옛 이름으로 호출한다.
# (--web은 stateless라 '목록이 바뀌었다'는 알림을 보낼 수 없음) 그래서 옛 이름도 받아서 새 도구로 넘긴다.
RENAMED_TOOLS = {"get_dataset": "list_analysis_datasets"}
REMOVED_TOOLS = {"raw_response": "개발자 점검용이라 평소에는 꺼 둔 도구입니다(서버에 MOLIT_DEBUG를 넣어야 켜짐). 데이터 탐색에는 필요 없습니다."}
REFRESH_TIP = "이 커넥터가 옛 도구 목록을 보고 있으니, 사용자에게 커넥터를 껐다 켜거나 다시 연결해 도구 목록을 새로 받으라고 알려 주세요."
_called_as = contextvars.ContextVar("called_as", default=None)


class Server(_BaseServer):
    async def call_tool(self, name, arguments, *args, **kwargs):
        known = {t.name for t in await self.list_tools()}
        if name not in known:
            if name in RENAMED_TOOLS:
                # 옛 인자(title·creator·page)는 새 도구에 없으므로 버린다. 목록이 몇 건뿐이라 통째로 줘도 됨.
                _called_as.set(name)
                name, arguments = RENAMED_TOOLS[name], {}
            else:
                why = REMOVED_TOOLS.get(name, "이 서버에 없는 도구입니다.")
                raise ToolError(f"'{name}': {why} 지금 쓸 수 있는 도구: {', '.join(sorted(known))}. {REFRESH_TIP}")
        return await super().call_tool(name, arguments, *args, **kwargs)


mcp = Server(
    "molit-data",
    instructions="""국토교통 협력형 분석센터(data.molit.go.kr)의 데이터 '목록'을 찾는 도구. 데이터 값은 주지 않고 설명(메타데이터)만 준다.

목록이 두 개이고 서로 크기가 전혀 다르다:
1. 통합 목록 (1만 건 이상) → search_data
   공공기관 데이터셋·Open API 전체. 제목·설명·기관·키워드·상세페이지 주소까지만 나온다.
   파일 목록·원본 포털·저작권은 결과의 url을 get_detail에 넣으면 나온다.
   이 목록은 '어디에 있는지' 알려주는 카탈로그다. 파일은 분석센터가 아니라 원래 제공기관 포털에 있다.
2. 분석 데이터셋 목록 (몇 건뿐) → list_analysis_datasets
   분석과제를 수행한 기관이 과제에 쓴 데이터를 직접 올려 둔 것. 파일 다운로드 주소·라이선스가 나온다.
   통합 목록의 '상세 조회'가 아니다. 통합 목록에서 찾은 제목은 대부분 여기에 없다.

쓰는 순서: search_data로 한 단어씩 검색하며 후보를 모은다 → 쓸 만한 후보만 get_detail로 파일 목록·받는 곳을 확인한다.
결과가 0건이면 도구 고장이 아니라 그 목록에 없는 것이니, 응답의 hint를 따른다.

상세 페이지(url)는 자바스크립트 화면이라 curl·fetch로 열면 빈 껍데기만 온다. 직접 열지 말고 get_detail을 쓴다.
파일은 대개 제공기관 포털에 있고, 그 포털은 로그인·활용신청·이용 설문을 요구하는 경우가 많다.
그런 단계는 우회하거나 임의로 채우지 말고, get_detail의 how_to_get대로 어느 포털에서 무엇을 받으면 되는지 사용자에게 안내한다.""",
)


# ───────────── 내부 함수 ─────────────
def _mask(text) -> str:
    """에러 메시지·로그에 서비스키가 평문으로 남지 않게 가림."""
    text = str(text)
    if KEY:
        text = text.replace(KEY, "***")
        text = text.replace(requests.utils.quote(KEY, safe=""), "***")
    return text


def _call(path: str, params: dict) -> dict:
    if not KEY:
        raise RuntimeError("MOLIT_KEY 환경변수에 인증키가 없습니다.")
    failures = []
    for scheme in SCHEMES:
        url = f"{scheme}://{HOST}{PATH}{path}"
        try:
            r = requests.get(url, params={"serviceKey": KEY, "returnType": "JSON", **params}, timeout=20)
        except requests.RequestException as e:
            # 연결 단계 실패(거부·타임아웃·DNS 등) → 다음 scheme 시도
            failures.append(f"{scheme}: {type(e).__name__}: {_mask(e)}")
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{scheme} HTTP {r.status_code}: {_mask(r.text[:300])}")
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(f"{scheme} 응답이 JSON이 아님: {_mask(r.text[:300])}")
        err = data.get("error") if isinstance(data, dict) else None
        if err:
            # 서버는 오류를 {"error": {...}} 모양으로 보냄 (예: ERROR-30 등록되지 않은 서비스키)
            if isinstance(err, dict):
                code = err.get("code") or err.get("resultCode") or ""
                msg = err.get("message") or err.get("resultMsg") or err
                raise RuntimeError(f"{code}: {_mask(msg)}" if code else _mask(err))
            raise RuntimeError(_mask(err))
        header = data.get("header") or {}
        code = str(header.get("resultCode", ""))
        if code.startswith("ERROR"):
            raise RuntimeError(f"{code}: {header.get('resultMsg')}")
        return data
    raise RuntimeError("국토부 서버에 연결하지 못함 → " + " | ".join(failures))


def _safe(fn):
    """도구 안에서 난 예외를 일반 문구로 삼키지 않고, 원인을 문자열로 돌려줌."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {_mask(e)}"
            # 반환 타입이 str인 도구는 문자열로 돌려줘야 출력 스키마와 맞음
            return msg if fn.__annotations__.get("return") in (str, "str") else {"error": msg}
    return wrapper


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


def _period(ds: dict) -> str:
    """기간이 없으면 'None ~ None' 대신 빈 문자열."""
    start, end = ds.get("temporalStartDate") or "", ds.get("temporalEndDate") or ""
    return f"{start} ~ {end}" if (start or end) else ""


def _short(text, n=300):
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[:n] + "…"


def _norm(title) -> str:
    return "".join((title or "").split())


def _files(ds: dict) -> list:
    """파일 정보가 통째로 빈 항목({name: null, url: null})은 뺌."""
    out = []
    for f in ds.get("datasetDataList") or []:
        url = f.get("dataDownloadUrl") or f.get("dataUrl") or f.get("urlOutr")
        if f.get("dataNm") or url:
            out.append({"name": f.get("dataNm"), "url": url})
    return out


def _dataset_view(ds: dict) -> dict:
    files, page_url = _files(ds), ds.get("landingPage")
    return {
        "title": ds.get("title"),
        "category": ds.get("conceptName"),
        "creator": ds.get("creatorNm"),
        "publisher": ds.get("publisherNm"),
        "keywords": ds.get("keyword"),
        "description": _short(ds.get("description"), 500),
        "period": _period(ds) or "미기재",
        "license": ds.get("license") or "미기재",
        "access": ds.get("accessRights"),
        "registered": ds.get("issued"),
        "files": files,
        "original_page": page_url,
        "how_to_get": ("files의 url로 바로 내려받음 (분석 기관이 올린 가공·샘플 데이터)" if files
                       else "original_page(원본 포털)에서 받음" if page_url
                       else "받을 수 있는 경로가 등록돼 있지 않음"),
    }


_ANALYSIS_CACHE = {"at": 0.0, "items": []}


def _analysis_datasets(max_age: float = 600) -> list:
    """분석 데이터셋 목록 전체. 몇 건뿐이라 통째로 받아 10분간 기억해 둠."""
    if time.time() - _ANALYSIS_CACHE["at"] > max_age:
        items, page = [], 1
        while page <= 10:
            data = _call(DATASET_URL, {"page": page, "perPage": 100})
            got = _items(data)
            items += got
            if not got or len(items) >= (_total(data) or 0):
                break
            page += 1
        _ANALYSIS_CACHE.update(at=time.time(), items=items)
    return _ANALYSIS_CACHE["items"]


def _kind(url) -> str:
    """상세 페이지 주소로 항목 종류를 구분."""
    url = url or ""
    if "/data-search/" in url:
        return "데이터"
    if "/asmt/" in url:
        return "분석과제"
    return "기타"


def _search_hint(query: str, total, page: int, narrowed: bool) -> str:
    words = query.split()
    total = total or 0
    if total == 0:
        tips = ["이 목록에 그 단어가 없음(도구 오류 아님)."]
        if len(words) > 1:
            tips.append(f"한 단어로 줄여 다시 검색: {' / '.join(words)}")
        else:
            tips.append("더 짧은 낱말이나 비슷한 말로 다시 검색 (예: 셔틀버스 → 셔틀, 통학 → 학교).")
        if narrowed:
            tips.append("categories·data_types 조건을 빼고 검색.")
        return " ".join(tips)
    if len(words) > 1 and total > PER_PAGE:
        return (f"여러 단어는 '하나라도 맞으면 포함'으로 검색돼 {total}건이 됨. 관련 높은 것이 앞에 오긴 하지만, "
                f"가장 구체적인 한 단어({max(words, key=len)})로 다시 검색하면 좁혀짐.")
    if total > PER_PAGE * page:
        return f"{total}건 중 {PER_PAGE * page}건까지 봄. 더 보려면 page={page + 1}, 좁히려면 categories 지정."
    return ""


# ───────────── AI가 쓰는 도구 ─────────────
@mcp.tool()
@_safe
def search_data(
    query: Annotated[str, Field(description="검색어. 한 단어 권장(예: '환승'). 띄어 쓰면 단어 중 하나만 맞아도 걸려 결과가 폭증함.")],
    categories: Annotated[list[Category] | None, Field(description="분야로 좁히기. 비우면 전체.")] = None,
    data_types: Annotated[list[DataType] | None, Field(
        description="비우면 데이터(dataset=파일형, dataservice=Open API형)만 검색. "
                    "['all']이면 지난 분석과제·공모전 출품작도 포함(어떤 데이터가 어떤 아이디어에 쓰였는지 참고용).")] = None,
    page: Annotated[int, Field(description="결과는 한 번에 20건. total이 더 크면 2, 3…으로 다음 쪽.", ge=1)] = 1,
) -> dict:
    """통합 목록(1만 건 이상)에서 국토교통 데이터를 키워드로 찾는다. 데이터를 찾을 때 항상 이 도구부터 쓴다.

    돌려주는 것: 제목·분야·기관·키워드·설명·상세페이지 주소(url). 데이터 '값'은 주지 않는다.
    돌려주지 않는 것: 파일 목록·원본 포털·저작권. 필요한 후보만 결과의 url을 get_detail에 넣어 확인한다.
      예외로, 결과에 analysis_dataset이 붙어 있으면 그 항목은 파일 주소·라이선스가 그 안에 이미 들어 있다.

    검색 요령: 한 단어로 시작해 결과의 keywords에서 다음 검색어를 골라 넓혀간다 (통학 → 셔틀 → 환승 → 정류장).
    기관별로 찾고 싶으면 기관명을 검색어로 넣지 말고, 주제어로 검색한 뒤 결과의 agency를 본다.
    결과가 0건이거나 너무 많으면 응답의 hint에 다음에 할 일이 적혀 있다.
    """
    params = {"page": page, "perPage": PER_PAGE, "searchQuery": query}
    if categories:
        params["categoryNames"] = ",".join(categories)
    types = data_types or ["dataset", "dataservice"]
    if "all" not in types:
        params["dataTypes"] = ",".join(types)
    data = _call(SEARCH_URL, params)

    try:        # 분석 데이터셋과 겹치는 항목엔 파일·라이선스를 바로 붙여 줌. 실패해도 검색 결과는 그대로.
        analysis = {_norm(ds.get("title")): ds for ds in _analysis_datasets()}
    except Exception:  # noqa: BLE001
        analysis = {}

    results = []
    for it in _items(data):
        row = {
            "title": it.get("title"),
            "kind": _kind(it.get("detailPage")),
            "category": it.get("categoryName"),
            "agency": it.get("agentName"),
            "keywords": it.get("keyword"),
            "description": _short(it.get("description")),
            "url": it.get("detailPage"),
            "modified": (it.get("modified") or "")[:10],
        }
        ds = analysis.get(_norm(it.get("title")))
        if ds and row["kind"] == "데이터":
            view = _dataset_view(ds)
            row["analysis_dataset"] = {k: view[k] for k in ("files", "license", "period", "original_page", "how_to_get")}
        results.append(row)

    total = _total(data)
    out = {"query": query, "page": page, "total": total, "results": results}
    hint = _search_hint(query, total, page, bool(categories or data_types))
    if hint:
        out["hint"] = hint
    return out


def _date(ms) -> str:
    """밀리초 타임스탬프 → 'YYYY-MM-DD' (한국 시간)."""
    if not ms:
        return ""
    try:
        kst = datetime.timezone(datetime.timedelta(hours=9))
        return datetime.datetime.fromtimestamp(int(ms) / 1000, kst).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


def _size(n) -> str:
    if not n:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return ""


def _detail_call(seq: str) -> dict:
    body = {"resourceSeq": seq, "siteCode": "molit_anals", "algrthId": "1", "simildegerPt": 50,
            "simildegerSort": None, "hitResourceSort": None, "startRow": 0, "rowsPerPage": 10}
    try:
        r = requests.post(DETAIL_URL, json=body, timeout=20,
                          headers={"Accept": "application/json", "Referer": f"https://{HOST}/anals/data-search/detail/{seq}"})
    except requests.RequestException as e:
        raise RuntimeError(f"상세 정보 서버에 연결하지 못함: {type(e).__name__}: {e}")
    if r.status_code >= 400:
        raise RuntimeError(f"상세 정보 HTTP {r.status_code}: {r.text[:300]}")
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"상세 정보 응답이 JSON이 아님: {r.text[:300]}")
    if not data.get("success") or not isinstance(data.get("result"), dict):
        raise RuntimeError(f"상세 정보 조회 실패: {data.get('message') or str(data)[:300]}")
    return data["result"]


@mcp.tool()
@_safe
def get_detail(
    url: Annotated[str, Field(description="search_data 결과의 url(…/data-search/detail/숫자) 또는 그 끝의 숫자 id.")],
) -> dict:
    """search_data에서 고른 항목 하나의 상세 페이지 내용을 본다. 상세 페이지를 브라우저·curl로 직접 여는 대신 이걸 쓴다.

    돌려주는 것: 원본 포털 이름·주소, 파일 목록(제목·형식·크기·수정일·주소), 저작권, how_to_get(받는 방법).
    파일 '내용'은 주지 않는다. 대부분 파일은 제공기관 포털에 있고, 그 포털이 로그인·설문을 요구하면 사용자에게 안내한다.
    """
    m = re.search(r"(\d+)\D*$", url.strip())
    if not m:
        return {"error": "url에서 id(끝의 숫자)를 찾지 못함. search_data 결과의 url을 그대로 넣어 주세요."}
    seq = m.group(1)
    res = _detail_call(seq)
    resource, system, agent = res.get("resource") or {}, res.get("system") or {}, res.get("agent") or {}
    if not resource:
        return {"error": f"id {seq}에 해당하는 항목이 없음. search_data 결과의 url인지 확인해 주세요."}

    files = []
    for d in res.get("distributions") or []:
        files.append({
            "title": d.get("title"),
            "format": d.get("format") or d.get("mediaType"),
            "size": _size(d.get("byteSize")),
            "modified": _date(d.get("modified")),
            "download_url": d.get("downloadUrl"),
            "page_url": d.get("accessUrl"),
        })
    for d in res.get("datasetDatas") or []:      # 분석센터에 직접 올라온 파일
        link = d.get("dataDownloadUrl") or d.get("dataUrl") or d.get("urlOutr")
        if d.get("dataNm") or link:
            files.append({"title": d.get("dataNm"), "format": d.get("dataFormat") or d.get("format"),
                          "download_url": link, "page_url": None})

    landing = resource.get("landingPage")
    portal = system.get("sysNm") or agent.get("agentName")
    direct = [f for f in files if f["download_url"]]
    if direct:
        how = "files의 download_url로 바로 받을 수 있음"
    elif files and landing:
        how = (f"파일 {len(files)}개가 '{portal}'에 있음. landing_page(또는 각 파일의 page_url)에서 받아야 함. "
               "로그인·활용신청·이용 설문을 요구할 수 있으니 사용자에게 안내할 것.")
    elif landing:
        how = f"등록된 파일 목록은 없음. '{portal}'의 landing_page에서 확인해야 함 (Open API형이면 거기서 활용신청)."
    else:
        how = "받을 수 있는 경로가 등록돼 있지 않음"

    return {
        "title": resource.get("title"),
        "type": {"dataset": "파일형", "dataservice": "Open API형"}.get(resource.get("type"), resource.get("type")),
        "category": resource.get("conceptName"),
        "agency": agent.get("agentName"),
        "description": _short(resource.get("description"), 500),
        "keywords": ", ".join(k.get("keyword", "") for k in res.get("keywords") or []),
        "modified": _date(resource.get("modified")),
        "license": resource.get("license") or "미기재",
        "rights": resource.get("rights"),
        "portal": portal,
        "landing_page": landing,
        "files": files,
        "how_to_get": how,
        "url": f"https://{HOST}/anals/data-search/detail/{seq}",
    }


@mcp.tool()
@_safe
def list_analysis_datasets() -> dict:
    """분석과제에 쓰인 뒤 분석센터에 따로 올라온 '분석 데이터셋'을 전부 보여준다(몇 건뿐이라 검색어 없이 통째로).

    search_data 결과의 상세 조회가 아니다. search_data와는 별개의 작은 목록이라, 거기서 찾은 제목은 대부분 여기에 없다.
    (겹치는 항목은 search_data 결과에 analysis_dataset으로 이미 붙어 나오므로, 그걸 확인하려고 이 도구를 부를 필요는 없다.)

    쓰는 때: 다른 기관이 실제 분석에 쓴 가공·결합·샘플 데이터를 구경하거나, 바로 내려받을 파일이 필요할 때.
    항목은 두 종류다. how_to_get에 어느 쪽인지 적혀 있다.
    - 분석 기관이 직접 올린 파일: files에 다운로드 주소가 있음. 라이선스·기간은 대개 '미기재'.
    - 원본 포털을 가리키는 항목: 파일은 없고 original_page(공공데이터포털 등)와 라이선스가 있음.
    """
    items = _analysis_datasets(max_age=0)
    out = {"total": len(items), "datasets": [_dataset_view(ds) for ds in items]}
    old = _called_as.get()
    if old:
        out["notice"] = f"'{old}'은(는) list_analysis_datasets로 이름이 바뀌었고 인자를 받지 않습니다. 전체 목록을 돌려줍니다. {REFRESH_TIP}"
    return out


if os.environ.get("MOLIT_DEBUG"):
    # 개발자 점검용. AI가 평소 탐색에 끌어다 쓰지 않도록 MOLIT_DEBUG를 켰을 때만 도구로 등록함.
    @mcp.tool()
    @_safe
    def raw_response(api: Literal["search", "dataset"], query: str) -> str:
        """[개발자 점검용] API 원본 응답을 그대로 본다. 데이터 탐색에는 쓰지 말 것."""
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

1. search_data로 '{theme}'와 관련 단어들을 한 단어씩 검색해 후보 데이터를 넓게 모아.
   결과에 나온 키워드를 다음 검색어로 써서 최소 5번 이상 넓혀가.
2. 서로 엮을 수 있어 보이는 데이터는 get_detail에 url을 넣어 파일 목록·받는 곳·저작권을 확인해.
   (list_analysis_datasets는 별개의 작은 목록이라 검색 결과의 상세 확인에는 쓸 수 없음)
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
    import logging
    log = logging.getLogger("uvicorn.error")
    token = token.strip().strip('"').strip("'")

    def _clean(raw: str) -> str:
        """'Bearer xxx', 'xxx', 따옴표·공백 섞인 값까지 토큰만 뽑아냄."""
        v = raw.strip().strip('"').strip("'")
        if v.lower().startswith("bearer"):
            v = v[6:].strip()
        return v.strip('"').strip("'")

    async def _deny(send, status, msg):
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"text/plain"),
                                (b"www-authenticate", b"Bearer")]})
        await send({"type": "http.response.body", "body": msg.encode()})

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            # 로그인 방식 탐색 요청엔 "OAuth 없음"(404)으로 답해서 헤더 인증으로 넘어가게 함
            if path.startswith("/.well-known/"):
                await _deny(send, 404, "no oauth")
                return
            headers = dict(scope.get("headers") or [])
            raw = headers.get(b"authorization", b"").decode("utf-8", "ignore")
            if not raw:
                log.warning("[auth] Authorization 헤더 없음 → 401 (%s %s)", scope.get("method"), path)
                await _deny(send, 401, "missing token")
                return
            got = _clean(raw)
            if not hmac.compare_digest(got.encode(), token.encode()):
                log.warning("[auth] 토큰 불일치 → 401 (받은 값 길이 %d / 서버 값 길이 %d, 앞 4자 %r)",
                            len(got), len(token), got[:4])
                await _deny(send, 401, "wrong token")
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
