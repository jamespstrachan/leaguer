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

weeks = range(1, len(teams))


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

""" sketch of make triangle
for teams:
    for others[j:]:
        triangle <= (home_team, away_team), Int('week_of_{home}_plays_{away}')

for week in weeks:
    for home_team_idx, home_team:
        for away_team_idx, away_team:
            (fixtures[home_team, week] == away_team_idx) == (triangle[home_team, away_team] == week)
"""



fixtures_by_division = [(division, make_fixtures(division.teams)) for division in divisions]

def extract_all_opponents(fixtures_dict, home_team):
    for week in weeks:
        yield fixtures_dict[home_team, week]

def extract_all_away_teams(fixtures_dict, week, teams):
    for home_team in teams:
        yield fixtures_dict[home_team, week]

def condition_match_happens(fixtures, teams):
    match_happens = []
    for team1_idx, team1 in enumerate(teams):
        for team2_idx, team2 in list(enumerate(teams))[team1_idx+1:]:
            match_happens_team1_home = Or(*(fixtures[team1, week] == team2_idx for week in weeks))
            match_happens_team2_home = Or(*(fixtures[team2, week] == team1_idx for week in weeks))
            match_happens_at_all        = Or(match_happens_team1_home, match_happens_team2_home)
            match_happens_home_and_away = And(match_happens_team1_home, match_happens_team2_home)
            match_happens.append(And(match_happens_at_all, Not(match_happens_home_and_away)))
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

    return And(*(Not(And(is_playing_at_home(fixtures, week, team),
                      is_playing_away(fixtures, week, team_idx)))
                for week in weeks
                for team_idx, team in enumerate(teams)
               ))


def condition_play_equal_home_away(fixtures, teams):
    from itertools import combinations
    min_number_home_games = int(len(weeks)/2)
    all_played_half_both = []
    for team in teams:
        team_played_half_both = []
        for home_weeks in combinations(weeks, min_number_home_games):
            played_half_home = And(*(fixtures[team, week] != -1 for week in home_weeks))
            other_weeks = [week for week in weeks if week not in home_weeks]
            played_half_away = Or(*(And(*(fixtures[team, week] == -1 for week in away_weeks))
                                  for away_weeks in combinations(other_weeks, min_number_home_games)
                                  ))

            team_played_half_both.append(And(played_half_home, played_half_away))
            #raise Exception(played_half_both)
        all_played_half_both.append(Or(*team_played_half_both))
    return  And(*all_played_half_both)


def condition_is_valid_opponent(fixtures, teams):
    return And(*(And(-1 <= f, f < len(teams)) for f in fixtures.values()))


def conditions_for_division(fixtures, teams):
    return And(
               condition_is_valid_opponent(fixtures, teams),
               condition_not_playing_twice_away(fixtures, teams),
               condition_match_happens(fixtures, teams),
               condition_not_playing_home_and_away(fixtures, teams),
               condition_play_equal_home_away(fixtures, teams),
               True
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