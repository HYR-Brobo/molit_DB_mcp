# 국토교통부 데이터 검색 MCP

AI로 국토교통부 데이터통합채널의 데이터 **목록과 상세 정보**를 검색하는 도구입니다. “자율주행 관련 데이터를 찾아줘”처럼 물으면 관련 데이터의 제목, 제공기관, 원본 페이지, csv 다운링크 혹은 공개 api안내 페이지를 찾습니다. 데이터 파일 자체를 가져오거나 개별 제공기관의 API를 호출하지는 않습니다.

처음 설정할 때 Python, 데이터통합채널의 Open API 인증키(`MOLIT_KEY`)필요합니다. 실행 방법은 둘 중 하나를 고르세요.

| 실행 위치 | AI 연결 방법 |
|---|---|
| Render등 무료 서버 | AI의 사용자 지정 웹 커넥터 |
| 내 컴퓨터 |  로컬 MCP |

> `MOLIT_KEY`는 이 프로젝트의 **데이터통합채널 검색 API**에 쓰는 키입니다. 검색 결과에 나오는 개별 데이터의 API 키와 다릅니다. `MCP_TOKEN`은 웹에 공개한 MCP 서버를 보호하는 별도 비밀번호입니다. 두 값 모두 Git 저장소에 넣지 마세요.

`MCP_TOKEN`은 개인이 아래 명령어 등을 통해 임의로 생성하는 키입니다.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```


## 목차

- [사용법](#사용법)
- [기술 설명: 도구와 응답 형식](#기술-설명-도구와-응답-형식)
- [1. 국토교통부 Open API 인증키 받기](#1-국토교통부-open-api-인증키-받기)
- [2. Render 무료 웹 서버에 올리기](#2-render-무료-웹-서버에-올리기)
  - [Claude에 웹 MCP 연결](#claude에-웹-mcp-연결)
- [3. 내 컴퓨터에서 실행](#3-내-컴퓨터에서-실행)
  - [설치](#설치)
  - [로컬 터미널에 인증키 넣기](#로컬-터미널에-인증키-넣기)
  - [Claude Desktop 연결](#claude-desktop-연결)
  - [Claude Code 연결](#claude-code-연결)
- [문제가 생기면](#문제가-생기면)

## 사용법

Claude에 다음처럼 요청하세요.

> 국토교통부 데이터에서 자율주행 관련 데이터를 검색하고, 쓸 만한 항목 3개의 상세 정보와 실제 받는 방법을 알려줘.

처음 연결한 뒤에는 **“`search_data`로 버스를 검색해줘”**라고 요청해 실제 검색이 되는지도 확인하세요.

서버는 `search_data`(통합 목록 검색), `get_detail`(항목 상세 확인), `list_analysis_datasets`(별도의 분석 데이터셋 목록)를 제공합니다. 파일이나 개별 API를 실제로 사용하려면 결과에 표시된 원본 제공기관에서 별도의 신청이나 인증이 필요할 수 있습니다.

## 1. 국토교통부 Open API 인증키 받기

1. [인증키 신청/내역](https://data.molit.go.kr/anals/open-api/authentication)에서 **인증키 발급**을 진행합니다. 사이트에서 로그인을 요구하면 먼저 로그인하세요.
2. [Open API 목록](https://data.molit.go.kr/anals/open-api/apiList)에서 이 프로젝트가 사용하는 **통합검색 조회 API**와 **분석 데이터셋 조회 API**의 기능을 각각 신청합니다. API 설명은 [통합검색 조회 API](https://data.molit.go.kr/anals/open-api/apiView/1), [분석 데이터셋 조회 API](https://data.molit.go.kr/anals/open-api/apiView/2)에서 확인할 수 있습니다.
3. 발급된 **데이터통합채널 인증키**를 아래 설정의 `MOLIT_KEY`에 입력합니다. 신청 상태에 따라 호출이 거부되면 위 페이지에서 인증키와 두 API의 신청 상태를 확인하세요.

프로젝트에 옮겨 적은 API 명세는 [API사용법.md](API사용법.md)에 있습니다. 다른 국토교통부 서비스나 공공데이터포털에서 발급한 키와 혼동하지 마세요.

## 2. Render 무료 웹 서버에 올리기

Claude 웹(`claude.ai`)에서도 연결하려면 이 방법을 사용합니다. Render의 **Public Git Repository**에 이 프로젝트의 공개 저장소 주소를 입력하면 바로 가져와 배포할 수 있습니다. 별도로 저장소를 만들거나 포크할 필요는 없습니다.

1. [Render](https://render.com/)에 로그인하고 https://dashboard.render.com/에서 오른쪽 위 **+ New → Web Service**를 선택합니다. 프로젝트 화면에서 시작한다면 **Create new service → Web Services → New Web Service**로 들어가도 됩니다.
2. **Source Code → Public Git Repository** 탭을 선택합니다.
3. 주소 입력란에 아래 URL을 붙여넣고 **Connect**를 누릅니다.

```text
https://github.com/HYR-Brobo/molit_DB_mcp
```

연결 후 아래와 같이 설정합니다. Project는 선택 사항입니다. 새 프로젝트를 만들고 싶다면 **Projects → Create new project**에서 이름을 입력하고 Environment name은 기본값인 **Production**으로 두면 됩니다.

| Render 설정 | 입력값 |
|---|---|
| Source Code | `HYR-Brobo / molit_DB_mcp` |
| Name | 원하는 서비스 이름 |
| Project | 선택 사항. 만든 프로젝트가 있으면 선택 |
| Branch | `main` |
| Region | 선택할 수 있으면 Singapore (Southeast Asia) |
| Root Directory | 비워둠 |
| Language | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python molit_mcp.py --web` |
| Compute | **Free ($0 / month)** |

같은 설정 화면 아래의 **Environment Variables → Add Environment Variable**에서 아래 두 줄을 추가합니다. 왼쪽 **KEY**에는 이름을, 오른쪽 **VALUE**에는 실제 값을 입력하세요. Render가 제공하는 `PORT`를 프로그램이 자동으로 읽으므로 직접 설정할 필요가 없습니다.

| 이름 | 값 |
|---|---|
| `MOLIT_KEY` | 데이터통합채널 인증키 |
| `MCP_TOKEN` | 직접 만든 16자 이상의 무작위 비밀 문자열 |

토큰은 로컬에서 `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`로 만들 수 있습니다. 이 명령이 출력한 문자열을 Render의 `MCP_TOKEN`에 저장하고, 아래 Claude 요청 헤더에도 **같은 문자열**을 사용합니다. [Render 환경변수 안내](https://render.com/docs/configure-environment-variables)를 참고하세요.

화면 아래에 **$0 / month**가 표시되는지 확인한 뒤 **Deploy web service**를 누릅니다. 배포 상태가 **Live**가 되면 서비스에 표시된 `https://…onrender.com` 주소를 복사하세요. Claude에 입력할 주소는 **자신의 서비스 주소 뒤에 `/mcp`를 붙인 것**입니다. 예: `https://내-서비스.onrender.com/mcp`.

Render Free 웹 서비스는 요청이 15분 동안 없으면 중지됩니다. 다음 요청 때 다시 시작하는 데 약 1분 걸릴 수 있고 월별 무료 사용량 제한도 있습니다. 처음 연결이 지연되면 다시 시도하세요. [Render 무료 서비스 안내](https://render.com/docs/free)

### Claude에 웹 MCP 연결

Claude의 **플러그인 → 추가 → 커스텀 커넥터 추가**를 엽니다. 화면 버전에 따라 **Customize → Connectors → + Add → Add custom connector**로 표시될 수도 있습니다.

1. **이름**에 알아보기 쉬운 이름을 입력합니다. 예: 국토부 데이터.
2. **MCP 서버 URL**에 자신의 Render 서비스 주소 뒤에 `/mcp`를 붙여 입력하고 **계속**을 누릅니다.
3. 인증은 **로그인 없음(No sign in)**을 선택하고 **요청 헤더(Request headers)**에 아래 값을 추가합니다.

| Header name | Header value |
|---|---|
| `Authorization` | `Bearer 여기에_MCP_TOKEN_값` (`Bearer` 뒤에 한 칸 띄움) |

저장 후 해당 커넥터를 **Connect**하고 대화창의 **+ → Connectors**에서 켭니다. Claude 웹 커넥터는 Claude 서버에서 공개 HTTPS 주소로 접속하므로 `localhost:8000/mcp`는 사용할 수 없습니다. Claude 무료 계정의 사용자 지정 커넥터 수 제한 등 현재 조건은 [Claude 공식 안내](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)를 확인하세요.

## 3. 내 컴퓨터에서 실행

### 설치

Python 3와 [Git](https://git-scm.com/downloads)을 설치합니다. 터미널에서 아래 명령을 실행하세요. 저장소를 이미 내려받았다면 `git clone`은 건너뛰세요.

```bash
git clone https://github.com/HYR-Brobo/molit_DB_mcp.git
cd molit_DB_mcp
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows PowerShell에서는 마지막 두 줄을 아래 명령으로 바꿉니다.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 로컬 터미널에 인증키 넣기

터미널에서 직접 서버를 실행하거나 점검할 때는 `MOLIT_KEY` 환경변수에 발급받은 키를 넣습니다. 키의 앞뒤 따옴표는 셸 문법이며, 실제 키 값에는 포함되지 않습니다.

Linux 또는 macOS의 bash:

```bash
export MOLIT_KEY='발급받은_데이터통합채널_인증키'
test -n "$MOLIT_KEY" && echo 'MOLIT_KEY 설정됨'
```

Windows PowerShell:

```powershell
$env:MOLIT_KEY = '발급받은_데이터통합채널_인증키'
if ($env:MOLIT_KEY) { 'MOLIT_KEY 설정됨' }
```

이 값은 **현재 터미널에서 시작한 프로그램에만** 전달되며, 터미널을 닫으면 사라집니다. bash에서 매번 입력하지 않으려면 `~/.bashrc`에 같은 `export` 줄을 추가할 수 있지만, 키가 파일에 평문으로 저장됩니다. 실제 키를 확인하려고 `echo $MOLIT_KEY`를 실행하면 화면에 키가 그대로 표시되므로 위 명령처럼 설정 여부만 확인하세요.

아래 Claude Desktop 방식에서는 터미널의 `export` 대신 설정 파일의 `env`에 키를 넣습니다. Claude Desktop이 터미널에서 실행되지 않을 수도 있어 두 설정은 서로 대체되지 않습니다. 발급받은 키는 임의로 URL 인코딩하지 말고 원래 값을 입력하세요. 이 프로그램이 API 요청을 만들 때 `requests`로 쿼리 파라미터를 처리합니다.

### Claude Desktop 연결

Claude Desktop의 로컬 MCP 구성 파일 `claude_desktop_config.json`을 엽니다. 위치는 macOS에서 `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows에서 `%APPDATA%\Claude\claude_desktop_config.json`입니다. 기존에 `mcpServers`가 있다면 그 안에 `molit-data` 항목을 추가하세요. 아래 경로는 **자신의 컴퓨터에 있는 실제 절대 경로**로 바꿉니다.

```json
{
  "mcpServers": {
    "molit-data": {
      "command": "/절대경로/molit_DB_mcp/.venv/bin/python",
      "args": ["/절대경로/molit_DB_mcp/molit_mcp.py"],
      "env": {
        "MOLIT_KEY": "발급받은_데이터통합채널_인증키"
      }
    }
  }
}
```

Windows에서는 `command`를 `C:\\경로\\molit_DB_mcp\\.venv\\Scripts\\python.exe`, `args`의 파일 경로를 `C:\\경로\\molit_DB_mcp\\molit_mcp.py` 형태로 씁니다. JSON 안의 역슬래시는 두 개씩 적어야 합니다. Claude Desktop을 완전히 종료하고 다시 실행한 뒤, 대화창의 **+ → Connectors**에서 도구가 보이는지 확인하세요. 이 방식은 현재 컴퓨터의 Claude Desktop에만 적용됩니다. [Claude Desktop 로컬 MCP 안내](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop), [MCP Python SDK 연결 안내](https://py.sdk.modelcontextprotocol.io/get-started/real-host/)

### Claude Code 연결

Claude Code를 쓴다면 터미널에서 아래 명령으로 등록할 수도 있습니다. 경로와 키를 실제 값으로 바꾸세요. 키가 셸 기록에 남을 수 있으므로 공유 컴퓨터에서는 주의하세요.

```bash
claude mcp add molit-data --env MOLIT_KEY=발급받은_인증키 -- /절대경로/molit_DB_mcp/.venv/bin/python /절대경로/molit_DB_mcp/molit_mcp.py
```

Claude Code에서 `/mcp`를 실행해 연결 상태를 확인합니다. [MCP Python SDK 연결 안내](https://py.sdk.modelcontextprotocol.io/get-started/real-host/)

## 문제가 생기면

| 증상 | 확인할 곳 |
|---|---|
| `MOLIT_KEY 환경변수에 인증키가 없습니다` | Claude Desktop 설정의 `env` 또는 Render의 `MOLIT_KEY` 값 |
| Claude 웹 커넥터 연결 실패 | URL 끝의 `/mcp`, 요청 헤더의 `Authorization: Bearer ...`, Render의 `MCP_TOKEN` 확인 |
| Render 배포 실패 | Build/Start Command, Root Directory, Render 배포 로그 |
| 첫 연결이나 첫 검색이 시간 초과 | Render Free 서버가 잠에서 깨는 중일 수 있음. Live 상태를 확인하고 다시 시도 |
| `get_detail` 등 도구가 보이지 않음 | Claude에서 커넥터를 껐다 켜거나 다시 연결 |
| API가 `ERROR-30` 또는 `ERROR-31`을 반환 | 데이터통합채널 인증키의 등록 및 유효기간 확인 ([API 오류 목록](API사용법.md)) |

## 기술 설명: 도구와 응답 형식

### 도구
| 도구 | 보는 목록 | 나오는 것 |
|---|---|---|
| `search_data` | 통합 목록 (1만 건 이상) | 제목·종류(`kind`: 파일형/Open API형/분석과제)·기관·키워드·설명·상세페이지 주소. 같은 데이터의 다른 등록본(원본 포털판·`기관명_` 공공데이터포털판·`(FILE)`판)은 한 항목의 `variants`에 묶음. 결과가 0건이거나 너무 많으면 `hint`에, 결과가 있으면 `next_step`에 다음 할 일이 나옴 |
| `get_detail` | 통합 목록의 항목 (최대 10개) | `urls`에 상세 주소 목록을 넣으면 파일 목록·원본 포털 주소·저작권·받는 방법, 그리고 사이트가 꼽은 유사 데이터 `related` (인증키 없이 사이트 내부 API 사용) |
| `list_analysis_datasets` | 분석 데이터셋 목록 (몇 건) | 파일 다운로드 주소·라이선스·원본 페이지 |

두 목록은 별개다. `list_analysis_datasets`는 `search_data` 결과의 상세 조회가 아니며,
겹치는 항목은 `search_data` 결과에 `analysis_dataset`으로 자동으로 붙어 나온다.

검색 API 응답에는 파일형/Open API형 표시가 없다. 그래서 두 종류가 섞인 검색이면 같은 조건으로 Open API형만 한 번 더 조회해
`kind`를 나눈다. Open API형이 100건을 넘거나 그 조회가 실패하면 `kind`는 `데이터`로 남는다 (`get_detail`의 `type`으로 확인).

상세 조회는 `get_detail(urls=["9423", "11856545"])`처럼 묶어 호출한다.
인자는 `urls` 하나다(문자열 하나도 받음). 한 건이면 상세 하나를, 여러 건이면 `{count, items}`를 반환한다.
옛 인자 `url`은 도구 목록에서 뺐다. 옛 목록을 든 커넥터가 `url`로 불러도 서버가 `urls`로 넘겨 처리한다(`Server.call_tool`).
인자가 둘이면 모델이 쉬운 `url`로 한 건씩 여러 번 부르는 일이 실제로 있어서 하나로 합쳤다. 10개를 넘으면 처음 10개와 나머지 재호출 안내를 반환한다.

`related`의 `relationship`은 유사도 점수가 아니라 제목으로 먼저 가린다. 기관명 접두어·`(FILE)`·`[API]`·`(5분 지연)`을 뗀 제목을 비교해서
- 같으면 **같은 데이터의 다른 등록본**
- 끝 괄호만 다르고 그 괄호가 단위(`5분 단위`, `1개월 단위` 등)면 **같은 데이터의 다른 집계 단위** (`differs_in`에 양쪽 괄호 표시)
- 끝 괄호만 다르고 단위가 아니면 **같은 데이터의 다른 구분**
- 제목이 다르고 유사도 100이면 **같은 데이터의 다른 등록본 후보**, 그 밖은 **유사 데이터**

예: 콘존 1개월 단위의 related에 나오는 5분·15분 단위는 유사도가 64라 점수만으로는 구별되지 않지만 제목으로 잡힌다.
같은 데이터 계열이 목록 앞쪽에 온다. `kind`는 원본 `type`이 있거나 제목에 `(FILE)`이 있을 때만 넣는다.
`related_hint`는 묶음 응답에서 항목마다 반복하지 않고 맨 위에 한 번만 넣는다.
다른 등록본·집계 단위의 다운로드 방법, 라이선스, 기간을 그대로 적용하지 말고, 추천·안내할 후보만 상세를 확인한다.
자동승인인 API도 `how_to_get`에 있는 활용신청 등의 절차를 안내해야 한다.
인자 변경을 도구 목록에 반영하려면 서버 재시작 후 커넥터를 다시 연결한다.

### `data_types=['all']` 검색
`all`은 분석과제·출품작·보도자료까지 섞고 정렬도 달라져 데이터가 뒤로 밀린다.
2026-11 '자율주행' `all` 검색은 1·2쪽에 부산 자율주행버스 Open API 8종이 하나도 없어서, AI가 운행 데이터가 없다고 잘못 결론 냈다.
그래서 `all` 검색 결과가 한 쪽을 넘으면 `hint`에 "data_types 없이 다시 검색"을 붙인다.
인자 설명에도 같은 내용이 있지만, 재연결 전에는 옛 설명이 보이므로 응답에도 넣는다.

### 응답 크기
도구 응답은 AI의 컨텍스트에 그대로 쌓이므로 짧게 보낸다.
- 응답은 공백 없는 JSON 한 줄이다(`_compact`). MCP 서버 기본 변환은 `indent=2`라 들여쓰기만으로 토큰을 15%쯤 더 쓴다.
  `structured_output=False`로 등록해 같은 내용이 `structuredContent`로 한 번 더 가지 않게 한다.
- 값이 없는 필드(`null`·`""`·빈 목록)는 뺀다. `results`·`items`·`datasets`는 비어도 남긴다.
- `get_detail` 항목에는 상세 url 대신 `id`만 넣는다(호출한 쪽이 url을 이미 갖고 있음). `related`의 `url`은 다음 조회에 쓰므로 그대로 둔다.
- `api_spec`에서 앞 operation과 파라미터·응답 필드 이름이 같은 operation은 목록을 빼고 `same_params_as`에 그 path만 남긴다(지역별로 쪼갠 API 대응. 교통카드 합성데이터 명세 2,852 → 약 700토큰).
- 검색마다 붙는 `next_step`은 두 문장만 둔다. 확인 범위·related·활용신청 규칙은 도구 설명과 서버 안내문에 있다.

2026-11 측정(o200k 토크나이저 기준): `search_data` 20건 5,732 → 4,947, `get_detail` 4건 묶음 3,409 → 2,787, 1건 975 → 718.

### Open API형의 `api_spec`
Open API형(`type`이 `Open API형`)이면 `get_detail`이 원본 포털의 페이지(`landing_page`)를 열어 `api_spec`을 붙인다.
원본 페이지 구조가 포털·등록 방식마다 달라서(2026-11, 68건 측정) 명세를 뽑을 수 있을 때만 뽑고, 못 뽑으면 이유를 `status`·`note`로 알린다.

| `status` | 뜻 | 측정 비율 |
|---|---|---|
| `swagger` | 페이지에 실린 Swagger에서 `base_url`·`operations`(필수/선택 파라미터·응답 필드)를 뽑음 | 37% |
| `html` | 명세가 페이지 본문 표에 있음. 공공데이터포털이면 `endpoints`(요청주소)만 뽑음 | 18% |
| `link` | 공공데이터포털 'LINK'형. 실제 API는 제공기관 사이트에 있고 '바로가기'를 눌러야 주소가 나옴 | 24% |
| `no_content` | 자바스크립트로 그리는 포털이라 자동으로 열면 빈 화면 (부산·제주 등) | 12% |
| `elsewhere` | 본문에 명세가 없고 별도 탭에 있음 (서울 열린데이터광장 등) | 4% |
| `not_found` / `unreachable` | 페이지 삭제(404) / 접속 실패(SSL 등) | 6% |

인증키는 넣지 않는다. 활용신청·키 발급은 사용자가 해야 하므로 `how_to_get`이 그 절차를 안내한다.
페이지는 1시간 동안 기억해 두고(접속 실패는 제외), 파일형에서는 열지 않는다.

### Claude가 `get_detail`을 못 찾을 때
Claude 앱은 연결된 도구가 많으면 도구를 이름만 올려 두고 필요할 때 불러온다(지연 로딩). 이때 `get_detail`을 불러오지 않으면
"도구가 없다"고 잘못 결론 낼 수 있다. 그래서 `search_data` 응답의 `next_step`에 "이름만 있으면 불러와 쓰고, 아예 없으면 재연결"을 매번 적어 보낸다.
서버 안내문(`instructions`)에도 같은 내용이 있지만, 안내문은 연결할 때 한 번 받은 것이 계속 남아 있어서 재연결 전에는 바뀐 내용이 안 보인다.
응답 본문은 매번 새로 가므로 배포하면 바로 적용된다.

### 환경변수
- `MOLIT_KEY`: 분석센터 Open API 인증키 (필수)
- `MCP_TOKEN`: `--web` 실행 시 요청을 통과시킬 비밀 토큰 (16자 이상)
- `MOLIT_DEBUG`: 값을 넣으면 원본 응답을 보는 점검용 도구 `raw_response`가 추가됨

### 도구 이름이 바뀐 뒤 "Unknown tool"이 나올 때
`--web` 서버는 stateless라 도구 목록이 바뀌어도 클라이언트에 알리지 못한다. 그래서 이미 연결돼 있던 커넥터는
옛 목록(`get_dataset`, `raw_response`)을 그대로 보여주고 옛 이름으로 호출한다.
- 서버 쪽: 옛 이름 `get_dataset`은 `list_analysis_datasets`로 넘겨 처리하고, 없는 이름에는 지금 쓸 수 있는 도구를 알려준다.
  도구 이름을 또 바꾸면 `molit_mcp.py`의 `RENAMED_TOOLS`에 옛 이름을 추가한다.
- 클라이언트 쪽: 커넥터를 껐다 켜거나 다시 연결하면 도구 목록이 새로 받아진다.
