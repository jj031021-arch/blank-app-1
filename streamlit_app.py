import streamlit as st  # 무조건 1등으로 있어야 합니다!
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

# API 키 가져오기
GMAPS_API_KEY = st.secrets.get("google_maps_api_key", "")
GEMINI_API_KEY = st.secrets.get("gemini_api_key", "")

# 클라이언트 초기화
gmaps = None
if GMAPS_API_KEY:
    try:
        gmaps = googlemaps.Client(key=GMAPS_API_KEY)
    except Exception as e:
        st.error(f"❌ 구글맵 설정 오류: {e}")

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        st.error(f"❌ Gemini 설정 오류: {e}")

# ---------------------------------------------------------
# 2. 데이터 및 API 함수
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
def get_google_places_detailed(place_type, keyword=None, min_rating=4.0): # 평점 기준 4.0으로 완화
    if not gmaps:
        return []
    
    # 베를린 중앙 (알렉산더 광장 근처로 중심 이동)
    berlin_center = (52.5200, 13.4050)
    places_result = []
    
    try:
        # 반경을 15000 (15km)로 대폭 늘림
        results = gmaps.places_nearby(
            location=berlin_center,
            radius=15000, 
            type=place_type,
            keyword=keyword
        )
        
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
        return []

@st.cache_data
def load_crime_data(csv_file):
    try:
        df = pd.read_csv(csv_file, on_bad_lines='skip') 
        if 'District' not in df.columns: return pd.DataFrame()
        
        if 'Year' in df.columns:
            latest_year = df['Year'].max()
            df = df[df['Year'] == latest_year]
        
        numeric_cols = df.select_dtypes(include=['number']).columns
        cols_to_sum = [c for c in numeric_cols if c not in ['Year', 'Code', 'District', 'Location']]
        
        df['Total_Crime'] = df[cols_to_sum].sum(axis=1)
        return df.groupby('District')['Total_Crime'].sum().reset_index()
    except:
        return pd.DataFrame()

def get_gemini_response(prompt):
    if not GEMINI_API_KEY: return "API 키 확인 필요"
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except: return "응답 불가"

# ---------------------------------------------------------
# 3. 메인 화면
# ---------------------------------------------------------
st.title("🇩🇪 베를린 전체 정복하기 (Travel & Safety)")

if 'reviews' not in st.session_state: st.session_state['reviews'] = {}
if 'messages' not in st.session_state: st.session_state['messages'] = []

col1, col2 = st.columns(2)
with col1:
    rate = get_exchange_rate()
    st.info(f"💶 환율: {rate:.0f}원")
with col2:
    w = get_weather()
    st.info(f"⛅ 날씨: {w['temperature']}°C")

# 사이드바
st.sidebar.header("🔍 지도 필터")
show_crime = st.sidebar.toggle("🚨 범죄 위험도 (구역별 색상)", True)
show_res = st.sidebar.toggle("🍽️ 맛집 (평점 4.0+)", True)
show_hotel = st.sidebar.toggle("🏨 숙박시설", False)
show_tour = st.sidebar.toggle("📸 관광지", False)

st.sidebar.divider()

# 6가지 여행 코스 정의
courses = {
    "🌳 1. 상쾌한 공기가 필요한 날 (티어가르텐)": [
        {"name": "전승기념탑 (Siegessäule)", "lat": 52.5145, "lng": 13.3501, "desc": "베를린 천사가 내려다보는 탑"},
        {"name": "티어가르텐 산책로", "lat": 52.5135, "lng": 13.3575, "desc": "도심 속 거대한 숲"},
        {"name": "Cafe am Neuen See", "lat": 52.5076, "lng": 13.3448, "desc": "호숫가에서 즐기는 맥주와 피자"}
    ],
    "🎨 2. 미술적 교양이 필요한 날 (박물관섬)": [
        {"name": "구 국립 미술관", "lat": 52.5208, "lng": 13.3982, "desc": "아름다운 건축과 고전 예술"},
        {"name": "제임스 사이먼 갤러리", "lat": 52.5203, "lng": 13.3996, "desc": "현대적 건축미가 돋보이는 입구"},
        {"name": "베를린 돔", "lat": 52.5190, "lng": 13.4010, "desc": "베를린을 상징하는 거대한 성당"}
    ],
    "🏰 3. 역사의 흔적을 걷는 날 (장벽 투어)": [
        {"name": "베를린 장벽 기념관", "lat": 52.5352, "lng": 13.3903, "desc": "분단의 아픔이 생생한 곳"},
        {"name": "마우어파크 (Mauerpark)", "lat": 52.5404, "lng": 13.4048, "desc": "주말 벼룩시장과 가라오케"},
        {"name": "이스트 사이드 갤러리", "lat": 52.5050, "lng": 13.4397, "desc": "장벽 위에 그려진 예술 작품들"}
    ],
    "🛍️ 4. 지갑이 열리는 날 (서베를린 쇼핑)": [
        {"name": "카이저 빌헬름 교회", "lat": 52.5048, "lng": 13.3350, "desc": "전쟁의 상처를 간직한 교회"},
        {"name": "KaDeWe 백화점", "lat": 52.5015, "lng": 13.3414, "desc": "유럽 최대 규모의 럭셔리 백화점"},
        {"name": "쿠담 거리 (Kurfürstendamm)", "lat": 52.5028, "lng": 13.3323, "desc": "명품과 패션의 거리"}
    ],
    "🕶️ 5. 힙한 베를린을 느끼는 날 (크로이츠베르크)": [
        {"name": "Markthalle Neun", "lat": 52.5020, "lng": 13.4310, "desc": "트렌디한 실내 시장과 길거리 음식"},
        {"name": "오버바움 다리", "lat": 52.5015, "lng": 13.4455, "desc": "가장 아름다운 붉은 벽돌 다리"},
        {"name": "Voo Store", "lat": 52.5005, "lng": 13.4215, "desc": "베를린 힙스터들의 편집샵"}
    ],
    "🍺 6. 맥주와 야경이 고픈 날 (프렌츠라우어)": [
        {"name": "Kulturbrauerei", "lat": 52.5390, "lng": 13.4135, "desc": "오래된 양조장을 개조한 문화 복합 공간"},
        {"name": "Prater Beer Garden", "lat": 52.5399, "lng": 13.4101, "desc": "베를린에서 가장 오래된 비어가든"},
        {"name": "소니 센터 (야경)", "lat": 52.5098, "lng": 13.3732, "desc": "미래 도시 같은 화려한 지붕 야경"}
    ]
}

st.sidebar.header("🛤️ 추천 여행 코스 (6 Themes)")
course_select = st.sidebar.radio("오늘의 테마는?", ["선택 안함"] + list(courses.keys()))

# 지도 그리기
st.subheader("🗺️ 베를린 전체 지도")
m = folium.Map(location=[52.5200, 13.4050], zoom_start=12) # 줌 레벨 조정

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

# 2. 마커 추가 함수
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
    add_markers_detailed(get_google_places_detailed('restaurant', min_rating=4.0), 'green', 'cutlery', '맛집')
if show_hotel:
    add_markers_detailed(get_google_places_detailed('lodging', min_rating=4.0), 'blue', 'bed', '호텔')
if show_tour:
    add_markers_detailed(get_google_places_detailed('tourist_attraction', min_rating=4.0), 'purple', 'camera', '관광지')

# 3. 코스 표시
if course_select != "선택 안함":
    # 선택된 코스 이름에서 이모지와 번호 등을 매칭
    c_data = courses[course_select]
    points = [(p['lat'], p['lng']) for p in c_data]
    
    # 시작/중간/끝 마커
    for i, p in enumerate(c_data):
        folium.Marker(
            [p['lat'], p['lng']], 
            tooltip=f"{i+1}. {p['name']}",
            popup=f"<b>{p['name']}</b><br>{p['desc']}",
            icon=folium.Icon(color='red', icon='flag', prefix='fa')
        ).add_to(m)
    
    # 경로 선
    folium.PolyLine(points, color="red", weight=5, opacity=0.8).add_to(m)

st_folium(m, width="100%", height=600)

st.divider()

# 채팅 & AI
col_chat, col_ai = st.columns([1, 1])

with col_chat:
    st.subheader("💬 장소별 수다방")
    unique_places = sorted(list(set(all_places_for_chat)))
    if not unique_places:
        place_options = ["(장소 로딩중 or 없음)"]
    else:
        place_options = ["(장소를 선택하세요)"] + unique_places

    sel_place = st.selectbox("어디에 대해 이야기할까요?", place_options)
    
    if sel_place not in ["(장소를 선택하세요)", "(장소 로딩중 or 없음)"]:
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
