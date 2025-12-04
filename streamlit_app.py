@st.cache_data
def get_google_places_detailed(place_type, keyword=None, min_rating=0.0):
    # 1. 클라이언트 객체 확인
    if not gmaps: 
        st.error("❌ 구글맵 클라이언트가 생성되지 않았습니다. API 키를 확인해주세요.")
        return []
    
    berlin_center = (52.5200, 13.4050)
    places_result = []
    
    try:
        # 2. API 호출 시도
        results = gmaps.places_nearby(
            location=berlin_center,
            radius=3000,
            type=place_type,
            keyword=keyword
        )
        
        # 3. 결과 상태 확인 (디버깅용)
        status = results.get('status')
        if status != 'OK':
            # OK가 아니면 화면에 에러 메시지 출력
            error_msg = results.get('error_message', '메시지 없음')
            st.error(f"⚠️ API 호출 실패 ({place_type}): {status}")
            st.error(f"구글 에러 메시지: {error_msg}")
            
            if status == 'REQUEST_DENIED':
                st.warning("👉 해결법: 결제 계정(카드) 등록 여부와 'Places API'가 켜져 있는지 확인하세요.")
            elif status == 'OVER_QUERY_LIMIT':
                st.warning("👉 해결법: 결제 계정이 연결되지 않았거나 쿼리 한도를 초과했습니다.")
            return []

        # 4. 데이터 가공
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
                
        # 결과가 0개일 경우 안내
        if not places_result:
            st.warning(f"검색 결과가 0건입니다. (조건: {place_type}, 평점 {min_rating} 이상)")
            
        return places_result

    except Exception as e:
        st.error(f"🚫 파이썬 코드 실행 중 치명적 오류: {e}")
        return []
