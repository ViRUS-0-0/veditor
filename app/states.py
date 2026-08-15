class InvalidTransitionError(Exception):
    def __init__(self, current_state: str, new_state: str):
        self.current_state = current_state
        self.new_state = new_state
        super().__init__(f"Invalid transition from {current_state} to {new_state}")

TRANSITIONS = {
    "waiting_for_files": ["pending_approval"],
    "pending_approval": ["cutting", "rejected"],
    "cutting": ["generating_previews", "broken"],
    "generating_previews": ["preview", "broken"],
    "preview": ["transcoding", "needs_work", "rejected"],
    "transcoding": ["uploading", "broken"],
    "uploading": ["done", "broken"],
    "needs_work": ["cutting"],
    "done": [],
    "rejected": [],
    "broken": []
}

def advance(talk, new_state: str):
    current_state = talk.status
    
    if current_state not in TRANSITIONS:
        raise InvalidTransitionError(current_state, new_state)
    
    if new_state not in TRANSITIONS[current_state]:
        raise InvalidTransitionError(current_state, new_state)
    
    talk.status = new_state
    return talk
