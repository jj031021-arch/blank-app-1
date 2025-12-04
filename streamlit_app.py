import streamlit as st  # <--- 이 친구가 무조건 1등으로 있어야 합니다!
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

# API 키 가져오기 (오류 방지 처리)
GMAPS_API_KEY = st.secrets.get("google_maps_api_key", "")
GEMINI_API_KEY = st.secrets.get("gemini_api_key", "")

# 클라이언트 초기화
gmaps = None
if GMAPS_API_KEY:
    try:
        gmaps = googlemaps.Client(key=GMAPS_API_KEY)
    except Exception as e:
        st.error(f"❌ 구글맵 클라이언트 설정 오류: {e}")

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        st.error(f"❌ Gemini 설정 오류: {e}")

# ---------------------------------------------------------
# 2. 데이터 및 API 함수들 (디버깅 강화)
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
    # [디버깅] 클라이언트 확인
    if not gmaps:
        return [] # 키가 없으면 조용히 빈 리스트 반환 (화면 깨짐 방지)
    
    berlin_center = (52.5200, 13.4050)
    places_result = []
    
    try:
        # API 호출
        results = gmaps.places_nearby(
            location=berlin_center,
            radius=3000,
            type=place_type,
            keyword=keyword
        )
        
        # [디버깅] 구글 API 상태 확인
        status = results.get('status')
        if status != 'OK' and status != 'ZERO_RESULTS':
            st.error(f"⚠️ 구글맵 오류 ({place_type}): {status}")
            if status == 'REQUEST_DENIED':
                st.warning("👉 해결법: 구글 클라우드 콘솔에서 [결제 카드 등록] 및 [Places API 사용 설정]을 확인하세요.")
            return []

        for place in results.get('results', []):
            rating = place.get('rating', 0)
            if rating >= min_rating:
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
        st.error(f"데이터 가져오기 실패: {e}")
        return []

@st.cache_data
def load_crime_data(csv_file):
    try:
        # 파일 읽기 에러 방지
        df = pd.read_csv(csv_file, on_bad_lines='skip') 
        
        # 필수 컬럼 확인
        if 'District' not in df.columns:
            # st.warning("CSV 파일에 'District' 컬럼이 없습니다.")
            return pd.DataFrame()

        # 데이터 전처리
        if 'Year' in df.columns:
            latest_year = df['Year'].max()
            df = df[df['Year'] == latest_year]
        
        # 숫자형 컬럼만 골라서 합계 내기 (범죄 수 계산)
        numeric_cols = df.select_dtypes(include=['number']).columns
        cols_to_sum = [c for c in numeric_cols if c not in ['Year', 'Code', 'District', 'Location']]
        
        df['Total_Crime'] = df[cols_to_sum].sum(axis=1)
        return df.groupby('District')['Total_Crime'].sum().reset_index()

    except Exception:
        # 파일이 없거나 문제가 있어도 앱이 멈추지 않게 빈 데이터 반환
        return pd.DataFrame()

def get_gemini_response(prompt):
    if not GEMINI_API_KEY:
        return "API 키가 없어서 답변할 수 없어요 🥲"
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"오류 발생: {e}"

# ---------------------------------------------------------
# 3. 메인 화면 구성
# ---------------------------------------------------------
st.title("🇩🇪 베를린: 여행, 안전, 그리고 AI")

# 세션 상태 초기화
if 'reviews' not in st.session_state: st.session_state['reviews'] = {}
if 'messages' not in st.session_state: st.session_state['messages'] = []

# 상단 정보
col1, col2 = st.columns(2)
with col1:
    rate = get_exchange_rate()
    st.info(f"💶 유로 환율: {rate:.0f}원")
with col2:
    w = get_weather()
    st.info(f"⛅ 날씨: {w['temperature']}°C")

# 사이드바
st.sidebar.title("설정 & 메뉴")
st.sidebar.subheader("1. 지도 필터")
show_crime = st.sidebar.toggle("🚨 범죄 위험도", True)
show_res = st.sidebar.toggle("🍽️ 맛집 (4.5+)", True)
show_hotel = st.sidebar.toggle("🏨 숙박시설", False)
show_tour = st.sidebar.toggle("📸 관광지", False)

st.sidebar.subheader("2. 추천 여행 코스")
course_select = st.sidebar.radio("코스 선택:", ("선택 안함", "🏛️ 박물관 섬 & 힙한 점심", "🕊️ 역사와 쇼핑의 조화"))

# 지도
st.subheader("🗺️ 인터랙티브 지도")
m = folium.Map(location=[52.5200, 13.4050], zoom_start=13)

# 1. 범죄 지도
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

# 2. 장소 마커 (채팅방 목록 수집용)
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

# 구글 맵 데이터 로드
if show_res:
    add_markers_detailed(get_google_places_detailed('restaurant', min_rating=4.5), 'green', 'cutlery', '맛집')
if show_hotel:
    add_markers_detailed(get_google_places_detailed('lodging'), 'blue', 'bed', '호텔')
if show_tour:
    add_markers_detailed(get_google_places_detailed('tourist_attraction'), 'purple', 'camera', '관광지')

# 3. 여행 코스 (하드코딩)
courses = {
    "🏛️ 박물관 섬 & 힙한 점심": [
        {"name": "1. 보데 박물관", "lat": 52.5218, "lng": 13.3956},
        {"name": "2. 제임스 사이먼 공원", "lat": 52.5213, "lng": 13.4005},
        {"name": "3. Monsieur Vuong (맛집)", "lat": 52.5244, "lng": 13.4085},
        {"name": "4. 알렉산더 광장", "lat": 52.5219, "lng": 13.4132}
    ],
    "🕊️ 역사와 쇼핑의 조화": [
        {"name": "1. 브란덴부르크 문", "lat": 52.5163, "lng": 13.3777},
        {"name": "2. 홀로코스트 추모비", "lat": 52.5139, "lng": 13.3787},
        {"name": "3. Mall of Berlin", "lat": 52.5106, "lng": 13.3807},
        {"name": "4. 체크포인트 찰리", "lat": 52.5074, "lng": 13.3904}
    ]
}

if course_select != "선택 안함":
    c_data = courses[course_select]
    points = [(p['lat'], p['lng']) for p in c_data]
    
    # 마커
    for p in c_data:
        folium.Marker([p['lat'], p['lng']], tooltip=p['name'], icon=folium.Icon(color='red', icon='info-sign')).add_to(m)
    # 선
    folium.PolyLine(points, color="red", weight=5, opacity=0.8).add_to(m)

st_folium(m, width="100%", height=500)

st.divider()

# 하단: 채팅 및 AI
col_chat, col_ai = st.columns([1, 1])

with col_chat:
    st.subheader("💬 장소별 수다방")
    unique_places = sorted(list(set(all_places_for_chat)))
    if not unique_places:
        place_options = ["(장소 없음 - API 키를 확인하세요)"]
    else:
        place_options = ["(장소를 선택하세요)"] + unique_places

    sel_place = st.selectbox("어디에 대해 이야기할까요?", place_options)
    
    if sel_place not in ["(장소를 선택하세요)", "(장소 없음 - API 키를 확인하세요)"]:
        if sel_place not in st.session_state['reviews']:
            st.session_state['reviews'][sel_place] = []
        
        with st.form("chat_form", clear_on_submit=True):
            user_input = st.text_input("메시지 입력")
            if st.form_submit_button("전송"):
                st.session_state['reviews'][sel_place].append(user_input)
                st.rerun()
        
        for msg in st.session_state['reviews'][sel_place][::-1]:
            st.info(f"🗣️ {msg}")

with col_ai:
    st.subheader("🤖 Gemini 여행 비서")
    chat_box = st.container(height=400)
    with chat_box:
        for m in st.session_state['messages']:
            st.chat_message(m["role"]).write(m["content"])
            
    if prompt := st.chat_input("질문하세요..."):
        st.session_state['messages'].append({"role": "user", "content": prompt})
        chat_box.chat_message("user").write(prompt)
        
        with chat_box.chat_message("assistant"):
            resp = get_gemini_response(prompt)
            st.write(resp)
        st.session_state['messages'].append({"role": "assistant", "content": resp})
