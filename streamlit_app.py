import streamlit as st
import pandas as pd
import googlemaps
import folium
from streamlit_folium import st_folium
import requests
import google.generativeai as genai

# ---------------------------------------------------------
# 1. 설정 및 API 키 안전하게 로드
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="베를린 여행 & AI 가이드")

# API 키 가져오기 (없어도 앱이 꺼지지 않도록 처리)
GMAPS_API_KEY = st.secrets.get("google_maps_api_key", "")
GEMINI_API_KEY = st.secrets.get("gemini_api_key", "")

# 클라이언트 초기화 (키가 없으면 None으로 설정)
gmaps = None
if GMAPS_API_KEY:
    try:
        gmaps = googlemaps.Client(key=GMAPS_API_KEY)
    except Exception as e:
        st.error(f"구글맵 설정 오류: {e}")

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        st.error(f"Gemini 설정 오류: {e}")

# ---------------------------------------------------------
# 2. 데이터 관리 (Session State)
# ---------------------------------------------------------
if 'user_places' not in st.session_state:
    st.session_state['user_places'] = []
if 'reviews' not in st.session_state:
    st.session_state['reviews'] = {} 
if 'messages' not in st.session_state:
    st.session_state['messages'] = []

# ---------------------------------------------------------
# 3. 데이터 및 API 함수들
# ---------------------------------------------------------
@st.cache_data
def get_exchange_rate():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/EUR"
        data = requests.get(url).json()
        return data['rates']['KRW']
    except:
        return 1450.0

@st.cache_data
def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current_weather=true"
        data = requests.get(url).json()
        return data['current_weather']
    except:
        return {"temperature": "--", "weathercode": 0}

@st.cache_data
def get_google_places_detailed(place_type, keyword=None, min_rating=0.0):
    if not gmaps: return [] # 키 없으면 빈 리스트 반환
    
    berlin_center = (52.5200, 13.4050)
    places_result = []
    
    try:
        results = gmaps.places_nearby(
            location=berlin_center,
            radius=3000,
            type=place_type,
            keyword=keyword
        )
        
        for place in results.get('results', []):
            rating = place.get('rating', 0)
            if rating >= min_rating:
                # 구글 검색 링크 생성
                search_query = f"{place['name']}+Berlin".replace(" ", "+")
                link = f"https://www.google.com/search?q={search_query}"
                
                places_result.append({
                    "name": place['name'],
                    "lat": place['geometry']['location']['lat'],
                    "lng": place['geometry']['location']['lng'],
                    "rating": rating,
                    "address": place.get('vicinity', ''),
                    "type": place_type,
                    "link": link
                })
        return places_result
    except Exception as e:
        # 화면에 에러를 띄우지 않고 조용히 넘어감 (사용자 경험 위해)
        print(f"Maps Error: {e}")
        return []

@st.cache_data
def load_crime_data(csv_file):
    try:
        # 인코딩 문제나 구분자 문제 해결을 위한 옵션 추가
        df = pd.read_csv(csv_file, on_bad_lines='skip') 
        
        # 파일에 실제 존재하는 컬럼인지 확인
        required_cols = ['Year', 'District']
        if not all(col in df.columns for col in required_cols):
            st.error("CSV 파일 형식이 맞지 않습니다. (Year, District 컬럼 필요)")
            return pd.DataFrame()

        latest_year = df['Year'].max()
        df = df[df['Year'] == latest_year]
        
        # 범죄 유형 컬럼 (파일에 있는 것만 합산)
        target_cols = ['Robbery', 'Street_robbery', 'Injury', 'Agg_assault', 'Theft', 'Burglary', 'Drugs']
        available_cols = [c for c in target_cols if c in df.columns]
        
        df['Total_Crime'] = df[available_cols].sum(axis=1)
        return df.groupby('District')['Total_Crime'].sum().reset_index()
    except FileNotFoundError:
        st.error("CSV 파일을 찾을 수 없습니다. 프로젝트 폴더에 파일이 있는지 확인하세요.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"데이터 처리 중 오류: {e}")
        return pd.DataFrame()

def get_gemini_response(prompt):
    if not GEMINI_API_KEY:
        return "API 키가 설정되지 않아 답변할 수 없습니다."
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"오류 발생: {e}"

# ---------------------------------------------------------
# 4. 메인 화면 구성
# ---------------------------------------------------------
st.title("🇩🇪 베를린: 여행, 안전, 그리고 AI")

col1, col2 = st.columns(2)
with col1:
    rate = get_exchange_rate()
    st.info(f"💶 유로 환율: {rate:.0f}원")
with col2:
    w = get_weather()
    st.info(f"⛅ 날씨: {w['temperature']}°C")

# ----------------- 사이드바 -----------------
st.sidebar.title("설정 & 메뉴")

st.sidebar.subheader("1. 지도 필터")
show_crime = st.sidebar.toggle("🚨 범죄 위험도", True)
show_res = st.sidebar.toggle("🍽️ 맛집 (4.5+)", True)
show_hotel = st.sidebar.toggle("🏨 숙박시설", False)
show_tour = st.sidebar.toggle("📸 관광지", False)

st.sidebar.subheader("2. 추천 여행 코스")
course_select = st.sidebar.radio(
    "코스를 선택하세요:",
    ("선택 안함", "🏛️ 박물관 섬 & 힙한 점심", "🕊️ 역사와 쇼핑의 조화")
)

st.sidebar.divider()
st.sidebar.info("💡 팁: 지도의 핀을 클릭하면 구글 검색으로 이동합니다.")

# ----------------- 지도 영역 -----------------
st.subheader("🗺️ 인터랙티브 지도")

m = folium.Map(location=[52.5200, 13.4050], zoom_start=13)

# 1. 범죄 지도 레이어
if show_crime:
    crime_df = load_crime_data("Berlin_crimes.csv")
    if not crime_df.empty:
        folium.Choropleth(
            geo_data="https://raw.githubusercontent.com/funkeinteraktiv/Berlin-Geodaten/master/berlin_bezirke.geojson",
            data=crime_df,
            columns=["District", "Total_Crime"],
            key_on="feature.properties.name",
            fill_color="YlOrRd",
            fill_opacity=0.5,
            line_opacity=0.2,
            name="범죄 위험도"
        ).add_to(m)

# 2. 장소 마커 리스트 (채팅방용)
all_places_for_chat = []

def add_markers_detailed(data_list, color, icon_type, type_name):
    fg = folium.FeatureGroup(name=type_name)
    for item in data_list:
        all_places_for_chat.append(item['name'])
        html = f"""
        <div style="font-family:sans-serif; width:200px">
            <h4>{item['name']}</h4>
            <p>⭐ {item['rating']}</p>
            <a href="{item['link']}" target="_blank" style="background-color:#4CAF50; color:white; padding:5px 10px; text-decoration:none; border-radius:5px; font-size:12px;">상세보기</a>
        </div>
        """
        folium.Marker(
            [item['lat'], item['lng']],
            popup=folium.Popup(html, max_width=250),
            icon=folium.Icon(color=color, icon=icon_type, prefix='fa')
        ).add_to(fg)
    fg.add_to(m)

if show_res:
    add_markers_detailed(get_google_places_detailed('restaurant', min_rating=4.5), 'green', 'cutlery', '맛집')
if show_hotel:
    add_markers_detailed(get_google_places_detailed('lodging'), 'blue', 'bed', '호텔')
if show_tour:
    add_markers_detailed(get_google_places_detailed('tourist_attraction'), 'purple', 'camera', '관광지')

# 3. 구체적인 여행 코스 (하드코딩)
# 코스 데이터 정의
courses = {
    "🏛️ 박물관 섬 & 힙한 점심": [
        {"name": "1. 보데 박물관 (출발)", "lat": 52.5218, "lng": 13.3956, "desc": "박물관 섬의 북쪽 끝, 아름다운 조각상 감상"},
        {"name": "2. 제임스 사이먼 공원", "lat": 52.5213, "lng": 13.4005, "desc": "슈프레 강변을 따라 걷는 산책로"},
        {"name": "3. Monsieur Vuong (점심)", "lat": 52.5244, "lng": 13.4085, "desc": "베를린 미테 지구의 유명한 베트남 쌀국수 맛집"},
        {"name": "4. 알렉산더 광장 (종료)", "lat": 52.5219, "lng": 13.4132, "desc": "TV 타워 구경 및 쇼핑"}
    ],
    "🕊️ 역사와 쇼핑의 조화": [
        {"name": "1. 브란덴부르크 문 (출발)", "lat": 52.5163, "lng": 13.3777, "desc": "베를린의 상징"},
        {"name": "2. 홀로코스트 추모비", "lat": 52.5139, "lng": 13.3787, "desc": "미로 같은 비석 사이 걷기"},
        {"name": "3. Mall of Berlin (쇼핑/식사)", "lat": 52.5106, "lng": 13.3807, "desc": "대형 쇼핑몰과 푸드코트"},
        {"name": "4. 체크포인트 찰리 (종료)", "lat": 52.5074, "lng": 13.3904, "desc": "분단 시절 검문소"}
    ]
}

if course_select != "선택 안함":
    selected_course = courses[course_select]
    points = []
    
    # 코스 마커 찍기
    for place in selected_course:
        points.append((place['lat'], place['lng']))
        folium.Marker(
            location=[place['lat'], place['lng']],
            tooltip=place['name'],
            popup=f"<b>{place['name']}</b><br>{place['desc']}",
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
    
    # 경로 선 그리기
    folium.PolyLine(
        locations=points,
        color="red",
        weight=5,
        opacity=0.8,
        tooltip=course_select
    ).add_to(m)

st_folium(m, width="100%", height=500)

st.divider()

# ----------------- 하단 기능 (채팅 & AI) -----------------
col_chat, col_ai = st.columns([1, 1])

# [기능 1] 장소별 소통방
with col_chat:
    st.subheader("💬 장소별 수다방")
    
    # 중복 제거 및 정렬
    unique_places = sorted(list(set(all_places_for_chat)))
    if not unique_places:
        st.warning("지도에서 장소를 불러오는 중이거나 장소가 없습니다.")
        place_options = ["(장소 없음)"]
    else:
        place_options = ["(장소를 선택하세요)"] + unique_places

    selected_place = st.selectbox("어디에 대해 이야기할까요?", place_options)

    if selected_place not in ["(장소를 선택하세요)", "(장소 없음)"]:
        st.success(f"**'{selected_place}'** 게시판 입장 완료!")
        
        if selected_place not in st.session_state['reviews']:
            st.session_state['reviews'][selected_place] = []

        with st.form(f"form_{selected_place}", clear_on_submit=True):
            user_msg = st.text_input("후기/팁을 남겨주세요")
            if st.form_submit_button("전송"):
                st.session_state['reviews'][selected_place].append(user_msg)
                st.rerun()
        
        # 최신순 출력
        for msg in st.session_state['reviews'][selected_place][::-1]:
            st.info(f"🗣️ {msg}")

# [기능 2] Gemini AI
with col_ai:
    st.subheader("🤖 Gemini 여행 비서")
    
    if not GEMINI_API_KEY:
        st.error("Gemini API 키가 설정되지 않았습니다. .streamlit/secrets.toml을 확인하세요.")
    
    chat_container = st.container(height=400)
    with chat_container:
        for message in st.session_state['messages']:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    if prompt := st.chat_input("질문하세요 (예: 비 오는 날 어디 갈까?)"):
        st.session_state['messages'].append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("Gemini가 생각 중..."):
                    response = get_gemini_response(prompt)
                    st.markdown(response)
        
        st.session_state['messages'].append({"role": "assistant", "content": response})
