#!/usr/bin/env python3
"""
Extract job-posting signal from a large .mbox export.

Stdlib only. Streams the file, so a 574MB mbox uses little memory.

Usage:
    python3 extract_mbox.py /path/to/your.mbox [outdir]

Writes three CSVs to outdir (default: alongside the mbox):
    messages.csv   one row per email  (date, sender, subject)
    postings.csv   one row per job link found (company, title, url, ...)
    companies.csv  unique companies with counts and date range  <- send this first
"""

import csv
import os
import re
import sys
from collections import defaultdict
from email import message_from_string
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser


def decode_hdr(value):
    """Decode an RFC 2047 header (=?UTF-8?B?...?=) to plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value

# Senders worth parsing. Add to this list if you see others in messages.csv.
SENDER_RE = re.compile(
    r"linkedin\.com|climatebase\.org|builtin\.com|climatetechlist|getro\.com"
    r"|careerbuilder|80000hours|ziprecruiter|indeed\.com|glassdoor|substack\.com"
    r"|greenhouse\.io|lever\.co|ashbyhq\.com|workday",
    re.I,
)

JOB_URL_RE = re.compile(r"https?://[^\s\"'<>]*?/jobs?/view/(\d+)", re.I)
ANY_JOB_URL_RE = re.compile(
    r"https?://[^\s\"'<>]*?(?:/jobs?/|/careers?/|greenhouse\.io/|lever\.co/|ashbyhq\.com/)[^\s\"'<>]*",
    re.I,
)

# LinkedIn saved-search alert subjects look like:
#   “"chief of staff"”: AHEAD - AI Principal Consultant, AI Services posted on 9/7/26
SUBJECT_ALERT_RE = re.compile(
    "^[“\"']?(?P<query>.*?)[”\"']?\\s*:\\s*(?P<company>.+?)\\s+-\\s+(?P<title>.+?)\\s+posted on\\s+(?P<posted>[\\d/]+)\\s*$"
)


class LinkText(HTMLParser):
    """Collect (href, visible_text) pairs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            self._href = d.get("href")
            self._buf = []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._buf).split())
            self.links.append((self._href, text))
            self._href = None
            self._buf = []


def iter_messages(path):
    """Yield raw message strings from an mbox, streaming."""
    buf = []
    prev_blank = True
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if prev_blank and line.startswith("From ") and buf:
                yield "".join(buf)
                buf = []
            prev_blank = line.strip() == ""
            if line.startswith("From ") and not buf:
                continue  # drop the mbox separator itself
            buf.append(line)
    if buf:
        yield "".join(buf)


def get_html_body(msg):
    parts = []
    if msg.is_multipart():
        for p in msg.walk():
            if p.get_content_type() in ("text/html", "text/plain"):
                try:
                    payload = p.get_payload(decode=True)
                except Exception:
                    continue
                if payload:
                    cs = p.get_content_charset() or "utf-8"
                    parts.append(payload.decode(cs, errors="replace"))
    else:
        try:
            payload = msg.get_payload(decode=True)
        except Exception:
            payload = None
        if payload:
            cs = msg.get_content_charset() or "utf-8"
            parts.append(payload.decode(cs, errors="replace"))
    return "\n".join(parts)


def clean(s, limit=300):
    return " ".join((s or "").split())[:limit]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mbox = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(mbox))
    os.makedirs(outdir, exist_ok=True)

    m_path = os.path.join(outdir, "messages.csv")
    p_path = os.path.join(outdir, "postings.csv")
    c_path = os.path.join(outdir, "companies.csv")

    companies = defaultdict(lambda: {"n": 0, "first": None, "last": None, "titles": set()})
    seen_urls = set()
    n_msgs = n_parsed = n_post = 0

    with open(m_path, "w", newline="", encoding="utf-8") as mf, \
         open(p_path, "w", newline="", encoding="utf-8") as pf:
        mw = csv.writer(mf)
        pw = csv.writer(pf)
        mw.writerow(["date", "sender", "subject"])
        pw.writerow(["date", "company", "title", "url", "alert_query", "source_sender"])

        for raw in iter_messages(mbox):
            n_msgs += 1
            try:
                msg = message_from_string(raw)
            except Exception:
                continue

            sender = clean(decode_hdr(msg.get("From", "")), 200)
            subject = clean(decode_hdr(msg.get("Subject", "")), 400)
            try:
                dt = parsedate_to_datetime(msg.get("Date", ""))
                date = dt.strftime("%Y-%m-%d")
            except Exception:
                date = ""

            mw.writerow([date, sender, subject])

            if not SENDER_RE.search(sender):
                continue
            n_parsed += 1

            # 1) Company/title straight from the alert subject line, when present.
            sm = SUBJECT_ALERT_RE.match(subject)
            alert_query = ""
            if sm:
                alert_query = clean(sm.group("query"), 120)
                comp = clean(sm.group("company"), 120)
                titl = clean(sm.group("title"), 200)
                if comp:
                    pw.writerow([date, comp, titl, "", alert_query, sender])
                    n_post += 1
                    rec = companies[comp]
                    rec["n"] += 1
                    rec["first"] = min(rec["first"] or date, date) if date else rec["first"]
                    rec["last"] = max(rec["last"] or date, date) if date else rec["last"]
                    if titl:
                        rec["titles"].add(titl)

            # 2) Job links in the body.
            body = get_html_body(msg)
            if not body:
                continue
            parser = LinkText()
            try:
                parser.feed(body)
            except Exception:
                pass

            for href, text in parser.links:
                if not href or not ANY_JOB_URL_RE.match(href):
                    continue
                jid = JOB_URL_RE.search(href)
                key = jid.group(1) if jid else href.split("?")[0]
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                if not text or len(text) < 3:
                    continue
                # Anchor text is usually "Title" or "Title at Company"
                comp, titl = "", text
                if " at " in text:
                    titl, comp = text.rsplit(" at ", 1)
                pw.writerow([date, clean(comp, 120), clean(titl, 200),
                             href.split("?")[0][:400], alert_query, sender])
                n_post += 1
                if comp:
                    rec = companies[clean(comp, 120)]
                    rec["n"] += 1
                    rec["first"] = min(rec["first"] or date, date) if date else rec["first"]
                    rec["last"] = max(rec["last"] or date, date) if date else rec["last"]
                    rec["titles"].add(clean(titl, 200))

    with open(c_path, "w", newline="", encoding="utf-8") as cf:
        cw = csv.writer(cf)
        cw.writerow(["company", "n_postings", "first_seen", "last_seen", "sample_titles"])
        for comp, rec in sorted(companies.items(), key=lambda kv: -kv[1]["n"]):
            cw.writerow([comp, rec["n"], rec["first"] or "", rec["last"] or "",
                         " | ".join(sorted(rec["titles"])[:5])])

    print(f"messages scanned : {n_msgs}")
    print(f"job-alert emails : {n_parsed}")
    print(f"postings found   : {n_post}")
    print(f"unique companies : {len(companies)}")
    print()
    for p in (m_path, p_path, c_path):
        print(f"{os.path.getsize(p)/1e6:8.2f} MB  {p}")


if __name__ == "__main__":
    main()
