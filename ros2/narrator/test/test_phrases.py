from narrator.phrases import render

NAMES = {'p1': 'Ali', 'p2': 'Marwa'}


def test_private_events_are_silent():
    assert render('detective_answer', {'target': 'p1', 'is_mafia': True}, NAMES) == ''
    assert render('roles_assigned', {'roles': {}}, NAMES) == ''


def test_death_announcement_uses_name_ar_and_en():
    ar = render('day_begins', {'death': 'p2', 'saved': False}, NAMES, 'ar')
    en = render('day_begins', {'death': 'p2', 'saved': False}, NAMES, 'en')
    assert 'Marwa' in ar and 'Marwa' in en


def test_saved_night():
    ar = render('day_begins', {'death': None, 'saved': True}, NAMES, 'ar')
    assert 'الدكتور' in ar
    en = render('day_begins', {'death': None, 'saved': True}, NAMES, 'en')
    assert 'doctor' in en.lower()


def test_peek_callout_names_the_cheater():
    ar = render('peek_callout', {'player': 'p1', 'phase': 'night_mafia'}, NAMES, 'ar')
    assert 'Ali' in ar
    en = render('peek_callout', {'player': 'p1', 'phase': 'night_mafia'}, NAMES, 'en')
    assert 'Ali' in en and 'Busted' in en


def test_elimination_reveals_role():
    ar = render('player_eliminated', {'player': 'p2', 'role': 'mafia'}, NAMES, 'ar')
    assert 'مافيا' in ar and 'Marwa' in ar


def test_game_over_both_winners():
    assert 'المافيا' in render('game_over', {'winner': 'mafia'}, NAMES, 'ar')
    assert 'Justice' in render('game_over', {'winner': 'civilians'}, NAMES, 'en')


def test_unknown_event_silent():
    assert render('some_future_event', {}, NAMES) == ''
