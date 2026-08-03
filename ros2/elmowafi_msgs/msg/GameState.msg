# Current phase of the mafia game, published latched by game_master
string phase          # lobby | night_mafia | night_doctor | night_detective |
                      # day_announce | day_discussion | day_vote | game_over
uint8 round
string[] alive_ids
string winner         # empty until game_over: "mafia" | "civilians"
