
import csv
import pandas
from datetime import datetime, timedelta
import os

from z3 import Bool, Solver, And, Or, Not, Implies

file_format       = 'xlsx'
# file_format      = 'csv'
rest_days         = 4
output_filename   = 'results {}.{}'.format(datetime.now().strftime('%Y%b%d %H.%M.%S'), file_format)
fixtures_filename = 'fixtures.{}'.format(file_format)
old_fixtures_filename = 'old_fixtures.{}'.format(file_format)
slots_filename    = 'slots.{}'.format(file_format)
date_format       = '%d/%m/%Y'
newline           = "\r\n"
dir_path          = os.path.dirname(os.path.realpath(__file__))
league_start_date = datetime.strptime('24/04/2020', date_format)
league_end_date   = datetime.strptime('28/06/2020', date_format)

if file_format == 'xlsx':
    # make fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(fixtures_filename, "rb") as xlsxfile:
        fixtures_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False)
        fixture_file_headers = fixtures_dataframe.columns
        fixtures = fixtures_dataframe.to_dict(orient="records")

    # make old fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(old_fixtures_filename, "rb") as xlsxfile:
        old_fixtures_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False)
        old_fixtures = old_fixtures_dataframe.to_dict(orient="records")

    # make slots list of dicts with keys: Date,Time,Court,Team 1,Team 2
    with open(slots_filename, "rb") as xlsxfile:
        slots_dataframe = pandas.read_excel(xlsxfile, engine="openpyxl", na_filter=False)
        slots = slots_dataframe.to_dict(orient="records")

else:
    # make fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(fixtures_filename, newline=newline) as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        fixture_file_headers = reader.fieldnames
        fixtures = list(reader)

    # make old fixtures list of dicts with keys: Date,Time,League Type,Event,Draw,Nr,Team 1,Team 2,Court,Location
    with open(old_fixtures_filename, newline=newline) as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        old_fixtures = list(reader)

    # make slots list of dicts with keys: Date,Time,Court,Team 1,Team 2
    with open(slots_filename, newline=newline) as csvfile:
        reader = csv.DictReader(csvfile, delimiter=',', quotechar='"')
        slots = list(reader)


fixtures = [x for x in fixtures if x['Team 1'] != 'Bye']


team_slots = {}
teams_sharing_slots = []
for fixture in fixtures:
    team = fixture['Team 1']
    if team in team_slots:
        continue
    for i, slot in enumerate(slots):
        if team in (slot['Team 1'], slot['Team 2']):
            if slot['Team 2']:
                teams_sharing_slots.append(slot['Team 1'])
                teams_sharing_slots.append(slot['Team 2'])
            team_slots[team] = i
            break
    if team not in team_slots:
        raise Exception('Team "{}" have no slot defined in {}'.format(team, slots_filename))

team_progress = [{'team': team,
                  'fixtures': 0,
                  'next_date': datetime.strptime(slots[slot_idx]['Date'], date_format),
                  }
                  for team, slot_idx in team_slots.items()]

teams_by_division = {}
division_for_team = {}
for fixture in fixtures:
    division = fixture['Draw']
    team = fixture['Team 1']
    if division not in teams_by_division:
        teams_by_division[division] = []
    if team not in teams_by_division[division]:
        teams_by_division[division].append(team)
    if team not in division_for_team:
        division_for_team[team] = division

# limited_teams_by_division = {
    # 'MENS DIVISION 1': teams_by_division['MENS DIVISION 1'],
    # 'MENS DIVISION 2': teams_by_division['MENS DIVISION 2'],
# }
# teams_by_division = limited_teams_by_division

weeks = range(1, 10)

grids_by_division = {}
for division, teams in teams_by_division.items():
    grid = {}
    for home_team in teams:
        for away_team in teams:
            for week in weeks:
                grid[home_team, away_team, week] = Bool(f'{home_team}_vs_{away_team}_week_{week}')
    grids_by_division[division] = grid



def condition_match_happens_once(grid, teams):
    pairing_happens = []
    plays_self = []
    plays_both = []
    for home_team in teams:
        for away_team in teams:
            if home_team == away_team:
                plays_self.append(Or(*(grid[home_team, away_team, week] for week in weeks)))
            else:
                plays_home = (grid[home_team, away_team, week] for week in weeks)
                plays_away = (grid[away_team, home_team, week] for week in weeks)
                pairing_happens.append(Or(*plays_home, *plays_away))
                plays_both.append(And(Or(*plays_home), Or(*plays_away)))
    return And(*pairing_happens, Not(Or(*plays_self)), Not(Or(*plays_both)))


def condition_play_once_per_week(grid, teams):
    play_once = []
    for week in weeks:
        for home_team in teams:
            for away_team in teams:
                home_other_home = Or(*(grid[home_team, opp, week] for opp in teams if opp != away_team))
                home_any_away   = Or(*(grid[opp, home_team, week] for opp in teams))
                away_any_home   = Or(*(grid[away_team, opp, week] for opp in teams))
                away_other_away = Or(*(grid[opp, away_team, week] for opp in teams if opp != home_team))
                this_match                = grid[home_team, away_team, week]
                any_other_match_this_week = Or(home_other_home, home_any_away, away_any_home, away_other_away)
                play_once.append(Implies(this_match, Not(any_other_match_this_week)))
    return And(*play_once)

def condition_shared_slot_not_double_booked(grids_by_division):
    not_double_booked = []
    for slot in slots:
        if not slot['Team 2']:
            continue
        team1 = slot['Team 1']
        team2 = slot['Team 2']
        team1_division    = division_for_team[team1]
        team1_grid        = grids_by_division[team1_division]
        team1_oppositions = teams_by_division[team1_division]
        team2_division    = division_for_team[team2]
        team2_grid        = grids_by_division[team2_division]
        team2_oppositions = teams_by_division[team2_division]
        for week in weeks:
            team1_at_home = Or(*(team1_grid[team1, opp, week] for opp in team1_oppositions))
            team2_at_home = Or(*(team2_grid[team2, opp, week] for opp in team2_oppositions))
            not_double_booked.append(Not(And(team1_at_home, team2_at_home)))
    return And(*not_double_booked)

def conditions_for_division(grid, teams):
    return And(
               condition_match_happens_once(grid, teams),
               condition_play_once_per_week(grid, teams),
               # condition_play_equal_home_away(grid, teams),
               True
               )

def conditions_between_divisions(grids_by_division):
    return And(condition_shared_slot_not_double_booked(grids_by_division))

solver = Solver()
for division, grid in grids_by_division.items():
    solver.add(conditions_for_division(grid, teams_by_division[division]))
    print(solver.check())
    model = solver.model()

solver.add(conditions_between_divisions(grids_by_division))
print(solver.check())
model = solver.model()

for division, grid in grids_by_division.items():
    print(f"= {division} =========== ")
    teams = teams_by_division[division]
    print(" ↓ home team {:>26}".format('   \    away team → \t'), end='')
    print('\t'.join(f'({idx+1})' for idx in range(0, len(teams))))
    for home_idx, home_team in enumerate(teams):
        matches = {i: week for i, away_team in enumerate(teams) for week in weeks if model[grid[home_team, away_team, week]]}
        print(f"({home_idx+1}){home_team:>31} :", end='')
        for idx in range(0, len(teams)):
            if idx in matches:
                print(f'\twk{matches[idx]}', end='')
            else:
                print('\t -', end='')
        print('')
    print('')


