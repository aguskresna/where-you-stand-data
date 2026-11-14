"""The catalog's translation sheet: export the question catalog's text to a CSV for a translator or a
native speaker, and bring the reviewed sheet back into the overlays in questions/i18n/.

The sheet has the same columns as the app's own sheet (app/docs/translations.csv) and the shared
workflow (security_tool_kits_app/docs/TRANSLATION_WORKFLOW.md), one row per English text:

    python -m statsapp_pipeline sheet                        write questions/i18n/translations.csv
    python -m statsapp_pipeline sheet-import <returned.csv>  check a returned sheet, write nothing
    python -m statsapp_pipeline sheet-import <returned.csv> --write   update i18n/<lang>.json

A row's key is the path of the text in the overlay, segments joined by "/" ("~1" stands for a "/"
inside a segment and "~0" for "~"), for example questions/us-income-rank/text/sentence or
lists/sex/F. List items are numbered from 0.

Option lists of place names (US states, Malaysian states, Indonesian provinces) stay English on
purpose and are left out of the sheet unless some language already translates them.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from . import i18n
from .common import QUESTIONS_DIR

SHEET = QUESTIONS_DIR / "i18n" / "translations.csv"
LANGUAGE_NAMES = {"id": "Indonesian", "ms": "Malay"}
COLUMN_ORDER = ["id", "ms"]  # same order as app/docs/translations.csv

COLUMNS = [
    "#", "Key (do not change)", "English", "Context (where it appears)", "Purpose", "UI element",
    "Placeholders (keep exactly as written)", "English with example values",
    "English length (characters)", "Length guidance", "Do not translate", "Notes",
]
COMMENTS = "Translator comments"

# Words that must stay as they are: publishers and their data sites, products, the app's name, the
# owner's name, currency codes and symbols, and official terms kept in their own language.
DO_NOT_TRANSLATE = [
    "Hall of Ranks", "Agus Kresna", "BPS", "DOSM", "OpenDOSM", "data.gov.my", "Census Bureau",
    "BLS", "NCHS", "CDC", "OECD", "CIA World Factbook", "Anthropic Economic Index", "Claude", "GED",
    "Bumiputera", "B40", "M40", "T20", "USD", "MYR", "IDR", "RM", "Rp",
]

# ---------------------------------------------------------------- placeholder examples
# Made-up but realistic values, the way the app fills them in (in English here; the app fills them
# in the person's language). Most general first; a mode's and a question's own values win.
EXAMPLES = {
    "pct": "72%", "pctAbove": "28%", "share": "18%", "younger": "64%", "older": "35%",
    "rank": "72nd percentile", "ordinal": "10th", "of": "366", "group": "women aged 25–34 in Texas",
    "age": "35", "band": "25–34", "bandLabel": "25–34", "who": "women", "sex": "women",
    "place": "in Texas", "state": "in Texas", "where": "in Selangor", "label": "Texas",
    "label.state": "Texas", "label.country": "Japan", "label.place": "Japan", "label.home": "Texas",
    "label.province": "Papua Pegunungan", "label.ageGroup": "25–34", "province": "Jawa Barat",
    "name": "Japan", "year": "1990", "date": "June 15", "births": "11,200", "mean": "10,400",
    "first": "1994", "last": "2014", "from": "1960", "to": "2026", "left": "44", "liveTo": "79",
    "alive": "3.9 million", "birthsLine": " 4.2 million babies were born in the US that year.",
    "count": "1,250", "total": "1.2 million", "people": "Americans", "lo": "28", "hi": "35",
    "seeking": "women", "kids": "girls", "oneIn": "1 in 1,250", "peakYear": "1987",
    "peakCount": "9,800", "since": "1880", "lastYear": "2024", "lastCount": "2,140",
    "value": "12", "inverse": "3.4", "ratio": "1.4", "ratioNum": "1.4", "typicalRatio": "5.2",
    "priceRatio": "4.8", "diff": "+0.4", "month": "September 2026", "personalPct": "3.2%",
    "overall": "2.9%", "thisYear": "2026", "then": "5.3 billion", "today": "8.2 billion",
    "now": "2.1", "trend": "down", "tfr": "1.2", "world": "2.2", "mac": "29", "v.birthYear": "1990",
    "v.year": "1990", "v.age": "31", "v.kids": "2", "v.down": "20", "n.size": "3",
    "years": "14 years", "when": "in 14 years", "dataYear": "2023", "growth": "3%",
    "avg.sleep": "8.8", "avg.screens": "3.1", "avg.leisure": "4.6", "avg.paidWork": "3.9",
    "avg.personalCare": "10.9", "avg.unpaidWork": "2.6", "years.sleep": "16", "years.work": "8",
    "years.screens": "6", "years.leisure": "8", "years.paidWork": "7", "sameAge": "11%",
    "even": "8.3%", "sign": "Virgos", "animal": "Horse", "job": "registered nurses",
    "lower": "registered nurses", "jobPhrase": "in manufacturing ", "eduName": "tertiary education",
    "manEdu": "a bachelor's degree", "womanEdu": "a bachelor's degree", "verb": "grow", "size": "6%",
    "allChange": "4%", "baseYear": "2024", "projYear": "2034", "aLabel": "heart disease",
    "bLabel": "a car crash", "aOdds": "6", "bOdds": "95", "cents": "84", "allCents": "83",
    "speakers": "41.8 million", "language": "Spanish", "country": "Mexico", "spread": "5.1",
    "firstLabel": "Hawaii", "lastLabel": "Mississippi", "homeName": "Malaysia", "homeYear": "2023",
    "fewer": "21", "you": "1,950", "tier": "middle 40% (M40)", "range": "RM 5,250 to RM 11,819",
    "next": "top 20% (T20)", "latest": "2024", "thenTfr": "1.8", "nowTfr": "1.6", "thenYear": "1990",
    "cpiYear": "2025", "missingShare": "4%", "ownName": "Malaysia", "online": "68", "onlineYear": "2023",
    "richer": "62", "parts": "62 would live on less than you and 64 would be younger than you",
    "allBirths": "93 million", "largest": "Islam", "largestPct": "63.5%", "indexNum": "0.8",
    "bracketShare": "21%", "period": "March 2026", "multiple": "4.2",
    "class": "Middle class (kelas menengah)", "local": "kelas menengah",
    "localNote": " BPS calls this kelas menengah.", "sub": "upper part",
}
# Amounts, in each mode's currency.
MONEY = {
    "us": {"median": "$52,000", "p25": "$34,000", "p75": "$78,000", "price": "$412,000",
           "monthly": "$1,200", "income": "$61,000", "typical": "$4,100", "women": "$71,000",
           "men": "$76,000", "cut1": "$41,000", "cut2": "$123,000", "salaryText": "$65,000",
           "converted": "$65,000", "total": "$48,000", "gdp": "$12,400", "threshold": "$30"},
    "world": {"median": "$7.90", "perDay": "$12", "price": "$310,000", "monthly": "$900",
              "salaryText": "RM 60,000", "converted": "$36,000", "threshold": "$30",
              "gdp": "$12,400", "first": "$41,000", "last": "$78,000"},
    "my": {"median": "RM 3,200", "typical": "RM 3,200", "women": "RM 2,900", "men": "RM 3,300",
           "overall": "RM 3,100", "cut1": "RM 5,250", "cut2": "RM 11,819", "toNext": "RM 4,700"},
    "id": {"median": "Rp 2.500.000", "typical": "Rp 3.300.000", "perPerson": "Rp 2.000.000",
           "line": "Rp 669.235", "amount": "Rp 2.342.323", "gap": "Rp 342.323",
           "from": "Rp 1.500.000", "to": "Rp 2.000.000", "range": "Rp 1.500.000 to Rp 2.000.000"},
}
QUESTION_EXAMPLES = {
    "us-birthday-rank": {"rank": "120th", "date": "June 15", "place": "in the US"},
    "my-birthday-rank": {"rank": "120th", "date": "June 15", "place": "in Malaysia"},
    "us-time-left": {"place": "in the US"}, "my-time-left": {"place": "in Malaysia", "who": "women"},
    "id-time-left": {"place": "in Indonesia"}, "world-time-left": {"place": "in Japan"},
    "us-age-rank": {"place": "in the US"}, "my-age-rank": {"place": "in Malaysia", "who": "women"},
    "id-age-rank": {"place": "in Indonesia"}, "world-age-rank": {"place": "in Japan"},
    "us-your-generation": {"place": "in the US"},
    "world-your-generation": {"place": "in Japan", "births": "1.2 million"},
    "us-years-to-home": {"place": "in Texas", "years": "14 years"},
    "world-years-to-home": {"name": "Malaysia", "price": "RM 410,000", "monthly": "RM 1,500"},
    "us-singles-near-you": {"label": "Texas", "count": "310,000", "total": "2.4 million"},
    "us-marriage-timing": {"label": "Texas", "age": "30"},
    "us-own-home-age": {"label": "Texas", "band": "35–44"},
    "us-middle-class": {"label": "Texas", "group": "in Texas", "ratio": "1.4"},
    "us-rent-burden": {"label": "Texas", "value": "34", "group": "in Texas"},
    "us-commute-rank": {"label": "Texas", "group": "in Texas", "pct": "72%"},
    "us-income-rank": {"label": "Texas", "band": "25–34"},
    "us-pay-in-job": {"label": "Texas", "group": "registered nurses in Texas"},
    "us-home-size": {"from": "1,500", "to": "1,999", "range": "1,500 to 1,999 sq ft",
                     "group": "owner-occupied homes in the US"},
    "us-age-gap": {"value": "3"},
    "us-risk-odds": {"value": "16"},
    "us-degree-earns": {"label": "economics", "median": "$84,000", "overall": "$70,000"},
    "us-debt-check": {"age": "35–44", "none": "23%", "total": "$48,000"},
    "us-student-debt": {"age": "25–34", "none": "78%", "total": "$28,000"},
    "us-family-size": {"age": "35–44"}, "us-education-rank": {"age": "25–34"},
    "us-living-with-parents": {"age": "25", "sex": "men"},
    "us-job-outlook": {"job": "registered nurses"},
    "us-diaspora": {"people": "1.6 million", "country": "the Philippines", "income": "$58,000"},
    "us-family-then-now": {"year": "1990"},
    "us-salary-furthest": {"place": "in Texas", "first": "$58,000", "last": "$92,000",
                           "firstLabel": "Mississippi", "lastLabel": "Hawaii", "label.home": "Texas"},
    "us-life-exp-state": {"first": "80.7 years"},
    "us-personal-inflation": {"place": "US"}, "my-personal-inflation": {"place": "Malaysian",
                                                                     "overall": "1.5%"},
    "id-personal-inflation": {"place": "Indonesian", "overall": "2.4%"},
    "us-name-popularity": {"name": "Olivia", "rank": "3", "year": "2024", "count": "14,700",
                           "oneIn": "1 in 120", "total": "1.4 million"},
    "us-zodiac-share": {"people": "Americans", "first": "1994", "last": "2014", "share": "8.6%"},
    "my-zodiac-share": {"people": "Malaysians", "first": "2000", "last": "2023", "share": "8.6%"},
    "world-income-rank": {"name": "Malaysia", "median": "$7.90"},
    "world-100-people": {"name": "Malaysia", "younger": "64"},
    "world-pop-when-born": {"name": "Malaysia", "then": "18 million", "today": "36 million",
                            "ratio": "2.0"},
    "world-family-size": {"diff": "0.9"}, "world-parenthood-age": {"diff": "2.1"},
    "world-family-lottery": {"then": "3.3", "today": "2.2"},
    "world-chinese-zodiac": {"place": "in the world", "share": "8.7%"},
    "world-birth-lottery": {"name": "Malaysia", "year": "1990"},
    "world-dream-partner": {"name": "Malaysia", "people": "women aged 28–35", "total": "38 million"},
    "world-life-in-hours": {"name": "Japan", "who": "woman"}, "us-life-in-hours": {"who": "woman"},
    "world-life-exp-anywhere": {"first": "84.9", "year": "2026", "firstLabel": "Japan",
                                "lastLabel": "Nigeria", "spread": "30.1"},
    "world-salary-across": {"label": "Japan"},
    "world-ai-use": {"name": "Malaysia", "rank": "45th", "count": "116"},
    "world-religion": {"name": "Malaysia"},
    "world-work-hours": {"total": "38"},
    "my-income-rank": {"label": "Selangor", "group": "in Selangor"},
    "my-b40": {"range": "from RM 5,250 to RM 11,819", "next": "top 20% (T20)"},
    "my-pay-median": {"place": "Selangor", "who": "Women", "ratio": "1.3×", "typical": "RM 3,200"},
    "my-pay-gap": {"state": "Selangor", "where": "in Selangor"},
    "my-education-earns": {"who": "Employees", "median": "RM 3,500"},
    "id-kelas-sosial": {"name": "Middle class (kelas menengah)", "next": "Upper class (kelas atas)"},
    "id-family-size": {"then": "3.1", "diff": "1.0"},
    "id-spending-rank": {"province": "Jawa Barat"},
    "id-pay-average": {"place": "Jawa Barat", "value": "manufacturing", "ratio": "1.2×",
                       "typical": "Rp 3.300.000"},
}
MESSAGE_EXAMPLES = {
    "label": "your yearly income", "date": "January 1, 1994", "year": "1990", "name": "Malaysia",
    "from": "1926", "to": "2026", "group": "adults aged 25–34 in the US", "ordinal": "10th",
    "age": "85",
}

# ---------------------------------------------------------------- key paths


def make_key(path: list) -> str:
    return "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in path)


def split_key(key: str) -> list[str]:
    return [p.replace("~1", "/").replace("~0", "~") for p in key.split("/")]


def _strings_with_paths(o, path):
    if isinstance(o, str):
        yield path, o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield from _strings_with_paths(v, path + [k])
    elif isinstance(o, list):
        for i, v in enumerate(o):
            if v is not None:
                yield from _strings_with_paths(v, path + [i])


def _get(o, path):
    for p in path:
        if isinstance(o, dict) and p in o:
            o = o[p]
        elif isinstance(o, list) and isinstance(p, int) and 0 <= p < len(o):
            o = o[p]
        else:
            return None
    return o


def resolve(english: dict, key: str) -> list | None:
    """The path a sheet key stands for (list positions as ints), or None when the catalog has no
    such translatable text."""
    o, out = english, []
    for seg in split_key(key):
        if isinstance(o, dict) and seg in o:
            o = o[seg]
            out.append(seg)
        elif isinstance(o, list) and seg.isdigit() and int(seg) < len(o) and o[int(seg)] is not None:
            o = o[int(seg)]
            out.append(int(seg))
        else:
            return None
    return out if isinstance(o, str) else None


# ---------------------------------------------------------------- describing a row

_ERROR_KEYS = {"error", "missing", "empty", "required", "rangeError", "requirePositive", "notFound",
               "noPpp", "noCountry", "noYear", "noTable", "noWeights"}
_CAVEAT_KEYS = {"caveats", "fallbackCaveat", "caveat", "cpiNote", "noCpiNote", "missCaveat"}
_STAT_KEYS = {"stats", "stat", "nextStat", "thresholdStat", "alsoFor", "rowStats"}
_BAR_KEYS = {"bars", "barsTitle", "activities", "animals", "signs", "labels", "you", "main",
             "others", "rest"}
_PHRASE_KEYS = {"parts", "who", "place", "people", "kids", "prefix", "suffix", "placePhrase",
                "values", "trend", "crossing", "when", "rangeText", "name", "compare", "eduName",
                "manEdu", "womanEdu", "verb", "where", "birthsLine", "sentenceParts"}

SHORT = "Short: aim for at most ~1.3x the English length; space is limited."
TIGHT = "Very tight: one short word if possible."
FLEX = "Wraps onto several lines; length is flexible, keep it clear."
NO_LIMIT = "No limit (not shown in a tight space)."


def _length(kind: str, text: str) -> str:
    if kind in ("Unit (after a number)", "Segmented button"):
        return TIGHT
    if kind in ("Title / heading", "Label", "Option in a list", "Result heading (large)",
                "Bar label", "Stat label", "Stat value", "Mode name", "Topic heading") or len(text) <= 25:
        return SHORT
    return FLEX


def _describe_param(keys: list[str], text: str) -> tuple[str, str, str]:
    """(purpose, UI element, note) for a string inside a question's params."""
    where = " › ".join(keys)
    ks = set(keys)
    last = keys[-1] if keys else ""
    if "whenZero" in ks or (keys[:2] == ["phrases", "headline"]) or (keys[:2] == ["phrases", "sentence"]):
        if last == "headline" or keys[:2] == ["phrases", "headline"]:
            return f"Result headline used in a special case (params › {where})", "Result heading (large)", ""
        return f"Result sentence used in a special case (params › {where})", "Result sentence", ""
    if keys[:2] == ["phrases", "summary"] or last in ("sentenceAnyIncome",) or keys[0] == "values" and "comparison" in ks:
        return f"Result sentence, or part of it (params › {where})", "Result sentence", ""
    if last in ("localNote", "birthsLine"):
        return (f"Sentence added to the end of the result sentence (params › {where})", "Result sentence",
                "Joined straight onto the end of the result sentence.")
    if ks & _ERROR_KEYS:
        return f"Error shown instead of a result (params › {where})", "Error message", ""
    if ks & _CAVEAT_KEYS:
        return f"Caveat: small print under the result (params › {where})", "Caveat (small print)", ""
    if "gridCaption" in ks:
        return "Caption under the picture of 100 figures", "Caption", ""
    if ks & _STAT_KEYS:
        pos = next((p for p in reversed(keys) if p.isdigit()), None)
        kind = "Stat value" if pos == "1" else "Stat label"
        return f"{kind} in the result's figures (params › {where})", kind, ""
    if ks & _BAR_KEYS:
        if last in ("title", "barsTitle"):
            return "Title above the bar chart", "Title / heading", ""
        return f"Label of a bar in the chart (params › {where})", "Bar label", ""
    if "tiers" in ks:
        if last == "name":
            return "Name of an income tier, inserted as {tier}", "Word inserted into another sentence", \
                "Inserted into the result sentence as {tier} (\"Your household is in the {tier}\")."
        return "A tier's income range, inserted as {range}", "Word inserted into another sentence", \
            "Inserted into the result sentence as {range} (\"covers household incomes {range} a month\")."
    if "format" in ks and last == "suffix":
        return "Unit written after a number in the result", "Unit (after a number)", \
            "Starts with a space; keep it."
    if ks & _PHRASE_KEYS or "phrase" in ks or "phrases" in ks or "map" in ks:
        return (f"Words inserted into the result sentence or headline (params › {where})",
                "Word inserted into another sentence",
                "Inserted into other texts of this question in place of a {placeholder}; it must fit "
                "grammatically there (see the question's sentence and headline rows).")
    return f"Text the calculation shows (params › {where})", "Body text", ""


def describe(path: list, text: str, catalog: dict, english: dict) -> dict:
    """Context, purpose, UI element and notes for one translatable text."""
    section = path[0]
    modes = {m["id"]: m for m in catalog.get("modes", [])}
    if section == "modes":
        field = path[2]
        if field == "title":
            return dict(context="Home screen (a comparison's card) and the top of that comparison's screen",
                        purpose="Comparison (mode) name", ui="Mode name",
                        notes="One of the four comparisons: keep the same pattern for all four.")
        return dict(context="Home screen, under the comparison's name",
                    purpose="One line saying what the comparison is and whose data it uses",
                    ui="Subtitle", notes="")
    if section == "topics":
        return dict(context="Question list of every comparison (section heading)",
                    purpose=f"Topic heading ({path[1]})", ui="Topic heading", notes="")
    if section == "lists":
        name, value = path[1], path[2]
        users = [f"{modes.get(q['mode'], {}).get('title', q['mode'])} › {q['title']}"
                 for q in catalog["questions"]
                 if any(i.get("options") == f"@{name}" for i in q.get("inputs", []))]
        ctx = "Question form, option shared by: " + "; ".join(users[:4]) + (f" (+{len(users) - 4} more)" if len(users) > 4 else "")
        return dict(context=ctx, purpose=f"Option label in the shared list \"{name}\" (value {value})",
                    ui="Option in a list", notes="")
    if section == "messages":
        key = path[1]
        low = text.lower()
        if key.endswith(("Caveat",)):
            purpose, ui = "Caveat a calculation adds by itself", "Caveat (small print)"
        elif key.endswith("Caption"):
            purpose, ui = "Caption a calculation adds under the picture of 100 figures", "Caption"
        elif key in ("everythingElse", "populationYear", "chanceOfReaching"):
            purpose, ui = "Stat or bar label a calculation adds by itself", "Stat label"
        elif key == "thePeople":
            purpose, ui = "Words a calculation inserts into a sentence", "Word inserted into another sentence"
        elif key in ("belowPercentile", "abovePercentile"):
            purpose, ui = "Rank shown as a result headline at the ends of the scale", "Result heading (large)"
        elif key in ("groupFallback", "lifeTableFallback"):
            purpose, ui = "Caveat when the calculation had to use a broader group", "Caveat (small print)"
        elif low.startswith(("enter", "pick", "type", "check")):
            purpose, ui = "Error about what the person entered", "Error message"
        else:
            purpose, ui = "Error shown instead of a result", "Error message"
        notes = ""
        if key == "thePeople":
            notes = "Inserted as {who} into sentences such as \"You're older than {younger} of {who} living {place}\"."
        if key in ("belowPercentile", "abovePercentile"):
            notes = "{ordinal} is filled with a number word such as \"10th\", already in the person's language."
        return dict(context=f"Any question: calculation message \"{key}\"", purpose=purpose, ui=ui, notes=notes)

    # questions/<id>/...
    qid = path[1]
    q = next(x for x in catalog["questions"] if x["id"] == qid)
    mode_title = modes.get(q["mode"], {}).get("title", q["mode"])
    context = f"{mode_title} › {q['title']}"
    field = path[2]
    notes = ""
    if field == "title":
        purpose, ui = "Question title (in the question list and at the top of the question screen)", "Title / heading"
    elif field == "question":
        purpose, ui = "The question asked, under the title", "Subtitle"
    elif field == "inputs":
        ikey, what = path[3], path[4]
        inp = next((i for i in q.get("inputs", []) if i.get("key") == ikey), {})
        label = inp.get("label") or ikey
        if what == "label":
            purpose, ui = f"Label of the input \"{ikey}\"", "Label"
        elif what == "help":
            purpose, ui = f"Help under the input \"{label}\"", "Help text"
        elif what == "unit":
            purpose, ui = f"Unit after the number in \"{label}\"", "Unit (after a number)"
        else:
            purpose = f"Option (value {path[5]}) of the input \"{label}\""
            ui = "Segmented button" if inp.get("type") == "choice" else "Option in a list"
            if what == "first":
                purpose += ", shown first in the list"
    elif field == "text":
        what = path[3]
        if what == "headline":
            purpose, ui = "Result headline: the big line of the result", "Result heading (large)"
            notes = "One of the most important texts: must be clear at a glance, in a few words."
        elif what == "sentence":
            purpose, ui = "Result sentence, under the headline", "Result sentence"
            notes = "One of the most important texts: plain, exact, no judgement."
        elif what == "stats":
            kind = "Stat label" if path[5] == 0 else "Stat value"
            purpose, ui = f"{kind} in the result's figures", kind
        elif what == "caveats":
            purpose, ui = "Caveat: small print under the result", "Caveat (small print)"
        else:
            purpose, ui = f"Result text ({what})", "Body text"
    else:  # params
        keys = [str(p) for p in path[3:]]
        purpose, ui, notes = _describe_param(keys, text)
        if ui == "Result heading (large)":
            notes = (notes + " " if notes else "") + "One of the most important texts: must be clear at a glance."
    return dict(context=context, purpose=purpose, ui=ui, notes=notes)


def examples_for(path: list, catalog: dict) -> dict:
    if path[0] == "messages":
        return {**EXAMPLES, **MESSAGE_EXAMPLES}
    if path[0] != "questions":
        return EXAMPLES
    q = next(x for x in catalog["questions"] if x["id"] == path[1])
    out = {**EXAMPLES, **MONEY.get(q["mode"], {}), **QUESTION_EXAMPLES.get(q["id"], {})}
    # {label.KEY} and {in.KEY}: the first real option of that input.
    lists = catalog.get("lists", {})
    for inp in q.get("inputs", []):
        opts = inp.get("options")
        if isinstance(opts, str) and opts.startswith("@"):
            opts = lists.get(opts[1:])
        if isinstance(opts, list):
            real = [o for o in opts if isinstance(o, list) and len(o) >= 2 and o[0] not in ("*", "all")]
            if real:
                out.setdefault(f"label.{inp['key']}", str(real[min(1, len(real) - 1)][1]))
                out.setdefault(f"in.{inp['key']}", str(real[min(1, len(real) - 1)][0]))
    return out


def _notes(text: str, extra: str) -> str:
    notes = [extra] if extra else []
    if i18n.placeholders(text):
        notes.append("Keep each {placeholder} exactly; you may move it within the sentence. The app fills it in "
                     "with a value already in the person's language.")
    if text != text.lstrip():
        notes.append("Starts with a space; keep it (joined to the text before).")
    if text != text.rstrip():
        notes.append("Ends with a space; keep it (joined to the text after).")
    if "\n" in text:
        notes.append("Contains a line break; keep it.")
    return " ".join(notes)


def _keep_words(text: str) -> list[str]:
    bare = re.sub(r"\{[^{}]*\}", "", text)
    return [w for w in DO_NOT_TRANSLATE if re.search(r"(?<![\w.])" + re.escape(w) + r"(?![\w])", bare)]


# ---------------------------------------------------------------- export


def rows(catalog: dict, overlays: dict[str, dict]) -> list[list]:
    english = i18n.translatable(catalog)
    langs = [c for c in COLUMN_ORDER if c in overlays] + sorted(set(overlays) - set(COLUMN_ORDER))
    out = []
    for path, text in _strings_with_paths(english, []):
        current = {lang: _get(overlays[lang], path) for lang in langs}
        current = {k: v if isinstance(v, str) else "" for k, v in current.items()}
        if path[0] == "lists" and not any(current.values()):
            continue  # place names that stay English on purpose
        d = describe(path, text, catalog, english)
        ex = examples_for(path, catalog)
        names = sorted(set(i18n._PLACEHOLDER.findall(text)), key=lambda n: text.index("{" + n + "}"))
        filled = text
        for n in names:
            filled = filled.replace("{" + n + "}", ex.get(n, f"<{n}>"))
        out.append([
            len(out) + 1, make_key(path), text, d["context"], d["purpose"], d["ui"],
            "; ".join(f"{{{n}}} = {ex.get(n, '(a value)')}" for n in names),
            filled if names else "", len(text), _length(d["ui"], text), ", ".join(_keep_words(text)),
            _notes(text, d["notes"]),
            *[current[lang] for lang in langs], "",
        ])
    return out


def header(langs: list[str]) -> list[str]:
    return COLUMNS + [f"{LANGUAGE_NAMES.get(c, c)} ({c}) - current" for c in langs] + [COMMENTS]


def export(path: Path = SHEET, catalog: dict | None = None, overlays: dict | None = None) -> int:
    from . import questions

    catalog = catalog if catalog is not None else questions.load()
    overlays = overlays if overlays is not None else i18n.load_overlays()
    langs = [c for c in COLUMN_ORDER if c in overlays] + sorted(set(overlays) - set(COLUMN_ORDER))
    body = rows(catalog, overlays)
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(header(langs))
    w.writerows(body)
    Path(path).write_bytes(buf.getvalue().encode("utf-8-sig"))
    return len(body)


# ---------------------------------------------------------------- import

_LANG_COLUMN = re.compile(r"\((\w+)\)(?: - current)?$")


def _put(o: dict, key, value, english: dict) -> None:
    """Set o[key], placing a new key where the English order puts it among the keys already there."""
    if key in o:
        o[key] = value
        return
    order = list(english)
    rank = order.index(key)
    items = list(o.items())
    at = len(items)
    for i, (k, _) in enumerate(items):
        if k in english and order.index(k) > rank:
            at = i
            break
    items.insert(at, (key, value))
    o.clear()
    o.update(items)


def _set(overlay: dict, english: dict, path: list, text: str) -> None:
    """Put text at path in an overlay, creating objects and English-length lists on the way."""
    o, en = overlay, english
    for i, p in enumerate(path):
        en_next = en[p]
        if i == len(path) - 1:
            nxt = text
        else:
            cur = o.get(p) if isinstance(o, dict) else o[p]
            nxt = cur if isinstance(cur, (dict, list)) else ([None] * len(en_next) if isinstance(en_next, list) else {})
        if isinstance(o, dict):
            _put(o, p, nxt, en)
        else:
            o[p] = nxt
        o, en = nxt, en_next


def apply(catalog: dict, overlays: dict[str, dict], sheet_rows: list[list[str]]):
    """Check a returned sheet against the catalog. Returns (overlays with the sheet's text,
    refused problems, warnings, changes per language)."""
    english = i18n.translatable(catalog)
    head = sheet_rows[0] if sheet_rows else []
    try:
        key_col = next(i for i, h in enumerate(head) if h.startswith("Key"))
    except StopIteration:
        return overlays, ["no \"Key (do not change)\" column"], [], {}
    lang_cols = {}
    for i, h in enumerate(head):
        m = _LANG_COLUMN.search(h)
        if m and m.group(1) in i18n.LANGUAGES:
            lang_cols[m.group(1)] = i
    if not lang_cols:
        return overlays, ["no language columns, expected e.g. \"Indonesian (id) - current\""], [], {}
    new = {lang: json.loads(json.dumps(overlays.get(lang) or {"schema": i18n.SCHEMA, "language": lang, "modes": {}, "topics": {}, "lists": {}, "messages": {}, "questions": {}}))
           for lang in lang_cols}
    problems, warnings = [], []
    changes = {lang: 0 for lang in lang_cols}
    seen = set()
    for line, row in enumerate(sheet_rows[1:], 2):
        key = row[key_col].strip() if key_col < len(row) else ""
        if not key:
            continue
        path = resolve(english, key)
        if path is None:
            problems.append(f"line {line}: unknown key \"{key}\"")
            continue
        if key in seen:
            problems.append(f"line {line}: key \"{key}\" appears twice")
            continue
        seen.add(key)
        en = _get(english, path)
        keep = _keep_words(en)
        for lang, col in lang_cols.items():
            text = row[col] if col < len(row) else ""
            if not text.strip():
                problems.append(f"line {line} {lang} {key}: empty")
                continue
            if i18n.placeholders(text) != i18n.placeholders(en):
                problems.append(f"line {line} {lang} {key}: placeholders {i18n.placeholders(text)}, "
                                f"expected {i18n.placeholders(en)}")
                continue
            lost = [w for w in keep if w not in text]
            if lost:
                warnings.append(f"line {line} {lang} {key}: missing {', '.join(lost)} (check it)")
            if _get(new[lang], path) != text:
                _set(new[lang], english, path, text)
                changes[lang] += 1
    return new, problems, warnings, changes


def read_sheet(path: Path) -> list[list[str]]:
    text = Path(path).read_bytes().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


def dump_overlay(overlay: dict, newline: str = "\n") -> bytes:
    text = json.dumps(overlay, ensure_ascii=False, indent=2) + "\n"
    return text.replace("\n", newline).encode("utf-8")


def write_overlay(path: Path, overlay: dict) -> bool:
    """Write an overlay as the repository keeps them (2-space JSON, UTF-8, the file's own line
    endings). Returns whether the file changed."""
    path = Path(path)
    old = path.read_bytes() if path.exists() else b""
    newline = "\r\n" if b"\r\n" in old else "\n"
    data = dump_overlay(overlay, newline)
    if data == old:
        return False
    path.write_bytes(data)
    return True
