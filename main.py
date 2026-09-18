# -*- coding: utf-8 -*-
"""
어제의 영화 박스오피스를 보여주는 스트림릿 앱
- 데이터 출처: KOBIS(영화진흥위원회) 오픈API - 일별 박스오피스
- 인증키는 st.secrets["KOBIS_KEY"] 에서 읽어옵니다. (코드에는 절대 넣지 않습니다)
"""

import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ----------------------------------------------------------------------
# 1. 기본 설정 
# ----------------------------------------------------------------------

# KOBIS 일별 박스오피스 조회 API 주소
API_URL = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"

# 페이지 기본 설정 (제목, 넓은 화면 레이아웃)
st.set_page_config(page_title="어제의 박스오피스", layout="wide")


def get_yesterday_kst() -> str:
    """
    '어제' 날짜를 한국 시간(KST) 기준으로 계산해서 yyyymmdd 형식 문자열로 돌려줍니다.

    주의:
    - 스트림릿 클라우드 서버의 시계는 한국 시간이 아닐 수 있습니다.
    - 그래서 datetime.now()를 그냥 쓰지 않고, zoneinfo로 '한국 시간이 지금 몇 시인지'를
      직접 계산한 뒤에 하루를 뺍니다.
    """
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    yesterday_kst = now_kst - timedelta(days=1)
    return yesterday_kst.strftime("%Y%m%d")


# ----------------------------------------------------------------------
# 2. API 호출 (같은 날짜는 1시간 동안 다시 부르지 않고 캐시 사용)
# ----------------------------------------------------------------------

@st.cache_data(ttl=3600)  # ttl=3600초 = 1시간. 같은 target_dt로 부르면 캐시된 값을 재사용합니다.
def fetch_box_office(target_dt: str, api_key: str) -> dict:
    """
    KOBIS API를 호출해서 원본 응답(JSON을 딕셔너리로 변환한 것)을 그대로 돌려줍니다.

    성공/실패 판단은 이 함수를 호출하는 쪽(main 함수)에서 합니다.
    - 여기서는 '요청 자체가 실패했는지'만 예외로 처리합니다.
    - 'faultInfo가 왔는지', '영화 목록이 비었는지' 같은 내용 판단은 밖에서 합니다.
    """
    params = {
        "key": api_key,
        "targetDt": target_dt,
    }
    # timeout을 꼭 지정해서, 서버 응답이 없을 때 앱이 무한정 멈추지 않게 합니다.
    response = requests.get(API_URL, params=params, timeout=10)
    response.raise_for_status()  # 상태코드가 200이 아니면 여기서 예외 발생
    return response.json()


def to_int(value: str) -> int:
    """
    API에서 숫자가 전부 문자열("1,234" 또는 "1234")로 오기 때문에
    쉼표를 제거하고 정수로 바꿔주는 도우미 함수입니다.
    """
    if value is None or value == "":
        return 0
    return int(str(value).replace(",", ""))


# ----------------------------------------------------------------------
# 3. 화면 구성 시작
# ----------------------------------------------------------------------

st.title("🎬 어제의 박스오피스")

# 3-1. 인증키 확인
# secrets에 KOBIS_KEY가 없으면 API를 호출하기도 전에 안내하고 멈춥니다.
if "KOBIS_KEY" not in st.secrets:
    st.error(
        "인증키를 찾을 수 없습니다.\n\n"
        "스트림릿 클라우드의 [Settings] → [Secrets]에 아래 형식으로 등록해 주세요.\n\n"
        'KOBIS_KEY = "발급받은_인증키"'
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]
target_dt = get_yesterday_kst()

# 화면에 조회 기준 날짜를 사람이 읽기 좋은 형식(yyyy-mm-dd)으로 보여줍니다.
pretty_date = f"{target_dt[0:4]}-{target_dt[4:6]}-{target_dt[6:8]}"
st.caption(f"조회 기준일(한국시간, 어제): {pretty_date}")

# ----------------------------------------------------------------------
# 4. API 호출 및 오류 처리
# ----------------------------------------------------------------------

try:
    raw_data = fetch_box_office(target_dt, api_key)
except requests.exceptions.RequestException:
    # 인터넷 연결 문제, 타임아웃, KOBIS 서버 장애 등 '요청 자체'가 실패한 경우
    st.error(
        "박스오피스 데이터를 불러오는 데 실패했습니다.\n\n"
        "다음을 확인해 주세요.\n"
        "1. 인터넷(네트워크) 연결 상태\n"
        "2. KOBIS 서버가 정상 동작 중인지 (잠시 후 다시 시도)\n"
        "3. API 주소가 올바른지"
    )
    st.stop()

# 4-1. faultInfo 상자 확인 (인증키가 틀렸을 때 등, 상태코드는 200이지만 오류가 담겨 옵니다)
if "faultInfo" in raw_data:
    fault_message = raw_data["faultInfo"].get("message", "알 수 없는 오류")
    st.error(
        "KOBIS API에서 오류를 반환했습니다.\n\n"
        f"오류 내용: {fault_message}\n\n"
        "다음을 확인해 주세요.\n"
        "1. Secrets에 등록한 KOBIS_KEY 값이 정확한지 (오탈자, 앞뒤 공백)\n"
        "2. 발급받은 인증키가 아직 유효한지 (KOBIS 홈페이지에서 확인)\n"
        "3. 요청 변수(targetDt 형식 등)가 올바른지"
    )
    st.stop()

# 4-2. 정상 응답 구조인지 확인 후 영화 목록 꺼내기
box_office_result = raw_data.get("boxOfficeResult", {})
movie_list = box_office_result.get("dailyBoxOfficeList", [])

# 4-3. 영화 목록이 비어 있는 경우
if not movie_list:
    st.warning(
        "해당 날짜의 박스오피스 데이터가 비어 있습니다.\n\n"
        "다음을 확인해 주세요.\n"
        "1. 조회 날짜가 너무 이른 시각이라 KOBIS 측 집계가 아직 안 됐을 수 있습니다.\n"
        "2. targetDt 형식(yyyymmdd, 8자리)이 올바른지\n"
        "3. 잠시 후 새로고침해서 다시 시도해 보세요."
    )
    st.stop()

# ----------------------------------------------------------------------
# 5. 데이터 정리 (문자열 숫자를 진짜 숫자로 변환)
# ----------------------------------------------------------------------

rows = []
for movie in movie_list:
    rows.append(
        {
            "순위": to_int(movie.get("rank")),
            "영화명": movie.get("movieNm", ""),
            "개봉일": movie.get("openDt", ""),
            "관객수": to_int(movie.get("audiCnt")),
            "누적관객": to_int(movie.get("audiAcc")),
            "스크린수": to_int(movie.get("scrnCnt")),
        }
    )

df = pd.DataFrame(rows)
# 순위를 숫자 기준으로 정렬 (문자열이면 "10"이 "2"보다 앞에 오는 실수가 생길 수 있어서 방지)
df = df.sort_values("순위").reset_index(drop=True)

# ----------------------------------------------------------------------
# 6. 1위 영화 - 지표 카드 3장
# ----------------------------------------------------------------------

top_movie = df.iloc[0]

st.subheader(f"🏆 1위: {top_movie['영화명']}")

col1, col2, col3 = st.columns(3)
col1.metric("어제 관객수", f"{top_movie['관객수']:,}명")
col2.metric("누적 관객수", f"{top_movie['누적관객']:,}명")
col3.metric("스크린수", f"{top_movie['스크린수']:,}개")

st.divider()

# ----------------------------------------------------------------------
# 7. 관객수 상위 5편 - 막대그래프
# ----------------------------------------------------------------------

st.subheader("📊 관객수 상위 5편")

top5 = df.sort_values("관객수", ascending=False).head(5)
# streamlit의 bar_chart는 인덱스를 x축 라벨로 사용하므로 영화명을 인덱스로 지정합니다.
chart_data = top5.set_index("영화명")["관객수"]
st.bar_chart(chart_data)

st.divider()

# ----------------------------------------------------------------------
# 8. 전체 박스오피스 표
# ----------------------------------------------------------------------

st.subheader("📋 전체 박스오피스")

# 표에서도 숫자 컬럼에 천 단위 구분 쉼표를 넣어 보기 좋게 표시합니다.
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "관객수": st.column_config.NumberColumn(format="%d"),
        "누적관객": st.column_config.NumberColumn(format="%d"),
        "스크린수": st.column_config.NumberColumn(format="%d"),
    },
)
