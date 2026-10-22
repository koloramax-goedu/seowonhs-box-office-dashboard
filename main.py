import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone, date

# 1. 스트림릿 페이지 기본 설정 (제목, 레이아웃)
st.set_page_config(
    page_title="박스오피스 순위 조회",
    page_icon="🎬",
    layout="wide"
)

# 2. 한국 표준시(KST, UTC+9) 기준으로 '어제' 날짜 계산 (달력의 최대 선택 가능 일자)
kst = timezone(timedelta(hours=9))
yesterday_kst = (datetime.now(kst) - timedelta(days=1)).date()

st.title("🎬 박스오피스 순위 조회")

# 달력(date_input)으로 날짜 선택 기능 추가 (최대 선택 날짜는 '어제'로 제한)
selected_date = st.date_input(
    "📅 조회할 날짜를 선택하세요 (최대 어제 날짜까지 선택 가능)",
    value=yesterday_kst,
    max_value=yesterday_kst,
    min_value=date(2004, 1, 1)  # KOBIS 데이터 시작 시점
)

# API 요청용 날짜 문자열(YYYYMMDD) 및 화면 표시용 문자열(YYYY년 MM월 DD일)
target_dt = selected_date.strftime("%Y%m%d")
display_date = selected_date.strftime("%Y년 %m월 %d일")

st.subheader(f"🗓️ {display_date} 박스오피스")

# 3. 비밀 금고(st.secrets)에서 API 키 불러오기
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("❌ API 키(KOBIS_KEY)가 설정되지 않았습니다.")
    st.info("""
    **💡 확인 및 해결 안내:**
    - **로컬 실행 시:** 프로젝트 폴더 내 `.streamlit/secrets.toml` 파일을 만들고 아래 코드를 작성하세요.
      ```toml
      KOBIS_KEY = "발급받은_인증키"
      ```
    - **Streamlit Cloud 배포 시:** 대시보드의 `App Settings` ➡️ `Secrets` 메뉴에 `KOBIS_KEY = "발급받은_인증키"`를 추가하세요.
    """)
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

# 4. KOBIS API 데이터 조회 함수 (동일 날짜 재조회 시 캐시 활용)
@st.cache_data(ttl=3600)
def fetch_box_office(key: str, date_str: str):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": key, "targetDt": date_str}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as err:
        return None, f"네트워크 통신 중 오류가 발생했습니다: {err}"

api_data, network_error = fetch_box_office(api_key, target_dt)

# 5. 네트워크 통신 에러 처리
if network_error:
    st.error("❌ 데이터 요청 실패")
    st.info(f"""
    **💡 확인해야 할 사항:**
    - 인터넷 연결 상태를 확인해 주세요.
    - 영화관입장권통합전산망(KOBIS) 서버 응답이 지연되고 있을 수 있습니다.
    - 상세 에러 내용: `{network_error}`
    """)
    st.stop()

# 6. KOBIS API 내 오류 발생 처리 (faultInfo 응답)
if "faultInfo" in api_data:
    fault = api_data["faultInfo"]
    st.error(f"❌ KOBIS API 오류 발생: {fault.get('message', '인증 실패')}")
    st.info("""
    **💡 확인해야 할 사항:**
    - `st.secrets`에 등록한 `KOBIS_KEY`가 정확한지 확인해 주세요.
    - KOBIS 개발자 센터에서 키가 정상 승인 상태인지, 일일 사용량을 초과하지 않았는지 확인해 주세요.
    """)
    st.stop()

# 7. 데이터 유효성 검사 (영화 목록이 비어있는 경우)
box_office_result = api_data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ 선택하신 날짜의 박스오피스 데이터가 존재하지 않습니다.")
    st.info("""
    **💡 확인 안내:**
    - **그날은 아직 집계 전입니다.**
    - 집계 일정에 따라 데이터 업데이트까지 시간이 걸릴 수 있으니 다른 날짜를 선택해 주세요.
    """)
    st.stop()

# 8. 판다스 데이터프레임 변환 및 숫자형 변환
df = pd.DataFrame(daily_list)

numeric_columns = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]
for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

# 9. 순위 증감(rankInten) 화살표 표시 및 누적관객 100만 이상(🏆) 가공
def format_rank_change(val):
    if val > 0:
        return f"🔺 {val}"  # 순위 상승 (빨간 위 화살표)
    elif val < 0:
        return f"🔹 {abs(val)}"  # 순위 하락 (파란 아래/기호 표시)
    return "-"

def format_movie_title(row):
    title = row["movieNm"]
    # 누적 관객수가 100만 명(1,000,000) 이상인 경우 이름 옆에 트로피 이모지 추가
    if row["audiAcc"] >= 1_000_000:
        return f"{title} 🏆"
    return title

df["순위변동"] = df["rankInten"].apply(format_rank_change)
df["표시영화명"] = df.apply(format_movie_title, axis=1)

# 10. 1위 영화 상단 지표 카드 3장
top1_movie = df.iloc[0]

st.subheader(f"🥇 1위 영화: {top1_movie['표시영화명']}")

col1, col2, col3 = st.columns(3)
col1.metric(label="당일 관객수", value=f"{top1_movie['audiCnt']:,} 명")
col2.metric(label="누적 관객수", value=f"{top1_movie['audiAcc']:,} 명")
col3.metric(label="스크린수", value=f"{top1_movie['scrnCnt']:,} 개")

st.markdown("---")

# 11. 관객수 상위 5편 막대그래프
st.subheader("📊 관객수 상위 5개 영화")

top5_df = df.head(5)[["movieNm", "audiCnt"]].copy()
top5_df = top5_df.rename(columns={"movieNm": "영화명", "audiCnt": "관객수"})

st.bar_chart(
    data=top5_df,
    x="영화명",
    y="관객수",
    use_container_width=True
)

st.markdown("---")

# 12. 전체 박스오피스 표 출력
st.subheader("📋 전체 박스오피스 순위표")

# 요구사항 컬럼 조합: 순위, 순위증감, 영화명, 개봉일, 관객수, 누적관객, 스크린수
selected_df = df[["rank", "순위변동", "표시영화명", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
selected_df.columns = ["순위", "순위증감", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# 천 단위 쉼표 포맷팅
display_df = selected_df.copy()
display_df["관객수"] = display_df["관객수"].map("{:,}".format)
display_df["누적관객"] = display_df["누적관객"].map("{:,}".format)
display_df["스크린수"] = display_df["스크린수"].map("{:,}".format)

st.dataframe(
    display_df,
    hide_index=True,
    use_container_width=True
)
