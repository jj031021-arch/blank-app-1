import streamlit as st
import pandas as pd
import googlemaps
import folium
from streamlit_folium import st_folium
import requests

# ---------------------------------------------------------
# 1. 초기 설정 및 API 키 로드
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="베를린 여행 & 안전 지도")

# API 키 가져오기 (배포 환경 vs 로컬 환경 처리)
try:
    GMAPS_API_KEY = st.secrets["google_maps_api_key"]
except:
    # 로컬 테스트용 키 (배포 시에는 Streamlit Cloud Secrets에 입력하므로 비워둬도 됨)
    GMAPS_API_KEY = "YOUR_GOOGLE_MAPS_API_KEY_HERE"

# 구글맵 클라이언트 설정
try:
    gmaps = googlemaps.Client(key=GMAPS_API_KEY)
except ValueError:
    st.error("Google Maps API 키가 설정되지 않았습니다.")
    gmaps = None

# ---------------------------------------------------------
# 2. 데이터 관리 (Session State - 임시 저장소)
# ---------------------------------------------------------
if 'user_places' not in st.session_state:
    st.session_state['user_places'] = []  # 사용자가 추가한 맛집 리스트
if 'reviews' not in st.session_state:
    st.session_state['reviews'] = []      # 후기 리스트

# ---------------------------------------------------------
# 3. 유틸리티 함수 (환율, 날씨, 구글맵, 데이터처리)
# ---------------------------------------------------------

@st.cache_data
def get_exchange_rate():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/EUR"
        data = requests.get(url).json()
        return data['rates']['KRW']
    except:
        return 1450.0 # 기본값

@st.cache_data
def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current_weather=true"
        data = requests.get(url).json()
        return data['current_weather']
    except:
        return {"temperature": "--", "weathercode": 0}

@st.cache_data
def get_google_places(place_type, keyword=None, min_rating=0.0):
    if not gmaps: return []
    berlin_center = (52.5200, 13.4050)
    places_result = []
    
    try:
        results = gmaps.places_nearby(
            location=berlin_center,
            radius=5000, # 반경 5km
            type=place_type,
            keyword=keyword
        )
        for place in results.get('results', []):
            rating = place.get('rating', 0)
            if rating >= min_rating:
                places_result.append({
                    "name": place['name'],
                    "lat": place['geometry']['location']['lat'],
                    "lng": place['geometry']['location']['lng'],
                    "rating": rating,
                    "address": place.get('vicinity', ''),
                    "type": place_type
                })
        return places_result
    except Exception as e:
        return []

def geocode_address(address):
    if not gmaps: return None, None
    try:
        geocode_result = gmaps.geocode(address)
        if geocode_result:
            loc = geocode_result[0]['geometry']['location']
            return loc['lat'], loc['lng']
    except:
        return None, None
    return None, None

@st.cache_data
def load_and_process_crime_data(csv_file):
    try:
        # 1. CSV 파일 읽기
        df = pd.read_csv(csv_file)
        
        # 2. 최신 연도 데이터만 필터링 (데이터가 누적된 경우를 대비)
        latest_year = df['Year'].max()
        df_latest = df[df['Year'] == latest_year]

        # 3. 범죄 위험도 계산 (주요 범죄 합산)
        # 로컬(Local) 범죄 합계나 주요 강력 범죄를 합쳐서 'Risk_Score'를 만듭니다.
        # 파일 컬럼: Robbery, Theft, Burglary, Injury, Agg_assault, Drugs 등
        cols_to_sum = ['Robbery', 'Street_robbery', 'Injury', 'Agg_assault', 'Theft', 'Burglary', 'Drugs']
        
        # 실제 CSV에 존재하는 컬럼만 합산
        existing_cols = [c for c in cols_to_sum if c in df_latest.columns]
        df_latest['Total_Crime'] = df_latest[existing_cols].sum(axis=1)

        # 4. 'District' (구) 기준으로 그룹화하여 합계 계산
        district_crime = df_latest.groupby('District')['Total_Crime'].sum().reset_index()
        
        return district_crime
    except Exception as e:
        st.error(f"범죄 데이터 처리 중 오류 발생: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------
# 4. 메인 화면 구성
# ---------------------------------------------------------
st.title("🐻 베를린 여행 가이드 (Berlin Trip & Safety)")
st.caption("안전한 여행을 위해 범죄 위험도와 추천 장소를 한눈에 확인하세요.")

# (1) 정보 대시보드
col1, col2 = st.columns(2)
rate = get_exchange_rate()
weather = get_weather()

with col1:
    st.info(f"💶 현재 환율: 1 EUR = **{rate:.0f} KRW**")
with col2:
    st.info(f"⛅ 베를린 날씨: **{weather['temperature']}°C**")

st.divider()

# ---------------------------------------------------------
# 5. 사이드바 - 필터 및 입력
# ---------------------------------------------------------
st.sidebar.title("🛠️ 지도 설정")

st.sidebar.subheader("1. 레이어 켜기/끄기")
show_crime = st.sidebar.toggle("🚨 범죄 위험지역 (구역별 색상)", value=True)
show_restaurant = st.sidebar.toggle("🍽️ 맛집 (평점 4.5+)", value=True)
show_hotel = st.sidebar.toggle("🏨 숙박시설", value=True)
show_tourist = st.sidebar.toggle("📸 관광지", value=True)
show_user_places = st.sidebar.toggle("⭐ 내가 추가한 장소", value=True)

st.sidebar.divider()

st.sidebar.subheader("2. 나만의 맛집 추가")
with st.sidebar.form("add_place"):
    u_addr = st.text_input("주소 (구글맵 검색 가능한 주소)")
    u_name = st.text_input("장소 이름")
    u_type = st.selectbox("종류", ["한식", "양식", "중식", "카페/디저트", "기타"])
    submitted = st.form_submit_button("지도에 추가")
    
    if submitted and u_addr and u_name:
        lat, lng = geocode_address(u_addr)
        if lat:
            st.session_state['user_places'].append({
                "name": u_name, "lat": lat, "lng": lng, 
                "category": u_type, "type": "user"
            })
            st.success(f"'{u_name}' 추가 성공!")
        else:
            st.error("주소를 찾을 수 없습니다.")

# ---------------------------------------------------------
# 6. 지도 시각화 (핵심 기능)
# ---------------------------------------------------------
st.subheader("🗺️ 베를린 인터랙티브 지도")

# 지도 초기화 (베를린 중심)
m = folium.Map(location=[52.5200, 13.4050], zoom_start=11)

# [기능 1] 범죄 위험도 Choropleth Map (구역 색칠)
if show_crime:
    crime_df = load_and_process_crime_data("Berlin_crimes.csv")
    
    if not crime_df.empty:
        # 베를린 구(District) 경계 GeoJSON URL (공개 데이터)
        berlin_geo_url = "https://raw.githubusercontent.com/funkeinteraktiv/Berlin-Geodaten/master/berlin_bezirke.geojson"
        
        # 코로플레스 맵 생성
        folium.Choropleth(
            geo_data=berlin_geo_url,
            name="범죄 위험도",
            data=crime_df,
            columns=["District", "Total_Crime"], # CSV의 구 이름, 범죄 수
            key_on="feature.properties.name",    # GeoJSON의 구 이름 속성
            fill_color="YlOrRd",                 # 노랑 -> 주황 -> 빨강
            fill_opacity=0.6,
            line_opacity=0.2,
            legend_name="범죄 발생 건수 (높을수록 위험)",
            highlight=True
        ).add_to(m)

# [기능 2] 장소 마커 표시 함수
def add_markers(data_list, color, icon_name, group_name):
    fg = folium.FeatureGroup(name=group_name)
    for item in data_list:
        # 팝업 내용
        popup_html = f"""
        <div style="width:150px">
            <b>{item['name']}</b><br>
            <span style="color:grey">{item.get('category', item.get('type', ''))}</span><br>
            ⭐ {item.get('rating', 'N/A')}
        </div>
        """
        folium.Marker(
            location=[item['lat'], item['lng']],
            popup=folium.Popup(popup_html, max_width=200),
            icon=folium.Icon(color=color, icon=icon_name, prefix='fa')
        ).add_to(fg)
    fg.add_to(m)

# 필터에 따라 마커 추가
if show_restaurant:
    res_data = get_google_places('restaurant', min_rating=4.5)
    add_markers(res_data, "green", "cutlery", "맛집")

if show_hotel:
    hotel_data = get_google_places('lodging')
    add_markers(hotel_data, "blue", "bed", "숙박")

if show_tourist:
    tour_data = get_google_places('tourist_attraction')
    add_markers(tour_data, "purple", "camera", "관광지")

if show_user_places:
    # 사용자 데이터는 아이콘 색상을 카테고리별로 다르게 하지는 않고 통일 (주황색)
    add_markers(st.session_state['user_places'], "orange", "star", "내 장소")

# 지도 그리기
st_folium(m, width="100%", height=600)

# ---------------------------------------------------------
# 7. 후기 게시판
# ---------------------------------------------------------
st.divider()
st.subheader("🗣️ 여행자 수다방 (리뷰 & 팁)")
st.caption("※ 주의: 새로고침하면 대화 내용이 사라집니다.")

# 입력 폼
with st.form("review_form", clear_on_submit=True):
    col_a, col_b = st.columns([1, 3])
    with col_a:
        r_name = st.text_input("닉네임")
        r_cat = st.selectbox("주제", ["맛집", "숙박", "관광", "치안/기타"])
    with col_b:
        r_text = st.text_area("내용을 입력하세요", height=82)
    
    r_submit = st.form_submit_button("등록하기")
    
    if r_submit and r_name and r_text:
        st.session_state['reviews'].insert(0, { # 최신글이 위로 오게
            "name": r_name, "category": r_cat, "text": r_text, "time": pd.Timestamp.now().strftime("%H:%M")
        })
        st.rerun() # 화면 갱신

# 리스트 출력
for review in st.session_state['reviews']:
    with st.chat_message("user"):
        st.write(f"**[{review['category']}] {review['name']}** ({review['time']})")
        st.write(review['text'])
