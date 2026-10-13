#!/usr/bin/env python3
"""Send the current HSK 3 course day to a Telegram chat."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

START_DATE = os.environ.get('START_DATE', '2026-10-14')
TIMEZONE = ZoneInfo('Asia/Yangon')
TELEGRAM_MAX_SAFE = 3300


def esc(value: object) -> str:
    return html.escape(str(value or ''), quote=True)


def chunks_for_segments(title: str, segments: list[str], footer: str = '') -> list[str]:
    """Pack HTML segments below Telegram's 4096-character message limit."""
    header = f'<b>{esc(title)}</b>'
    messages: list[str] = []
    current = header
    for segment in segments:
        candidate = current + '\n\n' + segment
        if len(candidate) > TELEGRAM_MAX_SAFE and current != header:
            messages.append(current)
            current = header + '\n\n' + segment
        else:
            current = candidate
    if footer:
        if len(current) + len(footer) + 2 <= TELEGRAM_MAX_SAFE:
            current += '\n\n' + footer
        else:
            messages.append(current)
            current = header + '\n\n' + footer
    if current != header:
        messages.append(current)
    return messages or [header]


def render_lesson(lesson: dict) -> list[str]:
    segments: list[str] = []
    if lesson.get('objective'):
        segments.append('<b>Goal:</b> ' + esc(lesson['objective']))
    if lesson.get('grammar_note'):
        segments.append('<b>Grammar:</b> ' + esc(lesson['grammar_note']))

    for i, item in enumerate(lesson.get('vocabulary') or [], 1):
        audio = item.get('audio_url')
        audio_line = f'<a href="{esc(audio)}">Audio</a>' if audio else 'Audio: not available'
        segments.append(
            f'<b>{i}. {esc(item.get("word"))} ({esc(item.get("pinyin"))})</b> — {esc(item.get("burmese"))}'
            f'\n<i>{esc(item.get("example_cn"))}</i>'
            f'\n{esc(item.get("example_pinyin"))}'
            f'\n{esc(item.get("example_myanmar"))}'
            f'\n{audio_line}'
        )

    if lesson.get('tasks'):
        segments.append('<b>Practice:</b>\n' + '\n'.join(esc(x) for x in lesson['tasks']))
    if lesson.get('audio_note'):
        segments.append('<i>' + esc(lesson['audio_note']) + '</i>')

    footer_parts = []
    if lesson.get('ibt_typing_tip'):
        footer_parts.append('<b>iBT typing tip:</b> ' + esc(lesson['ibt_typing_tip']))
    if lesson.get('review_task'):
        footer_parts.append('<b>Review:</b> ' + esc(lesson['review_task']))
    rendered = chunks_for_segments(
        lesson.get('title', f'Day {lesson.get("day")}'), segments, '\n'.join(footer_parts)
    )

    # Keep mock answer keys separate so the learner can attempt the questions first.
    if lesson.get('answer_key'):
        key_segments = ['<b>Self-check — reveal after attempting the practice:</b>']
        key_segments.extend(esc(x) for x in lesson['answer_key'])
        rendered.extend(chunks_for_segments(lesson.get('title', 'Answer key') + ' — Answer key', key_segments))
    return rendered


def send_message(token: str, chat_id: str, text: str) -> None:
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    body = json.dumps({
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
        if not result.get('ok'):
            raise RuntimeError('Telegram rejected sendMessage: ' + str(result.get('description', 'unknown error')))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:500]
        raise RuntimeError(f'Telegram API HTTP {exc.code}: {detail}') from None


def main() -> int:
    token = os.environ.get('BOT_TOKEN', '').strip()
    chat_id = os.environ.get('CHAT_ID', '').strip()
    if not token or not chat_id:
        print('BOT_TOKEN and CHAT_ID must be set in the process environment.', file=sys.stderr)
        return 2

    course_path = Path(__file__).with_name('hsk3_60days_course.json')
    course = json.loads(course_path.read_text(encoding='utf-8'))
    start = dt.date.fromisoformat(START_DATE)
    today = dt.datetime.now(TIMEZONE).date()
    day_number = (today - start).days + 1

    if day_number < 1:
        print(f'Course has not started. Start date: {start.isoformat()}; Myanmar date: {today.isoformat()}.')
        return 0
    if day_number > 60:
        print('The 60-day course is complete; no lesson sent.')
        return 0

    lessons = {int(item['day']): item for item in course['lessons']}
    lesson = lessons.get(day_number)
    if lesson is None:
        raise RuntimeError(f'No course lesson found for day {day_number}.')

    messages = render_lesson(lesson)
    for index, text in enumerate(messages, 1):
        if len(text) > 4096:
            raise RuntimeError(f'Rendered Telegram message {index} exceeds the API size limit.')
        send_message(token, chat_id, text)
        if index < len(messages):
            time.sleep(0.5)
    print(f'Sent day {day_number} ({len(messages)} Telegram message(s)) for {today.isoformat()} Myanmar time.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
