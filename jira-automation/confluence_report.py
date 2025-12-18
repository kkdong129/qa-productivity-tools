import json
from time import localtime, strftime
import time
import os
import html
from datetime import datetime, timedelta
import calendar

# Confluence API 및 Store review 수집
from atlassian import Confluence
import pandas as pd
from google_play_scraper import Sort, reviews
from app_store_scraper import AppStore
import urllib.parse

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

"""Atlassian API를 사용하여 월간 보고서 페이지를 작성합니다. 작성된 페이지는 Config.json에 정의된 페이지에 작성됩니다.

Notes:
    # 1. "confluence_report.py"와 "confluence_config.json" 파일을 동일한 디렉토리에 위치시킨 다음에 이 스크립트를 실행합니다.
    # 2. Window OS의 Task Scheduler 또는 Mac OS의 Crontab, Launchd 등을 활용하여 특정 주기마다 이 스크립트를 실행시킬 수 있습니다.
"""

def web_driver_setting():
    """점유율 웹사이트 크롤링을 위한 초기 설정 함수
    크롬 웹드라이버를 초기화하고, 헤드리스 모드로 설정합니다.

    Returns:
        driver: 헤드리스 모드로 설정된 크롬 웹드라이버를 리턴합니다.
    """
    try:
        service = ChromeService(ChromeDriverManager().install())
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.implicitly_wait(10)
        print("WebDriver 초기화 완료 (Headless Mode).")
        return driver
    except Exception as e:
        print(f"WebDriver 초기화 실패. Chrome 또는 드라이버 관리 문제: {e}")
        return None

def load_config(CONFIG_PATH):
    """confluence_config.json 데이터 로드
    CONFIG_PATH에 저장된 JSON 데이터를 세팅하고 리턴합니다.

    Arg:
        CONFIG_PATH: "confluence_config.json" 파일의 경로

    Returns:
        "confluence_config.json" 파일의 데이터를 리턴합니다.
    """
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"confluence_config.json 파일 로드 오류: {e}")
        return None

def initialize_confluence_client(config):
    """Atlassian Confluence 클라이언트 초기화
    CONFIG_PATH에 저장된 JSON 데이터를 세팅하고, confluence 객체를 리턴합니다.

    Args:
        config: "confluence_config.json" 파일의 데이터

    Returns:
        confluence: 페이지 작성에 필요한 Confluence 데이터를 저장해서 리턴합니다.
    """
    try:
        BASE_URL = config['confluence']['base_url']
        API_USERNAME = config['auth']['username']
        API_TOKEN = config['auth']['api_token']

        confluence = Confluence(
            url=BASE_URL,
            username=API_USERNAME,
            password=API_TOKEN,
            cloud=True
        )
        # print("Confluence 클라이언트 초기화 성공.")
        return confluence
    except Exception as e:
        print(f"클라이언트 초기화 실패: {e}")
        return None

def create_confluence_page(confluence_client, space_key, parent_id, title, content):
    """Confluence 페이지 작성 API 호출

    Args:
        confluence_client: 페이지 작성에 필요한 Confluence 데이터
        space_key: 작성할 페이지의 컨플루언스 스페이스 아이디
        parent_id: 작성되는 페이지의 상위 페이지 아이디
        title: 작성할 페이지의 제목
        content: 작성될 페이지의 본문

    Returns:
        page_id: 페이지 작성에 성공하면, 페이지 아이디를 리턴합니다.
    """
    print(f"\n'{title}' 페이지 작성 시작...")
    try:
        response = confluence_client.create_page(
            space=space_key,
            title=title,
            body=content,
            representation='storage',
            parent_id=parent_id if parent_id else None
        )

        page_id = response['id']
        page_url = f"{confluence_client.url}/pages/viewpage.action?pageId={page_id}"
        print(f"페이지 작성 성공! 제목: **{title}**")
        print(f"페이지 링크: {page_url}")
        return page_id

    except Exception as e:
        print(f"페이지 작성 실패. 오류: {e}")
        return False

def get_last_month_range():
    """스토어 리뷰 기준일자를 리턴하는 함수
    스크립트 실행일을 기준으로 지난달의 시작일과 종료일을 계산합니다.

    Returns:
        start_date: 지난달의 시작일
        end_date: 지난달의 종료일

    Notes:
        이 함수는 스토어 리뷰 페이지 작성을 위해서 호출됩니다.
    """
    today = datetime.now()
    last_month_date = today.replace(day=1) - timedelta(days=1)
    year = last_month_date.year
    month = last_month_date.month
    _, last_day = calendar.monthrange(year, month)
    start_date = datetime(year, month, 1, 0, 0, 0)
    end_date = datetime(year, month, last_day, 23, 59, 59)
    return start_date, end_date

def get_last_month_info():
    """점유율 기준일자를 리턴하는 함수
    스크립트 실행일을 기준으로 지난 연도와 월의 문자열을 계산합니다.

    Returns:
        last_month_yyyymm: 지난달의 연도와 월을 계산하여 "YYYYMM" 형태의 문자열로 리턴합니다.

    Notes:
        # 1. 이 함수는 점유율 페이지 작성을 위해서 호출됩니다.
    """
    today = datetime.now()
    last_month_date = today.replace(day=1) - timedelta(days=1)
    last_month_yyyymm = last_month_date.strftime('%Y%m')
    return last_month_yyyymm

def attach_csv_to_page(confluence_client, page_id, filename):
    """작성된 페이지에 CSV 파일을 첨부하는 함수
    작성된 페이지에 수집된 데이터를 CSV 파일로 첨부합니다.

    Args:
        confluence_client: 파일첨부에 필요한 Confluence 데이터
        page_id: 파일을 첨부할 페이지 아이디
        filename: 첨부파일의 파일명

    Returns:
        Boolean(True/False): 파일 첨부 여부에 따라 리턴합니다.

    Notes:
        # 1. 이 함수는 페이지 아이디가 필요하기 때문에, 페이지가 작성된 이후에 바로 호출됩니다.
        # 2. 첨부된 파일은 페이지의 세부정보에서 확인해주세요.
    """
    try:
        print(f"CSV 파일 첨부 시도: {filename}")
        confluence_client.attach_file(
            filename=filename,
            name=os.path.basename(filename), # 컨플루언스에 표시될 이름
            content_type='text/csv',
            page_id=page_id,
        )
        print(f"CSV 파일 첨부 완료: {filename}")

        # 첨부 후 로컬 파일 삭제 (선택 사항)
        os.remove(filename)
        print(f"로컬 CSV 파일 삭제 완료.")
        return True

    except Exception as e:
        print(f"파일 첨부 실패: {e}")
        return False

def scrape_app_store_reviews(app_id, app_name, country_code, start_date):
    """앱 스토어 리뷰를 수집하는 함수
    "confluence_config.json"에 있는 정보를 바탕으로 앱 스토어에서 리뷰를 수집합니다.

    Args:
        app_id: 앱 스토어에 등록된 앱아이디
        app_name: 앱 스토어에 등록된 앱이름
        country_code: 수집할 리뷰의 국가코드
        start_date: 수집할 리뷰의 시작 일자

    Returns:
        app_store_reviews: 앱 스토어 리뷰를 리스트 형태로 리턴합니다.
    """
    app = AppStore(country=country_code, app_id=app_id, app_name=app_name)
    app_store_reviews = []

    try:
        app.review()
    except Exception as e:
        print(f"App Store 리뷰 수집 중 라이브러리 오류 발생: {e}. 수집을 건너뜁니다.")
        return []

    if not app.reviews:
        return []

    for review in app.reviews:
        review_date = review['date']

        if review_date >= start_date:
            temp_list = [review['rating'], review['review'], review_date, 'App Store']
            app_store_reviews.append(temp_list)
        else:
            print("App Store: 지난달 시작일 이전 리뷰 도달, 수집 중단.")
            return app_store_reviews

    return app_store_reviews

def scrape_reviews_store(config, confluence_client):
    """플레이 스토어와 앱스토어 리뷰를 수집하여 페이지를 작성하는 함수
    "confluence_config.json"에 있는 정보를 바탕으로 스토어에서 리뷰를 수집하고 페이지를 작성합니다.

    Args:
        config: "confluence_config.json" 파일의 데이터
        confluence_client: 스토어 리뷰페이지 작성에 필요한 Confluence 데이터

    Notes:
        # 1. 이 함수가 실행되면, 각 스토어의 등록된 앱 리뷰를 수집해서 페이지가 작성됩니다.
        # 2. 페이지 작성이 완료되면, CSV 파일을 첨부합니다.
    """
    # 설정 정보 로드
    GP_APP_ID = config.get('review_config', {}).get('gp_app_id')
    AS_APP_ID = config.get('review_config', {}).get('as_app_id')
    AS_APP_NAME = config.get('review_config', {}).get('as_app_name')
    AS_COUNTRY = config.get('review_config', {}).get('as_country_code', 'kr')

    review_space_key = config['review_config']['space_key']
    review_parent_id = config['review_config']['parent_page_id']

    START_DATE, END_DATE = get_last_month_range()

    all_reviews = []

    # Google Play 리뷰 수집
    if GP_APP_ID:
        gp_reviews = []
        token = None
        keep_scraping = True
        # print(f"--- Google Play ({START_DATE.strftime('%Y년 %m월')}) 리뷰 수집 시작 ---")

        while keep_scraping:
            result, continuation_token = reviews(GP_APP_ID, lang='ko', country='kr', continuation_token=token, sort=Sort.NEWEST, count=1000, filter_score_with=None)
            if not result: break
            token = continuation_token

            for review in result:
                review_date = review['at']
                if review_date >= START_DATE:
                    # 'score', 'content', 'date', 'source' 순서에 맞춤
                    gp_reviews.append([review['score'], review['content'], review_date,'Google Play'])
                else:
                    keep_scraping = False
                    break
            if not keep_scraping and not token: break

        all_reviews.extend(gp_reviews)
    else:
        print("Google Play 앱 ID가 없어 수집을 건너뜁니다.")


    # # App Store 리뷰 수집
    # if AS_APP_ID and AS_APP_NAME:
    #     as_reviews = scrape_app_store_reviews(AS_APP_ID, AS_APP_NAME, AS_COUNTRY, START_DATE)
    #     all_reviews.extend(as_reviews)
    # else:
    #     print("App Store ID 또는 App Name이 없어 수집을 건너뜁니다.")


    # 데이터 통합 및 최종 필터링
    # DataFrame 컬럼 통일: ['score', 'content', 'date', 'source']
    review_df = pd.DataFrame(all_reviews, columns=['score', 'content', 'date', 'source'])
    filtered_df = review_df[review_df['date'] <= END_DATE]

    filtered_count = len(filtered_df)

    # print(f"{START_DATE.strftime('%Y년 %m월')} 최종 통합 리뷰 수: {filtered_count}")

    if filtered_df.empty:
        print("수집된 리뷰가 없어 페이지 작성을 건너뜁니다.")
        return

    # CSV 파일 작성
    csv_filename = f"reviews_{START_DATE.strftime('%Y%m')}.csv"
    filtered_df.to_csv(csv_filename, index=True, encoding='utf-8')
    # print(f"CSV 파일 작성 완료: {csv_filename}")

    # HTML 변환
    html_table = filtered_df.to_html(index=False, classes="confluenceTable", escape=False)

    # 컨플루언스 내용 구성
    page_title = f"[App Review] {START_DATE.strftime('%Y-%m')}"

    storage_format_content = f"""
    <h2>{START_DATE.strftime('%Y년 %m월')} 통합 앱 리뷰 보고서입니다. </h2>
    <p>수집 플랫폼: Google Play Store</p>
    <p>수집 기간: {START_DATE.strftime('%Y-%m-%d')} ~ {END_DATE.strftime('%Y-%m-%d')}</p>
    <p>작성된 시간: {strftime('%Y-%m-%d %H:%M:%S')}</p>

    <h3>지난달 리뷰 목록 (총 {filtered_count}건)</h3>

    {html_table}
    """

    # 페이지 작성 호출
    page_id = create_confluence_page(confluence_client, review_space_key, review_parent_id, page_title, storage_format_content)

    if page_id:
        # CSV 파일 첨부 및 로컬 파일 삭제
        attach_csv_to_page(confluence_client, page_id, csv_filename)
    return

def crawl_data(driver, crawling_target_url):
    """타겟 웹사이트에서 필요한 데이터를 크롤링하고 HTML로 전환하는 함수
    각 url에 진입하여 점유율 데이터를 크롤링하고, 페이지 작성을 위한 HTML과 테이블 아이디, CSV 파일이름을 리턴합니다.

    Args:
        driver: 셀레니움을 실행할 웹드라이버 객체
        crawling_target_url: "confluence_config.json"에 저장된 크롤링 대상이 되는 웹페이지

    Returns:
        full_report_html: 페이지에 첨부할 본문의 HTML을 리턴합니다.
        first_table_id: 페이지 작성에 필요한 테이블의 아이디를 리턴합니다.
        csv_filename: 페이지에 첨부된 CSV 파일의 이름을 리턴합니다.
    """
    PATH_LIST = [
        "android-version-market-share/mobile/",
        "android-version-market-share/tablet/",
        "ios-version-market-share/mobile/",
        "ios-version-market-share/tablet/",
        "vendor-market-share/mobile/",
        "vendor-market-share/tablet/",
        "vendor-market-share/console/",
        "browser-market-share/all/",
        "browser-version-market-share/all/",
        "ai-chatbot-market-share/all/"
    ]

    last_month_yyyymm = get_last_month_info()
    from_month = last_month_yyyymm
    to_month = last_month_yyyymm
    periode = f"{from_month}-{to_month}"

    full_report_html = ""
    first_table_id = None

    # print(f"수집 대상 기간: {last_month_yyyymm}월")

    # CSV 저장을 위한 데이터 수집 리스트 초기화
    csv_data = []

    for path in PATH_LIST:
        URL = f"{crawling_target_url}{path}south-korea/#monthly-{periode}-bar"
        driver.get(URL)
        time.sleep(3)

        current_table_id = f"stats-table-{path.split('/')[0]}"
        if first_table_id is None:
            first_table_id = current_table_id

        data_success = False
        temp_versions = []
        temp_shares = []
        table_caption = ""

        try:
            # 1. 통계 테이블 데이터 추출 (파싱)
            stats_table_element = driver.find_element(By.CLASS_NAME, 'stats-snapshot')
            table_caption = stats_table_element.find_element(By.TAG_NAME, 'tfoot').text
            data_rows = stats_table_element.find_elements(By.XPATH, './/tbody/tr')

            for row in data_rows:
                item = row.find_element(By.TAG_NAME, 'th').text
                share_span = row.find_element(By.CSS_SELECTOR, 'td > span.count')
                share_value = float(share_span.text)

                temp_versions.append(item)
                temp_shares.append(share_value)

                data_source = path.split('/')[0]
                for version, share_value in zip(temp_versions, temp_shares):
                    csv_data.append([data_source, version, share_value])

            data_success = True

        except Exception as e:
            print(f"크롤링 실패 ({path}): {e}. 테이블 작성 스킵.")
            full_report_html += f"<h2>{path.replace('-market-share/', '').replace('/', ' ').strip().upper()}</h2>"
            full_report_html += f"<p>데이터 로드 오류: {e}</p>"
            continue

        if data_success:
            # Others 항목 계산 및 추가 (100% 맞추기)
            total_crawled_share = sum(temp_shares)
            remaining_share = 100.0 - total_crawled_share
            if remaining_share > 0:
                others_share = round(remaining_share, 2)
                temp_versions.append('기타(Others)')
                temp_shares.append(others_share)

            # 테이블 HTML 구성 (항목/점유율 행렬 변환)
            item_cells = "".join([f"<td>{v}</td>" for v in temp_versions])
            item_row = f"<tr><th>항목</th>{item_cells}</tr>"
            share_cells = "".join([f"<td>{s:.2f}%</td>" for s in temp_shares])
            share_row = f"<tr><th>점유율(%)</th>{share_cells}</tr>"
            col_count = len(temp_versions) + 1

            transposed_table_html = f"""<table id='{current_table_id}' class="confluenceTable" border="1" style="width:100%; text-align:center;">
                <thead><tr><th colspan="{col_count}" style="text-align:left; background-color:#f0f0f0; padding: 10px;">{table_caption}</th></tr></thead>
                <tbody>{item_row}{share_row}</tbody></table>"""

            full_report_html += f"<h2>{path.replace('-market-share/', '').replace('/', ' ').strip().upper()}</h2>"
            full_report_html += transposed_table_html

            # 임베드 코드 추출 및 추가
            embed_code_value = driver.find_element(By.XPATH, '//*[@id="embed-code"]').get_attribute('value')
            full_report_html += f"<div style='margin-bottom: 30px; border: 1px solid #eee; padding: 5px;'>{html.unescape(embed_code_value)}</div>"

    share_df = pd.DataFrame(csv_data, columns=['Source', 'Item', 'Share (%)'])
    csv_filename = f"market_share_{get_last_month_info()}.csv"
    share_df.to_csv(csv_filename, index=False, encoding='utf-8')
    # print(f"CSV 파일 작성 완료: {csv_filename}")
    # print(f"총 {len(PATH_LIST)}개 경로 크롤링 완료.")
    return full_report_html, first_table_id, csv_filename

def crawl_market_share(driver, config):
    """웹페이지를 크롤링하여 점유율 페이지를 작성하는 함수
    "confluence_config.json"에 있는 정보를 바탕으로 해당 웹페이지에서 점유율 데이터를 수집하고 페이지를 작성합니다.

    Args:
        config: "confluence_config.json" 파일의 데이터
        confluence_client: 점유율 페이지 작성에 필요한 Confluence 데이터

    Notes:
        # 1. 이 함수가 실행되면, 각 웹페이지에서 점유율을 크롤링해서 페이지가 작성됩니다.
        # 2. 페이지 작성이 완료되면, CSV 파일을 첨부합니다.
    """

    crawling_target_url = config['market_share_config']['target_url']
    share_space_key = config['market_share_config']['space_key']
    share_parent_id = config['market_share_config']['parent_page_id']

    # 크롤링 실행 및 데이터 받기
    crawled_html_content, first_table_id, csv_filename = crawl_data(driver, crawling_target_url)

    if not crawled_html_content or not first_table_id:
        print("점유율 크롤링된 내용이 없거나 테이블 ID를 찾을 수 없어 페이지 작성을 건너뜁니다.")
        return

    # 컨플루언스 내용 구성
    last_month_info = get_last_month_info()
    page_title = f"[Market Share] {last_month_info[:4]}-{last_month_info[4:]}"

    storage_format_content = f"""
    <h2>{last_month_info[:4]}년 {last_month_info[4:]}월 점유율 보고서입니다. </h2>
    <p>작성된 시간: {strftime('%Y-%m-%d %H:%M:%S')}</p>

    {crawled_html_content}
    """

    page_id = create_confluence_page(confluence_client, share_space_key, share_parent_id, page_title, storage_format_content)
    if page_id:
        # 파일 첨부 및 로컬 파일 삭제
        attach_csv_to_page(confluence_client, page_id, csv_filename)
    return

# ====================================================================
# D. 메인 실행 루틴
# ====================================================================

if __name__ == "__main__":
    """메인 함수 실행
    이 스크립트 파일이 실행될때 아래 순서대로 로직을 실행합니다.

    # 1. 실행된 스크립트 파일의 절대 경로를 script_dir에 저장하고, CONFIG_PATH 변수에 저장합니다.
    # 2. 이 스크립트의 주요 로직이 아래 순서대로 실행됩니다.
        # 2-1. load_config()
        # 2-2. initialize_confluence_client()
        # 2-3. web_driver_setting()
        # 2-4. scrape_reviews_store()
        # 2-5. crawl_market_share()
    """

    script_dir = os.path.dirname(os.path.abspath(__file__)) # 이 스크립트 파일이 위치한 디렉토리의 절대경로
    CONFIG_PATH = os.path.join(script_dir, "confluence_config.json") # "{script_dir}\confluence_config.json"의 형태로 운영체제에 맞게 파일경로를 작성

    # 설정 저장
    config = load_config(CONFIG_PATH)

    if config is None:
        exit()

    # 컨플루언스 클라이언트 초기화
    confluence_client = initialize_confluence_client(config)

    if confluence_client is None:
        exit()

    # 웹 드라이버 초기화 (점유율 크롤링에 필요)
    driver = web_driver_setting()

    # 리뷰 보고서 작성 (통합 함수 호출)
    page_id_review = scrape_reviews_store(config, confluence_client)
    if page_id_review:
        pass

    # 점유율 보고서 작성 (드라이버가 초기화된 경우에만 실행)
    if driver:
        result = crawl_market_share(driver, config)

        driver.quit()
        print("--- WebDriver 종료 ---")
    else:
        print("WebDriver 초기화 실패로 시장 점유율 보고서 작성을 건너뜁니다.")

    print("\n\n=== 모든 보고서 작성 프로세스 완료 ===")
