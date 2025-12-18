"""
jql_search.py
- Jira Cloud 최신 API (User Privacy 대응)
- accountId 기반 필터 강제
- pdcleaner API로 JQL 자동 변환
- X-Atlassian-Force-Account-Id 헤더 추가
- GET 요청 사용 (안정성 우선)
"""

import requests
from requests.auth import HTTPBasicAuth
import json
import csv
import sys

# ======================
# Jira 계정 정보 수정
# ======================
JIRA_BASE_URL = "https://your-domain.atlassian.net"
JIRA_EMAIL = "email@company.com"
JIRA_API_TOKEN = "your-api-token"

PAGE_SIZE = 100  # 한 번에 가져올 이슈 수
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Atlassian-Force-Account-Id": "true"  # GDPR 모드 강제
}

# =====================================
# JQL 변환 함수 (User Privacy 대응)
# =====================================
def clean_jql_with_pdcleaner(jql_query):
    """
    Jira의 /rest/api/3/jql/pdcleaner API로 username/userKey 기반 JQL을 accountId 기반으로 자동 변환합니다.
    """
    url = f"{JIRA_BASE_URL}/rest/api/3/jql/pdcleaner"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    payload = {"queries": [jql_query]}

    try:
        resp = requests.post(url, headers=HEADERS, auth=auth, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            new_jql = data.get("queries", [{}])[0].get("query", jql_query)
            if new_jql != jql_query:
                print("JQL이 accountId 기반으로 변환되었습니다:")
                print(f"  → {new_jql}")
            return new_jql
        else:
            print(f"⚠️ pdcleaner 호출 실패 ({resp.status_code}) — 원문 JQL 사용")
            return jql_query
    except Exception as e:
        print(f"⚠️ pdcleaner 변환 중 오류 발생: {e}")
        return jql_query


# =====================================
# JQL로 이슈 조회 (GET 방식)
# =====================================
def fetch_issues_with_jql(jql_query, max_results=1000, fields="key,summary,status,assignee,created"):
    """
    GET /rest/api/3/search/jql?jql=... 방식으로 이슈 조회 (페이징 자동)
    """
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    url = f"{JIRA_BASE_URL}/rest/api/3/search/jql"

    start_at = 0
    all_issues = []

    while True:
        params = {
            "jql": jql_query,
            "startAt": start_at,
            "maxResults": min(PAGE_SIZE, max_results - len(all_issues)) if max_results else PAGE_SIZE,
            "fields": fields
        }

        resp = requests.get(url, headers=HEADERS, auth=auth, params=params)

        if resp.status_code != 200:
            print(f"요청 실패 ({resp.status_code})")
            try:
                print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
            except Exception:
                print(resp.text)
            return None

        data = resp.json()
        issues = data.get("issues", [])
        total = data.get("total", 0)

        all_issues.extend(issues)
        fetched = len(issues)
        print(f"[INFO] startAt={start_at} fetched={fetched} total_so_far={len(all_issues)} / {total}")

        if fetched == 0 or len(all_issues) >= total or (max_results and len(all_issues) >= max_results):
            break

        start_at += fetched

    return all_issues


# =====================================
# 결과 출력 및 저장
# =====================================
# =====================================
# 결과 출력 (콘솔 링크 포함)
# =====================================
def print_issues(issues):
    if not issues:
        print("결과가 없습니다.")
        return

    print(f"\n 총 {len(issues)}개의 이슈를 가져왔습니다.\n")
    print(f"{'Jira Link':<70} | {'Status':<12} | {'Assignee':<20} | {'Created':<10} | Summary")
    print("-" * 130)

    for issue in issues:
        key = issue.get("key")
        f = issue.get("fields", {})
        summary = f.get("summary", "")
        status = f.get("status", {}).get("name", "")
        assignee = f.get("assignee", {}).get("displayName") if f.get("assignee") else "Unassigned"
        created = f.get("created", "")[:10] if f.get("created") else ""
        link = f"{JIRA_BASE_URL}/browse/{key}"  # Jira 티켓 링크

        print(f"{link:<70} | {status:<12} | {assignee:<20} | {created:<10} | {summary}")


# =====================================
# CSV 저장 (티켓 링크 포함)
# =====================================
def save_to_csv(issues, filename="jira_issues.csv"):
    if not issues:
        print("⚠️ 저장할 이슈가 없습니다.")
        return

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["key", "url", "status", "assignee", "created", "summary"])

        for issue in issues:
            key = issue.get("key")
            flds = issue.get("fields", {})
            status = flds.get("status", {}).get("name", "")
            assignee = flds.get("assignee", {}).get("displayName") if flds.get("assignee") else ""
            created = flds.get("created", "")[:10] if flds.get("created") else ""
            summary = flds.get("summary", "")
            url = f"{JIRA_BASE_URL}/browse/{key}"

            writer.writerow([key, url, status, assignee, created, summary])

    print(f"CSV 파일 저장 완료: {filename}")


# =====================================
# 실행
# =====================================
if __name__ == "__main__":
    print("Jira JQL 검색기 (v3, User Privacy 대응)")
    print('예시: project = QA AND status = "In Progress" ORDER BY created DESC')
    print("주의: assignee/reporter 조건은 accountId 기반으로 검색해야 합니다.")
    print("   (예: assignee = 5f8e3b2c1234560071a1a1a1)\n")

    jql_input = input("JQL 입력: ").strip()
    if not jql_input:
        print("JQL을 입력해야 합니다.")
        sys.exit(1)

    # ① pdcleaner API로 JQL 자동 변환
    jql_cleaned = clean_jql_with_pdcleaner(jql_input)

    # ② 최대 이슈 수 입력
    max_input = input("가져올 최대 이슈 수 (기본=1000): ").strip()
    max_results = int(max_input) if max_input.isdigit() else 1000

    # ③ 이슈 조회
    issues = fetch_issues_with_jql(jql_cleaned, max_results=max_results)
    if not issues:
        sys.exit(1)

    # ④ 콘솔 출력
    print_issues(issues)

    # ⑤ CSV 저장 옵션
    if input("\nCSV로 저장할까요? (y/N): ").strip().lower() == "y":
        fname = input("파일명 (기본 jira_issues.csv): ").strip() or "jira_issues.csv"
        save_to_csv(issues, fname)
