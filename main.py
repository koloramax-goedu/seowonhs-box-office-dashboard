import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# 1. 스트림릿 페이지 기본 설정 (제목, 레이아웃 등)
st.set_page_config(
    page_title="어제 박스오피스 순위",
    page_icon="🎬",
    layout="wide"
)

# 2. 한국 표준시(KST, UTC+9) 기준으로 '어제' 날짜 계산
# 배포 서버(Streamlit Cloud)의 시계가 UTC 기준이므로 한국 시간대로 명시적 변환합니다.
kst = timezone(timedelta(hours=9))
yesterday_kst = datetime.now(kst) - timedelta(days=1)

# API 요청에 쓰일 여덟 자리 날짜 문자열 (YYYYMMDD)
target_dt = yesterday_kst.strftime("%Y%m%d")
# 화면 상단 제목 표시용 날짜 (YYYY년 MM월 DD일)
display_date = yesterday_kst.strftime("%Y년 %m월 %d일")

st.title(f"🎬 어제({display_date}) 박스오피스 순위")

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

# 4. KOBIS API 데이터 조회 함수 (1시간 동안 캐시 처리하여 반복 요청 방지)
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

# API 호출 execution
api_data, network_error = fetch_box_office(api_key, target_dt)

# 5. 네트워크 통신 에러 처리
if network_error:
    st.error(f"❌ 데이터 요청 실패")
    st.info(f"""
    **💡 확인해야 할 사항:**
    - 인터넷 연결 상태를 확인해 주세요.
    - 영화관입장권통합전산망(KOBIS) 서버 응답이 지연되고 있을 수 있습니다.
    - 상세 에러 내용: `{network_error}`
    """)
    st.stop()

# 6. KOBIS 응답 내부 오류 처리 (200 상태코드로 응답하지만 faultInfo가 들어온 경우)
if "faultInfo" in api_data:
    fault = api_data["faultInfo"]
    st.error(f"❌ KOBIS API 오류 발생: {fault.get('message', '인증 실패')}")
    st.info("""
    **💡 확인해야 할 사항:**
    - `st.secrets`에 등록한 `KOBIS_KEY`가 정확한지 확인해 주세요.
    - KOBIS 개발자 센터에서 키가 정상 승인 상태인지, 일일 사용량을 초과하지 않았는지 확인해 주세요.
    """)
    st.stop()

# 7. 데이터 유효성 검사 (영화 목록 존재 여부)
box_office_result = api_data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ 해당 날짜의 박스오피스 데이터가 비어 있습니다.")
    st.info("""
    **💡 확인해야 할 사항:**
    - KOBIS 집계 서버의 업데이트 지연 문제일 수 있습니다.
    - 잠시 후 다시 새로고침해 주세요.
    """)
    st.stop()

# 8. 판다스 데이터프레임 변환 및 숫자 형변환 (KOBIS API는 숫자를 문자열로 전달함)
df = pd.DataFrame(daily_list)

numeric_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt"]
for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

# 9. 1위 영화 상단 메트릭 카드 3개 표시
top1_movie = df.iloc[0]

st.subheader(f"🏆 1위 영화: {top1_movie['movieNm']}")

col1, col2, col3 = st.columns(3)
col1.metric(label="어제 관객수", value=f"{top1_movie['audiCnt']:,} 명")
col2.metric(label="누적 관객수", value=f"{top1_movie['audiAcc']:,} 명")
col3.metric(label="스크린수", value=f"{top1_movie['scrnCnt']:,} 개")

st.markdown("---")

# 10. 관객수 상위 5편 막대그래프 표시
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

# 11. 전체 박스오피스 표 출력
st.subheader("📋 전체 박스오피스 순위표")

# 요구 항목 필터링: 순위, 영화명, 개봉일, 관객수, 누적관객, 스크린수
selected_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()

# 표에 표시될 열 이름 한글화
selected_df.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# 숫자 보기 좋게 쉼표 포맷팅
display_df = selected_df.copy()
display_df["관객수"] = display_df["관객수"].map("{:,}".format)
display_df["누적관객"] = display_df["누적관객"].map("{:,}".format)
display_df["스크린수"] = display_df["스크린수"].map("{:,}".format)

# 테이블 출력
st.dataframe(
    display_df,
    hide_index=True,
    use_container_width=True
)
