# Per-player eye state from cv_referee
string player_id      # empty if the face is not yet identified
uint32 face_index     # stable index of the detected face in frame
bool eyes_open
float32 confidence
