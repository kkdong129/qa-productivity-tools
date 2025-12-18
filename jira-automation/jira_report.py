import requests
import json
from datetime import datetime, timedelta, timezone
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
import csv

"""JIRA REST API를 요청하여 이슈를 조회합니다. 조회된 결과는 슬랙 메세지와 csv파일이 첨부된 이메일로 전송됩니다.

Notes:
    # 1. "jira_report.py"와 "jira_config.json" 파일을 동일한 디렉토리에 위치시킨 다음에 이 스크립트를 실행합니다.
    # 2. Window OS의 Task Scheduler 또는 Mac OS의 Crontab, Launchd 등을 활용하여 특정 주기마다 이 스크립트를 실행시킬 수 있습니다.
"""

def fetch_jira_issues(jql, max_results=1000):
    """Jira 이슈 조회
    CONFIG_PATH에 저장된 JSON 데이터를 세팅하고, JIRA REST API(/search/jql)를 요청하고 응답값을 저장합니다.

    Args:
        jql: 검색에 필요한 jql 쿼리
        max_results: jql로 가져올 검색 결과의 최대 개수 제한, Default 1000개

    Returns:
        report: jql로 조회한 각 티켓의 데이터를 리스트로 저장해서 리턴합니다.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    jira_conf = config["jira"]

    url = f"{jira_conf['base_url']}/rest/api/3/search/jql"
    auth = (jira_conf["email"], jira_conf["api_token"])
    headers = {"Content-Type": "application/json"}
    payload = {
        "jql": jql,
        "maxResults": max_results,
        "fields": ["key", "summary", "status", "assignee", "updated", "priority", "comment"] # 조회에 필요한 필드를 정의합니다.
    }

    resp = requests.post(url, auth=auth, headers=headers, json=payload)
    if resp.status_code != 200:
        print(f"Jira API 오류: {resp.status_code}\n{resp.text}")
        return []

    data = resp.json()["issues"]
    report = []
    for issue in data:
        # payload에 요청했던 fields를 각 변수에 저장합니다.
        f = issue["fields"]
        assignee_obj = f.get("assignee")
        assignee_id = assignee_obj.get("accountId") if assignee_obj else None
        priority_obj = f.get("priority")
        priority_name = priority_obj.get("name") if priority_obj else "None"

        comments_data = f.get("comment", {}).get("comments", [])
        latest_comment_date = "없음"

        if comments_data:
            # Jira API는 기본적으로 오래된 순으로 정렬하므로 [-1]이 최신입니다.
            # 날짜 파싱 오류를 방지하기 위해 단순히 문자열 앞부분(YYYY-MM-DD)만 가져옵니다.
            raw_date = comments_data[-1].get("updated", "")
            if raw_date:
                latest_comment_date = raw_date[:10]

        report.append({
            "key": issue["key"],
            "url": f"{jira_conf['base_url']}/browse/{issue['key']}",
            "priority": priority_name,
            "summary": f.get("summary", ""),
            "status": f.get("status", {}).get("name", ""),
            "assignee": assignee_obj.get("displayName") if assignee_obj else "Unassigned",
            "updated": f.get("updated", "")[:10],
            "latest_comment_date": latest_comment_date,
            "assignee_id": assignee_id
        })

    return report


def add_comment_to_issue(issue_key, assignee_id, comment_text):
    """Jira 코멘트 추가
    CONFIG_PATH에 저장된 JSON 데이터를 세팅하고, JIRA REST API(/issue/{issue_key}/comment)를 요청하고 코멘트를 추가합니다.

    Args:
        issue_key: 코멘트를 추가할 티켓의 키 값
        assignee_id: 해당 티켓의 담당자
        comment_text: 티켓에 추가할 코멘트 내용

    Notes:
        # 1. 코멘트를 추가하는 계정은 "jira_config.json"에 정의된 계정으로 코멘트를 추가하게 됩니다.
        # 2. 이 함수가 실행되면, 각 티켓에 바로 코멘트가 추가됩니다.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    jira_conf = config["jira"]

    url = f"{jira_conf['base_url']}/rest/api/3/issue/{issue_key}/comment"
    auth = (jira_conf["email"], jira_conf["api_token"])
    headers = {"Content-Type": "application/json"}

    #ADF 구조에 mention 노드를 포함합니다.
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "mention",  # 멘션 노드 시작
                            "attrs": {
                                "id": assignee_id,
                                "accessLevel": "CONTAINER"
                            }
                        },
                        {
                            "type": "text",  # 텍스트 노드 (멘션 뒤 텍스트)
                            "text": comment_text
                        }
                    ]
                }
            ]
        }
    }

    resp = requests.post(url, auth=auth, headers=headers, json=payload)
    if resp.status_code == 201:
        print(f"코멘트 추가 성공: {issue_key}")
    else:
        print(f"코멘트 추가 실패: {issue_key} ({resp.status_code})")
        print(resp.text)


def build_slack_message(report, title):
    """Slack 메세지 생성
    Slack 메세지를 작성합니다. send_slack_message 함수 내부에서 실행됩니다.

    Args:
        report: jql로 조회된 각 티켓의 데이터 리스트
        title: jql을 설명하는 제목, jql_queries 딕셔너리 안에 저장된 키

    Returns:
        "\n".join(lines): 반복문으로 작성된 문자열을 줄바꿈하여 하나의 문자열로 리턴합니다.
    """
    if not report:
        return f"{title}: 🎉 해당 조건의 Jira 이슈가 없습니다!"

    lines = [f"*{title}*"]
    for r in report[:15]: # Slack 메세지로 작성할 이슈의 개수를 최대 15개로 제한합니다.
        comment_info = f"[최근 코멘트 등록일자: {r['latest_comment_date']}]"
        lines.append(f"• <{r['url']}|{r['key']}> - {r['status']}, {r['summary']}, {r['assignee']} - {comment_info}")
    lines.append(f"\n*총 {len(report)}개 이슈* — {datetime.now().strftime('%Y-%m-%d %H:%M')} 기준")
    return "\n".join(lines)


def send_slack_message(report, title):
    """Slack 메세지 생성
    CONFIG_PATH에 저장된 JSON 데이터를 세팅하고, Slack 웹훅으로 메세지를 전송합니다.

    Args:
        report: jql로 조회된 각 티켓의 데이터 리스트
        title: jql을 설명하는 제목, jql_queries 딕셔너리 안에 저장된 키

    Notes:
        # 1. 이 함수가 실행되면, 설정된 웹훅으로 바로 Slack 메세지가 전송됩니다.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    webhook_url = config["slack"]["webhook_url"]
    message = build_slack_message(report, title) #줄바꿈이 적용된 문자열을 저장합니다.
    payload = {"text": message}
    resp = requests.post(webhook_url, json=payload)
    if resp.status_code == 200:
        print(f"Slack 메시지 전송 완료: {title}")
    else:
        print(f"Slack 전송 실패: {resp.status_code}, {resp.text}")


def format_report_html(report, title):
    """이메일 본문 HTML 형식 보고서 생성
    이메일 본문에 사용되는 보고서인 HTML을 작성합니다.

    Args:
        report: jql로 조회된 각 티켓의 데이터 리스트
        title: jql을 설명하는 제목, jql_queries 딕셔너리 안에 저장된 키

    Returns:
        html: 이메일 본문에 작성할 HTML 문자열을 리턴합니다.
    """
    if not report:
        return f"<h2>{title}</h2><p>🎉 해당 조건의 이슈가 없습니다!</p>"

    # HTML 형식으로 보고서 블록 생성
    html = f'<h2>{title} ({len(report)}개 이슈)</h2>'
    html += '<ul style="list-style-type: none; padding-left: 20px;">'  # HTML 리스트

    for r in report:
        comment_label = f'<span style="color: #666;">(최근 댓글 등록일: {r["latest_comment_date"]})</span>'
        # HTML <a> 태그 사용
        item_html = (
            f'<li>• <a href="{r["url"]}" style="text-decoration:none;">{r["key"]}</a> - '
            f'{r["status"]}, {r["summary"]}, {r["assignee"]} {comment_label}</li>'
        )
        html += item_html

    html += '</ul>'
    return html


def send_report_email(subject, body, email_attachments=None):
    """Gmail 전송 함수
    이메일 제목, HTML, 첨부 파일 경로를 받아서 CONFIG_PATH에 저장된 이메일로 전송합니다.

    Args:
        subject: Jira 보고서 이메일의 제목
        body: 이메일 본문에 작성할 HTML
        email_attachments: 이메일에 첨부할 파일 경로,  Default 첨부 파일 없음
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    gmail_conf = config["gmail"]

    sender_email = gmail_conf["sender_email"]
    recipient_emails = gmail_conf["recipient_emails"]
    app_password = gmail_conf["app_password"]
    recipients_header = ", ".join(recipient_emails)

    # 1. MIME 객체 생성: 반드시 MIMEMultipart()를 사용해야 합니다.
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipients_header
    msg['Subject'] = Header(subject, 'utf-8')

    # 2. 본문(HTML) 추가: msg에 본문을 첨부합니다.
    msg.attach(MIMEText(body, 'html', 'utf-8'))

    # 3. 첨부 파일 추가
    if email_attachments:
        for file_path in email_attachments:
            if not os.path.exists(file_path):
                print(f"첨부 파일을 찾을 수 없습니다: {file_path}")
                continue

            try:
                # 3-1. 파일 읽기 및 MIMEBase 객체 생성
                with open(file_path, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")  # MIME 타입
                    part.set_payload(attachment.read())

                # 3-2. Base64 인코딩
                encoders.encode_base64(part)

                # 3-3. 파일 이름 지정
                file_name = os.path.basename(file_path)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename=\"{Header(file_name, 'utf-8').encode()}\"",
                )

                # 3-4. 메시지에 첨부
                msg.attach(part)
                print(f"첨부 파일 추가됨: {file_name}")

            except Exception as e:
                print(f"첨부 파일 처리 중 오류 발생: {file_path} -> {e}")

    try:
        # 3. SMTP 서버 연결 및 로그인
        server = smtplib.SMTP(gmail_conf["smtp_server"], gmail_conf["smtp_port"])
        server.starttls()  # 보안 연결 설정
        server.login(sender_email, app_password)

        # 4. 이메일 전송
        server.sendmail(sender_email, recipient_emails, msg.as_string())
        server.quit()

        print(f"Jira 보고서 이메일 전송 완료: {recipients_header}")

    except Exception as e:
        print(f"이메일 전송 실패: {e}")


def create_csv_file(report, filename="report_data.csv"):
    """CSV 파일 생성 함수
    이메일에 첨부할 csv 파일을 생성합니다.

    Args:
        report: jql로 조회된 각 티켓의 데이터 리스트
        filename: 이 함수로 생성되는 csv 파일의 이름입니다.

    Returns:
        csv_file_path: 생성된 csv 파일의 경로를 리턴합니다.
    """
    # CSV 파일은 이 스크립트가 실행되는 디렉터리에 저장됩니다.
    csv_file_path = os.path.join(script_dir, filename)

    # report가 비어있는 경우
    if not report:
        print(f"보고서가 비어있어 CSV 파일 '{filename}'을 생성하지 않습니다.")
        return None

    # 헤더 설정 (report 리스트의 첫 번째 항목 키를 사용)
    fieldnames = [
        "key",
        "url",
        "summary",
        "priority",
        "status",
        "assignee",
        "updated",
        "latest_comment_date",
        "assignee_id"
    ]

    try:
        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            writer.writerows(report)

        print(f"CSV 파일이 성공적으로 생성되었습니다: {csv_file_path}")
        return csv_file_path

    except Exception as e:
        print(f"CSV 파일 생성 중 오류 발생: {e}")
        return None


def job():
    """이 스크립트 파일이 실행되는 주요 로직 실행 함수
    python jira_report.py 스크립트가 직접 실행될때, 동작하는 로직을 실행합니다.

    Notes:
        # 1. 미리 정의된 각 jql에 대해서 조회 결과를 report 리스트에 저장합니다.
            # 1.1 report = fetch_jira_issues(jql)

        # 2. for 반복문이 실행되어 각 jql 조회 결과를 Slack 메세지로 전송하고 동시에 HTML 보고서 파일을 취합하여 작성합니다.
            # 2.1 send_slack_message(report, title)
            # 2.2 message = build_slack_message(report, title)
            # 2.3 report_html_block = format_report_html(report, title)

        # 3. for 반복문이 종료되면, 취합된 jql 조회 결과를 현재 디렉토리 위치에 CSV 파일을 생성합니다.
            # 3.1 csv_path = create_csv_file(full_issue_report, csv_filename)

        # 4. 이메일 제목과 취합된 HTML 보고서, 생성된 CSV 파일을 첨부하여 이메일을 전송합니다.
            # 4.1 send_report_email(email_subject, full_report_body_html, email_attachments=[csv_path])

        # 5. 생성된 CSV 파일을 삭제합니다.
    """
    base_jql = '''project IN (TUYA, QA) AND type IN (Bug, Improvement) AND status NOT IN ("완료 (Done)", "QA 완료", "이슈 아님")'''
    sort_jql = '''ORDER BY priority DESC''' # jql 조회 결과를 우선순위 순서대로 정렬합니다.

    jql_queries = {
        "😮 1주 이상 ~ 2주 미만 미업데이트 이슈": f"{base_jql} AND updated <= -1w AND updated > -2w {sort_jql}",
        "😲 2주 이상 ~ 3주 미만 미업데이트 이슈": f"{base_jql} AND updated <= -2w AND updated > -3w {sort_jql}",
        "😢 3주 이상 ~ 4주 미만 미업데이트 이슈": f"{base_jql} AND updated <= -3w AND updated > -4w {sort_jql}",
        "😭 장기 미업데이트 이슈 (4주 초과)": f"{base_jql} AND updated <= -4w {sort_jql}"
    }

    # 검색 결과 취합을 위한 변수 초기화
    full_issue_report = []

    # 이메일 본문 취합용
    full_report_body_html = """
    <h1>Jira 미업데이트 이슈 데일리 보고서</h1>
    <p>현재 TUYA와 QA 프로젝트에 등록되어있는 이슈들입니다. 각 티켓의 담당자는 현재 진행상태를 업데이트해주세요!</p>
    <p>티켓의 상태가 완료('완료 (Done)', 'QA 완료', '이슈 아님')인 이슈는 모두 제외되었습니다.</p>
    <br><hr><br>
    """
    total_issue_count = 0

    print(f"[{datetime.now()}] 🔍 Jira 검색 실행 및 보고서 취합 중...")

    for title, (jql) in jql_queries.items():
        print(f"\n[{datetime.now()}] -> {title} 검색 시작...")

        report = fetch_jira_issues(jql)

        # 생성되는 CSV 파일에 구분선 역할을 할 딕셔너리 생성
        separator_row = {
            "key": f"--- {title} ({len(report)}건) ---",
            "url": "",
            "summary": "",
            "priority": "",
            "status": "",
            "assignee": "",
            "updated": "",
            "latest_comment_date": "",
            "assignee_id": ""
        }
        # 전체 리포트에 구분선 추가
        full_issue_report.append(separator_row)
        full_issue_report.extend(report)

        # SLACK: 개별 메시지로 즉시 전송 (반복문 안에서 실행됩니다.)
        send_slack_message(report, title)

        # EMAIL: HTML 블록 생성 및 취합
        report_html_block = format_report_html(report, title)  # HTML 포맷 함수 호출
        full_report_body_html += report_html_block + "<br><hr><br>"
        total_issue_count += len(report)

        # (옵션) 코멘트 추가 로직은 여기에 위치

    # GMAIL: 모든 보고서가 취합된 후, 최종적으로 1회만 전송 (반복문 밖에서 1번 실행)
    total_issue_count = len(full_issue_report)

    # CSV 파일 생성
    csv_filename = f"jira_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = create_csv_file(full_issue_report, csv_filename)

    # 이메일 제목 구성
    email_subject = f"Jira 미업데이트 이슈 데일리 보고서 (총 {total_issue_count}건) - {datetime.now().strftime('%Y-%m-%d')}"

    # Gmail 전송
    if total_issue_count > 0 and csv_path:
        # CSV 파일 경로를 리스트로 전달합니다.
        send_report_email(email_subject, full_report_body_html, email_attachments=[csv_path])
    elif total_issue_count == 0:
        send_report_email(email_subject, "모든 조건에서 미업데이트 이슈가 발견되지 않았습니다. 🎉", email_attachments=None)

    # 7. 생성된 CSV 파일 삭제 (스크립트 실행 후 파일을 남기지 않으려면)
    if csv_path and os.path.exists(csv_path):
        os.remove(csv_path)
        print(f"🗑️ 생성된 CSV 파일 삭제: {csv_path}")

    # if report:
    #     print("💬 미업데이트 티켓에 코멘트 추가 중...")
    #     for issue in report:
    #         if not issue["assignee_id"]:
    #             print(f"⚠️ {issue['key']} 담당자 없음 — 코멘트 생략")
    #             continue
    #
    #         # 멘션 ID와 텍스트를 분리합니다.
    #         assignee_id = issue["assignee_id"]
    #
    #         # 멘션 뒤에 들어갈 텍스트만 정의
    #         comment_text = "님, 이 이슈는 최근 일주일 이상 업데이트되지 않았습니다. 확인 부탁드립니다 🙏"
    #
    #         # 함수 호출 시 3개의 인자를 전달
    #         add_comment_to_issue(issue["key"], assignee_id, comment_text)


if __name__ == "__main__":
    """메인 함수 실행
    이 스크립트 파일이 실행될때 아래 순서대로 로직을 실행합니다.

    # 1. 실행된 스크립트 파일의 절대 경로를 script_dir에 저장하고, CONFIG_PATH 변수에 저장합니다.
    # 2. 이 스크립트의 주요 로직이 포함된 함수가 실행됩니다.
        # 2-1. job()
    """

    script_dir = os.path.dirname(os.path.abspath(__file__)) # 이 스크립트 파일이 위치한 디렉토리의 절대경로
    CONFIG_PATH = os.path.join(script_dir, "jira_config.json") # "{script_dir}\jira_config.json"의 형태로 운영체제에 맞게 파일경로를 생성

    print("🤖 Jira → Slack & Email 자동 보고 봇 실행 중 (Ctrl+C로 종료)")
    job()