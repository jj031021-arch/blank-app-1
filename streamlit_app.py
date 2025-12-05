import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import requests
import google.generativeai as genai
import googlemaps
import plotly.express as px

# ---------------------------------------------------------
# 1. 설정 및 API 키 로드
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="베를린 가이드 (Google API Ver.)")

GMAPS_API_KEY = st.secrets.get("google_maps_api_key", "")
GEMINI_API_KEY = st.secrets.get("gemini_api_key", "")

# 클라이언트 초기화
gmaps = None
if GMAPS_API_KEY:
    try:
        gmaps = googlemaps.Client(key=GMAPS_API_KEY)
    except:
        pass

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except:
        pass

# ---------------------------------------------------------
# 2. 유틸리티 함수
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
        return {"temperature": 15.0, "weathercode": 0}

@st.cache_data
def get_google_places(place_type, lat, lng, radius_m=2000):
    """
    Google Places API를 사용하여 주변 장소를 검색합니다.
    """
    if not gmaps: return []
    
    places_result = []
    try:
        # Google Maps API 호출
        results = gmaps.places_nearby(
            location=(lat, lng),
            radius=radius_m,
            type=place_type
        )
        
        for place in results.get('results', []):
            name = place.get('name', 'Unknown')
            rating = place.get('rating', 'N/A')
            vicinity = place.get('vicinity', '')
            
            # 구글 검색 링크 생성
            search_query = f"{name} Berlin".replace(" ", "+")
            google_link = f"https://www.google.com/search?q={search_query}"
            
            # 타입에 따른 설명
            desc = "장소"
            if place_type == 'restaurant': desc = "맛집"
            elif place_type == 'lodging': desc = "숙소"
            elif place_type == 'tourist_attraction': desc = "명소"

            places_result.append({
                "name": name,
                "lat": place['geometry']['location']['lat'],
                "lng": place['geometry']['location']['lng'],
                "rating": rating,
                "address": vicinity,
                "type": place_type,
                "desc": desc,
                "link": google_link
            })
        return places_result
    except Exception as e:
        # st.error(f"Google API Error: {e}") 
        return []

# 주소 -> 좌표 변환 (Google Geocoding API 사용)
def get_coordinates_google(query):
    if not gmaps: return None, None, None
    try:
        geocode_result = gmaps.geocode(query)
        if geocode_result:
            loc = geocode_result[0]['geometry']['location']
            formatted_address = geocode_result[0]['formatted_address']
            return loc['lat'], loc['lng'], formatted_address
    except:
        pass
    return None, None, None

# 지도 표시용 범죄 데이터 (District 합계)
@st.cache_data
def load_and_process_crime_data(csv_file):
    try:
        df = pd.read_csv(csv_file, on_bad_lines='skip')
        if 'District' not in df.columns: return pd.DataFrame()
        if 'Year' in df.columns:
            latest_year = df['Year'].max()
            df = df[df['Year'] == latest_year]
        numeric_cols = df.select_dtypes(include=['number']).columns
        cols_to_exclude = ['Year', 'Code', 'District', 'Location', 'lat', 'lng', 'Lat', 'Lng']
        cols_to_sum = [c for c in numeric_cols if c not in cols_to_exclude]
        df['Total_Crime'] = df[cols_to_sum].sum(axis=1)
        district_df = df.groupby('District')['Total_Crime'].sum().reset_index()
        district_df['District'] = district_df['District'].str.strip()
        return district_df
    except: return pd.DataFrame()

# 통계 분석용 원본 데이터
@st.cache_data
def load_crime_data_raw(csv_file):
    try:
        df = pd.read_csv(csv_file, on_bad_lines='skip')
        if 'District' not in df.columns: return pd.DataFrame()
        return df
    except: return pd.DataFrame()

def get_gemini_response(prompt):
    if not GEMINI_API_KEY: return "API 키 확인 필요"
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text
    except: return "AI 응답 오류"

# ---------------------------------------------------------
# 3. 여행 코스 데이터
# ---------------------------------------------------------
courses = {
    "🌳 Theme 1: 숲과 힐링": [
        {"name": "1. 전승기념탑", "lat": 52.5145, "lng": 13.3501, "type": "view", "desc": "베를린 전경이 한눈에 보이는 황금 천사상"},
        {"name": "2. 티어가르텐 산책", "lat": 52.5135, "lng": 13.3575, "type": "walk", "desc": "도심 속 거대한 허파"},
        {"name": "3. Cafe am Neuen See", "lat": 52.5076, "lng": 13.3448, "type": "food", "desc": "호수 앞 비어가든"},
        {"name": "4. 베를린 동물원", "lat": 52.5079, "lng": 13.3377, "type": "view", "desc": "세계 최대 종을 보유한 동물원"},
        {"name": "5. Monkey Bar", "lat": 52.5049, "lng": 13.3353, "type": "food", "desc": "동물원 뷰 루프탑 바"},
        {"name": "6. 카이저 빌헬름 교회", "lat": 52.5048, "lng": 13.3350, "type": "view", "desc": "전쟁의 상처를 간직한 교회"}
    ],
    "🎨 Theme 2: 예술과 고전": [
        {"name": "1. 베를린 돔", "lat": 52.5190, "lng": 13.4010, "type": "view", "desc": "웅장한 돔 지붕"},
        {"name": "2. 구 국립 미술관", "lat": 52.5208, "lng": 13.3982, "type": "view", "desc": "고전 예술의 정수"},
        {"name": "3. 제임스 사이먼 공원", "lat": 52.5213, "lng": 13.4005, "type": "walk", "desc": "강변 산책로"},
        {"name": "4. Hackescher Hof", "lat": 52.5246, "lng": 13.4020, "type": "view", "desc": "아름다운 안뜰"},
        {"name": "5. Monsieur Vuong", "lat": 52.5244, "lng": 13.4085, "type": "food", "desc": "유명 베트남 쌀국수"},
        {"name": "6. Zeit für Brot", "lat": 52.5265, "lng": 13.4090, "type": "food", "desc": "최고의 시나몬 롤"}
    ],
    "🏰 Theme 3: 분단의 역사": [
        {"name": "1. 베를린 장벽 기념관", "lat": 52.5352, "lng": 13.3903, "type": "view", "desc": "장벽의 실제 모습"},
        {"name": "2. Mauerpark", "lat": 52.5404, "lng": 13.4048, "type": "walk", "desc": "주말 벼룩시장"},
        {"name": "3. Prater Beer Garden", "lat": 52.5399, "lng": 13.4101, "type": "food", "desc": "가장 오래된 비어가든"},
        {"name": "4. 체크포인트 찰리", "lat": 52.5074, "lng": 13.3904, "type": "view", "desc": "검문소"},
        {"name": "5. Topography of Terror", "lat": 52.5065, "lng": 13.3835, "type": "view", "desc": "나치 역사관"},
        {"name": "6. Mall of Berlin", "lat": 52.5106, "lng": 13.3807, "type": "food", "desc": "쇼핑몰"}
    ],
    "🕶️ Theme 4: 힙스터 성지": [
        {"name": "1. 오버바움 다리", "lat": 52.5015, "lng": 13.4455, "type": "view", "desc": "붉은 벽돌 다리"},
        {"name": "2. 이스트 사이드 갤러리", "lat": 52.5050, "lng": 13.4397, "type": "walk", "desc": "야외 갤러리"},
        {"name": "3. Burgermeister", "lat": 52.5005, "lng": 13.4420, "type": "food", "desc": "다리 밑 버거집"},
        {"name": "4. Markthalle Neun", "lat": 52.5020, "lng": 13.4310, "type": "food", "desc": "실내 시장"},
        {"name": "5. Voo Store", "lat": 52.5005, "lng": 13.4215, "type": "view", "desc": "편집샵"},
        {"name": "6. Landwehr Canal", "lat": 52.4960, "lng": 13.4150, "type": "walk", "desc": "운하 산책"}
    ],
    "🛍️ Theme 5: 럭셔리 & 쇼핑": [
        {"name": "1. KaDeWe", "lat": 52.5015, "lng": 13.3414, "type": "view", "desc": "최대 백화점"},
        {"name": "2. 쿠담 거리", "lat": 52.5028, "lng": 13.3323, "type": "walk", "desc": "명품 거리"},
        {"name": "3. Bikini Berlin", "lat": 52.5055, "lng": 13.3370, "type": "view", "desc": "컨셉 쇼핑몰"},
        {"name": "4. C/O Berlin", "lat": 52.5065, "lng": 13.3325, "type": "view", "desc": "사진 미술관"},
        {"name": "5. Schwarzes Café", "lat": 52.5060, "lng": 13.3250, "type": "food", "desc": "24시간 카페"},
        {"name": "6. Savignyplatz", "lat": 52.5060, "lng": 13.3220, "type": "walk", "desc": "서점과 카페"}
    ],
    "🌙 Theme 6: 화려한 밤": [
        {"name": "1. TV타워", "lat": 52.5208, "lng": 13.4094, "type": "view", "desc": "야경 감상"},
        {"name": "2. 로젠탈러 거리", "lat": 52.5270, "lng": 13.4020, "type": "walk", "desc": "트렌디한 골목"},
        {"name": "3. Clärchens Ballhaus", "lat": 52.5265, "lng": 13.3965, "type": "food", "desc": "무도회장 식사"},
        {"name": "4. House of Small Wonder", "lat": 52.5240, "lng": 13.3920, "type": "food", "desc": "브런치 맛집"},
        {"name": "5. Friedrichstadt-Palast", "lat": 52.5235, "lng": 13.3885, "type": "view", "desc": "화려한 쇼"},
        {"name": "6. 브란덴부르크 문", "lat": 52.5163, "lng": 13.3777, "type": "walk", "desc": "야경 랜드마크"}
    ]
}

# ---------------------------------------------------------
# 4. 메인 화면 구성
# ---------------------------------------------------------
st.title("🇩🇪 베를린 가이드 (Google API Powered)")
st.caption("Google Places API를 사용하여 정확하고 풍부한 정보를 제공합니다.")

# 세션 초기화
if 'reviews' not in st.session_state: st.session_state['reviews'] = {}
if 'recommendations' not in st.session_state: st.session_state['recommendations'] = []
if 'messages' not in st.session_state: st.session_state['messages'] = []
if 'map_center' not in st.session_state: st.session_state['map_center'] = [52.5200, 13.4050]
if 'search_marker' not in st.session_state: st.session_state['search_marker'] = None

# [1] 환율 & 날씨
col1, col2 = st.columns(2)
with col1:
    rate = get_exchange_rate()
    st.metric(label="💶 현재 유로 환율", value=f"{rate:.0f}원", delta="1 EUR 기준")
with col2:
    w = get_weather()
    st.metric(label="⛅ 베를린 기온", value=f"{w['temperature']}°C")

st.divider()

# --- 사이드바 ---
st.sidebar.title("🛠️ 여행 도구")

# 1. 검색 (Google Geocoding 사용)
st.sidebar.subheader("🔍 장소 찾기 (위치 이동)")
st.sidebar.caption("지도 중심을 이동하여 주변 정보를 갱신합니다.")
search_query = st.sidebar.text_input("장소 이름 (예: Potsdamer Platz)", placeholder="엔터키 입력")
if search_query:
    lat, lng, name = get_coordinates_google(search_query + " Berlin")
    if lat and lng:
        st.session_state['map_center'] = [lat, lng]
        st.session_state['search_marker'] = {"lat": lat, "lng": lng, "name": name}
        st.sidebar.success(f"이동: {name}")
    else:
        st.sidebar.error("장소를 찾을 수 없습니다. (Google API 확인 필요)")

st.sidebar.divider()

# 2. 필터
st.sidebar.subheader("🗺️ 지도 필터")
show_crime = st.sidebar.toggle("🚨 범죄 위험도 보기", True)
show_hotel = st.sidebar.toggle("🏨 숙박시설 (Lodging)", False)
show_tour = st.sidebar.toggle("📸 관광지 (Attraction)", False)
show_food = st.sidebar.toggle("🍽️ 음식점 (Restaurant)", True)

# --- 메인 탭 ---
tab1, tab2, tab3, tab4 = st.tabs(["🗺️ 구글 지도 탐험", "🚩 추천 코스 (6 Themes)", "💬 여행자 수다방", "📊 범죄 통계 분석"])

# =========================================================
# TAB 1: 자유 탐험 (Google Places API 사용)
# =========================================================
with tab1:
    center = st.session_state['map_center']
    m1 = folium.Map(location=center, zoom_start=14)

    # 검색 핀
    if st.session_state['search_marker']:
        sm = st.session_state['search_marker']
        folium.Marker(
            [sm['lat'], sm['lng']], 
            popup=sm['name'],
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m1)

    # 1. 범죄 지도
    if show_crime:
        crime_df = load_and_process_crime_data("Berlin_crimes.csv")
        if not crime_df.empty:
            folium.Choropleth(
                geo_data="https://raw.githubusercontent.com/funkeinteraktiv/Berlin-Geodaten/master/berlin_bezirke.geojson",
                data=crime_df,
                columns=["District", "Total_Crime"],
                key_on="feature.properties.name",
                fill_color="YlOrRd",
                fill_opacity=0.4,
                line_opacity=0.2,
                name="범죄"
            ).add_to(m1)

    # 2. 구글 플레이스 데이터 (중심 좌표 기준 검색)
    if show_food:
        places = get_google_places('restaurant', center[0], center[1], 2000)
        fg_food = folium.FeatureGroup(name="식당")
        for p in places:
            popup_html = (
                f"<div style='font-family:sans-serif; width:150px'>"
                f"<b>{p['name']}</b><br>"
                f"⭐{p['rating']}<br>"
                f"<a href='{p['link']}' target='_blank' style='text-decoration:none; color:blue;'>👉 구글 상세정보</a>"
                f"</div>"
            )
            folium.Marker(
                [p['lat'], p['lng']], popup=popup_html,
                icon=folium.Icon(color='green', icon='cutlery', prefix='fa')
            ).add_to(fg_food)
        fg_food.add_to(m1)

    if show_hotel:
        places = get_google_places('lodging', center[0], center[1], 2000)
        fg_hotel = folium.FeatureGroup(name="숙소")
        for p in places:
            popup_html = (
                f"<div style='font-family:sans-serif; width:150px'>"
                f"<b>{p['name']}</b><br>"
                f"⭐{p['rating']}<br>"
                f"<a href='{p['link']}' target='_blank' style='text-decoration:none; color:blue;'>👉 구글 상세정보</a>"
                f"</div>"
            )
            folium.Marker(
                [p['lat'], p['lng']], popup=popup_html,
                icon=folium.Icon(color='blue', icon='bed', prefix='fa')
            ).add_to(fg_hotel)
        fg_hotel.add_to(m1)

    if show_tour:
        places = get_google_places('tourist_attraction', center[0], center[1], 2000)
        fg_tour = folium.FeatureGroup(name="명소")
        for p in places:
            popup_html = (
                f"<div style='font-family:sans-serif; width:150px'>"
                f"<b>{p['name']}</b><br>"
                f"⭐{p['rating']}<br>"
                f"<a href='{p['link']}' target='_blank' style='text-decoration:none; color:blue;'>👉 구글 상세정보</a>"
                f"</div>"
            )
            folium.Marker(
                [p['lat'], p['lng']], popup=popup_html,
                icon=folium.Icon(color='purple', icon='camera', prefix='fa')
            ).add_to(fg_tour)
        fg_tour.add_to(m1)

    st_folium(m1, width="100%", height=600)

# =========================================================
# TAB 2: 추천 코스
# =========================================================
with tab2:
    st.subheader("🌟 테마별 추천 코스")
    theme_names = list(courses.keys())
    selected_theme = st.radio("테마 선택:", theme_names, horizontal=True)
    c_data = courses[selected_theme]
    
    c_col1, c_col2 = st.columns([1.5, 1])
    
    with c_col1:
        m2 = folium.Map(location=[c_data[2]['lat'], c_data[2]['lng']], zoom_start=13)
        points = []
        for i, item in enumerate(c_data):
            loc = [item['lat'], item['lng']]
            points.append(loc)
            color = 'orange' if item['type'] == 'food' else 'blue'
            icon = 'cutlery' if item['type'] == 'food' else 'camera'
            
            link = f"https://www.google.com/search?q={item['name'].replace(' ', '+')}+Berlin"
            popup_html = (
                f"<div style='font-family:sans-serif; width:180px'>"
                f"<b>{i+1}. {item['name']}</b><br>"
                f"{item['desc']}<br>"
                f"<a href='{link}' target='_blank' style='color:blue;'>👉 구글 상세정보</a>"
                f"</div>"
            )
            
            folium.Marker(
                loc, popup=popup_html, tooltip=f"{i+1}. {item['name']}",
                icon=folium.Icon(color=color, icon=icon)
            ).add_to(m2)
        folium.PolyLine(points, color="red", weight=4, opacity=0.7).add_to(m2)
        st_folium(m2, width="100%", height=500)
        
    with c_col2:
        st.markdown(f"### {selected_theme}")
        st.markdown("---")
        for item in c_data:
            icon_str = "🍽️" if item['type'] == 'food' else "📸" if item['type'] == 'view' else "🚶"
            with st.expander(f"{icon_str} {item['name']}", expanded=True):
                st.write(f"_{item['desc']}_")
                q = item['name'].replace(" ", "+") + "+Berlin"
                st.markdown(f"[🔍 구글 검색 바로가기](https://www.google.com/search?q={q})")

# =========================================================
# TAB 3: 수다방 & AI (추천 기능 보강)
# =========================================================
with tab3:
    col_chat, col_ai = st.columns([1, 1])
    
    with col_chat:
        st.subheader("💬 장소별 리뷰")
        input_method = st.radio("장소 선택 방식", ["목록에서 선택", "직접 입력하기"], horizontal=True, label_visibility="collapsed")
        all_places_list = sorted(list(set([p['name'] for v in courses.values() for p in v])))
        
        if input_method == "목록에서 선택":
            sel_place = st.selectbox("리뷰할 장소", all_places_list)
        else:
            sel_place = st.text_input("장소 이름 입력")
            
        if sel_place:
            if sel_place not in st.session_state['reviews']:
                st.session_state['reviews'][sel_place] = []

            with st.form("msg_form", clear_on_submit=True):
                txt = st.text_input(f"'{sel_place}' 후기 입력")
                if st.form_submit_button("등록"):
                    st.session_state['reviews'][sel_place].append(txt)
                    st.rerun()
            
            if st.session_state['reviews'][sel_place]:
                st.write("---")
                for i, msg in enumerate(st.session_state['reviews'][sel_place]):
                    c1, c2 = st.columns([8, 1])
                    c1.info(f"🗣️ {msg}")
                    if c2.button("🗑️", key=f"del_{sel_place}_{i}"):
                        del st.session_state['reviews'][sel_place][i]
                        st.rerun()

        st.divider()
        
        # [섹션 2] 나만의 추천 (대댓글 기능 포함)
        st.subheader("👍 나만의 장소 추천해요")
        with st.form("recommend_form", clear_on_submit=True):
            rec_place = st.text_input("장소 이름")
            rec_desc = st.text_input("이유 (한 줄)")
            if st.form_submit_button("추천 등록"):
                st.session_state['recommendations'].insert(0, {"place": rec_place, "desc": rec_desc, "replies": []})
                st.rerun()
        
        for i, rec in enumerate(st.session_state['recommendations']):
            st.markdown(f"**{i+1}. {rec['place']}**")
            c1, c2 = st.columns([8, 1])
            c1.success(rec['desc'])
            
            if c2.button("🗑️", key=f"del_rec_{i}"):
                del st.session_state['recommendations'][i]
                st.rerun()

            if 'replies' in rec and rec['replies']:
                for reply in rec['replies']:
                    st.caption(f"↳ 💬 {reply}")

            with st.expander("💬 댓글 달기"):
                reply_txt = st.text_input("댓글 내용", key=f"reply_input_{i}")
                if st.button("등록", key=f"reply_btn_{i}"):
                    if 'replies' not in rec: rec['replies'] = []
                    rec['replies'].append(reply_txt)
                    st.rerun()
            st.write("---")

    with col_ai:
        st.subheader("🤖 Gemini 가이드")
        chat_area = st.container(height=500)
        for msg in st.session_state['messages']:
            chat_area.chat_message(msg['role']).write(msg['content'])
        if prompt := st.chat_input("질문하세요..."):
            st.session_state['messages'].append({"role": "user", "content": prompt})
            chat_area.chat_message("user").write(prompt)
            with chat_area.chat_message("assistant"):
                resp = get_gemini_response(prompt)
                st.write(resp)
            st.session_state['messages'].append({"role": "assistant", "content": resp})

# =========================================================
# TAB 4: 범죄 통계 분석
# =========================================================
with tab4:
    st.header("📊 베를린 범죄 데이터 대시보드")
    st.caption("데이터 원본: Berlin_crimes.csv")

    raw_df = load_crime_data_raw("Berlin_crimes.csv")

    if not raw_df.empty and 'Year' in raw_df.columns:
        c_filter1, c_filter2 = st.columns(2)
        with c_filter1:
            years = sorted(raw_df['Year'].unique(), reverse=True)
            selected_year = st.selectbox("📅 분석 연도", years)
        with c_filter2:
            districts = sorted(raw_df['District'].unique())
            selected_districts = st.multiselect("🏙️ 구(District) 선택", districts, default=districts)
        
        df_year = raw_df[raw_df['Year'] == selected_year]
        if selected_districts:
            df_year = df_year[df_year['District'].isin(selected_districts)]
        
        crime_types = ['Robbery', 'Street_robbery', 'Injury', 'Agg_assault', 'Threat', 'Theft', 'Car', 'From_car', 'Bike', 'Burglary', 'Fire', 'Arson', 'Damage', 'Graffiti', 'Drugs']
        available_types = [c for c in crime_types if c in df_year.columns]
        
        st.markdown("### 📌 핵심 지표")
        kpi1, kpi2, kpi3 = st.columns(3)
        
        total_crimes = df_year[available_types].sum().sum()
        most_crime_district = df_year.groupby('District')[available_types].sum().sum(axis=1).idxmax()
        most_common_crime = df_year[available_types].sum().idxmax()
        
        kpi1.metric("총 범죄 발생", f"{total_crimes:,}건")
        kpi2.metric("최다 발생 지역", most_crime_district)
        kpi3.metric("최다 빈번 범죄", most_common_crime)
        
        st.divider()

        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.subheader("🏙️ 구별 범죄 순위")
            district_sum = df_year.groupby('District')[available_types].sum().sum(axis=1).reset_index(name='Count').sort_values('Count', ascending=True)
            fig_bar = px.bar(district_sum, x='Count', y='District', orientation='h', text='Count', color='Count', color_continuous_scale='Reds')
            fig_bar.update_traces(texttemplate='%{text:.2s}', textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with chart_col2:
            st.subheader("🥧 범죄 유형 비율")
            type_sum = df_year[available_types].sum().reset_index(name='Count').rename(columns={'index': 'Type'})
            fig_pie = px.pie(type_sum, values='Count', names='Type', hole=0.4)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
            
        st.subheader("📈 연도별 추이")
        yearly_trend = raw_df.groupby('Year')[available_types].sum().sum(axis=1).reset_index(name='Total')
        fig_line = px.line(yearly_trend, x='Year', y='Total', markers=True, labels={'Total': '총 범죄 수'})
        fig_line.update_layout(xaxis=dict(tickmode='linear'))
        st.plotly_chart(fig_line, use_container_width=True)

    else:
        st.error("데이터를 로드할 수 없습니다.")
