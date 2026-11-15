# molit_DB_mcp
국토교통부 데이터통합채널 협력형 분석센터를 AI에게 붙이는 MCP

## 도구
| 도구 | 보는 목록 | 나오는 것 |
|---|---|---|
| `search_data` | 통합 목록 (1만 건 이상) | 제목·기관·키워드·설명·상세페이지 주소. 결과가 0건이거나 너무 많으면 `hint`에 다음 할 일이 나옴 |
| `list_analysis_datasets` | 분석 데이터셋 목록 (몇 건) | 파일 다운로드 주소·라이선스·원본 페이지 |

두 목록은 별개다. `list_analysis_datasets`는 `search_data` 결과의 상세 조회가 아니며,
겹치는 항목은 `search_data` 결과에 `analysis_dataset`으로 자동으로 붙어 나온다.

## 환경변수
- `MOLIT_KEY`: 분석센터 Open API 인증키 (필수)
- `MCP_TOKEN`: `--web` 실행 시 요청을 통과시킬 비밀 토큰 (16자 이상)
- `MOLIT_DEBUG`: 값을 넣으면 원본 응답을 보는 점검용 도구 `raw_response`가 추가됨
