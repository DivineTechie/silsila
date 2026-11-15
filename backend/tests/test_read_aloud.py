"""Read aloud: a synthetic voice may only ever read approved text, exactly as written."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from silsila.content import AUDIO, Message, registry, sha256, teachback_text


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SILSILA_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("SILSILA_DEMO_FAMILY_PASSWORD", "test-family-pw")
    monkeypatch.setenv("SILSILA_DEMO_COUNSELLOR_PASSWORD", "test-counsellor-pw")
    monkeypatch.setenv("SILSILA_DEMO", "1")
    from silsila.api import app as app_mod, seed, store as store_mod
    importlib.reload(app_mod)
    s = store_mod.Store()
    seed.seed(s)
    app_mod._store = s
    return TestClient(app_mod.app)


def test_every_clip_reads_text_that_is_approved_today():
    reg = registry()
    wanted = {(w["lang"], sha256(w["text"])) for w in reg.read_aloud_texts()}
    have = {(lang, h) for lang in ("en", "ar") for h in reg.audio["clips"][lang]}
    assert have == wanted  # nothing missing, and no clip of a wording that is no longer approved
    for lang in ("en", "ar"):
        for h, clip in reg.audio["clips"][lang].items():
            data = (AUDIO / clip["file"]).read_bytes()
            assert clip["file"] == f"{lang}/{h[:16]}.mp3" and len(data) > 2000
            assert data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)  # an MP3 file
    assert reg.audio["meta"]["synthetic"] is True and "Azure" in reg.audio["meta"]["provider"]


def test_texts_with_names_or_numbers_are_never_pre_recorded():
    ids = {w["id"] for w in registry().read_aloud_texts() if w["kind"] == "template"}
    assert "invite.anonymous" in ids and "reply.decision_request" in ids
    assert not ids & {"invite.with_sender", "invite.with_condition", "result.carrier_probability", "result.couple_child_risk"}


def test_a_clip_is_attached_only_to_the_exact_text_it_reads():
    reg = registry()
    msg = reg.gate(reg.template(Message("en"), "invite.anonymous"))
    digest = msg.digest
    out = reg.with_audio(msg.parts, "en")
    assert out[0]["audio"]["synthetic"] is True and out[0]["audio"]["lang"] == "en"
    assert "audio" not in msg.parts[0] and msg.digest == digest  # the gated message itself is untouched
    text = msg.parts[0]["text"]
    assert reg.audio_for("en", text) is not None
    for changed in (text + " ", text.replace("Carrier testing", "Testing"), "It would be better not to marry."):
        assert reg.audio_for("en", changed) is None  # altered or unapproved text has no voice
    assert reg.audio_for("ar", text) is None  # and an English text has no Arabic clip


def test_relative_page_carries_clips_in_both_languages_and_serves_them(client):
    code = client.post("/api/demo/relative").json()["code"]
    for lang in ("en", "ar"):
        view = client.get(f"/api/r/{code}?lang={lang}").json()
        parts = view["message"] + view["information"] + view["consent_note"]
        assert all(p["audio"]["lang"] == lang for p in parts)  # Arabic view: Arabic wording and translation
        for q in view["teachback"]:
            assert set(q["audio"]) == {"en", "ar"}
        topic = client.get(f"/api/r/{code}/topics/faq.reproductive_options?lang={lang}").json()
        assert all("audio" in p for p in topic["parts"])
        r = client.get(parts[0]["audio"]["url"])
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 2000
    reg = registry()
    q = reg.teachback[0]
    assert reg.audio_for("ar", teachback_text(q, "ar"))["url"] == view["teachback"][0]["audio"]["ar"]["url"]
    # a relative's question gets a reply that can be read aloud; the same reply to a signed-in family does not change
    reply = client.post("/api/messages", json={"text": "What options do couples have?", "lang": "en", "invite_code": code}).json()
    assert any("audio" in p for p in reply["reply"])


def test_an_invitation_that_names_the_sender_has_no_clip_for_that_sentence(client):
    fam = {"Authorization": f"Bearer {client.post('/api/demo/login', json={'persona': 'mariam'}).json()['token']}"}
    cou = {"Authorization": f"Bearer {client.post('/api/demo/login', json={'persona': 'counsellor'}).json()['token']}"}
    client.post("/api/cases/case_cah_demo/consents", json={"scope": "invite", "granted": True}, headers=fam)
    inv = client.post("/api/cases/case_cah_demo/invitations", headers=fam, json={
        "person_id": "noura", "channel": "self_share_letter", "disclose_sender": True, "sender_name": "Mariam"}).json()
    code = client.post(f"/api/invitations/{inv['id']}/approve", headers=cou).json()["code"]
    view = client.get(f"/api/r/{code}").json()
    assert view["message"][0]["id"] == "invite.with_sender" and "audio" not in view["message"][0]


def test_only_clip_files_are_served(client):
    for bad in ("/api/audio/en/manifest.json", "/api/audio/en/0000000000000000.mp3", "/api/audio/fr/0000000000000000.mp3",
                "/api/audio/en/..%2F..%2Ftemplates.yaml", "/api/audio/en/ABCDEF0123456789.mp3"):
        assert client.get(bad).status_code in (404, 422), bad
