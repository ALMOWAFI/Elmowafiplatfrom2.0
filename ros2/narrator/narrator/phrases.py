"""Bilingual narration templates — pure functions, unit-tested.

render() turns a game event into the line the referee says out loud.
Private events (detective answers, role cards) return '' — they must
never reach the speaker.
"""

from __future__ import annotations

ROLE_AR = {'mafia': 'مافيا', 'doctor': 'الدكتور',
           'detective': 'الشايب', 'civilian': 'مواطن'}
ROLE_EN = {'mafia': 'Mafia', 'doctor': 'the Doctor',
           'detective': 'the Detective', 'civilian': 'a Civilian'}

# events that are private or purely mechanical -> never spoken
SILENT = {'roles_assigned', 'detective_answer', 'mafia_chose',
          'doctor_done', 'discussion_begins'}


def render(event: str, data: dict, names: dict[str, str],
           lang: str = 'ar') -> str:
    if event in SILENT:
        return ''
    n = lambda pid: names.get(pid, str(pid))  # noqa: E731

    if lang == 'ar':
        if event == 'night_begins':
            return (f"الليلة رقم {data.get('round', '؟')}. الكل يغمض عينيه. "
                    "المافيا تصحى وتختار ضحيتها.")
        if event == 'day_begins':
            if data.get('death'):
                return (f"صباح الخير يا عائلة. للأسف {n(data['death'])} "
                        "قُتل الليلة. البقاء لله.")
            if data.get('saved'):
                return "صباح الخير! المافيا هاجمت، لكن الدكتور أنقذ الضحية في اللحظة الأخيرة."
            return "صباح الخير! ليلة هادية — لا ضحايا."
        if event == 'vote_begins':
            return "وقت التصويت. كل واحد يختار المتهم من موبايله."
        if event == 'vote_tied':
            if data.get('revote'):
                return "تعادل في الأصوات! إعادة التصويت بين المتعادلين فقط."
            return "تعادل مرة تانية — لا إعدام اليوم."
        if event == 'player_eliminated':
            return (f"قررت العائلة إعدام {n(data['player'])}. "
                    f"كان {ROLE_AR.get(data.get('role', ''), data.get('role', ''))}!")
        if event == 'no_elimination':
            return "لا إعدام اليوم. الليل قادم."
        if event == 'game_over':
            if data.get('winner') == 'mafia':
                return "انتهت اللعبة! المافيا سيطرت على المدينة. حظ أوفر يا مواطنين!"
            return "انتهت اللعبة! المواطنون كشفوا كل المافيا. العدالة انتصرت!"
        if event == 'peek_callout':
            return f"يا {n(data['player'])}! عينك مفتوحة وانت المفروض نايم! عيب عليك!"
        return ''

    # English
    if event == 'night_begins':
        return (f"Night {data.get('round', '?')}. Everyone close your eyes. "
                "Mafia, wake up and choose your victim.")
    if event == 'day_begins':
        if data.get('death'):
            return (f"Good morning, family. Sadly, {n(data['death'])} "
                    "was killed last night.")
        if data.get('saved'):
            return "Good morning! The mafia struck, but the doctor saved the victim!"
        return "Good morning! A quiet night — nobody died."
    if event == 'vote_begins':
        return "Time to vote. Pick your suspect on your phone."
    if event == 'vote_tied':
        if data.get('revote'):
            return "It's a tie! Revote between the tied players only."
        return "Tied again — nobody is eliminated today."
    if event == 'player_eliminated':
        return (f"The family has decided: {n(data['player'])} is out. "
                f"They were {ROLE_EN.get(data.get('role', ''), data.get('role', ''))}!")
    if event == 'no_elimination':
        return "No elimination today. Night is coming."
    if event == 'game_over':
        if data.get('winner') == 'mafia':
            return "Game over! The mafia has taken the town. Better luck next time!"
        return "Game over! The civilians found every last mafioso. Justice wins!"
    if event == 'peek_callout':
        return f"{n(data['player'])}! Your eyes are open and you're supposed to be asleep! Busted!"
    return ''
