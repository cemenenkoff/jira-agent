from __future__ import annotations

from jira_agent.policies.loader import PolicyCorpus


def test_loads_all_ten_policies(corpus: PolicyCorpus) -> None:
    assert len(corpus) == 10
    ids = {p.id for p in corpus.policies}
    assert ids == {f"POL-{i:02d}" for i in range(1, 11)}


def test_every_policy_has_sections(corpus: PolicyCorpus) -> None:
    for policy in corpus.policies:
        assert policy.sections, f"{policy.id} has no sections"
        assert policy.title and policy.owner and policy.effective


def test_sections_are_numbered_under_their_policy(corpus: PolicyCorpus) -> None:
    # POL-01 sections start "1.", POL-10 sections start "10.", etc.
    for policy in corpus.policies:
        prefix = str(int(policy.id.split("-")[1]))
        for section in policy.sections:
            assert section.section.startswith(f"{prefix}."), (
                f"{policy.id} section {section.section} has unexpected prefix"
            )


def test_section_lookup(corpus: PolicyCorpus) -> None:
    section = corpus.get_section("POL-01", "1.4")
    assert section is not None
    assert "5 consecutive" in section.text
    assert str(section.citation) == "POL-01 §1.4"
    assert corpus.get_section("POL-01", "9.9") is None
