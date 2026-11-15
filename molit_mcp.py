"""
국토교통 협력형 분석센터 MCP 서버
AI(Claude)가 국토부 데이터를 스스로 검색·조회하며 공모전 아이디어를 탐색하게 해주는 도구 모음.

필요한 것:  pip install "mcp[cli]" requests
인증키:     환경변수 MOLIT_KEY (MCP 등록할 때 같이 넣어줌)
"""

import contextvars
import datetime
import functools
import html as _html
import json
import os
import re
import time
from typing import Annotated, Literal
from urllib.parse import urlparse

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
DETAIL_MAX = 10     # get_detail 한 번에 확인하는 최대 개수

# 도구 이름을 바꾸면, 이미 연결돼 있던 커넥터는 옛 도구 목록을 그대로 들고 옛 이름으로 호출한다.
# (--web은 stateless라 '목록이 바뀌었다'는 알림을 보낼 수 없음) 그래서 옛 이름도 받아서 새 도구로 넘긴다.
RENAMED_TOOLS = {"get_dataset": "list_analysis_datasets"}
REMOVED_TOOLS = {"raw_response": "개발자 점검용이라 평소에는 꺼 둔 도구입니다(서버에 MOLIT_DEBUG를 넣어야 켜짐). 데이터 탐색에는 필요 없습니다."}
REFRESH_TIP = "이 커넥터가 옛 도구 목록을 보고 있으니, 사용자에게 커넥터를 껐다 켜거나 다시 연결해 도구 목록을 새로 받으라고 알려 주세요."
_called_as = contextvars.ContextVar("called_as", default=None)


class Server(_BaseServer):
    async def call_tool(self, name, arguments, *args, **kwargs):
        # get_detail의 옛 인자 url은 urls로 합쳤다. 옛 도구 목록을 든 커넥터가 url로 불러도 받아 준다.
        if name == "get_detail" and isinstance(arguments, dict) and "url" in arguments:
            arguments = dict(arguments)
            old = arguments.pop("url")
            if old is not None and not arguments.get("urls"):
                arguments["urls"] = old
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
도구는 search_data·get_detail·list_analysis_datasets 세 개다. 도구 목록에 이름만 있으면(지연 로딩) 셋을 한꺼번에 불러와 쓴다.

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
그런 단계는 우회하거나 임의로 채우지 말고, get_detail의 how_to_get대로 어느 포털에서 무엇을 받으면 되는지 사용자에게 안내한다.
자동승인인 Open API도 활용신청은 사용자가 직접 해야 하므로 그 절차를 빠뜨리지 않는다.
Open API형은 get_detail의 api_spec에 명세(status=swagger) 또는 명세를 못 뽑은 이유가 나온다. 이유가 나오면 짐작해 채우지 말고 그대로 안내한다.
같은 데이터가 5분·15분·1개월처럼 집계 단위별로 따로 등록된 경우가 많다. 찾은 항목의 단위·기간이 맞지 않으면
'없다'고 단정하기 전에 get_detail의 related에서 '같은 데이터의 다른 집계 단위'를 확인한다.""",
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


# 결과 목록 자체는 비어 있어도 남긴다(0건이라는 사실이 정보다).
_KEEP_EMPTY = {"results", "items", "datasets"}


def _prune(v):
    """None·빈 문자열·빈 목록인 필드를 뺀다. 숫자 0과 False는 남긴다."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            x = _prune(x)
            if k in _KEEP_EMPTY or x not in (None, "", [], {}):
                out[k] = x
        return out
    if isinstance(v, list):
        return [_prune(x) for x in v]
    return v


def _compact(fn):
    """도구 응답을 공백 없는 JSON 한 줄로 보낸다. MCP 서버 기본 변환(indent=2)은 들여쓰기만으로 토큰을 15%쯤 더 쓴다.
    @mcp.tool(structured_output=False)와 같이 써야 같은 내용이 structuredContent로 한 번 더 가지 않는다."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        out = fn(*args, **kwargs)
        return out if isinstance(out, str) else json.dumps(_prune(out), ensure_ascii=False, separators=(",", ":"))
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
    """상세 페이지 주소로 항목 종류를 구분. 파일형/Open API형은 주소로 안 갈려서 search_data에서 다시 나눈다."""
    url = url or ""
    if "/data-search/" in url:
        return "데이터"
    if "/asmt/" in url:
        return "분석과제"
    return "기타"


TYPE_NAMES = {"dataset": "파일형", "dataservice": "Open API형"}


def _dataservice_urls(query: str, categories) -> set | None:
    """같은 검색 조건의 Open API형 결과 주소 전부. 검색 응답엔 파일형/API형 표시가 없어서 한 번 더 물어 구분한다.
    Open API형은 파일형보다 훨씬 적어(예: '환승' 323건 중 24건) 한 쪽에 다 들어온다. 다 안 들어오면 None(구분 포기)."""
    params = {"page": 1, "perPage": 100, "searchQuery": query, "dataTypes": "dataservice"}
    if categories:
        params["categoryNames"] = ",".join(categories)
    data = _call(SEARCH_URL, params)
    items = _items(data)
    if (_total(data) or 0) > len(items):
        return None
    return {it.get("detailPage") for it in items}


# 검색할 때마다 붙으므로 짧게 둔다. 확인 범위·related·활용신청 안내 같은 규칙은 get_detail 설명과 서버 안내문에 있다.
# 지연 로딩 대비 문장만은 응답 본문에 남긴다(안내문은 재연결 전에는 갱신되지 않음, README 참고).
NEXT_STEP = (f"추천·안내할 후보만 url을 get_detail의 urls에 묶어(최대 {DETAIL_MAX}개) 받는 곳·파일·저작권을 확인한다. "
             "get_detail이 이름만 있으면 불러와 쓰고, 아예 없으면 사용자에게 커넥터 재연결을 안내한다.")

# 같은 데이터가 원본 포털판·공공데이터포털 이관판('기관명_' 접두어)·파일판('(FILE)')·'OpenAPI 조회' 껍데기로 여러 번 등록돼 있다.
# 제목에서 이 꼬리표만 떼고 같으면 하나로 묶는다. '(15분 단위)'·'(1시간 단위)'처럼 내용이 다른 꼬리표는 떼지 않는다.
_VARIANT_TAGS = re.compile(r"^\s*\[API\]\s*|\(FILE\)|\(\d+분\s*지연\)")


def _base_title(title, agency) -> str:
    t = (title or "").strip()
    if agency and t.startswith(f"{agency}_"):
        t = t[len(agency) + 1:]
    return _norm(_VARIANT_TAGS.sub("", t))


def _as_variant(row: dict) -> dict:
    return {k: row[k] for k in ("title", "kind", "url", "modified", "analysis_dataset") if row.get(k)}


def _group_variants(results: list) -> tuple[list, int]:
    """같은 기관·같은 데이터의 다른 등록본을 앞쪽 항목 하나에 variants로 묶는다. 설명이 가장 긴 등록본을 대표로 세운다.
    분석과제·출품작처럼 데이터가 아닌 항목은 묶지 않는다."""
    heads, out, merged = {}, [], 0
    for row in results:
        key = None if row["kind"] in ("분석과제", "기타") else (row["agency"], _base_title(row["title"], row["agency"]))
        head = heads.get(key) if key else None
        if head is None:
            if key:
                heads[key] = row
            out.append(row)
            continue
        merged += 1
        if len(row.get("description") or "") > len(head.get("description") or ""):
            variants = head.pop("variants", []) + [_as_variant(head)]
            head.clear()
            head.update(row, variants=variants)
        else:
            head.setdefault("variants", []).append(_as_variant(row))
    return out, merged


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
@mcp.tool(structured_output=False)
@_compact
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

    돌려주는 것: 제목·종류(kind: 파일형/Open API형/분석과제)·분야·기관·키워드·설명·상세페이지 주소(url). 데이터 '값'은 주지 않는다.
    돌려주지 않는 것: 파일 목록·원본 포털·저작권. 필요한 후보만 결과의 url을 get_detail에 넣어 확인한다 (응답의 next_step 참고).
      예외로, 결과에 analysis_dataset이 붙어 있으면 그 항목은 파일 주소·라이선스가 그 안에 이미 들어 있다.
    같은 데이터가 원본 포털판·공공데이터포털판·파일판으로 여러 번 등록된 경우 한 항목의 variants에 묶여 나온다.

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

    # 파일형/Open API형 나누기. 한 종류만 골랐으면 그대로, 섞여 있으면 Open API형 주소를 따로 받아 맞춰 본다.
    data_rows = [r for r in results if r["kind"] == "데이터"]
    picked = [t for t in types if t in TYPE_NAMES]
    if data_rows and "all" not in types and len(picked) == 1:
        for r in data_rows:
            r["kind"] = TYPE_NAMES[picked[0]]
    elif data_rows:
        try:
            api_urls = _dataservice_urls(query, categories)
        except Exception:  # noqa: BLE001  구분 못 해도 검색 결과는 그대로 돌려줌
            api_urls = None
        if api_urls is not None:
            for r in data_rows:
                r["kind"] = "Open API형" if r["url"] in api_urls else "파일형"

    results, merged = _group_variants(results)

    total = _total(data)
    out = {"query": query, "page": page, "total": total, "results": results}
    if merged:
        out["grouped"] = f"다른 등록본 {merged}건을 variants에 묶음. 과거 이력은 파일형, 실시간·최신값은 Open API형 등록본."
    hint = _search_hint(query, total, page, bool(categories or data_types))
    if hint:
        out["hint"] = hint
    if data_rows:
        out["next_step"] = NEXT_STEP
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


# 사이트 내부 API는 CSRF 이중 제출 방식을 씀: XSRF-TOKEN 쿠키 값을 X-XSRF-TOKEN 헤더로 같이 보내야 함.
# 헤더가 없으면 HTTP 200에 본문만 {"status":403,"message":"해당 페이지에 접근할 권한이 없습니다."}로 거절한다.
# 쿠키는 상세 페이지 HTML이 아니라 /api/ 아래 GET 응답에서 발급되므로, 가벼운 GET 하나로 받아 둔다.
TOKEN_URL = f"https://{HOST}/api/common/getServerProperties"
_site = requests.Session()


def _xsrf_token(refresh: bool = False) -> str:
    if refresh:
        _site.cookies.clear()
    token = _site.cookies.get("XSRF-TOKEN")
    if not token:
        _site.get(TOKEN_URL, timeout=20)
        token = _site.cookies.get("XSRF-TOKEN")
    if not token:
        raise RuntimeError("분석센터가 XSRF-TOKEN 쿠키를 주지 않음 (사이트 방식이 바뀌었을 수 있음)")
    return token


def _detail_call(seq: str) -> dict:
    body = {"resourceSeq": seq, "siteCode": "molit_anals", "algrthId": "1", "simildegerPt": 50,
            "simildegerSort": None, "hitResourceSort": None, "startRow": 0, "rowsPerPage": 10}
    for attempt in range(2):        # 토큰이 만료됐을 수 있으니 403이면 새로 받아 한 번 더
        try:
            r = _site.post(DETAIL_URL, json=body, timeout=20, headers={
                "Accept": "application/json",
                "Referer": f"https://{HOST}/anals/data-search/detail/{seq}",
                "X-XSRF-TOKEN": _xsrf_token(refresh=attempt > 0),
            })
        except requests.RequestException as e:
            raise RuntimeError(f"상세 정보 서버에 연결하지 못함: {type(e).__name__}: {e}")
        if r.status_code >= 400 and r.status_code != 403:
            raise RuntimeError(f"상세 정보 HTTP {r.status_code}: {r.text[:300]}")
        try:
            data = r.json()
        except ValueError:
            raise RuntimeError(f"상세 정보 응답이 JSON이 아님: {r.text[:300]}")
        denied = r.status_code == 403 or str(data.get("status")) == "403"
        if denied and attempt == 0:
            continue
        if not data.get("success") or not isinstance(data.get("result"), dict):
            raise RuntimeError(f"상세 정보 조회 실패: {data.get('message') or str(data)[:300]}")
        return data["result"]
    raise RuntimeError("상세 정보 조회 실패: 토큰을 새로 받아도 접근이 거부됨")


def _detail_url(seq) -> str:
    return f"https://{HOST}/anals/data-search/detail/{seq}"


def _as_urls(value) -> list[str]:
    """url 하나·리스트·JSON 리스트 문자열·쉼표로 이은 문자열을 모두 받아 리스트로."""
    if isinstance(value, (list, tuple)):
        items = value
    else:
        text = str(value).strip()
        try:
            items = json.loads(text) if text.startswith("[") else re.split(r"[,\s]+", text)
        except ValueError:
            items = re.split(r"[,\s]+", text.strip("[]"))
    return [str(x).strip().strip('"\'') for x in items if str(x).strip().strip('"\'')]


# 제목 끝의 괄호 꼬리표. '(5분 단위)'·'(1개월 단위)'처럼 같은 데이터를 다른 단위로 집계한 판을 가른다.
_TAIL = re.compile(r"\(([^()]*)\)$")
# 꼬리표가 집계 단위(시간 간격·공간 단위)를 말하는지. 아니면(예: 지역명) '다른 구분'으로만 표시한다.
_UNIT_TAG = re.compile(r"단위|\d+\s*(분|초|시간|일|주|개월|월|년)|^(일|주|월|연|년|분기|시간)별$")


def _split_tail(base: str) -> tuple[str, str]:
    """_base_title 결과에서 끝 괄호 하나를 떼어 (몸통, 꼬리표)로."""
    m = _TAIL.search(base)
    return (base[:m.start()], m.group(1)) if m else (base, "")


def _tail_label(title) -> str:
    """사람이 읽을 꼬리표(띄어쓰기 유지). 없으면 '표기 없음'."""
    m = _TAIL.search(_VARIANT_TAGS.sub("", title or "").strip())
    return m.group(1).strip() if m else "표기 없음"


def _relationship(mine: str, theirs: str, similarity, mine_title="", their_title="") -> dict:
    """제목으로 관계를 가린다. 유사도 점수로는 '같은 데이터의 다른 집계 단위'와 그냥 비슷한 데이터가 구별되지 않는다
    (예: 콘존 1개월 단위 ↔ 5분 단위가 64점). 제목은 끝의 괄호만 다르다. mine·theirs는 _base_title 결과."""
    if mine == theirs:
        return {"relationship": "같은 데이터의 다른 등록본"}
    (body_a, tag_a), (body_b, tag_b) = _split_tail(mine), _split_tail(theirs)
    if body_a and body_a == body_b and (tag_a or tag_b):
        unit = bool(_UNIT_TAG.search(tag_a) or _UNIT_TAG.search(tag_b))
        return {"relationship": "같은 데이터의 다른 집계 단위" if unit else "같은 데이터의 다른 구분",
                "differs_in": f"이 항목 ({_tail_label(mine_title)}) ↔ 이것 ({_tail_label(their_title)})"}
    # 유사도는 동일성의 증명이 아니다. 100점이어도 다른 등록본 '후보'로만 안내한다.
    try:
        same = float(similarity) == 100
    except (TypeError, ValueError):
        same = False
    return {"relationship": "같은 데이터의 다른 등록본 후보" if same else "유사 데이터"}


_REL_ORDER = {"같은 데이터의 다른 집계 단위": 0, "같은 데이터의 다른 구분": 1,
              "같은 데이터의 다른 등록본": 2, "같은 데이터의 다른 등록본 후보": 3, "유사 데이터": 4}


def _related(res: dict, seq: str) -> list:
    """사이트가 상세 화면의 '유사 데이터'로 보여주는 목록. 같은 계열의 다른 단위·다른 등록본·짝이 되는 데이터가 여기 나온다."""
    resource, agent = res.get("resource") or {}, res.get("agent") or {}
    mine = _base_title(resource.get("title"), agent.get("agentName"))
    out = []
    for s in res.get("simildegers") or []:
        other = s.get("similrResourceSeq")
        if not other or str(other) == seq:
            continue
        title, agency = s.get("title") or "", s.get("agentName")
        row = {"title": title.strip(), "agency": agency}
        # 유사 목록은 대개 type을 주지 않는다(resourceType='개방 데이터'뿐). 알 수 있을 때만 kind를 넣는다.
        kind = TYPE_NAMES.get(s.get("type"))
        if not kind and re.search(r"\(FILE\)", title, re.IGNORECASE):
            kind = "파일형(제목의 (FILE) 표기로 추정)"
        if kind:
            row["kind"] = kind
        row.update(_relationship(mine, _base_title(title, agency), s.get("simildegerPt"),
                                 resource.get("title"), title))
        row.update(similarity=s.get("simildegerPt"), url=_detail_url(other))
        out.append(row)
    out.sort(key=lambda r: _REL_ORDER.get(r["relationship"], 9))     # 같은 데이터 계열을 앞으로
    return out


RELATED_HINT = ("related는 사이트가 꼽은 미검증 후보. 단위·기간이 안 맞으면 없다고 결론 내기 전에 '다른 집계 단위'를 확인하고, "
                "다른 등록본도 받는 방법·라이선스·기간은 따로 확인한다. 추천·안내할 것만 urls로 묶어 조회.")


# ───────────── Open API형 명세 확인 ─────────────
# Open API형 랜딩 페이지는 포털·등록 방식마다 구조가 다르다. 2026-11에 68건(버스·건축물·항공·철도)을 열어 본 결과:
#   공공데이터포털 + swaggerJson 스펙 37% · 본문 표 9% · 'LINK'형(실제 API는 외부, 스펙 없음) 24% · 삭제(404) 3%
#   다른 포털 본문 9% · 별도 탭 4% · 자바스크립트 껍데기 12% · 접속 실패 3%
# 그래서 스펙은 뽑을 수 있을 때만 뽑고, 못 뽑으면 왜 못 뽑는지 status로 알려 AI가 헛걸음하거나 추측하지 않게 한다.
SPEC_TIMEOUT = 12
SPEC_TTL = 3600
SPEC_MAX_OPS = 10
SPEC_MAX_FIELDS = 20
_SPEC_CACHE: dict = {}      # landing_page → (받은 시각, 결과)
_UA = {"User-Agent": "Mozilla/5.0 (molit-data MCP)"}
_AUTH_PARAMS = {"servicekey", "apikey", "key", "authkey", "crtfckey"}
# 응답 필드에서 뺄 공통 껍데기(결과코드·쪽 번호 등). 데이터 항목만 남긴다.
_ENVELOPE = {"resultCode", "resultMsg", "numOfRows", "pageNo", "totalCount", "dataType", "header", "body", "items", "item",
             "page", "perPage", "currentCount", "matchCount", "data"}


def _js_template(raw: str) -> str:
    """swaggerJson은 JS 템플릿 문자열(`…`) 안에 있다. JS가 푸는 이스케이프(\\\\ \\` \\$)를 같이 풀어야 JSON이 되는 페이지가 있다."""
    return re.sub(r"\\([\\`$])", r"\1", raw)


def _deref(schema, defs: dict, depth: int = 0):
    while isinstance(schema, dict) and "$ref" in schema and depth < 10:
        schema = defs.get(schema["$ref"].rsplit("/", 1)[-1])
        depth += 1
    return schema if isinstance(schema, dict) else {}


def _leaf_fields(schema, defs: dict, out: list, depth: int = 0) -> None:
    """응답 스키마에서 실제 데이터 항목(잎 필드)만 'name: 설명'으로 모은다."""
    schema = _deref(schema, defs)
    if depth > 8 or not schema:
        return
    if schema.get("items"):
        _leaf_fields(schema["items"], defs, out, depth + 1)
        return
    for name, sub in (schema.get("properties") or {}).items():
        sub = _deref(sub, defs)
        if sub.get("properties") or sub.get("items"):
            _leaf_fields(sub, defs, out, depth + 1)
        elif name not in _ENVELOPE:
            desc = _short(sub.get("description"), 40)
            out.append(f"{name}: {desc}" if desc else name)


def _param_line(p: dict) -> str:
    desc = _short(p.get("description"), 40)
    return f"{p.get('name')}: {desc}" if desc else str(p.get("name"))


_SPEC_LISTS = ("required", "optional", "response_fields")


def _fold_ops(ops: list) -> list:
    """지역별·기간별로 쪼갠 API는 operation마다 같은 파라미터·응답 필드를 되풀이한다(예: 교통카드 합성데이터 9개 지역).
    앞에 나온 operation과 이름 목록이 같으면 목록을 빼고 same_params_as에 그 path만 남긴다.
    설명은 비교하지 않는다: 같은 파라미터인데 설명만 잘린 길이가 다른 경우가 있다."""
    def names(row):
        return tuple(tuple(x.split(":", 1)[0] for x in row.get(k) or []) for k in _SPEC_LISTS)
    seen, out = {}, []
    for row in ops:
        key = names(row)
        if not any(key):
            out.append(row)
        elif key in seen:
            out.append({**{k: v for k, v in row.items() if k not in _SPEC_LISTS}, "same_params_as": seen[key]})
        else:
            seen[key] = row["path"]
            out.append(row)
    return out


def _swagger_spec(s: dict) -> dict | None:
    """Swagger 2.0 / OpenAPI 3 문서 → 호출에 필요한 것만. 경로나 주소가 비어 있으면 None(LINK형이 빈 껍데기를 싣는 경우)."""
    paths = s.get("paths") or {}
    if s.get("servers"):
        base = (s["servers"][0] or {}).get("url", "")
    elif s.get("host"):
        schemes = s.get("schemes") or ["https"]
        base = f"{'https' if 'https' in schemes else schemes[0]}://{s['host']}{s.get('basePath') or ''}"
    else:
        base = ""
    if not paths or not base:
        return None
    defs = s.get("definitions") or (s.get("components") or {}).get("schemas") or {}
    ops = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        common = [p for p in item.get("parameters") or [] if isinstance(p, dict)]
        for method, op in item.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch") or not isinstance(op, dict):
                continue
            params = [_deref(p, defs) for p in common + (op.get("parameters") or [])]
            params = [p for p in params if p.get("name") and p["name"].lower() not in _AUTH_PARAMS]
            row = {"method": method.upper(), "path": path,
                   "summary": op.get("summary") or _short(op.get("description"), 80),
                   "required": [_param_line(p) for p in params if p.get("required")],
                   "optional": [_param_line(p) for p in params if not p.get("required")]}
            ok = (op.get("responses") or {}).get("200") or {}
            schema = ok.get("schema") or ((ok.get("content") or {}).get("application/json") or {}).get("schema")
            fields: list = []
            _leaf_fields(schema, defs, fields)
            if fields:
                row["response_fields"] = fields[:SPEC_MAX_FIELDS]
                if len(fields) > SPEC_MAX_FIELDS:
                    row["response_fields"].append(f"…외 {len(fields) - SPEC_MAX_FIELDS}개")
            ops.append(row)
    if not ops:
        return None
    out = {"base_url": base, "operations": _fold_ops(ops[:SPEC_MAX_OPS])}
    if len(ops) > SPEC_MAX_OPS:
        out["operations_omitted"] = len(ops) - SPEC_MAX_OPS
    return out


def _page_text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", page)))


def _fetch_api_spec(landing: str, title: str) -> dict:
    try:
        r = requests.get(landing, headers=_UA, timeout=SPEC_TIMEOUT)
    except requests.RequestException as e:
        return {"status": "unreachable",
                "note": f"원본 페이지에 자동으로 접속하지 못함({type(e).__name__}). 브라우저로는 열릴 수 있으니 landing_page를 사용자에게 안내."}
    if r.status_code == 404:
        return {"status": "not_found",
                "note": "원본 페이지가 없어짐(404). 카탈로그가 옛 정보일 수 있으니 variants·related에서 다른 등록본을 찾는다."}
    if r.status_code >= 400:
        return {"status": "unreachable", "note": f"원본 페이지가 HTTP {r.status_code}로 응답함. landing_page를 사용자에게 안내."}
    page = r.text

    m = re.search(r"swaggerJson\s*=\s*`(.*?)`", page, re.S)
    if m and m.group(1).strip():
        for raw in (m.group(1), _js_template(m.group(1))):
            try:
                spec = _swagger_spec(json.loads(raw))
            except ValueError:
                continue
            if spec:
                return {"status": "swagger",
                        "note": "원본 페이지에 실린 API 명세(Swagger)에서 뽑음. 호출 주소 = base_url + path, 인증키는 별도로 붙인다.",
                        **spec}
            break

    text = _page_text(page)
    if urlparse(landing).netloc.endswith("data.go.kr"):
        endpoints = sorted(set(re.findall(r"https?://apis\.data\.go\.kr/[\w./-]+", text)))
        if "요청주소" in text and endpoints:
            return {"status": "html", "endpoints": endpoints[:SPEC_MAX_OPS],
                    "note": "명세 파일은 없고 요청주소만 뽑음. 요청변수·출력 항목은 landing_page 본문의 '상세기능' 표(오퍼레이션별 탭)에 있다."}
        if re.search(r"API\s*유형\s*LINK", text):
            return {"status": "link",
                    "note": "공공데이터포털에는 소개만 있고 실제 API는 제공기관 사이트에 있음(LINK형). 실제 주소·명세는 landing_page에서 "
                            "활용신청 후 '바로가기'를 눌러야 나온다. 같은 데이터가 다른 포털(예: 브이월드)에도 등록돼 있으면 variants·related에서 찾는다."}
        return {"status": "unknown", "note": "공공데이터포털 페이지지만 명세 위치를 알아보지 못함. landing_page를 직접 확인."}

    # 제목이 본문에 없으면 내용을 자바스크립트로 채우는 페이지다. 요청변수 표 머리글만 있고 값이 빈 경우(도로공사·교통빅데이터)도 여기 걸린다.
    # 길이로 판단하지 않는다: 철도산업정보센터는 1,500자 남짓이어도 명세가 다 들어 있다.
    core = _norm(_VARIANT_TAGS.sub("", (title or "").split("_")[-1] if "_" in (title or "") else title or ""))
    if not core or core not in _norm(text):
        return {"status": "no_content",
                "note": "이 포털은 내용을 자바스크립트로 그려서 자동으로 열면 빈 화면만 온다. 명세는 사용자가 브라우저로 landing_page를 열어 확인해야 한다."}
    if re.search(r"요청\s*변수|요청\s*인자|요청\s*파라미터|샘플\s*(URL|데이터|코드)", text):
        out = {"status": "html",
               "note": "명세가 landing_page 본문에 있음(요청변수·샘플 표). 포털마다 형식이 달라 요청 주소 말고는 자동으로 뽑지 않았다."}
        endpoints = sorted(set(re.findall(r"(?:요청\s*(?:URL|주소)|서비스\s*URL)\s*:?\s*(https?://[^\s?<>\"']+)", text)))
        if endpoints:
            out["endpoints"] = endpoints[:SPEC_MAX_OPS]
        return out
    return {"status": "elsewhere",
            "note": "명세가 이 페이지 본문에는 없음. 포털의 'Open API'·'명세' 탭이나 별도 문서에서 확인해야 한다."}


def _api_spec(landing: str, title: str) -> dict:
    """Open API형의 원본 페이지를 열어 명세를 뽑거나, 못 뽑으면 이유(status·note)를 준다. 같은 페이지는 1시간 동안 다시 받지 않는다."""
    if not landing:
        return {"status": "no_page", "note": "명세를 볼 원본 페이지가 등록돼 있지 않음."}
    hit = _SPEC_CACHE.get(landing)
    if hit and time.time() - hit[0] < SPEC_TTL:
        return hit[1]
    out = _fetch_api_spec(landing, title)
    if out["status"] != "unreachable":      # 일시적인 접속 실패는 기억하지 않는다
        _SPEC_CACHE[landing] = (time.time(), out)
    return out


def _api_how(portal: str, rights, spec: dict) -> str:
    # rights는 공공데이터포털에선 '개발단계 : 자동승인 / …'이지만 다른 포털에선 저작권 문구가 들어 있다. 승인 정보일 때만 붙인다.
    approval = f" (승인 방식: {rights})" if rights and "승인" in str(rights) else ""
    if spec["status"] in ("swagger", "html") and (spec.get("base_url") or spec.get("endpoints")):
        return (f"Open API다. 파일이 아니라 호출해서 받는다. '{portal}'에서 활용신청해 인증키를 받은 뒤 api_spec대로 호출한다{approval}. "
                "활용신청·인증키 발급은 사용자가 직접 해야 하고, 인증키 없이 부르면 실패한다.")
    if spec["status"] == "html":
        return (f"Open API다. '{portal}'의 landing_page 본문에 명세가 있다(api_spec.note). "
                f"활용신청·인증키 발급은 사용자가 직접 해야 한다{approval}.")
    return (f"Open API다. 명세를 자동으로 확인하지 못했다(api_spec.status·note 참고). "
            f"'{portal}'의 landing_page에서 활용신청과 명세 확인을 하도록 사용자에게 안내한다{approval}.")


@mcp.tool(structured_output=False)
@_compact
@_safe
def get_detail(
    urls: Annotated[list[str] | str, Field(
        description="search_data·related·variants에서 고른 상세 url(…/data-search/detail/숫자) 또는 숫자 id. "
                    f"확인할 후보를 모두 리스트로 한 번에 넣는다(최대 {DETAIL_MAX}개). 한 건씩 여러 번 부르지 않는다.")],
) -> dict:
    """search_data에서 고른 항목의 상세 페이지 내용을 본다. 상세 페이지를 브라우저·curl로 직접 여는 대신 이걸 쓴다.

    돌려주는 것: 원본 포털 이름·주소, 파일 목록(제목·형식·크기·수정일·주소), 저작권, how_to_get(받는 방법),
    related(사이트가 꼽은 유사 데이터: 같은 데이터의 다른 집계 단위·다른 등록본·함께 쓸 만한 데이터).
    파일 '내용'은 주지 않는다. 대부분 파일은 제공기관 포털에 있고, 그 포털이 로그인·설문을 요구하면 사용자에게 안내한다.
    Open API형이면 api_spec이 붙는다. status가 swagger면 호출 주소(base_url+path)·필수/선택 파라미터·응답 필드가 들어 있어
    어떤 조건으로 무엇을 조회할 수 있는지 판단할 수 있다. 그 밖의 status(html·link·no_content·elsewhere·not_found·unreachable)는
    명세를 자동으로 못 뽑은 것이니 note대로 안내하고, 파라미터·코드값을 짐작해서 채우지 않는다. 인증키는 사용자가 활용신청으로 받아야 한다.

    한 건이면 상세 하나를, 여러 건이면 {count, items:[...]}를 돌려준다.
    api_spec의 operation에 same_params_as가 있으면 그 path의 operation과 파라미터·응답 필드가 같다.
    답변에서 추천하거나 받는 방법을 안내할 데이터는 검색 결과 설명만 믿지 말고 여기서 확인한다 (urls로 한 번에).
    related·variants는 전부 열 필요 없다. 그중 추천·안내할 것만 확인하고, 다른 등록본·집계 단위의 받는 방법·저작권·기간을 그대로 적용하지 않는다.
    related의 relationship이 '같은 데이터의 다른 집계 단위'면, 원하는 단위·기간이 없다고 결론 내기 전에 그 항목을 확인한다.
    """
    inputs = _as_urls(urls)
    if not inputs:
        return {"error": "urls가 비어 있음. search_data 결과의 url을 넣어 주세요."}
    if len(inputs) == 1:
        out = _detail_one(inputs[0])
        if out.get("related"):
            out["related_hint"] = RELATED_HINT
        return out
    items = []
    for u in inputs[:DETAIL_MAX]:
        try:
            items.append(_detail_one(u))
        except Exception as e:  # noqa: BLE001  하나가 실패해도 나머지는 돌려줌
            items.append({"input": u, "error": f"{type(e).__name__}: {_mask(e)}"})
    out = {"count": len(items)}
    if any(it.get("related") for it in items):
        out["related_hint"] = RELATED_HINT      # 항목마다 반복하지 않고 맨 위에 한 번
    out["items"] = items
    if len(inputs) > DETAIL_MAX:
        out["notice"] = f"한 번에 {DETAIL_MAX}개까지만 봄. 나머지 {len(inputs) - DETAIL_MAX}개는 다시 호출."
    return out


def _detail_one(url: str) -> dict:
    m = re.search(r"(\d+)\D*$", url.strip())
    if not m:
        return {"input": url, "error": "url에서 id(끝의 숫자)를 찾지 못함. search_data 결과의 url을 그대로 넣어 주세요."}
    seq = m.group(1)
    res = _detail_call(seq)
    resource, system, agent = res.get("resource") or {}, res.get("system") or {}, res.get("agent") or {}
    if not resource:
        return {"input": url, "error": f"id {seq}에 해당하는 항목이 없음. search_data 결과의 url인지 확인해 주세요."}

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
    spec = None
    if resource.get("type") == "dataservice":
        spec = _api_spec(landing, resource.get("title"))
    if direct:
        how = "files의 download_url로 바로 받을 수 있음"
    elif spec is not None:
        how = _api_how(portal, resource.get("rights"), spec)
    elif files and landing:
        how = (f"파일 {len(files)}개가 '{portal}'에 있음. landing_page(또는 각 파일의 page_url)에서 받아야 함. "
               "로그인·활용신청·이용 설문을 요구할 수 있으니 사용자에게 안내할 것.")
    elif landing:
        how = f"등록된 파일 목록은 없음. '{portal}'의 landing_page에서 확인해야 함 (Open API형이면 거기서 활용신청)."
    else:
        how = "받을 수 있는 경로가 등록돼 있지 않음"

    out = {
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
        "id": seq,      # 상세 url은 호출한 쪽이 이미 갖고 있다. 묶음 응답에서 항목을 맞춰 볼 id만 둔다.
    }
    if spec is not None:
        out["api_spec"] = spec
    related = _related(res, seq)
    if related:
        out["related"] = related
    return out


@mcp.tool(structured_output=False)
@_compact
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
    @mcp.tool(structured_output=False)
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
2. 서로 엮을 수 있어 보이는 데이터는 get_detail의 urls 인자에 리스트를 한 번에 넣어 파일 목록·받는 곳·저작권을 확인해.
   응답의 related·variants에 다른 집계 단위나 등록본이 있으면 후보에 넣고, 사용할 후보만 상세를 확인해.
   찾은 데이터의 단위·기간이 안 맞으면 없다고 단정하기 전에 related의 '같은 데이터의 다른 집계 단위'를 확인해.
   다른 항목의 다운로드 방법·라이선스·기간을 그대로 적용하지 마. 자동승인이어도 활용신청 등 how_to_get의 절차를 안내해.
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
