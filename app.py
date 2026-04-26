from __future__ import annotations

import json
import re
import secrets
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, redirect, request, session, url_for
from markupsafe import escape


BASE_DIR = Path(__file__).resolve().parent
PAGES_DIR = BASE_DIR / "templates" / "pages"
DATA_DIR = BASE_DIR / "data"
USER_ANSWERS_DIR = DATA_DIR / "user_answers"
LOGINS_FILE = DATA_DIR / "logins.jsonl"
EXIT_LINKS_FILE = DATA_DIR / "exit_links.json"
TEST_DURATION_SECONDS = 45 * 60

LOGIN_PAGE = "login.html"
CHOOSE_PAGE = "choose.html"
INTRO_PAGE = "intro.html"
END_PAGE = "end.html"
RESULTS_PAGE = "results.html"

QUESTION_PAGES = {
    "11": "q11.html",
    "12": "q12.html",
    "20": "q20.html",
    "30": "q30.html",
    "40": "q40.html",
    "50": "q50.html",
    "60": "q60.html",
    "70": "q70.html",
    "80": "q80.html",
    "90": "q90.html",
    "100": "q100.html",
}
QUESTION_LABELS = {
    "11": "1.1",
    "12": "1.2",
    "20": "2",
    "30": "3",
    "40": "4",
    "50": "5",
    "60": "6",
    "70": "7",
    "80": "8",
    "90": "9",
    "100": "10",
}
FIRST_QUESTION = next(iter(QUESTION_PAGES))

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

ASSET_ATTR_RE = re.compile(
    r'(href|src)=(["\'])([^"\']+(?:_files|_1|_2|_3|_4|_5|_6|_7|_8|_9|_10)[^"\']*/[^"\']+|[^"\']+_files/[^"\']+|results_files/[^"\']+|end_files/[^"\']+|[0-9]+(?:_[0-9]+)?_files/[^"\']+)\2'
)
QUESTION_BUTTON_RE = re.compile(
    r'<button class="[^"]*qnum[^"]*"([^>]*)value="([^"]*)"([^>]*)>(.*?)</button>',
    re.DOTALL,
)
TEXTAREA_RE = re.compile(
    r'<textarea name="(bvalue\d+)"([^>]*)>(.*?)</textarea>',
    re.DOTALL,
)
REMOTE_LINK_RE = re.compile(r'href=(["\'])https?://[^"\']+\1')
URL_RE = re.compile(r'(https?://[^\s<>"\']+|[A-Za-z0-9.-]+\.[A-Za-z]{2,}[^\s<>"\']*)')
GENERATED_FOOTER_RE = re.compile(
    r'\s*<br><center><font style="color:#cccccc;font-size:8pt">Page generated.*?</font></center>',
    re.DOTALL,
)
HTML_COMMENT_RE = re.compile(r"<!--(?!\s*test_28123\s*).*?-->", re.DOTALL)

app = Flask(__name__)
app.secret_key = "fake-mcko-local-secret"


@lru_cache(maxsize=32)
def raw_page(filename: str) -> str:
    return (PAGES_DIR / filename).read_text(encoding="utf-8")


def html(body: str) -> Response:
    response = Response(body, mimetype="text/html; charset=utf-8")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def save_jsonl(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    data = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), **data}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"error": "bad json", "raw": line})
    return rows


def read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_json_file(path: Path, data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


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


def question_order(value: str) -> int:
    try:
        return list(QUESTION_PAGES).index(value)
    except ValueError:
        return len(QUESTION_PAGES)


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
        parts = url.split("/")
        filename = parts[-1]
        folder = parts[-2] if len(parts) > 1 else ""
        if login_page and filename == "logo.png":
            new_url = "/static/assets/logo-login.png"
        elif filename in COMMON_ASSETS or filename == "logo.png" or filename in IMAGE_ASSETS:
            new_url = asset_url(filename)
        elif folder.endswith("_files"):
            folder_name = folder.removesuffix("_files")
            new_url = f"/static/question_assets/{folder_name}/{filename}"
        else:
            new_url = asset_url(filename)
        return f'{attr}={quote}{new_url}{quote}'

    body = ASSET_ATTR_RE.sub(replace_attr, body)
    body = body.replace("/test/questions/9203469/80680142.files/", "/static/question_assets/9/")
    body = body.replace("/test/questions/9203460/1608939.files/", "/static/question_assets/1_1/")
    return body


def clean_html(body: str) -> str:
    body = HTML_COMMENT_RE.sub("", body)
    body = GENERATED_FOOTER_RE.sub("", body)
    body = REMOTE_LINK_RE.sub('href="#"', body)
    body = body.replace("http://demo.mcko.ru/test/questions/", "#")
    return body


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
        if value in QUESTION_LABELS:
            label = QUESTION_LABELS[value]
        classes = ["qnum"]
        if value in answered:
            classes.append("yellow")
        if value == current:
            classes.append("qramka")
        return f'<button class="{" ".join(classes)}"{before}value="{value}"{after}>{label}</button>'

    body = QUESTION_BUTTON_RE.sub(replace, body)
    return replace_question_line(body, current)


def question_line(current: str) -> str:
    buttons = ['<button class="qnum" type="submit" name="n" value="">Описание</button>']
    answered = saved_questions()
    for value, label in QUESTION_LABELS.items():
        classes = ["qnum"]
        if value in answered:
            classes.append("yellow")
        if value == current:
            classes.append("qramka")
        buttons.append(f'<button class="{" ".join(classes)}" type="submit" name="n" value="{value}">{label}</button>')
    end_classes = "qnum qramka" if current == "999" else "qnum"
    buttons.append(f'<button class="{end_classes}" type="submit" name="n" value="999">закончить</button>')
    return "\n".join(buttons)


def replace_question_line(body: str, current: str) -> str:
    return re.sub(
        r'(<form method="post" action="[^"]*" onsubmit="\$\(window\)\.off\(\'beforeunload\'\);">\s*)(.*?)(\s*</form>)',
        lambda match: match.group(1) + "\n" + question_line(current) + "\n" + match.group(3),
        body,
        count=1,
        flags=re.DOTALL,
    )


def restore_answer_fields(body: str, current: str) -> str:
    answer = load_answers().get(current, {})

    def restore(match: re.Match[str]) -> str:
        name, attrs, value = match.groups()
        return f'<textarea name="{name}"{attrs}>{escape(answer.get(name, value))}</textarea>'

    return TEXTAREA_RE.sub(restore, body)


def inject_testing_helpers(body: str) -> str:
    script = """
<script>
(function () {
  function setValue(id, value, overwrite) {
    var field = document.getElementById(id);
    if (!field || value === undefined || value === null) return;
    if (!overwrite && field.value) return;
    field.value = String(value);
  }

  function valuesFor(selector) {
    return Array.prototype.map.call(document.querySelectorAll(selector), function (item) {
      return item.value || item.getAttribute("value") || "";
    }).join("");
  }

  function syncAnswerFields() {
    if (typeof window.FormAnswer === "function") {
      try { window.FormAnswer(0); } catch (error) {}
    }

    document.querySelectorAll("input[id^='a'], select[id^='a'], textarea[id^='a']").forEach(function (field) {
      var match = field.id.match(/^a(\\d+)$/);
      if (!match || field.type === "radio" || field.type === "checkbox") return;
      setValue("bvalue" + match[1], field.value, true);
    });

    document.querySelectorAll("input[type='radio'][name^='a']:checked").forEach(function (field) {
      var match = field.name.match(/^a(\\d+)$/);
      if (match) setValue("bvalue" + match[1], field.value, true);
    });

    document.querySelectorAll("input[type='checkbox'][name^='m']").forEach(function (field) {
      var match = field.name.match(/^m(\\d+)$/);
      if (match) setValue("bvalue" + match[1], valuesFor("input[type='checkbox'][name='" + field.name + "']:checked"), true);
    });

    var qanswer = Array.prototype.map.call(document.querySelectorAll("input[type='checkbox'][name^='qanswer']:checked"), function (field) {
      return field.name.replace(/^qanswer/, "");
    }).join("");
    if (qanswer) setValue("bvalue0", qanswer, true);

    document.querySelectorAll("span.ans.marked[name^='a'], div.ans.marked[name^='a']").forEach(function (field) {
      var match = field.getAttribute("name").match(/^a(\\d+)$/);
      if (match) setValue("bvalue" + match[1], field.getAttribute("value"), true);
    });

    document.querySelectorAll("span.ans[name^='m'], div.ans[name^='m'], input.ans[name^='m']").forEach(function (field) {
      var name = field.getAttribute("name");
      var match = name && name.match(/^m(\\d+)$/);
      if (!match) return;
      var values = Array.prototype.map.call(document.querySelectorAll(".ans.marked[name='" + name + "']"), function (item) {
        return item.getAttribute("value") || item.value || "";
      });
      if (!values.length) {
        values = Array.prototype.map.call(document.querySelectorAll("input.ans[type='checkbox'][name='" + name + "']:checked"), function (item) {
          return item.value || "";
        });
      }
      if (values.length) setValue("bvalue" + match[1], values.join(values.some(function (value) { return value.length > 1; }) ? "," : ""), true);
    });

    var checkedChoice = document.querySelector("input.aanswer:checked");
    if (checkedChoice) {
      setValue("bvalue0", checkedChoice.value || checkedChoice.id.replace(/^a/, ""), true);
    }

  }

  function restoreVisibleFields() {
    function attrEscape(value) {
      return String(value).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    }

    function markTokenAnswer(name, value) {
      document.querySelectorAll(".ans[name='" + attrEscape(name) + "']").forEach(function (item) {
        var itemValue = item.getAttribute("value") || item.value || "";
        if (itemValue !== value) return;
        item.classList.add("marked");
        if (item.type === "checkbox" || item.type === "radio") item.checked = true;
      });
    }

    function answerParts(name, value) {
      var text = String(value);
      if (/[,/ ]/.test(text)) return text.split(/[,/ ]/).filter(Boolean);
      var candidates = Array.prototype.map.call(document.querySelectorAll(".ans[name='" + attrEscape(name) + "']"), function (item) {
        return item.getAttribute("value") || item.value || "";
      }).filter(Boolean).sort(function (a, b) { return b.length - a.length; });
      if (!candidates.length) return text.split("").filter(Boolean);
      var parts = [];
      while (text) {
        var found = candidates.find(function (candidate) { return text.indexOf(candidate) === 0; });
        if (!found) return String(value).split("").filter(Boolean);
        parts.push(found);
        text = text.slice(found.length);
      }
      return parts;
    }

    document.querySelectorAll("textarea[id^='bvalue']").forEach(function (field) {
      var match = field.id.match(/^bvalue(\\d+)$/);
      if (!match || !field.value) return;
      var index = match[1];
      var value = field.value;
      if (value === "-") return;
      var visible = document.getElementById("a" + match[1]);
      if (visible && visible.tagName !== "SPAN") {
        if (visible.type === "radio" || visible.type === "checkbox") {
          visible.checked = true;
        } else if (!visible.value || visible.tagName === "SELECT") {
          visible.value = value;
          visible.dispatchEvent(new Event("change", { bubbles: true }));
          visible.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }
      document.querySelectorAll("input[type='radio'][name='a" + index + "'][value='" + attrEscape(value) + "']").forEach(function (radio) {
        radio.checked = true;
        radio.dispatchEvent(new Event("change", { bubbles: true }));
      });
      document.querySelectorAll("input[type='checkbox'][name='a" + index + "'][value='" + attrEscape(value) + "']").forEach(function (checkbox) {
        checkbox.checked = true;
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
      });
      answerParts("m" + index, value).forEach(function (part) {
        document.querySelectorAll("input[type='checkbox'][name='m" + index + "'][value='" + attrEscape(part) + "']").forEach(function (checkbox) {
          checkbox.checked = true;
          checkbox.dispatchEvent(new Event("change", { bubbles: true }));
        });
        document.querySelectorAll("input[type='checkbox'][name='a" + index + "'][value='" + attrEscape(part) + "']").forEach(function (checkbox) {
          checkbox.checked = true;
          checkbox.dispatchEvent(new Event("change", { bubbles: true }));
        });
      });
      answerParts("a" + index, value).forEach(function (part) {
        markTokenAnswer("a" + index, part);
        markTokenAnswer("m" + index, part);
        var q = document.getElementById("qanswer" + part);
        if (match[1] === "0" && q) q.checked = true;
      });
      var answerChoice = document.getElementById("a" + value);
      if (match[1] === "0" && answerChoice && answerChoice.classList.contains("aanswer")) {
        answerChoice.checked = true;
        answerChoice.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    if (typeof window.CheckAnswer === "function") {
      try { window.CheckAnswer(); } catch (error) {}
    }
    if (typeof window.FormAnswer === "function") {
      try { window.FormAnswer(0); } catch (error) {}
    }
  }

  function answerForm() {
    return document.forms.AnswerForm || document.getElementById("AnswerForm");
  }
  function saveCurrentAnswer() {
    var form = answerForm();
    if (!form || !window.fetch) return Promise.resolve();
    syncAnswerFields();
    var data = new FormData(form);
    data.set("Save", "1");
    return fetch("/autosave", {
      method: "POST",
      body: data,
      credentials: "same-origin",
      keepalive: true
    }).catch(function () {});
  }
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form || form.id === "AnswerForm" || form.dataset.skipAutosave === "1") return;
    if (!answerForm()) return;
    var submitter = event.submitter;
    event.preventDefault();
    saveCurrentAnswer().finally(function () {
      if (submitter && submitter.name) {
        var hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = submitter.name;
        hidden.value = submitter.value;
        form.appendChild(hidden);
      }
      form.dataset.skipAutosave = "1";
      form.submit();
    });
  }, true);
  document.addEventListener("click", function (event) {
    if (event.target && event.target.closest("#SaveButton, #AnswerHere button")) {
      syncAnswerFields();
    }
  }, true);
  document.addEventListener("DOMContentLoaded", restoreVisibleFields);
  window.syncAnswerFields = syncAnswerFields;
  window.saveCurrentAnswer = saveCurrentAnswer;
})();
</script>
"""
    return body.replace("</body>", script + "</body>", 1)


def first_unanswered_question() -> str:
    answered = saved_questions()
    for n in QUESTION_PAGES:
        if n not in answered:
            return n
    return session.get("current_question", FIRST_QUESTION)


def next_unanswered_question(current: str) -> str | None:
    answered = saved_questions()
    numbers = list(QUESTION_PAGES)
    if current in numbers:
        current_index = numbers.index(current)
        ordered = numbers[current_index + 1 :] + numbers[: current_index + 1]
    else:
        ordered = numbers
    for n in ordered:
        if n not in answered:
            return n
    return None


def prepare_login_page() -> str:
    body = clean_html(normalize_assets(raw_page(LOGIN_PAGE), login_page=True))
    body = body.replace('href="#" tabindex="90"', 'href="/" tabindex="90"')
    return body.replace(
        '<form method="post" name="af" id="ad" action="">',
        '<form method="post" name="af" id="ad" action="/login">',
    )


def prepare_choose_page() -> str:
    body = clean_html(normalize_assets(raw_page(CHOOSE_PAGE)))
    body = body.replace("document.location.href='?template=28123';", "document.location.href='/test?template=28123';")
    body = body.replace('href="https://demo.mcko.ru/test/?template=28123"', 'href="/test?template=28123"')
    body = body.replace("Русский язык, 10 класс  К6", "Русский язык, 8 класс")
    body = body.replace("Русский язык, 10 класс К6", "Русский язык, 8 класс")
    body = body.replace("Русский язык, 10 класс", "Русский язык, 8 класс")
    body = body.replace("  К6", "")
    body = body.replace("(заданий: 12 шт.)", f"(заданий: {len(QUESTION_PAGES)} шт.)")
    return body.replace(
        '<form method="post" action="" id="exit_button">',
        '<form method="post" action="/test" id="exit_button">',
    )


def prepare_intro_page() -> str:
    body = clean_html(normalize_assets(raw_page(INTRO_PAGE)))
    body = inject_watermarks(body)
    body = mark_question_buttons(body, "")
    body = body.replace(
        '<form method="post" action="" onsubmit="$(window).off(\'beforeunload\');">',
        '<form method="post" action="/test" onsubmit="$(window).off(\'beforeunload\');">',
    )
    body = body.replace(
        '<form method="post" action=""><button type="submit"',
        '<form method="post" action="/test"><button type="submit"',
    )
    return body.replace('name="n" value="1">Начать тестирование</button>', f'name="n" value="{FIRST_QUESTION}">Начать тестирование</button>')


def prepare_question_page(current: str) -> str:
    body = clean_html(normalize_assets(raw_page(QUESTION_PAGES[current])))
    body = inject_watermarks(body)
    body = mark_question_buttons(body, current)
    body = restore_answer_fields(body, current)
    body = body.replace(
        '<form method="post" action="" onsubmit="$(window).off(\'beforeunload\');">',
        '<form method="post" action="/test" onsubmit="$(window).off(\'beforeunload\');">',
    )
    body = body.replace(
        '<form method="post" name="AnswerForm" id="AnswerForm" action="">',
        '<form method="post" name="AnswerForm" id="AnswerForm" action="/test">',
    )
    return inject_testing_helpers(body)


def prepare_end_page() -> str:
    body = clean_html(normalize_assets(raw_page(END_PAGE)))
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
    body = body.replace(
        '<form method="post" action="" style="display: inline-block;"><input type="hidden" name="n" value="998">',
        '<form method="post" action="/test" style="display: inline-block;"><input type="hidden" name="n" value="998">',
    )
    return inject_testing_helpers(body)


def prepare_results_page() -> str:
    body = clean_html(normalize_assets(raw_page(RESULTS_PAGE)))
    body = inject_watermarks(body)
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
    body = re.sub(
        r'<h3 style="color:green">.*?</h3><br><table><tbody><tr><td><form method="post" action="" id="exit_button">.*?</form></td></tr></tbody></table>',
        """<div style="min-height:calc(100vh - 330px); display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;">
<h3 style="color:green; font-size:42px; margin:0 0 34px;">Благодарим Вас за участие!</h3>
<form method="post" action="/exit" id="exit_button">
<input type="hidden" name="logoff" value="1">
<input type="submit" value="Выход" style="padding:18px 55px; font-size:28px; font-weight:bold;">
</form>
<div style="margin-top:28px; color:#000000; font-size:28px; font-weight:bold;">Русский язык, 8 класс</div>
</div>""",
        body,
        flags=re.DOTALL,
    )
    body = body.replace(
        '<form method="post" action="" id="exit_button">',
        '<form method="post" action="/test" id="exit_button">',
    )
    body = body.replace("Русский язык, 10 класс  К6", "Русский язык, 8 класс")
    body = body.replace("Русский язык, 10 класс К6", "Русский язык, 8 класс")
    body = body.replace("Русский язык, 10 класс", "Русский язык, 8 класс")
    body = body.replace("  К6", "")
    body = re.sub(r'<!-- test_28123 -->0-test_28123, ученик 1', escape(participant_label()), body)
    body = re.sub(r'\d{1,2} [А-Яа-я]+ \d{4}', today_ru(), body, count=1)
    script = """<script>
(function () {
  var resultUrl = "/test?n=998";
  history.replaceState({ finished: true }, "", resultUrl);
  history.pushState({ finished: true }, "", resultUrl);
  window.addEventListener("popstate", function () {
    history.pushState({ finished: true }, "", resultUrl);
    window.location.replace(resultUrl);
  });
})();
</script>
"""
    return body.replace("</body>", script + "</body>", 1)


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
    session.pop("template_selected", None)
    session.pop("started", None)
    save_answers({})
    save_jsonl(
        LOGINS_FILE,
        {
            "login": session["login"],
            "password": session["password"],
            "sid": session["sid"],
            "participant_number": session["participant_number"],
            "ip": request.remote_addr,
            "user_agent": request.headers.get("User-Agent", ""),
        },
    )
    return redirect(url_for("test"))


@app.route("/choose", methods=["GET", "POST"])
def choose() -> Response:
    if request.method == "POST" and request.form.get("logoff") == "1":
        session.clear()
        return redirect(url_for("index"))
    return redirect(url_for("test"))


def has_non_empty_answer(answer: dict[str, str]) -> bool:
    return any(value.strip() and value.strip() != "-" for value in answer.values())


def normalize_exit_url(raw_value: str) -> str | None:
    match = URL_RE.search(raw_value.strip())
    if not match:
        return None
    target = match.group(1).rstrip(".,;)")
    if not re.match(r"^https?://", target, re.IGNORECASE):
        target = f"https://{target}"
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return target


def exit_url_from_answer(answer: dict[str, str]) -> str | None:
    keys = ["bvalue1", "bvalue0", *sorted(key for key in answer if key not in {"bvalue1", "bvalue0"})]
    for key in keys:
        target = normalize_exit_url(answer.get(key, ""))
        if target:
            return target
    return None


def saved_exit_url() -> str | None:
    return exit_url_from_answer(load_answers().get("80", {}))


def save_exit_link(answer: dict[str, str]) -> None:
    ensure_user_state()
    links = read_json_file(EXIT_LINKS_FILE)
    sid = session["sid"]
    links[sid] = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "login": session.get("login", ""),
        "password": session.get("password", ""),
        "link": exit_url_from_answer(answer) or "",
        "answer": answer,
    }
    write_json_file(EXIT_LINKS_FILE, links)


def save_submitted_answer(n: str, *, mark_answered: bool) -> bool:
    if n not in QUESTION_PAGES:
        return False
    answer = {key: value for key, value in request.form.items() if key.startswith("bvalue")}
    if not answer or not has_non_empty_answer(answer):
        return False
    answers = load_answers()
    answers[n] = answer
    save_answers(answers)
    if n == "80":
        save_exit_link(answer)
    if mark_answered:
        answered = saved_questions()
        answered.add(n)
        session["answered"] = sorted(answered, key=question_order)
    return True


def render_test_screen() -> Response:
    if request.method == "POST" and request.form.get("logoff") == "1":
        session.clear()
        return redirect(url_for("index"))

    n = request.values.get("n")
    if n is None:
        n = ""
    if request.values.get("template"):
        session["template_selected"] = request.values.get("template")

    if session.get("finished") and n != "998":
        return redirect(url_for("test", n="998"))

    if request.method == "POST" and request.form.get("Save") == "1":
        n = request.form.get("n") or session.get("current_question", FIRST_QUESTION)
        saved = save_submitted_answer(n, mark_answered=True)
        if not saved:
            return redirect(url_for("test", n=n))
        next_n = next_unanswered_question(n)
        return redirect(url_for("test", n=next_n or "999"))

    if n == "" and not session.get("template_selected"):
        return html(prepare_choose_page())
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


@app.route("/exit", methods=["GET", "POST"])
def exit_test() -> Response:
    target = saved_exit_url()
    session.clear()
    if target:
        return redirect(target)
    return redirect(url_for("index"))


@app.post("/autosave")
def autosave() -> Response:
    ensure_user_state()
    n = request.form.get("n") or session.get("current_question", FIRST_QUESTION)
    saved = save_submitted_answer(n, mark_answered=False)
    return jsonify({"ok": saved, "n": n})


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
        "FINISH": started + TEST_DURATION_SECONDS,
        "pause": 0,
        "UpInterval": 10000,
        "PauseNeeded": 0,
    }


def collect_manage_data() -> dict:
    answer_files = []
    answer_map = {}
    if USER_ANSWERS_DIR.exists():
        for path in sorted(USER_ANSWERS_DIR.glob("*.json")):
            try:
                answers = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                answers = {"error": "bad json"}
            item = {
                "sid": path.stem,
                "updated": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "answers": answers,
            }
            answer_files.append(item)
            answer_map[path.stem] = item
    exit_links = read_json_file(EXIT_LINKS_FILE)
    users = []
    seen_sids = set()
    for login in read_jsonl(LOGINS_FILE):
        sid = login.get("sid", "")
        seen_sids.add(sid)
        answer_item = answer_map.get(sid, {})
        answers = answer_item.get("answers", {})
        link = exit_url_from_answer(answers.get("80", {})) if isinstance(answers, dict) else None
        users.append(
            {
                "time": login.get("time", ""),
                "login": login.get("login", ""),
                "password": login.get("password", ""),
                "sid": sid,
                "ip": login.get("ip", ""),
                "link": link or exit_links.get(sid, {}).get("link", ""),
                "updated": answer_item.get("updated", ""),
            }
        )
    for sid, item in answer_map.items():
        if sid in seen_sids:
            continue
        users.append(
            {
                "time": "",
                "login": exit_links.get(sid, {}).get("login", ""),
                "password": exit_links.get(sid, {}).get("password", ""),
                "sid": sid,
                "ip": "",
                "link": exit_url_from_answer(item.get("answers", {}).get("80", {})) or exit_links.get(sid, {}).get("link", ""),
                "updated": item.get("updated", ""),
            }
        )
    return {
        "users": users,
        "logins": read_jsonl(LOGINS_FILE),
        "exit_links": exit_links,
        "answer_files": answer_files,
    }


def manage_data_version() -> str:
    files = [LOGINS_FILE, EXIT_LINKS_FILE]
    if USER_ANSWERS_DIR.exists():
        files.extend(sorted(USER_ANSWERS_DIR.glob("*.json")))
    parts = []
    for path in files:
        if not path.exists():
            continue
        stat = path.stat()
        parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def render_manage_page() -> Response:
    data = collect_manage_data()
    version = manage_data_version()
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    user_rows = []
    for item in data["users"]:
        link = item.get("link", "")
        link_cell = f'<a href="{escape(link)}" target="_blank" rel="noopener">{escape(link)}</a>' if link else ""
        user_rows.append(
            f"<tr><td>{escape(item.get('time', ''))}</td><td>{escape(item.get('login', ''))}</td>"
            f"<td>{escape(item.get('password', ''))}</td><td>{link_cell}</td>"
            f"<td>{escape(item.get('sid', ''))}</td><td>{escape(item.get('updated', ''))}</td>"
            f"<td>{escape(item.get('ip', ''))}</td></tr>"
        )
    page = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Manage</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; background: #f7f7f7; }}
    h1, h2 {{ margin: 0 0 14px; }}
    h2 {{ margin-top: 28px; }}
    a, button {{ font: inherit; }}
    .actions {{ display: flex; gap: 10px; margin-bottom: 20px; }}
    .button {{ display: inline-block; padding: 9px 12px; border: 1px solid #999; background: #fff; color: #111; text-decoration: none; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; margin-bottom: 22px; }}
    th, td {{ border: 1px solid #d5d5d5; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #ececec; }}
    pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; max-height: 360px; overflow: auto; }}
    .muted {{ color: #666; }}
  </style>
</head>
<body>
  <h1>Отправленные данные</h1>
  <div class="actions">
    <a class="button" href="/manage.json">JSON</a>
    <a class="button" href="/">На сайт</a>
  </div>
  <p class="muted">Пользователей: {len(data['users'])}. Файлов ответов: {len(data['answer_files'])}.</p>
  <h2>Пользователи</h2>
  <table>
    <thead><tr><th>Время входа</th><th>Логин</th><th>Пароль</th><th>Ссылка из задания 8</th><th>SID</th><th>Ответ обновлен</th><th>IP</th></tr></thead>
    <tbody>{''.join(user_rows) or '<tr><td colspan="7">Пока пусто</td></tr>'}</tbody>
  </table>
  <h2>Все данные</h2>
  <pre>{escape(payload)}</pre>
  <script>
    const manageVersion = {json.dumps(version)};
    async function refreshWhenChanged() {{
      try {{
        const response = await fetch("/manage.version", {{ cache: "no-store" }});
        if (!response.ok) return;
        const data = await response.json();
        if (data.version && data.version !== manageVersion) {{
          window.location.reload();
        }}
      }} catch (error) {{}}
    }}
    setInterval(refreshWhenChanged, 2500);
  </script>
</body>
</html>"""
    return html(page)


@app.get("/manage")
def manage() -> Response:
    return render_manage_page()


@app.get("/manage.json")
def manage_json() -> Response:
    return jsonify(collect_manage_data())


@app.get("/manage.version")
def manage_version() -> Response:
    return jsonify({"version": manage_data_version()})


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=4000)
