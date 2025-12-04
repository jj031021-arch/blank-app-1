import streamlit as st
import pandas as pd
import googlemaps
import folium
from streamlit_folium import st_folium
import requests
import google.generativeai as genai

# ---------------------------------------------------------
# 1. 설정 및 API 키
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="베를린 여행 & AI 가이드")

# API 키 로드 (배포용 secrets 혹은 로컬 테스트용)
try:
    GMAPS_API_KEY = st.secrets["google_maps_api_key"]
    GEMINI_API_KEY = st.secrets["gemini_api_key"] # secrets에 추가 필요
except:
    GMAPS_API_KEY = "내_구글맵_API_키"
    GEMINI_API_KEY = "내_제미나이_API_키"

# 클라이언트 설정
gmaps = googlemaps.Client(key=GMAPS_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------
# 2. 데이터 관리 (Session State)
# ---------------------------------------------------------
if 'user_places' not in st.session_state:
    st.session_state['user_places'] = []
if 'reviews' not in st.session_state:
    st.session_state['reviews'] = {} # 딕셔너리로 변경: {장소명: [후기리스트]}
if 'messages' not in st.session_state:
    st.session_state['messages'] = [] # Gemini 대화 기록

# ---------------------------------------------------------
# 3. 함수 정의 (데이터 가져오기, AI 등)
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
    # API 호출 실패를 대비한 예외처리 강화
    if not gmaps: return []
    berlin_center = (52.5200, 13.4050)
    places_result = []
    
    try:
        results = gmaps.places_nearby(
            location=berlin_center,
            radius=3000, # 3km 반경 (너무 넓으면 데이터가 안 올 수 있음)
            type=place_type,
            keyword=keyword
        )
        
        for place in results.get('results', []):
            rating = place.get('rating', 0)
            if rating >= min_rating:
                # 구글 검색 링크 생성 (사진/상세정보 대체)
                search_query = f"{place['name']}+Berlin".replace(" ", "+")
                link = f"https://www.google.com/search?q={search_query}"
                
                places_result.append({
                    "name": place['name'],
                    "lat": place['geometry']['location']['lat'],
                    "lng": place['geometry']['location']['lng'],
                    "rating": rating,
                    "address": place.get('vicinity', '주소 정보 없음'),
                    "type": place_type,
                    "link": link
                })
        return places_result
    except Exception as e:
        st.error(f"구글 맵 API 오류: {e}") # 에러 메시지 출력
        return []

@st.cache_data
def load_crime_data(csv_file):
    try:
        df = pd.read_csv(csv_file)
        # 데이터 전처리 (이전과 동일)
        latest_year = df['Year'].max()
        df = df[df['Year'] == latest_year]
        cols = ['Robbery', 'Street_robbery', 'Injury', 'Agg_assault', 'Theft', 'Burglary']
        existing = [c for c in cols if c in df.columns]
        df['Total_Crime'] = df[existing].sum(axis=1)
        return df.groupby('District')['Total_Crime'].sum().reset_index()
    except:
        return pd.DataFrame()

# Gemini 응답 함수
def get_gemini_response(prompt):
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"죄송합니다. 오류가 발생했습니다: {e}"

# ---------------------------------------------------------
# 4. 메인 화면 & 사이드바
# ---------------------------------------------------------
st.title("🇩🇪 베를린: 여행, 안전, 그리고 AI")

# 상단 정보창
col1, col2 = st.columns(2)
with col1:
    rate = get_exchange_rate()
    st.info(f"💶 유로 환율: {rate:.0f}원")
with col2:
    w = get_weather()
    st.info(f"⛅ 날씨: {w['temperature']}°C")

# ----------------- 사이드바 설정 -----------------
st.sidebar.title("설정 & 메뉴")

st.sidebar.subheader("1. 지도 필터")
show_crime = st.sidebar.toggle("🚨 범죄 위험도", True)
show_res = st.sidebar.toggle("🍽️ 맛집 (4.5+)", True)
show_hotel = st.sidebar.toggle("🏨 숙박시설", False)
show_tour = st.sidebar.toggle("📸 관광지", False)

st.sidebar.subheader("2. 추천 여행 코스")
course_select = st.sidebar.selectbox("오늘의 기분은?", ["선택 안함", "🚶 걷고 싶은 날 (공원 산책)", "🍷 화려한 밤 (미식 투어)"])

st.sidebar.divider()

# ----------------- 메인 지도 영역 -----------------
st.subheader("🗺️ 인터랙티브 지도")

m = folium.Map(location=[52.5200, 13.4050], zoom_start=12)

# [범죄 지도]
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

# [장소 마커 추가 함수]
all_places_for_chat = [] # 채팅방 선택 목록을 위해 저장

def add_markers_detailed(data_list, color, icon_type, type_name):
    fg = folium.FeatureGroup(name=type_name)
    for item in data_list:
        all_places_for_chat.append(item['name']) # 리스트에 이름 추가
        
        # HTML 팝업 (링크 포함)
        html = f"""
        <div style="font-family:sans-serif; width:200px">
            <h4>{item['name']}</h4>
            <p>⭐ {item['rating']} / {type_name}</p>
            <p style="font-size:12px">{item['address']}</p>
            <a href="{item['link']}" target="_blank" style="background-color:#4CAF50; color:white; padding:5px 10px; text-decoration:none; border-radius:5px;">구글 상세정보 & 사진 보기</a>
        </div>
        """
        folium.Marker(
            [item['lat'], item['lng']],
            popup=folium.Popup(html, max_width=250),
            icon=folium.Icon(color=color, icon=icon_type, prefix='fa')
        ).add_to(fg)
    fg.add_to(m)

# 데이터 로드 및 마커 표시
if show_res:
    res = get_google_places_detailed('restaurant', min_rating=4.5)
    add_markers_detailed(res, 'green', 'cutlery', '맛집')
if show_hotel:
    hotels = get_google_places_detailed('lodging')
    add_markers_detailed(hotels, 'blue', 'bed', '호텔')
if show_tour:
    tours = get_google_places_detailed('tourist_attraction')
    add_markers_detailed(tours, 'purple', 'camera', '관광지')

# [여행 코스 그리기]
courses = {
    "🚶 걷고 싶은 날 (공원 산책)": [
        (52.5163, 13.3777), (52.5139, 13.3501), (52.5096, 13.3323) # 브란덴부르크문 -> 티어가르텐 -> 동물원
    ],
    "🍷 화려한 밤 (미식 투어)": [
        (52.5273, 13.4077), (52.5200, 13.4050), (52.5096, 13.4019) # 해커셔마크트 -> 돔 -> 체크포인트찰리 인근
    ]
}

if course_select in courses:
    points = courses[course_select]
    folium.PolyLine(
        locations=points,
        color="blue",
        weight=5,
        tooltip=course_select
    ).add_to(m)
    # 시작점/끝점 표시
    folium.Marker(points[0], popup="코스 시작", icon=folium.Icon(color='red', icon='play')).add_to(m)
    folium.Marker(points[-1], popup="코스 종료", icon=folium.Icon(color='black', icon='stop')).add_to(m)

st_folium(m, width="100%", height=500)

st.divider()

# ---------------------------------------------------------
# 5. 장소별 소통방 (Context-Specific Chat)
# ---------------------------------------------------------
col_chat, col_ai = st.columns([1, 1])

with col_chat:
    st.subheader("💬 장소별 수다방")
    
    # 채팅할 장소 선택
    # 사용자 편의를 위해 '전체' 옵션과 '지도에 있는 장소들'을 합침
    place_options = ["(장소를 선택하세요)"] + sorted(list(set(all_places_for_chat)))
    selected_place = st.selectbox("어떤 장소에 대해 이야기할까요?", place_options)

    if selected_place != "(장소를 선택하세요)":
        st.caption(f"**'{selected_place}'**에 대한 여행자들의 의견입니다.")
        
        # 해당 장소의 리뷰 리스트가 없으면 생성
        if selected_place not in st.session_state['reviews']:
            st.session_state['reviews'][selected_place] = []

        # 리뷰 입력
        with st.form(f"form_{selected_place}", clear_on_submit=True):
            user_msg = st.text_input("한줄 평 남기기")
            if st.form_submit_button("등록"):
                st.session_state['reviews'][selected_place].append(user_msg)
                st.rerun()
        
        # 리뷰 출력
        if st.session_state['reviews'][selected_place]:
            for msg in st.session_state['reviews'][selected_place]:
                st.info(f"🗣️ {msg}")
        else:
            st.write("아직 등록된 글이 없습니다. 첫 글을 남겨보세요!")
    else:
        st.write("👆 위 목록에서 맛집이나 관광지를 선택하면 게시판이 열립니다.")

# ---------------------------------------------------------
# 6. Gemini AI 여행 비서
# ---------------------------------------------------------
with col_ai:
    st.subheader("🤖 Gemini 여행 비서")
    
    # 채팅 기록 표시
    chat_container = st.container(height=400)
    with chat_container:
        for message in st.session_state['messages']:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # 입력창
    if prompt := st.chat_input("베를린 여행에 대해 물어보세요! (예: 3일 일정 짜줘)"):
        # 사용자 메시지 표시 & 저장
        st.session_state['messages'].append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        # AI 응답 생성
        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("생각 중..."):
                    ai_response = get_gemini_response(prompt)
                    st.markdown(ai_response)
        
        # AI 응답 저장
        st.session_state['messages'].append({"role": "assistant", "content": ai_response})
