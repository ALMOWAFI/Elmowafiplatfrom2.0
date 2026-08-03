# Structured game event for the narrator and web bridge.
# data_json carries the event payload; private events (e.g. the detective's
# answer) must only be relayed to the player named in recipient_id.
builtin_interfaces/Time stamp
string type
string data_json
string recipient_id   # empty = broadcast
