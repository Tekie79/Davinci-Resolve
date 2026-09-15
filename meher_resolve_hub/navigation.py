"""Timeline navigation with explicit return-position support."""

from dataclasses import dataclass

from .models.operation import OperationResult


@dataclass
class NavigationState:
    timeline_id: str = ""
    previous_timecode: str = ""
    selected_key: str = ""
    result_index: int = -1


class NavigationEngine:
    def __init__(self, context_service):
        self.context_service = context_service
        self.state = NavigationState()

    def set_playhead(self, timecode, remember=True):
        context = self.context_service.refresh_context()
        if not context.timeline:
            return OperationResult(False, errors=["Open a timeline first."])
        if remember:
            self.state.timeline_id = context.timeline_id
            self.state.previous_timecode = context.current_timecode
        try:
            success = bool(context.timeline.SetCurrentTimecode(str(timecode)))
            actual = str(context.timeline.GetCurrentTimecode() or "")
        except Exception as exc:
            return OperationResult(False, failed=1, errors=[str(exc)])
        if not success or actual != str(timecode):
            return OperationResult(False, failed=1, errors=["Resolve did not move to %s." % timecode])
        return OperationResult(True, changed=1)

    def return_to_previous_position(self):
        context = self.context_service.refresh_context()
        if not self.state.previous_timecode:
            return OperationResult(False, errors=["No previous playhead position is stored."])
        if self.state.timeline_id and context.timeline_id != self.state.timeline_id:
            return OperationResult(False, errors=["The stored position belongs to another timeline."])
        value = self.state.previous_timecode
        self.state.previous_timecode = ""
        return self.set_playhead(value, remember=False)

    def go_to(self, timecode, selected_key="", result_index=-1):
        self.state.selected_key = selected_key
        self.state.result_index = result_index
        return self.set_playhead(timecode, remember=True)

    @staticmethod
    def adjacent(items, current_index, direction):
        if not items:
            return None, -1
        index = max(0, min(len(items) - 1, int(current_index) + int(direction)))
        return items[index], index

