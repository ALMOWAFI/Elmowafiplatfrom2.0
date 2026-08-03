# Per-player hand-raise state from cv_referee (day-vote signal).
# Role-blind and vote-blind by design, same as EyeState: this only
# reports a geometric fact ("this seat's hand is up"), never who they're
# voting for. How a raised hand becomes an actual vote/accusation is a
# game-flow decision NOT yet made (see cv_referee/node.py docstring) —
# phones remain the real vote mechanism until that's decided.
string player_id      # empty if the person is not yet seat-mapped
uint32 pose_index      # stable index of the detected pose in frame
bool hand_raised
float32 confidence
