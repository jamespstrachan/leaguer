from z3 import Int, Solver, Or, And

teams = (
    'Cambridge',
    'Huntingdon',
    'Royston',
    'Cocks & Hens',
)

class Division():

    def __init__(self, name, teams):
        self.name = name
        self.teams = teams

divisions = []
for div_number in range(1,5):
    divisions.append(Division(f'Mens {div_number}', f'{team} {div_number}') for team in teams)

#teams = [str(i) for i in range(1,17)]
weeks = range(1, len(teams)+1)

def make_fixtures(teams):
    return dict(((home_team, week), Int(f'{home_team}_week{week}_opponent'))
                for i, home_team in enumerate(teams)
                for week in weeks)

fixtures = make_fixtures(teams)

def extract_all_opponents(fixtures_dict, home_team):
    for week in weeks:
        yield fixtures_dict[home_team, week]

def extract_all_away_teams(fixtures_dict, week):
    for home_team in teams:
        yield fixtures_dict[home_team, week]


match_happens = []
for home_team in teams:
    opponents = list(extract_all_opponents(fixtures, home_team))
    for i, away_team in enumerate(teams):
        if away_team == home_team:
            continue
        match_happens.append(Or(*(opponent == i for opponent in opponents)))

not_playing_twice = []
for week in weeks:
    away_teams = list(extract_all_away_teams(fixtures, week))
    for i, away_team1 in enumerate(away_teams):
        for away_team2 in away_teams[i+1:]:
            not_playing_twice.append(away_team1 != away_team2)

is_valid_opponent = And(*(And(0 <= f, f < len(teams)) for f in fixtures.values()))
not_playing_twice = And(*not_playing_twice)
all_teams_play = And(*match_happens)

s = Solver()
s.add(is_valid_opponent, all_teams_play, not_playing_twice)
s.check()
m = s.model()
for team in teams:
    print(f"{team:>20} : ", end='')
    print('\t '.join(str(m[fixtures[team,week]]) for week in weeks))