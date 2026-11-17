"""Fill the organisers' submission template with Silsila's content.

    uv run --no-project --with python-pptx python tools/submission/build_deck.py TEMPLATE.pptx OUT.pptx

The template itself is the organisers' file and is not kept in this repository. Every slide of the template
is kept, in its order, with its heading; content is added in the empty area under each heading. Every number
is in README.md or docs/evidence. Then export OUT.pptx to PDF (LibreOffice: soffice --headless --convert-to pdf).
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

INK, TEAL, BRASS, MUTED = RGBColor(0x12, 0x30, 0x2F), RGBColor(0x0E, 0x5A, 0x57), RGBColor(0x7A, 0x5C, 0x24), RGBColor(0x4F, 0x5C, 0x58)
SOFT, SAND, LINE, WHITE = RGBColor(0xE4, 0xEF, 0xEC), RGBColor(0xF4, 0xEF, 0xE6), RGBColor(0xC9, 0xBD, 0xA8), RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Arial"
LIVE = "https://silsila-web.lemonisland-568f9acd.uaenorth.azurecontainerapps.io"
FILM = "https://youtu.be/fCHWTlGyeSY"
REPO = "https://github.com/DivineTechie/silsila"
TEAM = {"name": "Tushar Agarwal", "country": "India", "role": "Founder; design, engineering, evidence", "org": "Independent",
        "age": "18 or over: confirmed"}


def text(slide, x, y, w, h, paras, size=10.5, color=INK, anchor=MSO_ANCHOR.TOP, align=PP_ALIGN.LEFT):
    """paras: list of str or (str, {bold, size, color, bullet, italic, space})."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    first = True
    for p in paras:
        s, o = (p, {}) if isinstance(p, str) else p
        para = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        para.alignment = align
        para.space_after = Pt(o.get("space", 3))
        run = para.add_run()
        run.text = ("•  " + s) if o.get("bullet") else s
        f = run.font
        f.name, f.size, f.bold, f.italic = FONT, Pt(o.get("size", size)), o.get("bold", False), o.get("italic", False)
        f.color.rgb = o.get("color", color)
    return box


def card(slide, x, y, w, h, title, body, fill=SAND, title_color=TEAL, size=9.5, title_size=10.5):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = 0.06
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = LINE
    shp.line.width = Pt(0.5)
    shp.shadow.inherit = False
    paras = [(title, {"bold": True, "size": title_size, "color": title_color, "space": 4})] if title else []
    paras += body if isinstance(body, list) else [body]
    text(slide, x + 0.08, y + 0.06, w - 0.16, h - 0.1, paras, size=size)
    return shp


def stat(slide, x, y, w, h, number, label, source):
    card(slide, x, y, w, h, None, [(number, {"bold": True, "size": 19, "color": TEAL, "space": 2}), (label, {"size": 9, "space": 3}),
                                    (source, {"size": 7.5, "color": MUTED, "italic": True})], fill=WHITE)


def table(slide, x, y, w, col_widths, rows, size=8.5, header_fill=TEAL, row_h=0.3):
    shape = slide.shapes.add_table(len(rows), len(col_widths), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows)))
    t = shape.table
    tbl = shape._element.graphic.graphicData.tbl
    tbl.tblPr.remove(tbl.tblPr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId")) if tbl.tblPr.find(
        "{http://schemas.openxmlformats.org/drawingml/2006/main}tableStyleId") is not None else None
    total = sum(col_widths)
    for i, cw in enumerate(col_widths):
        t.columns[i].width = Inches(w * cw / total)
    for r, row in enumerate(rows):
        t.rows[r].height = Inches(row_h)
        for c, val in enumerate(row):
            cell = t.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.05)
            cell.margin_top = cell.margin_bottom = Inches(0.025)
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if r == 0 else (WHITE if r % 2 else SAND)
            tf = cell.text_frame
            tf.word_wrap = True
            tf.paragraphs[0].text = ""
            run = tf.paragraphs[0].add_run()
            run.text = val
            run.font.name, run.font.size, run.font.bold = FONT, Pt(size), r == 0
            run.font.color.rgb = WHITE if r == 0 else INK
    return shape


def box(slide, x, y, w, h, title, sub, fill=SOFT, title_color=INK):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = 0.12
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    shp.line.color.rgb = TEAL
    shp.line.width = Pt(0.75)
    shp.shadow.inherit = False
    text(slide, x + 0.04, y + 0.03, w - 0.08, h - 0.06, [(title, {"bold": True, "size": 9, "color": title_color, "space": 2}), (sub, {"size": 7.5, "color": MUTED})],
         anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)


def arrow(slide, x1, y1, x2, y2):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = TEAL
    c.line.width = Pt(1.25)
    ln = c.line._get_or_add_ln()
    tail = ln.makeelement("{http://schemas.openxmlformats.org/drawingml/2006/main}tailEnd", {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)


def restyle(shape):
    """The template's headings use a web font that a PDF export may not have; use the same safe font throughout."""
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            run.font.name = FONT


def main(src: str, dst: str) -> None:
    prs = Presentation(src)
    S = list(prs.slides)
    for s in S:
        for sh in s.shapes:
            if sh.has_text_frame:
                restyle(sh)

    # 1. Cover: the template's three lines, filled in
    cover = next(sh for sh in S[0].shapes if sh.has_text_frame)
    fills = {"Team Name:": "Silsila (سلسلة)", "Team Size:": "1", "Problem Statement:": "Fertility, Challenge 03: Understanding and Reducing Inherited Disease Risk"}
    for para in cover.text_frame.paragraphs:
        label = para.runs[0].text.strip() if para.runs else ""
        if label in fills:
            para.runs[0].font.bold = True
            extra = para.add_run()
            extra.text = fills[label]
            extra.font.name, extra.font.size = FONT, para.runs[0].font.size
    cover.text_frame.word_wrap = True
    for para in cover.text_frame.paragraphs:
        for run in para.runs:
            run.font.size = Pt(15)
    text(S[0], 0.48, 4.55, 9.0, 0.9, [
        ("Premarital screening protects the next marriage. Silsila protects the marriages that already happened.", {"italic": True, "size": 12, "color": TEAL, "space": 4}),
        (f"Live, no password: {LIVE}", {"size": 9.5, "color": MUTED}),
        (f"Film: {FILM}   ·   Code: {REPO}", {"size": 9.5, "color": MUTED}),
    ])

    # 2. Team members: one row
    tbl_shape = next(sh for sh in S[1].shapes if sh.has_table)
    t = tbl_shape.table
    for c, val in enumerate(["1", TEAM["name"], TEAM["country"], TEAM["role"], TEAM["org"], TEAM["age"]]):
        cell = t.cell(1, c)
        cell.text_frame.paragraphs[0].text = ""
        run = cell.text_frame.paragraphs[0].add_run()
        run.text = val
        run.font.name, run.font.size = FONT, Pt(10)
    tbl = tbl_shape._element.graphic.graphicData.tbl
    for tr in list(tbl.findall("{http://schemas.openxmlformats.org/drawingml/2006/main}tr"))[2:]:
        tbl.remove(tr)
    for row in t.rows:
        for cell in row.cells:
            for para in cell.text_frame.paragraphs:
                for run in para.runs:
                    run.font.name = FONT
    text(S[1], 0.4, 2.78, 9.2, 0.75, [
        ("A team of one. The team name is the project name.", {"size": 10.5, "space": 4}),
        ("What a pilot would add first: a genetic counsellor to review every template and queue rule, and a native Arabic-speaking clinician to "
         "review all Arabic wording and audio. Neither review has happened yet, and the product says so on every screen.", {"size": 9.5, "color": MUTED}),
    ])
    assets = Path(__file__).resolve().parent / "assets"
    for i, (img, cap) in enumerate([("cascade.jpg", "Watch a cascade: every relative's chance, and whom to tell first (live site, fictional family)"),
                                    ("twin.jpg", "Family Twin: 61 simulated relatives, each with an exact carrier chance (live site)")]):
        if (assets / img).exists():
            x = 0.4 + i * 4.7
            pic = S[1].shapes.add_picture(str(assets / img), Inches(x), Inches(3.58), width=Inches(3.3))
            pic.line.color.rgb = LINE
            pic.line.width = Pt(0.75)
            text(S[1], x + 3.38, 3.58, 1.25, 1.7, [(cap, {"size": 8, "color": MUTED})])

    # 3. Team capability (max 1,000 characters)
    cap = ("Silsila is entered by one person, Tushar Agarwal. Everything in this submission was produced between 6 and 16 November 2026. "
           "What the work shows: an exact Bayesian pedigree engine checked against an independent solver (30,000 of 30,000 probabilities agree); "
           "a pre-registered benchmark of five language models, including the co-creators' Jais 3; a bilingual, accessible web application "
           "running in Azure UAE North; FHIR R4B import and export; a hazard log of 24 hazards, model cards and a clause map to the DoH "
           "Responsible AI Standard; 250 backend tests. What the team does not have, stated plainly: a clinical genetics qualification and a "
           "native Arabic clinical reviewer. Both are the first additions for a pilot. No patient has used the system.")
    assert len(cap) <= 1000, len(cap)
    card(S[2], 0.4, 1.6, 9.2, 1.75, None, [(cap, {"size": 11, "space": 0})], fill=SAND)
    for i, (n, lab) in enumerate([("11 days", "from first commit to this submission"), ("250 + 145", "automated tests: application, benchmark harness"),
                                  ("0", "accessibility violations, every screen, English and Arabic (axe-core)"), ("UAE North", "where the live prototype runs today")]):
        card(S[2], 0.4 + i * 2.33, 3.55, 2.2, 1.05, None, [(n, {"bold": True, "size": 17, "color": TEAL, "space": 3}), (lab, {"size": 9, "color": INK})], fill=WHITE)

    # 4. Architecture / workflow
    s = S[3]
    y1, bw, bh, gap = 1.55, 1.38, 0.78, 0.175
    steps = [("1  Index result", "FHIR R4B record; checked,\nrefused if unsafe"), ("2  Exact engine", "every relative's chance,\nacross cousin loops"),
             ("3  Family decides", "who is told, and how;\nanonymous if chosen"), ("4  Counsellor approves", "nothing is sent\nbefore this"),
             ("5  Relative's link", "approved wording, quoted\nsource, read aloud, check"), ("6  Closed with evidence", "booking, test result,\nfamily view updates")]
    for i, (a, b) in enumerate(steps):
        x = 0.4 + i * (bw + gap)
        box(s, x, y1, bw, bh, a, b)
        if i:
            arrow(s, x - gap + 0.01, y1 + bh / 2, x - 0.01, y1 + bh / 2)
    text(s, 0.4, 2.42, 9.2, 0.25, [("Under every step", {"bold": True, "size": 9, "color": BRASS})])
    for i, (a, b) in enumerate([("Output gate", "Every sentence a person reads is an approved template or a word-for-word MedlinePlus quotation. Anything else is blocked."),
                                ("Audit chain", "Every action is an entry carrying the SHA-256 of the one before. Tampering shows where the chain breaks."),
                                ("Consent ledger", "Permission to calculate and permission to inform are separate and can be withdrawn."),
                                ("Outcome measures", "Comprehension, uptake, time to counselling, privacy, language. Never marriages or reproductive choices.")]):
        card(s, 0.4 + i * 2.33, 2.68, 2.2, 1.0, a, [(b, {"size": 8.5})], fill=SAND, size=8.5, title_size=9.5)
    text(s, 0.4, 3.8, 9.2, 0.25, [("Where models are, and are not", {"bold": True, "size": 9, "color": BRASS})])
    card(s, 0.4, 4.06, 4.5, 1.2, "Models only draft, and a person confirms", [
        ("Voice intake: Jais-ASR transcribes an Emirati family story and Jais 3 drafts the tree (people, parents, marriages). The counsellor confirms every "
         "person and marriage before the engine runs. A classifier orders the counsellor's message queue; every message is still read by a person.", {"size": 8.5})],
         fill=WHITE, size=8.5, title_size=9.5)
    card(s, 5.1, 4.06, 4.5, 1.2, "No model at run time", [
        ("Risk is never computed by a language model and no model writes to a family. The \"Ask about Silsila\" guide is fixed answers plus live lookups. "
         "Stack: Python (FastAPI), exact variable elimination, SQLite in the demo; Next.js web app in Arabic and English; Azure Container Apps, UAE North, CPU only.", {"size": 8.5})],
         fill=WHITE, size=8.5, title_size=9.5)

    # 5. Target users and intended outcome
    s = S[4]
    users = [("A family with a result", "A newborn screen, a premarital result or a diagnosis has found a recessive condition.",
              "They see every relative's calculated chance, decide who is told and how, and can decline. Nothing is revealed without their choice."),
             ("Relatives, often already married", "Brothers, sisters and cousins, many married to each other before premarital screening existed.",
              "A private link in Arabic or English: approved wording and quoted source text, read aloud on request, a comprehension check, one-tap booking."),
             ("Genetic counsellors", "The UAE has 9 practising genetic counsellors for nearly 11 million people (Almarri 2025).",
              "A ranked list of whom to invite first, a queue ordered by urgency (pregnancy first), approval of every message, closure only with evidence."),
             ("The programme (DoH)", "Owner of newborn and premarital screening, which already produce the index results.",
              "The challenge's own measures, live; a hash-chained audit trail; FHIR in and out; hosting in the UAE.")]
    for i, (a, who, out) in enumerate(users):
        card(s, 0.4 + i * 2.33, 1.5, 2.2, 2.55, a, [(who, {"size": 9, "color": MUTED, "space": 6}), (out, {"size": 9.8})], fill=SAND, size=9.8, title_size=10.5)
    card(s, 0.4, 4.2, 9.2, 1.1, "Intended outcome", [
        ("Relatives at risk learn of it in time to choose, on the family's terms: more at-risk couples reached per test and per counsellor hour, with comprehension "
         "checked and no disclosure the family did not choose. Silsila describes options and never recommends a marriage, a pregnancy decision or a test.", {"size": 9.5})],
         fill=WHITE, size=9.5)

    # 6. How success will be measured
    s = S[5]
    table(s, 0.4, 1.5, 5.7, [2.1, 3.6], [
        ["Measure (from the challenge statement)", "How Silsila computes it"],
        ["Comprehension", "Relatives who pass the comprehension check, by language"],
        ["Counselling uptake", "Opened the link, then booked counselling or testing"],
        ["Time to counselling", "From invitation sent to counselling booked; counsellor turnaround"],
        ["At-risk couples identified", "Per test and per family, against an unranked cascade"],
        ["Privacy", "Unauthorised disclosures (target 0), refused requests, blocked outputs, audit chain intact"],
        ["Equity", "Every measure by language; literacy access through read aloud"],
    ], size=8.5, row_h=0.36)
    card(s, 6.3, 1.5, 3.3, 1.2, "Never measured as success", [("Marriages, cancelled engagements, or any reproductive choice.", {"size": 9.5})], fill=SAND)
    card(s, 6.3, 2.82, 3.3, 1.2, "Live today", [("The counsellor's Outcomes tab computes these from recorded activity. The last step of Watch a cascade shows them for that one run.", {"size": 9})], fill=WHITE, size=9)
    card(s, 0.4, 4.15, 9.2, 1.15, "Pilot exit criteria (proposal)", [
        ("Zero unauthorised disclosures. Comprehension in Arabic no worse than in English. Less counsellor time per family than the current process, measured in a "
         "shadow phase before anything is sent. DoH conformity assessment passed (high-risk class). Today's numbers are from simulated families; uptake and "
         "comprehension in real families are what the pilot measures.", {"size": 9})], fill=SAND, size=9)

    # 7. Evidence
    s = S[6]
    table(s, 0.4, 1.55, 9.2, [3.1, 3.5, 2.6], [
        ["What was tested", "Result", "Where"],
        ["Extended-family testing after an affected child (published study)", "31% of relatives carriers; 8% of married couples both carriers; 0 of 397 controls", "Ahmed et al., NEJM 2002, PMID 12374877"],
        ["Engine vs an independent exact solver, 10,000 random families with cousin loops", "30,000 of 30,000 probabilities agree within 1e-9", "docs/evidence/b1_engine.json"],
        ["Malformed or impossible family trees", "0 silent failures in 237", "docs/evidence/b2_robustness.json"],
        ["Reproducing the NEJM 2002 yields in simulation", "All four published figures inside the simulated range", "docs/evidence/b3_nejm.json"],
        ["At-risk couples per 1,000 tests, Silsila's order vs unranked (5 tests per family)", "HBB 65 vs 41 (ratio 1.58, 95% CI 1.43-1.77); CAH 51 vs 33 (1.53, 1.29-1.85)", "docs/evidence/b4_uae.json"],
        ["Five language models on 150 families, pre-registered (Silsila-Bench)", "Jais 3 7B: exact in 59.4% of free-text answers given; 70.8% with the engine as a tool", "docs/evidence/silsila_bench.md"],
        ["Unauthorised API requests, 14 kinds of attack", "0 disclosures in 10,000", "docs/evidence/privacy_api.json"],
        ["Crisis messages, blind 400-message test set", "Alert sensitivity 0.961 (95% CI 0.890-0.986); every message read by a person", "docs/evidence/triage_rules_ngram.json"],
        ["FHIR import: 22 unsafe records, 116 single-field deletions", "0 crashes, 0 silent failures", "backend/tests/test_fhir_import.py"],
    ], size=7.8, row_h=0.335)
    text(s, 0.4, 5.02, 9.2, 0.4, [("All benchmarks use synthetic families and messages; they describe the model, not observed patients. Cascade yields are projections. "
                                    "Every number, with its file, is on the Evidence page of the live site.", {"size": 8, "color": MUTED, "italic": True})])

    # 8. Data sources and legal right
    s = S[7]
    table(s, 0.4, 1.6, 9.2, [2.0, 1.7, 1.6, 1.2, 2.7], [
        ["Source", "Type", "Owner", "Sensitivity", "Permission / right to use"],
        ["MedlinePlus Genetics", "Patient information, quoted word for word", "US National Library of Medicine", "Public", "Public domain; credited on screen as the licence page requires"],
        ["Published studies (PMIDs in the parameter register)", "Carrier rates, consanguinity, study yields", "The authors and journals", "Public", "Facts cited from the literature, each with its PMID"],
        ["Synthetic families, messages and test sets", "Simulated pedigrees; written test messages", "The team", "None", "Generated for this project; no real person"],
        ["Fictional demo families and FHIR sample", "Demo data in the live app", "The team", "None", "Invented; labelled fictional on every screen"],
        ["Reported UAE programme figures", "News reports and one PubMed record", "The publishers", "Public", "Cited with links; no figure taken from the NEJM letter, whose text was not read"],
        ["Azure AI Speech neural voices", "Read-aloud clips; film narration", "Microsoft (service)", "None", "Generated with the team's own subscription; labelled synthetic"],
        ["Language models benchmarked (Jais 3, BiMediX2, Med42, gpt-oss-120b)", "Evaluated, not shipped", "Their publishers", "None", "Used under their published licences; only synthetic prompts sent"],
    ], size=7.8, row_h=0.37)
    card(s, 0.4, 4.7, 9.2, 0.62, None, [("No personal data is used anywhere: no patient, no real family, no real message. An imported result would keep the person's sex and the "
                                         "finding, and not the name, identifier or date of birth.", {"size": 9.5, "bold": True, "color": TEAL})], fill=SOFT)

    # 9. Risks and safeguards
    s = S[8]
    risks = [("Privacy", "Relatives see only what the index person chose to disclose, through an unguessable link; anonymous invitations name no person and no condition. 0 disclosures in 10,000 unauthorised requests."),
             ("Security", "Role checks on every request; hash-chained audit log; demo shortcuts answer 404 outside demo mode. Still needed for a pilot: managed database, UAE PASS, penetration test."),
             ("Bias and equity", "Population inputs are UAE-national studies with sample sizes shown; tribe structure tested in a sensitivity analysis; Arabic and English throughout; read aloud for low literacy."),
             ("Explainability", "Every value is labelled recorded, calculated, quoted or approved wording. The counsellor sees the engine's working and every source with its PMID."),
             ("Misuse", "No compatibility matching, no registry; success never counts marriages. Questions about marriage, pregnancy or religion are not answered and go to a counsellor."),
             ("Human oversight", "The family decides who is told. A genetic counsellor approves every invitation and confirms every tree a model drafts. Every message is read by a person."),
             ("Failure modes", "Results that cannot all be true show no number and go to a counsellor. Conditions without UAE data are refused, not estimated. Unsafe imported records are refused with the reason."),
             ("AI-written advice", "No language model writes to a family: an output gate re-derives every message from approved content and blocks anything else. Shown live in the cascade.")]
    for i, (a, b) in enumerate(risks):
        card(s, 0.4 + (i % 4) * 2.33, 1.55 + (i // 4) * 1.72, 2.2, 1.62, a, [(b, {"size": 8.8})], fill=SAND if i // 4 == 0 else WHITE, size=8.8, title_size=9.8)
    text(s, 0.4, 5.02, 9.2, 0.38, [("24 hazards with controls and tests are in the hazard log; risk class High under the DoH AI Risk Management Protocol. Not yet done: native "
                                    "Arabic clinical review, genetic-counsellor review of templates, a listening check of the audio.", {"size": 8, "color": MUTED, "italic": True})])

    # 10. Hardware
    card(S[9], 0.4, 1.6, 9.2, 1.3, "Not applicable: Silsila is software only", [
        ("No wearable, sensor or connected device. The service runs on ordinary cloud processors (today: 2 vCPU and 4 GiB for the API, 0.5 vCPU and 1 GiB for the web app, "
         "Azure Container Apps, UAE North) and needs no GPU at run time. Families and relatives use any phone or computer with a browser. Optional voice intake "
         "runs speech recognition on a clinic workstation so that audio does not leave the room.", {"size": 10.5})], fill=SAND, size=10.5)

    # 11. Login
    s = S[10]
    card(s, 0.4, 1.7, 9.2, 0.95, "Continue as Guest: no login is needed", [
        (LIVE, {"size": 11, "bold": True, "color": INK, "space": 4}),
        (f"Film (5 min): {FILM}   ·   Code and submission pack: {REPO}", {"size": 9.5, "color": INK, "space": 4}),
        ("Press \"Continue as guest\" on the home page: one-click roles with every feature. All families are fictional.", {"size": 10})], fill=SOFT)
    for i, (a, b) in enumerate([("Watch a cascade", "One newborn's result travelling through a family in 13 live steps. Start here."),
                                ("Family Twin", "A simulated clan of 61 people; record a result and watch every chance recalculated."),
                                ("Mariam (family)", "Give permission, choose whom to tell, send an anonymous invitation."),
                                ("Genetic counsellor", "Queue, approvals, FHIR import, voice intake, Outcomes, audit log."),
                                ("A relative's link", "The invitation as a relative sees it: Listen, common questions, check, booking."),
                                ("Ask about Silsila", "Bottom corner of every public page: answers about the tool, without AI.")]):
        card(s, 0.4 + (i % 3) * 3.1, 2.8 + (i // 3) * 1.12, 3.0, 1.02, a, [(b, {"size": 9})], fill=WHITE, size=9, title_size=10)
    text(s, 0.4, 5.05, 9.2, 0.35, [("Arabic or English from the header. \"Reset the demo data\" is in the counsellor's audit tab. Credentials, if preferred: username mariam, reem or "
                                    "counsellor; password Silsila-Judge-2026 (same for all three).", {"size": 9, "color": INK, "bold": True})])

    # 12. Path to pilot and scale
    s = S[11]
    cols = [("Stakeholders", "Buyer: the DoH screening programmes that already produce index results. Operator: the genetics service they refer to. Payer for confirmatory "
                             "tests: the existing benefit. Counsellor time is the scarce resource Silsila is priced against."),
            ("Integration", "Index results in as FHIR R4B, cases out the same way; a pilot maps to the exchange's real profile (none seen yet). Entry points and UAE PASS sign-in "
                            "come with the pilot. Hosting stays in the UAE."),
            ("Regulatory", "Decision support with a counsellor approving every message. DoH conformity assessment before patient use (high-risk class); medical-device "
                           "classification to be confirmed with DoH. Clause map and hazard log are in the repository."),
            ("Timeline (assumption)", "Months 1-2: shadow mode, counsellors work as usual while Silsila computes alongside; nothing is sent. Months 3-6: assisted mode, "
                                      "invitations go out with counsellor approval. Monthly report to DoH."),
            ("Sustainability", "Proposed licence per index family started, all relatives included; a fixed-fee pilot first. Hosting about USD 200 a month at list prices; cost grows "
                               "with families, not with model tokens. No price is validated yet.")]
    for i, (a, b) in enumerate(cols):
        card(s, 0.4 + i * 1.86, 1.55, 1.76, 2.75, a, [(b, {"size": 8.8})], fill=SAND if i % 2 == 0 else WHITE, size=8.8, title_size=9.6)
    card(s, 0.4, 4.42, 9.2, 0.9, "Scale, as a projection and not an observed outcome", [
        ("Newborn screening identified more than 100 babies in the past year and premarital screening 565 incompatible couples among 11,748 tested (reported figures). "
         "At 100 index newborns a year and 5 tests per family: about 25 at-risk couples found for CAH in Silsila's order against 17 unranked. No programme has asked for "
         "cascade testing; it is the step these programmes do not yet describe.", {"size": 8.8})], fill=SOFT, size=8.8, title_size=9.5)

    # 13. IP and third-party materials
    s = S[12]
    card(s, 0.4, 1.6, 4.5, 1.55, "Owned by the entrant", [
        ("All Silsila source code, the exact engine, the approved templates, the benchmarks and their results, the guide's answers, the demo families and the "
         "documents. Written for this challenge: the repository's history starts on 6 November 2026. No pre-existing product or prior codebase was brought in.", {"size": 9})], fill=SAND, size=9)
    card(s, 5.1, 1.6, 4.5, 1.55, "Restrictions", [
        ("None on Silsila's own work. Arabic text is machine translation and must be reviewed before use with patients. The organisers' template and logos are "
         "theirs and are used only for this submission. The code is released under the Apache-2.0 licence.", {"size": 9})], fill=WHITE, size=9)
    table(s, 0.4, 3.3, 9.2, [2.6, 3.4, 3.2], [
        ["Third-party material", "Use", "Licence or terms"],
        ["MedlinePlus Genetics (US National Library of Medicine)", "Verbatim patient information", "Public domain; credit line shown"],
        ["FastAPI, NumPy, scikit-learn, fhir.resources, Next.js, React, three.js, Tailwind", "Application libraries", "Open-source licences (MIT, BSD, Apache-2.0)"],
        ["pgmpy; axe-core; Playwright", "Independent cross-check; accessibility audit; film recording", "Open source; used for testing only"],
        ["IBM Plex Sans and IBM Plex Sans Arabic", "Typefaces", "SIL Open Font License"],
        ["Jais-ASR and Jais 3 (Inception, MBZUAI); other benchmarked models", "Voice-intake draft; evaluation only", "Their published licences (Jais 3 7B: Apache-2.0)"],
        ["Microsoft Azure (Container Apps, AI Speech, Translator)", "Hosting; synthetic voice; translation check", "The team's own subscription"],
    ], size=7.8, row_h=0.28)

    # 14. Conflict of interest
    card(S[13], 0.4, 1.7, 9.2, 1.5, "Declaration", [
        ("None. No member of the team has a conflict of interest to declare.", {"size": 13, "bold": True, "color": INK, "space": 8}),
        ("The entrant is not employed by or contracted to the Department of Health - Abu Dhabi, Future Health, Microsoft, Inception, MBZUAI or Hack2skill; has no family or "
         "close personal relationship with a judge, organiser or collaborator staff member; has no financial interest in an organisation running or judging the challenge; "
         "and has had no access to non-public information about the challenge or its evaluation.", {"size": 10})], fill=SAND, size=10)
    text(S[13], 0.4, 3.4, 9.2, 0.6, [("Silsila benchmarks the co-creators' publicly released models (Jais 3, Jais-ASR) and runs on Microsoft Azure as an ordinary customer. "
                                      "Neither is a relationship with the organisers.", {"size": 9.5, "color": MUTED})])

    # 15. Additional slide: what only Silsila does, and its limits
    s = S[14]
    extra = next(sh for sh in s.shapes if sh.has_text_frame)
    extra.top = Inches(0.94)
    extra.text_frame.paragraphs[0].runs[0].text = "Additional Slide: what only Silsila does, and what is not yet shown"
    for i, (n, lab, src) in enumerate([("30,000 / 30,000", "carrier probabilities match an independent exact solver, across cousin loops", "Benchmark B1"),
                                       ("1.58×", "as many at-risk couples per test as an unranked cascade (95% CI 1.43-1.77), simulated UAE clans", "Benchmark B4"),
                                       ("59.4%", "of Jais 3 7B's free-text risk numbers were exact; so no model computes risk here", "Silsila-Bench, pre-registered"),
                                       ("0 / 10,000", "disclosures in unauthorised requests; every action on a hash-chained audit log", "Privacy run")]):
        stat(s, 0.4 + i * 2.33, 1.5, 2.2, 1.5, n, lab, src)
    card(s, 0.4, 3.15, 4.5, 2.15, "Also live", [
        ("Emirati speech to a draft family tree, confirmed by a counsellor", {"bullet": True, "size": 9}),
        ("Read aloud of the exact approved text, Arabic and English, tied to the text by hash", {"bullet": True, "size": 9}),
        ("Reproductive options quoted word for word, described and never recommended", {"bullet": True, "size": 9}),
        ("A guide that answers questions about the tool with fixed answers and live lookups, no AI", {"bullet": True, "size": 9}),
        ("A five-minute film, recorded from the live site, that walks through all six criteria", {"bullet": True, "size": 9})], fill=SAND, size=9)
    card(s, 5.1, 3.15, 4.5, 2.15, "Not yet shown, said plainly", [
        ("No patient has used it. All evidence is on synthetic families and messages.", {"bullet": True, "size": 9}),
        ("Three genes with published UAE data; other conditions are refused.", {"bullet": True, "size": 9}),
        ("Arabic is machine translation; no native clinical review, no listening check of the audio.", {"bullet": True, "size": 9}),
        ("Quoted source text reads at a college level (grade 13.4); Silsila's own wording at grade 6.9.", {"bullet": True, "size": 9}),
        ("No programme has asked for cascade testing; no price is validated.", {"bullet": True, "size": 9})], fill=WHITE, size=9)

    prs.save(dst)
    print("saved", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
