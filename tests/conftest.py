from __future__ import annotations

import pytest

from jira_agent.config import get_settings
from jira_agent.eval.harness import load_eval_tickets
from jira_agent.models import EvalTicket
from jira_agent.policies.loader import PolicyCorpus, load_policies


@pytest.fixture(scope="session")
def corpus() -> PolicyCorpus:
    return load_policies(get_settings().policies_dir)


@pytest.fixture(scope="session")
def eval_tickets() -> list[EvalTicket]:
    return load_eval_tickets(get_settings().tickets_file)
