from z3 import Int, Solver, Or, And, Not

teams = (
    'Cambridge',
    'Huntingdon',
    'Royston',
    'Cocks & Hens',
    'Barrington',
    'Ely',
    'Stow-cum-quy',
    '10is Academy',
)

weeks = range(1, len(teams)*2)


class Division():

    def __init__(self, name, teams):
        self.name = name
        self.teams = teams


divisions = [Division(f'Mens {div_number}', [f'{team} {div_number}' for team in teams])
             for div_number in range(1, 3)]


def make_fixtures(teams):
    return dict(((home_team, week), Int(f'{home_team}_week{week}_opponent'))
                for i, home_team in enumerate(teams)
                for week in weeks)


fixtures_by_division = [(division, make_fixtures(division.teams)) for division in divisions]

#fixtures = make_fixtures(teams)

def extract_all_opponents(fixtures_dict, home_team):
    for week in weeks:
        yield fixtures_dict[home_team, week]

def extract_all_away_teams(fixtures_dict, week, teams):
    for home_team in teams:
        yield fixtures_dict[home_team, week]

def condition_match_happens(fixtures, teams):
    match_happens = []
    for home_team in teams:
        opponents = list(extract_all_opponents(fixtures, home_team))
        for i, away_team in enumerate(teams):
            if away_team == home_team:
                continue
            match_happens.append(Or(*(opponent == i for opponent in opponents)))
    return And(*match_happens)

def condition_not_playing_twice_away(fixtures, teams):
    not_playing_twice = []
    for week in weeks:
        away_teams = list(extract_all_away_teams(fixtures, week, teams))
        for i, away_team1 in enumerate(away_teams):
            for away_team2 in away_teams[i+1:]:
                not_playing_twice.append(Or(away_team1 != away_team2, away_team1 == -1))
    return And(*not_playing_twice)


def condition_not_playing_home_and_away(fixtures, teams):
    def is_playing_at_home(fixtures, week, team):
        return fixtures[team, week] != -1

    def is_playing_away(fixtures, week, team_idx):
        return Or(*(fixtures[home_team, week] == team_idx for home_team in teams))

    c = And(*(Not(And(is_playing_at_home(fixtures, week, team),
                      is_playing_away(fixtures, week, team_idx)))
                for week in weeks
                for team_idx, team in enumerate(teams)
               ))
    #print(c)
    return c


def condition_is_valid_opponent(fixtures, teams):
    return And(*(And(-1 <= f, f < len(teams)) for f in fixtures.values()))


def conditions_for_division(fixtures, teams):
    return And(
               condition_is_valid_opponent(fixtures, teams),
               condition_not_playing_twice_away(fixtures, teams),
               condition_match_happens(fixtures, teams),
               condition_not_playing_home_and_away(fixtures, teams),
               )

s = Solver()
for division, fixtures in fixtures_by_division:
    s.add(conditions_for_division(fixtures, division.teams))
    print(s.check())
    m = s.model()
    for division, fixtures in fixtures_by_division:
        print(division.name)
        for team in division.teams:
            print(f"{team:>20} : ", end='')
            print('\t '.join(str(m[fixtures[team,week]]) for week in weeks))