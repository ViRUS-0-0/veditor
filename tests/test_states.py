import pytest
from app.states import advance, TRANSITIONS, InvalidTransitionError

class DummyTalk:
    def __init__(self, status):
        self.status = status

def test_advance_legal_transitions():
    for current_state, next_states in TRANSITIONS.items():
        for next_state in next_states:
            talk = DummyTalk(current_state)
            advanced_talk = advance(talk, next_state)
            assert advanced_talk.status == next_state
            assert talk.status == next_state

def test_advance_illegal_transitions():
    # Test at least one illegal transition per state
    illegal_moves = {
        "waiting_for_files": "cutting",
        "pending_approval": "generating_previews",
        "cutting": "needs_work",
        "generating_previews": "transcoding",
        "preview": "done",
        "transcoding": "done",
        "uploading": "rejected",
        "needs_work": "preview",
        "done": "waiting_for_files",
        "rejected": "waiting_for_files",
        "broken": "waiting_for_files"
    }
    
    for current_state, invalid_next in illegal_moves.items():
        talk = DummyTalk(current_state)
        with pytest.raises(InvalidTransitionError) as exc_info:
            advance(talk, invalid_next)
        
        assert exc_info.value.current_state == current_state
        assert exc_info.value.new_state == invalid_next
        assert talk.status == current_state  # State should not mutate

def test_explicit_paths_per_acceptance_criteria():
    # pending_approval -> rejected
    talk = DummyTalk("pending_approval")
    advance(talk, "rejected")
    assert talk.status == "rejected"
    
    # preview -> needs_work -> cutting
    talk2 = DummyTalk("preview")
    advance(talk2, "needs_work")
    assert talk2.status == "needs_work"
    
    advance(talk2, "cutting")
    assert talk2.status == "cutting"
