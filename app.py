from __future__ import annotations

import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, redirect, request, session, url_for
from markupsafe import escape


BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "templates" / "pages"
DATA_DIR = BASE_DIR / "data"
USER_ANSWERS_DIR = DATA_DIR / "user_answers"
LOGINS_FILE = DATA_DIR / "logins.jsonl"
ANSWERS_FILE = DATA_DIR / "answers.jsonl"

LOGIN_PAGE = "login.html"
CHOOSE_PAGE = "choose.html"
INTRO_PAGE = "intro.html"
END_PAGE = "end.html"
RESULTS_PAGE = "results.html"

QUESTION_PAGES = {
    "1": "q1.html",
    "2": "q2.html",
    "3": "q3.html",
    "4": "q4.html",
    "5": "q5.html",
    "6": "q6.html",
    "7": "q7.html",
    "8": "q8.html",
    "9": "q9.html",
    "10": "q10.html",
    "11": "q11.html",
    "12": "q12.html",
}

COMMON_ASSETS = {
    "jquery.min.js",
    "jquery-ui.min.js",
    "jquery.ui.touch-punch.min.js",
    "jquery-ui.css",
    "virt_kb.css",
    "virt_kb.js",
    "kim.css",
    "main7.css",
    "main10.css",
    "mpu.css",
    "basic_am7.js",
    "katex.min.css",
    "katex.min.js",
    "auto-render.min.js",
}

IMAGE_ASSETS = {
    "icon_pdf.png": "icon_pdf.png",
    "print.png": "print.png",
    "test.mp3": "test.mp3",
    "fon2.png": "fon2.png",
    "user_logo.png": "user_logo.png",
}

app = Flask(__name__)
app.secret_key = "fake-mcko-local-secret"


def raw_page(filename: str) -> str:
    return (PAGES_DIR / filename).read_text(encoding="utf-8")


def html(body: str) -> Response:
    return Response(body, mimetype="text/html; charset=utf-8")


def save_jsonl(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    data = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), **data}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def ensure_user_state() -> None:
    if "sid" not in session:
        session["sid"] = secrets.token_hex(16)
    if "participant_number" not in session:
        session["participant_number"] = secrets.randbelow(30) + 1


def user_answers_path() -> Path:
    ensure_user_state()
    USER_ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
    return USER_ANSWERS_DIR / f"{session['sid']}.json"


def load_answers() -> dict[str, dict[str, str]]:
    path = user_answers_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_answers(answers: dict[str, dict[str, str]]) -> None:
    user_answers_path().write_text(
        json.dumps(answers, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def today_ru() -> str:
    months = {
        1: "Января",
        2: "Февраля",
        3: "Марта",
        4: "Апреля",
        5: "Мая",
        6: "Июня",
        7: "Июля",
        8: "Августа",
        9: "Сентября",
        10: "Октября",
        11: "Ноября",
        12: "Декабря",
    }
    now = datetime.now()
    return f"{now.day} {months[now.month]} {now.year}"


def participant_label() -> str:
    ensure_user_state()
    login = session.get("login") or "test_28123"
    return f"{login}, ученик {session['participant_number']}"


def saved_questions() -> set[str]:
    return set(session.get("answered", []))


def asset_url(filename: str) -> str:
    if filename in COMMON_ASSETS:
        return f"/static/common/{filename}"
    if filename == "logo.png":
        return "/static/assets/logo.png"
    if filename in IMAGE_ASSETS:
        return f"/static/assets/{IMAGE_ASSETS[filename]}"
    return filename


def normalize_assets(body: str, *, login_page: bool = False) -> str:
    def replace_attr(match: re.Match[str]) -> str:
        attr, quote, url = match.groups()
        filename = url.split("/")[-1]
        if login_page and filename == "logo.png":
            new_url = "/static/assets/logo-login.png"
        else:
            new_url = asset_url(filename)
        return f'{attr}={quote}{new_url}{quote}'

    return re.sub(
        r'(href|src)=(["\'])([^"\']+(?:_files|_1|_2|_3|_4|_5|_6|_7|_8|_9|_10)[^"\']*/[^"\']+|[^"\']+_files/[^"\']+|results_files/[^"\']+|end_files/[^"\']+|[0-9]+(?:_[0-9]+)?_files/[^"\']+)\2',
        replace_attr,
        body,
    )


def inject_watermarks(body: str) -> str:
    css = """<style>
html, body {
	background: #ffffff url("/static/assets/bg.png") center 150px / 684px auto fixed repeat !important;
}
#content, #QuestionTest, #help {
	background-color: transparent !important;
}
div.subheader2x {
	background: #f0f0f0 url("/static/assets/bg2.png") left top / 1159px auto repeat !important;
}
</style>
"""
    return body.replace("</head>", css + "</head>", 1)


def mark_question_buttons(body: str, current: str) -> str:
    answered = saved_questions()

    def replace(match: re.Match[str]) -> str:
        before, value, after, label = match.groups()
        classes = ["qnum"]
        if value in answered:
            classes.append("yellow")
        if value == current:
            classes.append("qramka")
        return f'<button class="{" ".join(classes)}"{before}value="{value}"{after}>{label}</button>'

    return re.sub(
        r'<button class="[^"]*qnum[^"]*"([^>]*)value="([^"]*)"([^>]*)>(.*?)</button>',
        replace,
        body,
        flags=re.DOTALL,
    )


def restore_answer_fields(body: str, current: str) -> str:
    answer = load_answers().get(current, {})

    def restore(match: re.Match[str]) -> str:
        name, attrs, value = match.groups()
        return f'<textarea name="{name}"{attrs}>{escape(answer.get(name, value))}</textarea>'

    return re.sub(
        r'<textarea name="(bvalue\d+)"([^>]*)>(.*?)</textarea>',
        restore,
        body,
        flags=re.DOTALL,
    )


def first_unanswered_question() -> str:
    answered = saved_questions()
    for n in QUESTION_PAGES:
        if n not in answered:
            return n
    return session.get("current_question", "1")


def prepare_login_page() -> str:
    body = normalize_assets(raw_page(LOGIN_PAGE), login_page=True)
    return body.replace(
        '<form method="post" name="af" id="ad" action="">',
        '<form method="post" name="af" id="ad" action="/login">',
    )


def prepare_choose_page() -> str:
    body = normalize_assets(raw_page(CHOOSE_PAGE))
    body = body.replace("document.location.href='?template=28123';", "document.location.href='/test?template=28123';")
    body = body.replace('href="https://demo.mcko.ru/test/?template=28123"', 'href="/test?template=28123"')
    return body.replace(
        '<form method="post" action="" id="exit_button">',
        '<form method="post" action="/choose" id="exit_button">',
    )


def prepare_intro_page() -> str:
    body = normalize_assets(raw_page(INTRO_PAGE))
    body = inject_watermarks(body)
    body = mark_question_buttons(body, "")
    body = body.replace(
        '<form method="post" action="" onsubmit="$(window).off(\'beforeunload\');">',
        '<form method="post" action="/test" onsubmit="$(window).off(\'beforeunload\');">',
    )
    return body.replace(
        '<form method="post" action=""><button type="submit"',
        '<form method="post" action="/test"><button type="submit"',
    )


def prepare_question_page(current: str) -> str:
    body = normalize_assets(raw_page(QUESTION_PAGES[current]))
    body = inject_watermarks(body)
    body = mark_question_buttons(body, current)
    body = restore_answer_fields(body, current)
    body = body.replace(
        '<form method="post" action="" onsubmit="$(window).off(\'beforeunload\');">',
        '<form method="post" action="/test" onsubmit="$(window).off(\'beforeunload\');">',
    )
    return body.replace(
        '<form method="post" name="AnswerForm" id="AnswerForm" action="">',
        '<form method="post" name="AnswerForm" id="AnswerForm" action="/test">',
    )


def prepare_end_page() -> str:
    body = normalize_assets(raw_page(END_PAGE))
    body = inject_watermarks(body)
    body = mark_question_buttons(body, "999")
    body = body.replace(
        '<form method="post" action="" onsubmit="$(window).off(\'beforeunload\');">',
        '<form method="post" action="/test" onsubmit="$(window).off(\'beforeunload\');">',
    )
    body = body.replace(
        '<form method="post" action="" style="display: inline-block;"><input type="hidden" name="n" value="2">',
        f'<form method="post" action="/test" style="display: inline-block;"><input type="hidden" name="n" value="{first_unanswered_question()}">',
    )
    return body.replace(
        '<form method="post" action="" style="display: inline-block;"><input type="hidden" name="n" value="998">',
        '<form method="post" action="/test" style="display: inline-block;"><input type="hidden" name="n" value="998">',
    )


def prepare_results_page() -> str:
    body = normalize_assets(raw_page(RESULTS_PAGE))
    body = mark_question_buttons(body, "")
    body = body.replace(
        '<form method="post" action="" onsubmit="$(window).off(\'beforeunload\');">',
        '<form method="post" action="/test" onsubmit="$(window).off(\'beforeunload\');">',
    )
    body = re.sub(
        r'\s*<table cellspacing="20" width="100%" style="display:block">.*?</table><br>(?=<h3 style="color:green">)',
        "",
        body,
        flags=re.DOTALL,
    )
    body = body.replace(
        '<form method="post" action="" id="exit_button">',
        '<form method="post" action="/test" id="exit_button">',
    )
    body = re.sub(r'<!-- test_28123 -->0-test_28123, ученик 1', escape(participant_label()), body)
    return re.sub(r'\d{1,2} [А-Яа-я]+ \d{4}', today_ru(), body, count=1)


@app.get("/")
def index() -> Response:
    return html(prepare_login_page())


@app.post("/login")
def login() -> Response:
    session.clear()
    ensure_user_state()
    session["login"] = request.form.get("login", "")
    session["password"] = request.form.get("password", "")
    session["answered"] = []
    session.pop("started", None)
    save_answers({})
    save_jsonl(
        LOGINS_FILE,
        {
            "login": session["login"],
            "password": session["password"],
            "ip": request.remote_addr,
        },
    )
    return redirect(url_for("choose"))


@app.route("/choose", methods=["GET", "POST"])
def choose() -> Response:
    if request.method == "POST" and request.form.get("logoff") == "1":
        session.clear()
        return redirect(url_for("index"))
    return html(prepare_choose_page())


def save_submitted_answer(n: str) -> None:
    answer = {key: value for key, value in request.form.items() if key.startswith("bvalue")}
    answers = load_answers()
    answers[n] = answer
    save_answers(answers)
    save_jsonl(
        ANSWERS_FILE,
        {
            "login": session.get("login", ""),
            "n": n,
            "answer": answer,
        },
    )
    answered = saved_questions()
    answered.add(n)
    session["answered"] = sorted(answered, key=lambda item: int(item))


def render_test_screen() -> Response:
    if request.method == "POST" and request.form.get("logoff") == "1":
        session.clear()
        return redirect(url_for("index"))

    n = request.values.get("n")
    if n is None:
        n = ""

    if request.method == "POST" and request.form.get("Save") == "1":
        n = request.form.get("n") or session.get("current_question", "1")
        save_submitted_answer(n)

    if n == "":
        return html(prepare_intro_page())
    if n == "998":
        session["finished"] = True
        return html(prepare_results_page())
    if n == "999":
        return html(prepare_end_page())
    if n not in QUESTION_PAGES:
        return html(prepare_intro_page())

    session.setdefault("started", int(time.time()))
    session["current_question"] = n
    return html(prepare_question_page(n))


@app.route("/test", methods=["GET", "POST"])
def test() -> Response:
    return render_test_screen()


@app.route("/question", methods=["GET", "POST"])
def question() -> Response:
    if request.method == "POST":
        return render_test_screen()
    n = request.args.get("n")
    return redirect(url_for("test", n=n) if n is not None else url_for("test"))


@app.route("/end", methods=["GET", "POST"])
def end() -> Response:
    if request.method == "POST":
        return render_test_screen()
    return redirect(url_for("test", n="999"))


@app.route("/result", methods=["GET", "POST"])
@app.route("/results", methods=["GET", "POST"])
def result() -> Response:
    if request.method == "POST":
        return render_test_screen()
    return redirect(url_for("test", n="998"))


@app.post("/up.php")
@app.post("/question/up.php")
def timer_update() -> dict:
    now = int(time.time())
    started = session.get("started", now)
    return {
        "now": now,
        "FINISH": started + 45 * 60,
        "pause": 0,
        "UpInterval": 10000,
        "PauseNeeded": 0,
    }


if __name__ == "__main__":
    app.run(debug=True)
