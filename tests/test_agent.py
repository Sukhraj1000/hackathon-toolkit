import pytest
from canton8_agent.mock_ledger import MockLedger
from canton8_agent.agent import Agent
from canton8_agent.approval_service import ApprovalService


def test_select_offer_filters_by_vendor_and_limits():
    mandate = {'totalLimit': 100, 'perPurchaseLimit': 25, 'approvedSellers': ['VendorA']}
    offers = {
        'o1': {'vendor': 'VendorA', 'price': 10},
        'o2': {'vendor': 'VendorB', 'price': 5},
        'o3': {'vendor': 'VendorA', 'price': 30},
    }
    ledger = MockLedger(mandate, offers, [100], [])
    agent = Agent('AgentX', ledger)

    chosen = agent.select_offer(offers, mandate)
    assert chosen is not None
    cid, offer = chosen
    assert cid == 'o1'
    assert offer['price'] == 10


def test_submit_buy_success():
    mandate = {'totalLimit': 100, 'perPurchaseLimit': 50, 'approvedSellers': ['VendorA']}
    offers = {'o1': {'vendor': 'VendorA', 'price': 20}}
    ledger = MockLedger(mandate, offers, [50], [])
    agent = Agent('AgentX', ledger)

    status, resp = agent.submit_buy('o1', offers['o1'])
    assert status == 'success'
    assert resp['status'] == 'ok'
    assert 'transactionId' in resp


def test_submit_buy_insufficient_funds_retryable():
    mandate = {'totalLimit': 100, 'perPurchaseLimit': 100, 'approvedSellers': ['VendorA']}
    offers = {'o1': {'vendor': 'VendorA', 'price': 60}}
    # holdings too small initially
    ledger = MockLedger(mandate, offers, [{'id':'u1','amount':30}], [])
    agent = Agent('AgentX', ledger)

    status, resp = agent.submit_buy('o1', offers['o1'], max_retries=1, backoff_seconds=0)
    # Should be rejected due to insufficient funds
    assert status == 'rejected'
    assert resp['reason'] == 'InsufficientFunds'


def test_utxo_spent_retryable():
    mandate = {'totalLimit': 100, 'perPurchaseLimit': 100, 'approvedSellers': ['VendorA']}
    offers = {'o1': {'vendor': 'VendorA', 'price': 40}}
    ledger = MockLedger(mandate, offers, [{'id':'u1','amount':50}], [])
    agent = Agent('AgentX', ledger)

    # Simulate UTXOSpent via ledger's next_failures
    ledger.next_failures = ['UTXOSpent']
    status, resp = agent.submit_buy('o1', offers['o1'], max_retries=0, backoff_seconds=0)
    assert status == 'rejected'
    assert resp['reason'] == 'UTXOSpent'


def test_transient_error_retry_then_success():
    mandate = {'totalLimit': 500, 'perPurchaseLimit': 300, 'approvedSellers': ['VendorA']}
    offers = {'o1': {'vendor': 'VendorA', 'price': 100}}
    ledger = MockLedger(mandate, offers, [{'id':'u1','amount':200}], [])
    # configure ledger to fail first with TransientError then succeed
    ledger.next_failures = ['TransientError']
    agent = Agent('AgentX', ledger)

    status, resp = agent.submit_buy('o1', offers['o1'], max_retries=2, backoff_seconds=0)
    assert status == 'success'
    assert resp['status'] == 'ok'


def test_schedule_external_spend_marks_utxo_spent():
    mandate = {'totalLimit': 100, 'perPurchaseLimit': 100, 'approvedSellers': ['VendorA']}
    offers = {}
    ledger = MockLedger(mandate, offers, [{'id':'u1','amount':50}], [])
    ledger.schedule_external_spend('u1', delay_seconds=0.01)
    import time
    time.sleep(0.05)
    assert any(u['id'] == 'u1' and u.get('spent') for u in ledger.holdings)
    ledger.stop()


def test_external_spend_causes_retry_then_success():
    """Schedule an external spend of the UTXO the agent will pick first, ensure agent retries and succeeds using another UTXO."""
    mandate = {'totalLimit': 500, 'perPurchaseLimit': 300, 'approvedSellers': ['VendorA']}
    offers = {'o1': {'vendor': 'VendorA', 'price': 80}}
    # two utxos: agent will pick the smaller u1 first
    holdings = [{'id': 'u1', 'amount': 80}, {'id': 'u2', 'amount': 200}]
    ledger = MockLedger(mandate, offers, holdings, [])
    agent = Agent('AgentX', ledger)

    # schedule external spend on u1 to occur shortly
    ledger.schedule_external_spend('u1', delay_seconds=0.005)

    # agent should attempt submit, receive UTXOSpent, retry and then succeed using u2
    status, resp = agent.submit_buy('o1', offers['o1'], max_retries=3, backoff_seconds=0.01)
    assert status == 'success'
    assert resp['status'] == 'ok'
    ledger.stop()


def test_propose_and_submit_approved():
    mandate = {'totalLimit': 500, 'perPurchaseLimit': 300, 'approvedSellers': ['VendorA']}
    offers = {'o1': {'vendor': 'VendorA', 'price': 200}}
    ledger = MockLedger(mandate, offers, [500], [])
    agent = Agent('AgentX', ledger, owner_policy={'approval_threshold': 100})
    approval = ApprovalService(auto_approve=True)
    agent.set_approval_service(approval)

    status, resp = agent.propose_and_submit('o1', offers['o1'])
    assert status == 'success'
    assert resp['status'] == 'ok'


def test_propose_and_submit_rejected_by_owner():
    mandate = {'totalLimit': 500, 'perPurchaseLimit': 300, 'approvedSellers': ['VendorA']}
    offers = {'o1': {'vendor': 'VendorA', 'price': 200}}
    ledger = MockLedger(mandate, offers, [500], [])
    agent = Agent('AgentX', ledger, owner_policy={'approval_threshold': 100})
    approval = ApprovalService(auto_approve=False, reason_on_reject='Nope')
    agent.set_approval_service(approval)

    status, resp = agent.propose_and_submit('o1', offers['o1'])
    assert status == 'rejected'
    assert resp['reason'] == 'OwnerRejected'
