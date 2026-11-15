국토교통부 데이터통합채널 협력형 분석센터의 https://data.molit.go.kr/anals/open-api/apiView/1, https://data.molit.go.kr/anals/open-api/apiView/2 api 설명 마크다운화
# 통합검색 조회 API

| 항목 | 내용 | 항목 | 내용 |
|---|---|---|---|
| API명 | 통합검색 조회 API | 사용범위 | 외부망 |
| 서비스 URL | `http://openapi.molit.go.kr/api/openapi/search/getOpenApiSearchList` | | |
| Content-Type | applycation/json | 메소드 | GET |
| 데이터포맷 | JSON | API 유형 | HTTP OPEN API |
| 유효기간 | 1년 마다 갱신필요 | 수정일 | 2022-12-09 |

## 요청변수 (Request Parameter)

| 항목명(국문) | 항목명(영문) | 타입 | 필수여부 | 샘플데이터 | 설명 |
|---|---|---|---|---|---|
| 서비스키 | serviceKey | string | 필수 | | 통합채널에서 발급받은 인증키 |
| 페이지 번호 | page | number | 필수 | 1 | 페이지 번호 [기본값 : 1] |
| 한 페이지 결과 수 | perPage | number | 필수 | 20 | 페이지 당 출 수 [기본값 : 20] |
| 결과 형식 | returnType | string | 필수 | JSON | 응답의 데이터 타입을 설정할 수 있습니다. XML 타입의 응답결과를 얻기 위해서는 XML 값으로 설정 [기본값 : JSON] |
| 검색어 | searchQuery | string | 필수 | | 검색어를 입력하세요. |
| 카테고리 | categoryNames | array | | 국토도시,주택토지,교통물류,항공,도로철도,일반,융합(기타) | 국토도시,주택토지,교통물류,항공,도로철도,일반,융합(기타) |
| 데이터 타입 | dataTypes | array | | dataset,dataservice | 데이터셋, 데이터서비스 두 가지 타입으로 나누어져 있으며 "dataset", "dataservice" 중 다중 선택 가능합니다. |

## 출력결과 (Response Element)

| 항목명1(국문) | 항목명1(영문) | 항목명2(국문) | 항목명2(영문) | 타입 | 필수여부 | 샘플데이터 | 설명 |
|---|---|---|---|---|---|---|---|
| header | header | | | object | 필수 | | |
| | | 결과코드 | resultCode | string | 필수 | INFO-00 | |
| | | 결과메시지 | resultMsg | string | 필수 | 정상 | |
| | | 페이지 번호 | page | number | 필수 | 1 | 조회 된 페이지 번호 |
| | | 한 페이지 결과 수 | perPage | number | 필수 | 20 | 조회 된 페이지 당 줄 수 |
| | | 조회 결과 수 | currentCount | number | 필수 | 20 | 조회 된 결과 수 |
| | | 전체 결과 수 | totalCount | number | 필수 | 40 | 검색 된 전체 결과 수 |
| 결과 리스트 | items | | | array | 필수 | [] | 검색 된 결과 리스트 |
| | | 제목 | title | string | | 국토교통부_2D 지도 API | 제목 |
| | | 설명 | description | string | | Openlayer 3.10.1 버전(이하 ol3)을 기반으로 .... | 설명 |
| | | 카테고리 | categoryName | string | | 일반 | 카테고리 |
| | | 제공기관 | agentName | string | | 기관명 | 제공기관 |
| | | 키워드 | keyword | string | | 키워드 | 키워드 |
| | | 상세페이지 | detailPage | string | | URL | 상세 페이지 URL |
| | | 등록일 | issued | string | | 2022-11-11T13:00:00.000Z | 등록일 |
| | | 수정일 | modified | string | | 2022-11-11T13:00:00.000Z | 수정일 |

## 샘플코드 (Sample Code)

**JSON** — `http://openapi.molit.go.kr//api/openapi/search/getOpenApiSearchList`

​```json
{
  "serviceKey": "발급받은 인증키",
  "page": 1,
  "perPage": 20,
  "returnType": "JSON",
  "searchQuery": "교통",
  "categoryNames": "국토도시,주택토지,교통물류,항공,도로철도,일반,융합(기타)",
  "dataTypes": "dataset,dataservice"
}
​```

## 에러메시지 (Error Message)

| 에러코드 | 설명 |
|---|---|
| ERROR-01 | 어플리케이션 에러 |
| ERROR-02 | 데이터베이스 에러 |
| ERROR-03 | 데이터없음 에러 |
| ERROR-04 | HTTP 에러 |
| ERROR-05 | 서비스 연결실패 에러 |
| ERROR-10 | 잘못된 요청 파라메터 에러 |
| ERROR-12 | 해당 오픈API서비스가 없거나 폐기됨 |
| ERROR-20 | 서비스 접근거부 |
| ERROR-21 | 일시적으로 사용할 수 없는 서비스 키 |
| ERROR-22 | 서비스 요청제한횟수 초과에러 |
| ERROR-23 | 서비스 신청중 |
| ERROR-30 | 등록되지 않은 서비스키 |
| ERROR-31 | 기한 만료된 서비스키 |
| ERROR-32 | 등록되지 않은 IP |
| ERROR-33 | 서명되지 않은 호출 |
| ERROR-34 | 사용자 정보가 없습니다. |
| ERROR-35 | 접근 권한이 없습니다. |
| ERROR-36 | 기타에러 |

# 분석 데이터셋 조회 API

## 기본정보

| 항목 | 내용 |
|---|---|
| API명 | 분석 데이터셋 조회 API |
| 사용범위 | 외부망 |
| 서비스 URL | http://openapi.molit.go.kr/api/openapi/dataset/getOpenApiDatasetList |
| Content-Type | applycation/json |
| 메소드 | GET |
| 데이터포맷 | JSON |
| API 유형 | HTTP OPEN API |
| 유효기간 | 1년 마다 갱신필요 |
| 수정일 | 2022-12-09 |

## 요청변수

| 항목명1(국문) | 항목명1(영문) | 항목명2(국문) | 항목명2(영문) | 타입 | 필수여부 | 샘플데이터 | 설명 |
|---|---|---|---|---|---|---|---|
| 서비스키 | serviceKey | | | string | 필수 | | 통합채널에서 발급받은 인증키 |
| 페이지 번호 | page | | | number | 필수 | 1 | 페이지 번호[기본값 : 1] |
| 한 페이지 결과 수 | perPage | | | number | 필수 | 20 | 페이지 당 줄 수[기본값 : 20] |
| 결과 형식 | returnType | | | string | 필수 | JSON,XML | 응답의 데이터 타입을 설정할 수 있습니다. XML 타입의 응답결과를 얻기 위해서는 XML 값으로 설정[기본값 : JSON] |
| 제목 | title | | | string | | | 제목 |
| 제공기관 | creator | | | string | | | 제공기관 |

## 출력변수

| 항목명1(국문) | 항목명1(영문) | 항목명2(국문) | 항목명2(영문) | 타입 | 필수여부 | 샘플데이터 | 설명 |
|---|---|---|---|---|---|---|---|
| 데이터셋 데이터 목록 | datasetDataList | | | | 필수 | | 해당 데이터셋에서 등록한 상세 데이터의 메타 정보 |
| | | 데이터명 | dataNm | string | 필수 | | |
| | | url 대민망 | urlOutr | string | 필수 | | |
| 현재개수 | currentCount | | | number | 필수 | | |
| 페이지 번호 | page | | | number | 필수 | 1 | |
| 페이지 당 줄 수 | perPage | | | number | 필수 | 20 | |
| 총 개수 | totalCount | | | number | 필수 | 36 | |
| 접근권한 | accessRights | | | string | 필수 | | |
| 제목 | title | | | string | 필수 | | |
| 카테고리 | conceptName | | | string | 필수 | 일반 or 국토도시 or 융합(기타) | |
| 설명 | description | | | string | 필수 | | |
| 제공기관 | creatorNm | | | string | 필수 | 국토지리정보원 | |
| 관리기관 | publisherNm | | | string | 필수 | 한국토지주택공사 | |
| 사용언어 | language | | | string | 필수 | 한글 or 영어 | |
| 키워드 | keyword | | | string | 필수 | 상의,입주,배경 | |
| URL | landingPage | | | string | 필수 | | |
| 라이센스 | license | | | string | 필수 | 공공저작물_출처표시 | |
| 유효기간 시작일 | temporalStartDate | | | string | 필수 | 2021-01-11 | yyyy-mm-dd |
| 유효기간 종료일 | temporalEndDate | | | string | 필수 | 2021-01-11 | yyyy-mm-dd |
| 등록일 | issued | | | string | 필수 | 2021-01-11 | yyyy-mm-dd |
| 수정일 | modified | | | string | 필수 | 2021-01-11 | yyyy-mm-dd |

## 샘플코드

JSON	http://openapi.molit.go.kr//api/openapi/dataset/getOpenApiDatasetList

```json
{
          "serviceKey": "발급받은 인증키",
          "page": 1,
          "perPage": 20,
          "returnType": "JSON",
          "title": "교통",
          "creator": "국토교통부"
}
```

## 에러메세지

| 에러코드 | 설명 |
|---|---|
| ERROR-01 | 어플리케이션 에러 |
| ERROR-02 | 데이터베이스 에러 |
| ERROR-03 | 데이터없음 에러 |
| ERROR-04 | HTTP 에러 |
| ERROR-05 | 서비스 연결실패 에러 |
| ERROR-10 | 잘못된 요청 파라메터 에러 |
| ERROR-12 | 해당 오픈API서비스가 없거나 폐기됨 |
| ERROR-20 | 서비스 접근거부 |
| ERROR-21 | 일시적으로 사용할 수 없는 서비스 키 |
| ERROR-22 | 서비스 요청제한횟수 초과에러 |
| ERROR-23 | 서비스 신청중 |
| ERROR-30 | 등록되지 않은 서비스키 |
| ERROR-31 | 기한 만료된 서비스키 |
| ERROR-32 | 등록되지 않은 IP |
| ERROR-33 | 서명되지 않은 호출 |
| ERROR-34 | 사용자 정보가 없읍니다. |
| ERROR-35 | 접근 권한이 없습니다. |
| ERROR-36 | 기타에러 |